@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist "modification_data.py" (
    echo [!] ОШИБКА: Файл 'modification_data.py' не найден.
    pause
    exit /b
)

python apply_patch.py

pause