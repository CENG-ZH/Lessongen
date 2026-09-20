@echo off
setlocal
cd /d "%~dp0.."
call conda activate PR4
if "%DEEPSEEK_API_KEY%"=="" echo [INFO] 将尝试从项目 .env 读取 DEEPSEEK_API_KEY
if "%ENGINE_INTERNAL_TOKEN%"=="" echo [INFO] 将尝试从项目 .env 读取 ENGINE_INTERNAL_TOKEN
python -m paper4_pipeline.web_api
