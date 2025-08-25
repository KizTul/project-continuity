@echo off
chcp 65001 > nul
echo.
echo === [ PROJECT SYNC TOOL ] : Синхронизация Проекта с GitHub ===
echo.
set /p COMMIT_MESSAGE="Введите осмысленное сообщение: "
if not defined COMMIT_MESSAGE (
    echo [!] Отменено. Сообщение не может быть пустым.
    goto end
)
git add .
git commit -m "%COMMIT_MESSAGE%"
git push origin main
echo.
echo === СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА ===
echo.
:end
pause
