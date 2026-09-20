<script setup lang="ts">
import { computed } from "vue";
import type { OptimizationSummary } from "../types/api";

const props = defineProps<{ summary: OptimizationSummary }>();
const gate = computed(() => props.summary.quality_gate);
const comparison = computed(() => props.summary.pairwise_comparison);

const gateLabel = computed(() => {
  if (!gate.value) return "旧任务未保存优化门槛判定";
  return gate.value.passed
    ? "达到设定的内部修订门槛"
    : "未达到设定的内部修订门槛";
});
const comparisonLabel = computed(() => {
  switch (comparison.value?.verdict) {
    case "candidate_preferred":
      return "双顺序比较倾向修改稿";
    case "baseline_preferred":
      return "双顺序比较倾向原稿";
    case "uncertain":
      return "双顺序比较尚无一致结论";
    default:
      return "本次未进行双顺序比较";
  }
});
const comparisonReason = computed(() => {
  const reason = comparison.value?.reason?.trim();
  if (!reason) return "当前结果未保存对照原因；不能据此推断修改稿质量已提升。";
  if (/budget|token|cost|预算|额度/i.test(reason))
    return "本次运行剩余预算不足，未完成双顺序比较；保留修改稿供教师复核。";
  if (/identity|duration changed|身份|课时变化/i.test(reason))
    return "原稿与修改稿的课程身份或课时不一致，不能直接比较。";
  if (/deterministic.*rules|hard.rules|结构规则/i.test(reason))
    return "候选稿未通过确定性教案规则检查，不能自动判断为更优。";
  if (/no canonical|no content|unchanged|没有.*内容变化/i.test(reason))
    return "原稿与候选稿没有可比较的教学内容变化，分数变化不能算作优化。";
  if (/input|payload|character|too large|输入过大/i.test(reason))
    return "需比较的内容超过单次对照输入上限；请教师直接对照原稿与修改稿。";
  if (/failed|failure|error|失败/i.test(reason))
    return "成对比较调用未全部成功，无法据此自动判断哪份教案更好。";
  if (/both.*required|两次.*必须/i.test(reason))
    return "只有完成两个展示顺序的对照，才能给出较稳妥的内部倾向。";
  if (/lacks consistent|regression concern|退步风险/i.test(reason))
    return "修改稿的优势或退步风险尚未形成一致证据。";
  if (/disagree|inconclusive|uncertain|不一致|无法判断/i.test(reason))
    return "交换展示顺序后的判断不一致或证据不足，结果需教师复核。";
  if (/favor.*baseline|baseline.preferred|倾向原稿/i.test(reason))
    return "两种展示顺序下均倾向原稿；请教师查看候选稿是否引入退步。";
  if (/favor.*candidate|candidate.preferred|倾向修改稿/i.test(reason))
    return "两种展示顺序下均倾向修改稿，但仍不代表课堂效果已得到验证。";
  return reason;
});
const reviewConclusion = computed(() => {
  if (!props.summary.content_changed)
    return "交付稿没有内容变化，不能视为完成优化。";
  if (gate.value?.passed && comparison.value?.verdict === "candidate_preferred")
    return "修改稿通过内部修订门槛，双顺序比较也倾向修改稿；是否用于课堂仍需教师判断。";
  if (comparison.value?.verdict === "baseline_preferred")
    return "虽有修改，双顺序比较更倾向原稿；建议对照两份 Word，由教师决定是否采用。";
  if (gate.value && !gate.value.passed)
    return "修改稿有真实内容变化，但尚未达到设定的内部修订门槛；请教师重点复核。";
  return "修改稿有真实内容变化，但尚无足够证据证明质量提升；请教师复核。";
});

function progressLabel(progress?: string): string {
  switch (progress) {
    case "improved":
      return "倾向有进展";
    case "unchanged":
      return "未发现明显进展";
    case "worse":
      return "疑似退步";
    default:
      return "未能判定";
  }
}

function readable(value: unknown): string {
  if (typeof value === "string") return value || "（空）";
  return value == null ? "（空）" : JSON.stringify(value, null, 2);
}
function roleLabel(role: string): string {
  if (role.startsWith("subject_critic")) return "学科审查";
  if (role.startsWith("pedagogy_critic")) return "教学法审查";
  if (role.startsWith("alignment_critic")) return "目标—活动—评价对齐审查";
  return role;
}
</script>

