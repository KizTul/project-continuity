@echo off
chcp 65001 > nul
echo [ARK] Собираю пакет тактического контекста для проекта...

REM Определяем путь к временному файлу
set "CONTEXT_PACKAGE=%TEMP%\ark_project_context.txt"
set "PROJECT_ROOT=%~dp0"

REM Очищаем старый файл, если он есть
if exist "%CONTEXT_PACKAGE%" del "%CONTEXT_PACKAGE%"

echo [+] Собираю документацию из '%PROJECT_ROOT%_docs\'

REM Собираем все документы в один файл
(
    echo --- [ ПАКЕТ ТАКТИЧЕСКОГО КОНТЕКСТА ПРОЕКТА ] ---
    echo.
    echo ### GDD & Roadmap ###
    type "%PROJECT_ROOT%_docs\GDD.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    type "%PROJECT_ROOT%_docs\Roadmap.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    
    echo ### Базы Знаний (если есть) ###
    REM Добавляем специфичные для проекта базы знаний
    if exist "%PROJECT_ROOT%_knowledge_base\" (
        for /r "%PROJECT_ROOT%_knowledge_base\" %%f in (*.md) do (
            echo. & echo [KB] %%~nxf & echo.
            type "%%f"
            echo. & echo --- END OF DOCUMENT --- & echo.
        )
    )

) > "%CONTEXT_PACKAGE%"

REM Копируем содержимое в буфер обмена
clip < "%CONTEXT_PACKAGE%"

echo [+] Пакет контекста проекта собран и скопирован в буфер обмена.
echo.
pause
