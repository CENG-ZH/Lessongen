# Lessongen（灵犀教案）

面向教师与师范生的多智能体教案生成、审查与 Word 优化系统。Python/LangGraph 负责真实模型闭环，Spring Boot 负责任务、数据库与文件管理，Vue 负责生成、优化、过程展示和结果下载。

> 当前状态：研究原型 / 本地部署 MVP。系统不使用 Mock 教案冒充成功；内部 Judge 分数只用于管线路由，不能替代教师评价或论文实验结论。

![Lessongen 首页](web/docs/ui-audit/01-dashboard-desktop.png)

## 主要功能

- 输入科目、年级、课题等信息生成结构化教案；
- 上传任意常见结构的 `.docx` 教案，解析后进行多轮定向优化；
- Design Architect、Writer、三类 Critic、Validator、Judge、Rewriter 分工协作；
- 记录版本、意见、裁决、实际修改、评分、token、费用和停止原因；
- 输出 JSON、Markdown、Word、manifest、trace 和优化报告；
- 页面展示任务阶段、模型用量、八维内部质量与“具体改了什么”；
- 对宏、加密包、嵌入 OLE、路径穿越和异常压缩包执行安全拦截；
- 不访问 Word 中的外部链接、外链图片或外部模板。

## 仓库结构

```text
Lessongen/
├── paper4_pipeline/       Python、LangGraph、FastAPI、DOCX 解析与导出
├── web/                   Spring Boot、MySQL/Flyway、Vue 3
│   ├── frontend/          Vue/TypeScript 前端
│   ├── src/               Java 后端
│   └── specs/             功能、接口、数据模型和 UI 规范
├── docs/                  项目架构说明
├── SECURITY.md            密钥、文档与部署安全边界
└── CONTRIBUTING.md        开发与提交规范
```

详细设计见 [项目架构与开发说明](docs/PAPER4_PROJECT_GUIDE.md)。

## 系统架构

```text
Browser
  │ /api/v1 + SSE
  ▼
Vue 3 / TypeScript
  ▼
Spring Boot 4 ───── MySQL 8
  │ /internal/v1 + X-Engine-Token
  ▼
FastAPI internal engine ───── 本地受控文件存储
  ▼
LangGraph / PipelineService
  ├─ Generate: Design Architect → Writer → Judge
  └─ Optimize: DOCX → normalized v0 → Judge
                       ↓
      Subject + Pedagogy + Alignment Critics
                       ↓
       Validator → targeted Rewriter → Verifier
                       ↓
                    Judge / Router（最多三轮）
```

![工程架构](web/docs/ui-audit/architecture-current.png)

## Agent 分工

| 角色 | 职责 | 输出 |
| --- | --- | --- |
| Design Architect | 比较候选认知路径并选择设计主线 | `LessonDesignBlueprint` |
| Writer | 将蓝图展开成完整初稿 | `LessonPlanDocument` |
| Subject Critic | 学科事实、条件、教材边界与误概念 | `CritiqueItem[]` |
| Pedagogy Critic | 认知进阶、支架、参与、差异化与可实施性 | `CritiqueItem[]` |
| Alignment Critic | 目标—活动—产出—评价一致性 | `CritiqueItem[]` |
| Validator | 去重、接受、拒绝、合并、延期 | `ValidationBatch` |
| Rewriter | 执行已接受意见并提交字段级修改 | `RewriteOutcome` |
| Verifier | 确定性核验与回归检测 | 状态迁移与回归标记 |
| Judge | 冻结八维内部评价 | `EvaluationReport` |

优化模式采用“相对原稿不退步”的校验：外部原稿可以分轮补齐；局部修改不会因为其他尚未修复的问题被误杀，但任何新增硬错误、身份篡改、伪修改或悬空引用都会被拒绝。

## 技术栈

- Python 3.10+、Pydantic 2、LangGraph、FastAPI；
- DeepSeek OpenAI-compatible API；
- Java 17、Spring Boot 4、Spring Data JPA、Flyway；
- MySQL 8；
- Vue 3、TypeScript、Vite、Pinia、Element Plus、ECharts；
- pytest、JUnit、Testcontainers、Vitest、Playwright。

