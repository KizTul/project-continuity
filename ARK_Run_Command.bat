@echo off

chcp 65001 > nul

set PYTHONUTF8=1

title ARK Command Runner



:: ARK Run Command v1.3 (Hotfix)

:: Safe launcher for the ARK Python CLI engine. Now supports interactive mode.



:: 1. Change to project root.

cd /d "%~dp0%"



:: 2. Check for Python.

where python >nul 2>&1

if errorlevel 1 (

    echo [ARK_Run_Command] ERROR: Python not found in PATH.

    pause

    exit /b 1

)



:: 3. Prefer local venv if available.

if exist "%~dp0%venv\Scripts\python.exe" (

    set PYTHON_CMD=%~dp0%venv\Scripts\python.exe

) else (

    set PYTHON_CMD=python

)



:: 4. Check if a command was provided as an argument.

if not "%~1"=="" (

    %PYTHON_CMD% _ark_system/_tools/cli.py %*

    goto :end

)



:: 5. Interactive mode: no command provided, so we ask for it.

echo.

set /p "user_command=Please paste the command and press Enter: "



%PYTHON_CMD% _ark_system/_tools/cli.py %user_command%



:end

pause