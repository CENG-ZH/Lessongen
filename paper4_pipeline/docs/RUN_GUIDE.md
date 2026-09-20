# Paper#4 运行指南

本文命令适用于 Windows Anaconda Prompt / CMD。路径中的 `<仓库目录>` 请替换为本机仓库根目录。

## 1. 安装

```bat
conda create -n PR4 python=3.10 -y
conda activate PR4
cd /d "<仓库目录>\paper4_pipeline"
python -m pip install -e ".[web,dev]"
```

## 2. 环境变量

```bat
copy .env.example .env
notepad .env
```

至少设置：

```dotenv
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
ENGINE_INTERNAL_TOKEN=随机长字符串
PAPER4_WEB_STATE_ROOT=./var/engine-state
PAPER4_ARTIFACTS_ROOT=./var/engine-artifacts
PAPER4_CONFIG_PATH=./configs/deepseek_v4_flash.json
```

`.env` 已被 Git 忽略。不要把真实 Key、Token 或用户教案提交到仓库。

## 3. 无费用检查

```bat
python -m paper4_pipeline.cli check
python -m pytest -q
```

这些命令不会调用付费模型。

## 4. 交互生成

```bat
python -m paper4_pipeline.cli generate
```

科目、年级、课题为必填；其余字段可回车跳过。系统在第一次付费调用前显示任务摘要并请求确认。

## 5. JSON 任务运行

```bat
python -m paper4_pipeline.cli run --task ".\examples\sample_task.json"
```

可用 `--output` 指定其他产物目录；不指定时写入 `PAPER4_ARTIFACTS_ROOT`。

## 6. 启动 Web 内部引擎

```bat
python -m paper4_pipeline.web_api
```

默认地址为 `http://127.0.0.1:8001`，健康检查为：

```bat
curl http://127.0.0.1:8001/internal/v1/health
```

除健康检查外，内部接口要求 `X-Engine-Token`。不要将 8001 端口直接暴露到公网。

## 7. 产物

一次正常运行可能生成：

- `input_task.json`；
- `run_result.json`；
- `best_lesson_plan.json`；
- `best_lesson_plan.md`；
- `best_lesson_plan.docx`；
- `optimization_report.json/.md`；
- `manifest.json`；
- `trace.jsonl`。

失败时不保证存在 Word；有安全版本时可能导出 recovery 文件。上传原件不是优化结果。

## 8. 离线检查历史结果

```bat
python -m paper4_pipeline.cli inspect --result ".\var\engine-artifacts\<run_id>\run_result.json"
python -m paper4_pipeline.cli export-process --run-dir ".\var\engine-artifacts\<run_id>"
python -m paper4_pipeline.cli analyze --artifacts ".\var\engine-artifacts"
```

## 9. 常见问题

| 现象 | 检查项 |
| --- | --- |
| 401 | Spring 与 Python 的 `ENGINE_INTERNAL_TOKEN` 是否完全一致 |
| 402/余额错误 | DeepSeek 账户余额；不要靠重复运行解决 |
| 连接失败 | API 地址、代理、防火墙和 8001 端口 |
| 没有 Word | 运行是否形成可交付版本、是否安装 `python-docx` |
| Word 优化失败 | DOCX 是否加密/含宏/OLE、任务元数据是否与原稿一致 |
| `needs_human` | 查看停止原因、未解决意见和候选版本，不等同于进程崩溃 |

## 10. 正式验收

自动测试通过后，再执行一条受控真实生成和一条脱敏 Word 优化。检查 trace 中模型、Prompt 版本、真实尝试次数、token 和费用，并确认优化报告中的字段变化与下载 Word 一致。