## 快速启动

### 1. Python 引擎

```bat
conda create -n PR4 python=3.10 -y
conda activate PR4
cd /d <仓库目录>\paper4_pipeline
python -m pip install -e ".[web,dev]"
copy .env.example .env
notepad .env
python -m paper4_pipeline.web_api
```

`paper4_pipeline/.env` 至少填写：

```dotenv
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
ENGINE_INTERNAL_TOKEN=一段随机长字符串
PAPER4_WEB_STATE_ROOT=./var/engine-state
PAPER4_ARTIFACTS_ROOT=./var/engine-artifacts
PAPER4_CONFIG_PATH=./configs/deepseek_v4_flash.json
```

健康检查：`http://127.0.0.1:8001/internal/v1/health`。

### 2. MySQL

```bat
cd /d <仓库目录>\web
copy .env.example .env
notepad .env
docker compose up -d mysql
docker compose ps
```

Docker Compose 默认使用主机端口 `3307`。

### 3. Spring Boot

Spring Boot 不自动读取 `.env`，请在启动终端或 IDEA Run Configuration 设置：

```bat
set DB_URL=jdbc:mysql://127.0.0.1:3307/lesoongen?useUnicode=true^&characterEncoding=utf8^&serverTimezone=UTC
set DB_USERNAME=lesoongen
set DB_PASSWORD=与web\.env一致
set ENGINE_BASE_URL=http://127.0.0.1:8001
set ENGINE_INTERNAL_TOKEN=与Python端完全一致
set LESSON_STORAGE_ROOT=./var/storage
cd /d <仓库目录>\web
mvnw.cmd spring-boot:run
```

后端健康检查：`http://127.0.0.1:8080/actuator/health`。

### 4. Vue

```bat
cd /d <仓库目录>\web\frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。

## 测试

```bat
cd /d <仓库目录>\paper4_pipeline
python -m pytest -q

cd /d <仓库目录>\web
mvnw.cmd test

cd /d <仓库目录>\web\frontend
npm test
npm run lint
npm run build
```

当前离线验证：Python 163 项通过；Java 21 项通过、1 项按环境跳过；Vue 6 项通过，lint 和生产构建通过。自动测试不会调用付费模型。

## 运行数据

默认数据写入被 Git 忽略的目录：

```text
paper4_pipeline/var/engine-state/
paper4_pipeline/var/engine-artifacts/
web/var/storage/
```

其中可能包含上传原文、生成教案、模型响应、trace 和费用信息，不得提交到公共仓库。

## 敏感信息

仓库只提交 `.env.example`。`.env`、API Key、数据库密码、内部 Token、上传 Word、数据库、运行产物、依赖缓存和本机路径均已排除。完整要求见 [SECURITY.md](SECURITY.md)。

## 已知边界

- 当前为单机 MVP，付费任务默认串行；
- Word 图片不执行 OCR，需要人工核对；
- Paper#3 课堂模拟尚未接入主图；
- RAG 权威课程标准库、用户登录和公网多租户部署尚未完成；
- 内部评分不等于真实教学效果，仍需教师与专家实验；
- 仓库暂未添加开源许可证。

## 文档

- [完整架构说明](docs/PAPER4_PROJECT_GUIDE.md)
- [Python 引擎说明](paper4_pipeline/README.md)
- [Python 运行指南](paper4_pipeline/docs/RUN_GUIDE.md)
- [优化闭环说明](paper4_pipeline/docs/OPTIMIZATION_WORKFLOW.md)
- [Web 说明](web/README.md)
- [Web Spec](web/specs/001-lesson-plan-web/README.md)
- [安全说明](SECURITY.md)
- [贡献指南](CONTRIBUTING.md)

> Java 包名和部分内部历史标识仍保留 `lesoongen`，用于兼容现有数据库与接口；对外仓库和产品名称统一为 **Lessongen**。
