@echo off
chcp 65001 > nul
set PYTHONUTF8=1
title ARK Apply Changes

cd /d "%~dp0%"

if exist "%~dp0%venv\Scripts\python.exe" (
    set PYTHON_CMD=%~dp0%venv\Scripts\python.exe
) else (
    set PYTHON_CMD=python
)

%PYTHON_CMD% _ark_system/_tools/apply_modifications.py

pause
