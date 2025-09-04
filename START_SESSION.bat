@echo off
chcp 65001 > nul
title ARK Full Context Initializer

:: ARK Start Session v3.0 (Unified Context Mode)
:: This tool concatenates all Core Docs, including the Tools Guide,
:: into a single package for a reliable AI initialization.

:: Ensure we run from the project root
cd /d "%~dp0%"

echo [ARK] Preparing full context package... Please wait.

(
    type "_ark_system\_core_docs\PROMETHEUS_INIT.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\_core_docs\OPERATING_PROCEDURES.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\_docs\ARK_Tools_Guide.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\ARK_STRUCTURE.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\ARK_CODEX.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\ARK_MANIFEST.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\gdd_ark.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\roadmap_ark.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\EXPERIENCE_SCHEMA.md"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
    type "_ark_system\ARK_EXPERIENCE_CODEX.json"
    echo.
    echo --- END OF DOCUMENT ---
    echo.
) | clip

echo [ARK] SUCCESS: The full ARK Core Context has been copied to your clipboard.
echo Please paste it into the new AI session to begin.
pause
