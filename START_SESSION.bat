@echo off
chcp 65001 > nul
echo [ARK] Собираю пакет контекста для инициализации...

REM Определяем путь к временному файлу
set "CONTEXT_PACKAGE=%TEMP%\ark_context_package.txt"

REM Очищаем старый файл, если он есть
if exist "%CONTEXT_PACKAGE%" del "%CONTEXT_PACKAGE%"

REM Собираем все документы в один файл
(
    echo --- [ ПАКЕТ КОНТЕКСТА ARK v3.0 ] ---
    echo.
    echo ### ДОКУМЕНТЫ ЯДРА ###
    type "_ark_system\_core_docs\PROMETHEUS_INIT.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    type "_ark_system\_core_docs\OPERATING_PROCEDURES.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    echo ### СИСТЕМНЫЕ ДОКУМЕНТЫ ###
    type "_ark_system\ARK_CODEX.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    type "_ark_system\ARK_MANIFEST.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    type "_ark_system\gdd_ark.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    type "_ark_system\roadmap_ark.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    echo ### СИСТЕМА ОПЫТА ###
    type "_ark_system\EXPERIENCE_SCHEMA.md"
    echo. & echo --- END OF DOCUMENT --- & echo.
    type "ARK_EXPERIENCE_CODEX.json"
    echo. & echo --- END OF DOCUMENT --- & echo.
) > "%CONTEXT_PACKAGE%"

REM Копируем содержимое в буфер обмена
clip < "%CONTEXT_PACKAGE%"

echo [+] Пакет контекста собран и скопирован в буфер обмена.
echo.
echo Теперь вы можете вставить его в сессию ИИ.
echo.
pause