<template>
  <section class="optimization-panel surface" aria-label="教案优化过程">
    <div class="optimization-heading">
      <div>
        <span class="eyebrow">OPTIMIZATION EVIDENCE</span>
        <h2>这份教案实际改了什么</h2>
      </div>
      <span
        class="outcome-pill"
        :class="summary.content_changed ? 'changed' : 'unchanged'"
      >
        {{
          summary.stop_reason === "rewrite_failed"
            ? "改写失败，仅保留原稿"
            : summary.content_changed
              ? "交付稿有内容变化·待复核"
              : "交付稿未修改"
        }}
      </span>
    </div>
    <p class="outcome-message">
      {{
        summary.stop_reason === "rewrite_failed"
          ? "审查产生了可执行意见，但改写阶段未形成合格版本；这不是“没有优化空间”。"
          : summary.message
      }}
    </p>
    <p class="score-context">
      下方对比的是“Word 内容结构化后的导入基线”与最终交付稿；原 Word
      保持不变，导入时遗漏的图片文字不属于已优化内容。
    </p>

    <div class="evidence-stats">
      <div>
        <strong>{{ summary.critique_count }}</strong
        ><span>审查意见</span>
      </div>
      <div>
        <strong>{{ summary.validation_batch_count }}</strong
        ><span>裁决批次</span>
      </div>
      <div>
        <strong>{{ summary.rewrite_count }}</strong
        ><span>改写轮次</span>
      </div>
      <div>
        <strong>{{ summary.changed_section_count }}</strong
        ><span>交付稿变化栏目</span>
      </div>
    </div>

    <p class="score-context">
      本次原稿评分 {{ summary.baseline_score?.toFixed(1) ?? "—" }}， 交付稿评分
      {{ summary.selected_score?.toFixed(1) ?? "—" }}。
      {{ summary.score_notice }}
    </p>
    <section class="quality-evidence" aria-label="优化达标与成对比较">
      <h3>修改效果的内部证据</h3>
      <p class="review-conclusion">{{ reviewConclusion }}</p>
      <div class="evidence-checks">
        <div>
          <strong>{{ gateLabel }}</strong>
          <p v-if="gate">
            {{ gate.content_changed ? "内容已改变" : "内容未改变" }}； 八维总评
            {{ gate.absolute_target_met ? "达标" : "未达标" }}；
            相对原稿提升与维度退步约束
            {{ gate.relative_target_met ? "达标" : "未达标" }}； 结构规则
            {{ gate.hard_rules_ok ? "通过" : "未通过" }}。
          </p>
          <p v-if="gate">
            设定值：总评 ≥ {{ gate.thresholds.overall.toFixed(1) }}，相对提升 ≥
            {{ gate.thresholds.minimum_gain.toFixed(1) }}，任一维度下降 ≤
            {{ gate.thresholds.maximum_dimension_drop.toFixed(1) }}。
          </p>
        </div>
        <div>
          <strong>{{ comparisonLabel }}</strong>
          <p v-if="comparison?.votes?.length === 2 && !comparison.failed_calls">
            已交换原稿与修改稿展示顺序完成两次对照；聚焦内容进展：{{
              progressLabel(comparison.target_issue_progress)
            }}。
          </p>
          <p v-else-if="comparison">
            本次只完成 {{ comparison.votes?.length ?? 0 }} / 2
            次有效对照，未形成可靠的双顺序判断。
          </p>
          <p v-if="comparison">对照说明：{{ comparisonReason }}</p>
          <p v-else-if="!comparison">
            当前结果未包含对照记录，可能是历史任务或预算、安全限制；不能据此判断修改稿优于原稿。
          </p>
          <p v-if="comparison?.regression_flags.length">
            疑似退步：{{ comparison.regression_flags.join("；") }}
          </p>
          <p v-if="comparison?.evidence.length">
            对照依据：{{ comparison.evidence.slice(0, 2).join("；") }}
          </p>
          <p v-if="comparison?.failed_calls">
            其中
            {{ comparison.failed_calls }} 次比较未完成，结论不可用于自动选优。
          </p>
        </div>
      </div>
      <p class="scope-note">
        内部分数和模型对照只用于筛选候选稿，不是教学效果证明；最终是否采用修改稿由教师决定。
      </p>
    </section>
    <p v-if="summary.unselected_candidate_version_id" class="candidate-note">
      系统另保存了真实修改候选稿
      {{ summary.unselected_candidate_version_id }} （内部评分
      {{ summary.unselected_candidate_score?.toFixed(1) ?? "—" }}），
      但质量筛选未将其选为交付最佳稿。可下载候选 Word
      与原稿对照，须由教师判断是否采用。
    </p>

    <div class="process-track">
      <h3>实际流程</h3>
      <ol>
        <li>
          上传原稿 <code>{{ summary.baseline_version_id }}</code
          >，进行内部基线评估
        </li>
        <li>
          {{
            summary.critique_count
              ? "三类 Critic 已提出审查意见"
              : "未完成 Critic 审查"
          }}
        </li>
        <li>
          {{
            summary.validation_batch_count
              ? "Validator 已裁决意见"
              : "未形成意见裁决"
          }}
        </li>
        <li>
          {{
            summary.rewrite_count
              ? `完成 ${summary.rewrite_count} 轮候选改写`
              : "未完成实际改写"
          }}
        </li>
        <li>
          选中交付版本 <code>{{ summary.selected_version_id }}</code>
        </li>
      </ol>
    </div>

    <div v-if="summary.rounds.length" class="rounds">
      <details
        v-for="(round, index) in summary.rounds"
        :key="`${round.input_version_id}-${round.output_version_id}`"
      >
        <summary>
          第 {{ index + 1 }} 轮：{{ round.input_version_id }} →
          {{ round.output_version_id }} ·
          {{
            round.strategy === "targeted_patch"
              ? "定向补丁"
              : round.strategy === "full_document"
                ? "全文修订"
                : "旧版路径"
          }}
          · 接受 {{ round.accepted_count }} / 修改
          {{ round.implemented_count }} / 未解决 {{ round.unresolved_count }}
        </summary>
        <ul v-if="round.changes.length">
          <li v-for="change in round.changes" :key="change.critique_id">
            问题 <code>{{ change.target_path }}</code> → 实改
            <code>{{ change.edited_paths?.join("、") || "旧记录未注明" }}</code
            >：{{ change.after_summary }}
          </li>
        </ul>
        <ul v-if="round.unresolved_reasons && round.unresolved_count">
          <li
            v-for="(reason, critiqueId) in round.unresolved_reasons"
            :key="critiqueId"
          >
            未解决 <code>{{ critiqueId }}</code
            >：{{ reason }}
          </li>
        </ul>
      </details>
    </div>

    <div v-if="summary.reviewed_issues.length" class="review-list">
      <h3>审查意见与裁决</h3>
      <details v-for="item in summary.reviewed_issues" :key="item.critique_id">
        <summary>
          {{ roleLabel(item.role) }} · {{ item.target_path }}
          <small>{{ item.status }}</small>
        </summary>
        <p><strong>发现：</strong>{{ item.issue }}</p>
        <p><strong>建议：</strong>{{ item.suggestion }}</p>
        <p>
          <strong>裁决：</strong>{{ item.decision || "未裁决" }}。{{
            item.decision_reason || ""
          }}
        </p>
      </details>
    </div>

    <div class="diff-list">
      <h3>最终交付稿相对原稿的内容对比</h3>
      <p v-if="!summary.changed_sections.length" class="no-diff">
        没有检测到实际内容变化。下载的 Word 与原稿在教学内容上相同。
      </p>
      <details v-for="section in summary.changed_sections" :key="section.field">
        <summary>
          {{ section.label }} <small>{{ section.field }}</small>
        </summary>
        <div class="diff-columns">
          <div>
            <span>修改前 · 原稿</span>
            <pre>{{ readable(section.before) }}</pre>
          </div>
          <div>
            <span>修改后 · 交付稿</span>
            <pre>{{ readable(section.after) }}</pre>
          </div>
        </div>
      </details>
    </div>
    <div
      v-if="summary.unselected_candidate_changed_sections?.length"
      class="diff-list"
    >
      <h3>未选中候选稿相对原稿的内容变化（待教师复核）</h3>
      <details
        v-for="section in summary.unselected_candidate_changed_sections"
        :key="section.field"
      >
        <summary>
          {{ section.label }} <small>{{ section.field }}</small>
        </summary>
        <div class="diff-columns">
          <div>
            <span>原稿</span>
            <pre>{{ readable(section.before) }}</pre>
          </div>
          <div>
            <span>修改候选稿</span>
            <pre>{{ readable(section.after) }}</pre>
          </div>
        </div>
      </details>
    </div>
  </section>
