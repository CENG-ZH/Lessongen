# 本地开发 Quickstart

下列命令按 Windows Anaconda Prompt / CMD 编写。`<仓库目录>` 表示 Git 仓库根目录。

## 1. 前置环境

- Python 3.10+ 与 Conda 环境 `PR4`；
- JDK 17；
- Node.js LTS 与 npm；
- Docker Desktop，或本机 MySQL 8；
- 可用的 DeepSeek API Key。

## 2. Python Engine

```bat
cd /d "<仓库目录>\paper4_pipeline"
conda activate PR4
python -m pip install -e ".[web,dev]"
copy .env.example .env
notepad .env
python -m paper4_pipeline.web_api
```

`.env` 中必须设置 `DEEPSEEK_API_KEY` 和随机的 `ENGINE_INTERNAL_TOKEN`。

## 3. MySQL

```bat
cd /d "<仓库目录>\web"
copy .env.example .env
notepad .env
docker compose up -d mysql
docker compose ps
```

默认从主机 `3307` 访问容器数据库。

## 4. Spring Boot

另开 CMD，并设置与 `web/.env`、Python `.env` 一致的值：

```bat
set DB_URL=jdbc:mysql://127.0.0.1:3307/lesoongen?useUnicode=true^&characterEncoding=utf8^&serverTimezone=UTC
set DB_USERNAME=lesoongen
set DB_PASSWORD=你的本地数据库密码
set ENGINE_BASE_URL=http://127.0.0.1:8001
set ENGINE_INTERNAL_TOKEN=与Python相同的随机字符串
set LESSON_STORAGE_ROOT=./var/storage
cd /d "<仓库目录>\web"
mvnw.cmd spring-boot:run
```

Flyway 自动建表。健康检查：`http://127.0.0.1:8080/actuator/health`。

## 5. Vue

```bat
cd /d "<仓库目录>\web\frontend"
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。

## 6. 自动测试

```bat
cd /d "<仓库目录>\paper4_pipeline"
python -m pytest -q

cd /d "<仓库目录>\web"
mvnw.cmd test

cd /d "<仓库目录>\web\frontend"
npm test
npm run lint
npm run build
```

自动测试不得调用真实付费模型。真实验收使用脱敏材料，并检查结果页、Word 和优化报告是否一致。
