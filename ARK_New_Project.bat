@echo off
chcp 65001 > nul
echo.
echo === [ ARK WIZARD ] : Создание Нового Проекта ===
echo.
set /p PROJECT_NAME="Введите имя нового проекта (например, MyNewGame): "
if not defined PROJECT_NAME (
    echo [!] ОШИБКА: Имя проекта не может быть пустым.
    goto end
)
set PROJECT_DIR="%~dp0projects\%PROJECT_NAME%"
set GITHUB_USERNAME=KizTul
set TEMPLATE_SYNC_SCRIPT="%~dp0_ark_system_staging\_tools\template_sync.bat"
set NEW_SYNC_SCRIPT="%~dp0projects\%PROJECT_NAME%\sync.bat"

echo.
echo --- Шаг 1: Создание директории...
if exist %PROJECT_DIR% (
    echo [!] ОШИБКА: Проект '%PROJECT_NAME%' уже существует.
    goto end
)
mkdir %PROJECT_DIR%
echo [+] Директория создана.
echo.
echo --- Шаг 2: Инициализация локального репозитория...
cd /d %PROJECT_DIR%
git init
echo [+] Локальный репозиторий создан.
echo.
echo --- Шаг 3: Создание репозитория на GitHub...
gh repo create %GITHUB_USERNAME%/%PROJECT_NAME% --public
if %errorlevel% neq 0 (
    echo [!] ОШИБКА: Не удалось создать репозиторий на GitHub.
    goto end
)
echo [+] Удаленный репозиторий создан.
echo.
echo --- Шаг 4: Связывание репозиториев...
git remote add origin https://github.com/%GITHUB_USERNAME%/%PROJECT_NAME%.git
echo [+] Репозитории связаны.
echo.
echo --- Шаг 5: Копирование инструмента синхронизации...
copy %TEMPLATE_SYNC_SCRIPT% %NEW_SYNC_SCRIPT% > nul
echo [+] Локальный инструмент 'sync.bat' развернут.
echo.
echo === ПРОЦЕСС ЗАВЕРШЕН ===
echo Проект '%PROJECT_NAME%' готов. Для синхронизации просто кликните sync.bat в его папке.
echo.
:end
pause