</template>

<style scoped>
.optimization-panel {
  margin-bottom: 22px;
  padding: clamp(20px, 3vw, 32px);
}
.optimization-heading {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
h2 {
  margin: 5px 0 0;
  font-size: clamp(21px, 2.3vw, 28px);
}
h3 {
  margin: 0 0 12px;
  font-size: 17px;
}
.outcome-pill {
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 700;
}
.outcome-pill.changed {
  background: #dcefeb;
  color: #12665f;
}
.outcome-pill.unchanged {
  background: #fff0e8;
  color: #9a503a;
}
.outcome-message {
  line-height: 1.75;
  margin: 14px 0 20px;
}
.evidence-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.evidence-stats div {
  background: #f6f8f5;
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.evidence-stats strong {
  font-size: 23px;
  color: #0b625c;
}
.evidence-stats span {
  color: #64747b;
  font-size: 12px;
}
.score-context {
  margin: 18px 0 0;
  color: #5b6c72;
  font-size: 13px;
  line-height: 1.7;
}
.quality-evidence {
  margin-top: 18px;
  padding: 18px;
  border: 1px solid #d7e5e0;
  border-radius: 14px;
  background: #f8fbf9;
}
.quality-evidence h3 {
  margin-bottom: 8px;
}
.review-conclusion {
  margin: 0 0 14px;
  line-height: 1.7;
  color: #194d49;
  font-weight: 600;
}
.evidence-checks {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.evidence-checks > div {
  padding: 13px 14px;
  background: #fff;
  border: 1px solid #e2ebe7;
  border-radius: 11px;
}
.evidence-checks strong {
  color: #173f45;
}
.evidence-checks p {
  margin: 7px 0 0;
  line-height: 1.55;
  color: #587076;
  font-size: 12px;
}
.scope-note {
  margin: 13px 0 0;
  color: #667a7b;
  line-height: 1.6;
  font-size: 12px;
}
.candidate-note {
  margin: 14px 0 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #fff7e8;
  color: #70551e;
  line-height: 1.7;
  font-size: 13px;
}
.process-track,
.diff-list,
.rounds,
.review-list {
  border-top: 1px solid #e3e9e6;
  margin-top: 22px;
  padding-top: 20px;
}
.process-track ol {
  margin: 0;
  padding-left: 22px;
  display: grid;
  gap: 9px;
  line-height: 1.55;
}
code {
  font-size: 12px;
  color: #285d68;
}
details {
  border: 1px solid #dce6e2;
  border-radius: 11px;
  margin-top: 10px;
  padding: 12px 14px;
}
summary {
  cursor: pointer;
  font-weight: 600;
  line-height: 1.5;
}
summary small {
  color: #75868b;
  font-weight: 400;
  margin-left: 8px;
}
details ul {
  line-height: 1.7;
  padding-left: 20px;
}
.no-diff {
  color: #8c5541;
  background: #fff7f1;
  border-radius: 10px;
  padding: 12px 14px;
}
.diff-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 14px;
}
.diff-columns > div {
  min-width: 0;
}
.diff-columns span {
  display: block;
  font-size: 12px;
  color: #536a70;
  margin-bottom: 7px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 340px;
  overflow: auto;
  background: #f5f7f6;
  border-radius: 8px;
  padding: 12px;
  line-height: 1.55;
  font-size: 12px;
}
@media (max-width: 700px) {
  .evidence-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .diff-columns,
  .evidence-checks {
    grid-template-columns: 1fr;
  }
}
</style>
