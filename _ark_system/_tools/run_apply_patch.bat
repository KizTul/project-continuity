@echo off
chcp 65001 > nul

echo.
echo --- Запуск ARK Patch Applicator ---
echo.

REM Убедимся, что мы находимся в директории со скриптом
cd /d "%~dp0"

if not exist "apply_patch.py" (
    echo [!] КРИТИЧЕСКАЯ ОШИБКА: Основной скрипт 'apply_patch.py' не найден.
    goto end
)
if not exist "modification_data.py" (
    echo [!] ОШИБКА: Файл с данными патча 'modification_data.py' не найден.
    goto end
)

python apply_patch.py

echo.
echo --- Готово ---
echo.

:end
pause