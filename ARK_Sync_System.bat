@echo off
chcp 65001 > nul
echo.
echo === [ ARK SYNC TOOL ] : Синхронизация Системы ARK с GitHub ===
echo.
echo --- Шаг 1: Добавление всех изменений...
git add .
echo [+] Файлы добавлены.
echo.
echo --- Шаг 2: Ввод сообщения коммита...
set /p COMMIT_MESSAGE="Введите осмысленное сообщение: "
if not defined COMMIT_MESSAGE (
    echo [!] Отменено. Сообщение не может быть пустым.
    goto end
)
git commit -m "%COMMIT_MESSAGE%"
echo.
echo --- Шаг 3: Отправка на GitHub...
git push origin main
echo.
echo === СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА ===
echo.
:end
pause