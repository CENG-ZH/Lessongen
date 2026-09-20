"""Teacher-readable and machine-readable evidence for optimization runs."""

from __future__ import annotations

import json
from pathlib import Path

from paper4_pipeline.control.optimization import optimization_summary
from paper4_pipeline.domain.models import PipelineResult
from paper4_pipeline.exporters.common import atomic_write_text


def export_optimization_report(result: PipelineResult, output_dir: Path) -> tuple[Path, Path]:
    summary = optimization_summary(result)
    baseline = min(result.versions, key=lambda item: (item.iteration, item.version_id))
    selected = next(item for item in result.versions
                    if item.version_id == result.best_version_id)
    payload = {
        "schema_version": "paper4-optimization-report-v1",
        "run_id": result.run_id,
        "status": result.status.value,
        "summary": summary,
        "baseline_plan": baseline.document.model_dump(mode="json"),
        "selected_plan": selected.document.model_dump(mode="json"),
        "critiques": [item.model_dump(mode="json") for item in result.critiques],
        "validation_batches": [item.model_dump(mode="json") for item in result.validation_batches],
        "rewrite_records": [item.model_dump(mode="json") for item in result.rewrite_records],
        "route_decisions": [item.model_dump(mode="json") for item in result.route_decisions],
        "iterations": [item.model_dump(mode="json") for item in result.iterations],
    }
    json_path = output_dir / "optimization_report.json"
    atomic_write_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    lines = [
        f"# 教案优化过程 · {result.run_id}", "",
        "> 本报告对比实际交付版本与上传原稿；分数不是内容改进或教学效果的证明。", "",
        f"## 结论\n\n{summary['message']}", "",
        f"- 原稿版本：`{summary['baseline_version_id']}`，本次基线内部评分：{summary['baseline_score']}",
        f"- 交付版本：`{summary['selected_version_id']}`，交付内部评分：{summary['selected_score']}",
        f"- 停止原因：`{summary['stop_reason']}`；内容变化栏目：{summary['changed_section_count']}",
        f"- 审查意见：{summary['critique_count']}；裁决批次：{summary['validation_batch_count']}；改写记录：{summary['rewrite_count']}",
        "", "## 内部门槛与独立比较", "",
    ]
    if summary["unselected_candidate_version_id"]:
        lines.extend([
            f"- 另有未选中的真实修改候选稿：`{summary['unselected_candidate_version_id']}`，"
            f"内部评分 {summary['unselected_candidate_score']}；需教师复核，不等同于交付最佳稿。",
        ])
    gate = summary["quality_gate"]
    comparison = summary["pairwise_comparison"]
    if gate:
        lines.extend([
            f"- 内部修订门槛：{'通过' if gate['passed'] else '未通过'}；"
            f"实质内容变化：{'有' if gate['content_changed'] else '无'}；"
            f"相对原稿分差：{gate['score_gain']}。",
            f"- 设定阈值：总评 ≥ {gate['thresholds']['overall']}、"
            f"相对增益 ≥ {gate['thresholds']['minimum_gain']}、"
            f"单维下降 ≤ {gate['thresholds']['maximum_dimension_drop']}。",
        ])
    if comparison:
        lines.extend([
            f"- 双顺序对照：`{comparison['verdict']}`；"
            f"焦点内容进展：`{comparison['target_issue_progress']}`。",
            f"- 对照说明：{comparison['reason']}",
        ])
        for evidence in comparison["evidence"]:
            lines.append(f"  - 对照证据：{evidence}")
    else:
        lines.append("- 双顺序对照：未执行或无记录。")
    lines.extend([
        "", "以上只属于内部筛选证据，不等于真实课堂教学效果；采用前仍应由教师复核。",
        "", "## 审查与裁决", "",
    ])
    if not summary["reviewed_issues"]:
        lines.extend(["没有审查意见记录。", ""])
    for issue in summary["reviewed_issues"]:
        lines.extend([
            f"### {issue['role']} · {issue['target_path']}", "",
            f"- 问题：{issue['issue']}",
            f"- 建议：{issue['suggestion']}",
            f"- 最终状态：`{issue['status']}`；裁决：`{issue['decision'] or '无'}`",
            f"- 裁决依据：{issue['decision_reason'] or '无记录'}", "",
        ])
    lines.extend(["## 逐轮改写", ""])
    if not summary["rounds"]:
        lines.extend(["没有实际完成的改写轮次。", ""])
    for index, round_item in enumerate(summary["rounds"], start=1):
        lines.extend([
            f"### 第 {index} 轮 · {round_item['input_version_id']} → {round_item['output_version_id']}", "",
            f"改写路径：`{round_item['strategy']}`。", "",
            f"接受 {round_item['accepted_count']} 条；记录修改 {round_item['implemented_count']} 条；未解决 {round_item['unresolved_count']} 条。", "",
        ])
        for change in round_item["changes"]:
            edited = ", ".join(f"`{path}`" for path in change["edited_paths"]) or "未记录"
            lines.append(
                f"- 问题位置 `{change['target_path']}`（{change['critique_id']}）；"
                f"实际修改 {edited}：{change['after_summary']}"
            )
        for critique_id, reason in round_item["unresolved_reasons"].items():
            lines.append(f"- 未解决 `{critique_id}`：{reason}")
        lines.append("")
    lines.extend(["## 交付稿相对原稿的实际内容变化", ""])
    if not summary["changed_sections"]:
        lines.extend(["没有实际内容变化。即使内部评分发生变化，也不能称为教案被优化。", ""])
    for section in summary["changed_sections"]:
        lines.extend([
            f"### {section['label']}（`{section['field']}`）", "",
            "修改前：", "", "~~~~json",
            json.dumps(section["before"], ensure_ascii=False, indent=2), "~~~~", "",
            "修改后：", "", "~~~~json",
            json.dumps(section["after"], ensure_ascii=False, indent=2), "~~~~", "",
        ])
    lines.extend(["## 评价边界", "", summary["score_notice"], ""])
    md_path = output_dir / "optimization_report.md"
    atomic_write_text(md_path, "\n".join(lines))
    return json_path, md_path
