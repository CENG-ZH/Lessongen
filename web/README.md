# 灵犀教案（Lesoongen）

面向教师和师范生的 Paper#4 多智能体教案 Web 工作台。MVP 只做两件事：从教学信息生成教案，以及上传 `.docx` 原稿后优化教案。浏览器不接触模型 Key、Prompt 或磁盘路径。

## 系统结构

```text
Vue 3 / TypeScript（表单、真实进度、结果预览）
          │ /api/v1 + SSE
Spring Boot 4（公开 API、任务状态、MySQL、文件归属）
          │ /internal/v1 + 内部 Token
FastAPI（持久化单工作器、DOCX 输入适配器）
          │
现有 PipelineService / LangGraph / DeepSeek V4 Flash
```

- MySQL 只保存任务、事件、文件元数据与哈希；教案、trace 和上传文件放在受控文件存储。
- 本机默认运行数据写入项目内被 Git 忽略的 `var/`；仍可用环境变量覆盖。
- 创建接口立即返回 `202`，Spring 调度器异步提交并对账；MVP 同时只运行一个付费任务。
- 优化先做 OOXML 安全检查与定位抽取；系统原样导出的 Word 可经哈希校验直接恢复结构化原稿，其他 Word 由结构化 Agent 处理，再进入真实 graph。优化任务不会因初稿评分达标就跳过审查。
- 结果页展示审查意见、裁决、改写轮次和原稿/交付稿的栏目对比；`optimization_report.json/.md` 提供完整过程。若内容未改动，会明确标为“未修改”，不会把模型评分波动称为优化效果。
- 生产代码没有 Mock Agent 或固定教案分支；自动测试的替身只隔离外部付费 API。

## 目录

```text
frontend/                          Vue 工作台
src/main/java/.../api              公共 Controller、SSE、Problem Details
src/main/java/.../application      任务编排、状态对账、产物复制
src/main/java/.../domain           显式状态机与领域实体
src/main/java/.../infrastructure   MySQL/JPA、Python Client、本地存储
src/main/resources/db/migration    Flyway V1–V3
specs/001-lesson-plan-web          完整 Spec、契约、数据模型和任务清单
```

## 开始运行

完整的 Windows Anaconda Prompt / CMD 命令见 [Quickstart](specs/001-lesson-plan-web/quickstart.md)。最短顺序为：

1. 启动 MySQL 8.x（可使用 `docker compose up -d mysql`），由 Flyway 自动建表；
2. 在 `paper4_pipeline` 的 `PR4` 环境启动 FastAPI（8001）；
3. 在本目录运行 `mvnw.cmd spring-boot:run`（8080）；
4. 在 `frontend` 运行 `npm run dev`（5173）。

三个服务中的 `ENGINE_INTERNAL_TOKEN` 必须保持一致（Vue 不设置此变量）。真实生成还需要 Python 环境中的 `DEEPSEEK_API_KEY`。

## 验证

```bat
mvnw.cmd test
cd frontend
npm run format:check
npm test
npm run lint
npm run lint:openapi
npm run test:e2e
npm run build
npm audit --audit-level=high
```

Python 项目：

```bat
conda activate PR4
python -m pip install -e ".[web,dev]"
python -m pytest -q
```

这些命令不会调用付费模型。执行真实生成或优化前，请确认账户余额和输入材料不含敏感数据。
