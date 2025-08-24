@echo off
chcp 65001 > nul
echo. & echo [ДЕПЛОЙ ЯДРА] Развертываю изменения из песочницы в рабочую среду...
python "%~dp0\deploy_staging_to_production.py"