@echo off
chcp 65001 > nul
echo.
echo === [ ARK WIZARD v3.0 ] : Создание Нового Проекта ===
echo.

set /p PROJECT_NAME="Введите имя нового проекта (например, MyNewGame): "
if not defined PROJECT_NAME (
    echo [!] ОШИБКА: Имя проекта не может быть пустым.
    goto end
)

set "PROJECT_DIR=projects\%PROJECT_NAME%"
set "GITHUB_USERNAME=KizTul"
set "TEMPLATE_SYNC_SCRIPT=_ark_system\_tools\template_sync.bat"

echo.
echo --- Шаг 1: Создание структуры проекта...
if exist "%PROJECT_DIR%" (
    echo [!] ОШИБКА: Проект '%PROJECT_NAME%' уже существует.
    goto end
)
mkdir "%PROJECT_DIR%"
mkdir "%PROJECT_DIR%\_docs"
mkdir "%PROJECT_DIR%\_src"
mkdir "%PROJECT_DIR%\_tools"
mkdir "%PROJECT_DIR%\_references"
echo [+] Структура папок создана.

echo.
echo --- Шаг 2: Инициализация Git...
cd /d "%PROJECT_DIR%"
git init
echo [+] Локальный репозиторий создан.

echo.
echo --- Шаг 3: Создание репозитория на GitHub...
gh repo create %GITHUB_USERNAME%/%PROJECT_NAME% --public --source=. --remote=origin
if %errorlevel% neq 0 (
    echo [!] ОШИБКА: Не удалось создать репозиторий на GitHub. Убедитесь, что gh CLI авторизован.
    cd ..\..
    goto end
)
echo [+] Удаленный репозиторий создан и связан.

echo.
echo --- Шаг 4: Развертывание инструментов проекта...
copy "..\..\%TEMPLATE_SYNC_SCRIPT%" "_tools\sync.bat" > nul
echo [+] Инструмент 'sync.bat' развернут.

cd ..\..

echo.
echo === ПРОЦЕСС ЗАВЕРШЕН ===
echo Проект '%PROJECT_NAME%' готов к работе.
echo.
:end
pause
