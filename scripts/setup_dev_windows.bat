@echo off
setlocal enabledelayedexpansion
:: 3D Survey Collection - Windows dev setup.
:: Downloads dependency wheels, regenerates the manifest and writes
:: .vscode\settings.json (autodetecting blender.exe) for the VSCode
:: "Blender Development" extension.
::
:: Usage (from repo root):  scripts\setup_dev_windows.bat [force] [3.11^|3.13]
:: Parse args by value (not position) so "force" and "3.11/3.13" work in any order.
set "FORCE_ARG="
set "PYTHON_VER=3.11"
for %%a in (%1 %2) do (
    if /i "%%a"=="force" set "FORCE_ARG=force"
    if "%%a"=="3.11" set "PYTHON_VER=3.11"
    if "%%a"=="3.13" set "PYTHON_VER=3.13"
)

echo === 3DSC dev setup (Windows) - Python !PYTHON_VER! ===

python --version >nul 2>&1
if errorlevel 1 ( echo ERROR: Python not found in PATH & pause & exit /b 1 )

:: Wheels
set "SETUP_ARGS=--python-version=!PYTHON_VER!"
if /i "!FORCE_ARG!"=="force" set "SETUP_ARGS=!SETUP_ARGS! --force"
python scripts\setup_development.py !SETUP_ARGS!
if errorlevel 1 ( echo ERROR: wheel download failed & pause & exit /b 1 )

:: Manifest
python scripts\version_manager.py set-mode --mode dev --python-version !PYTHON_VER! >nul
python scripts\version_manager.py update --python-version !PYTHON_VER!

:: Find Blender
set "BLENDER_PATH="
for %%d in ("C:\Program Files\Blender Foundation" "%LOCALAPPDATA%\Programs\Blender Foundation") do (
    if exist %%~d (
        for /d %%v in ("%%~d\Blender*") do (
            if exist "%%v\blender.exe" set "BLENDER_PATH=%%v\blender.exe"
        )
    )
)
if not defined BLENDER_PATH (
    where blender >nul 2>&1 && for /f "tokens=*" %%i in ('where blender') do set "BLENDER_PATH=%%i"
)

:: .vscode\settings.json from template
if not exist ".vscode" mkdir .vscode
if exist ".vscode\settings_template.json" (
    copy /y ".vscode\settings_template.json" ".vscode\settings.json" >nul
    if defined BLENDER_PATH (
        set "ESCAPED=!BLENDER_PATH:\=\\!"
        powershell -NoProfile -Command "(Get-Content '.vscode\settings.json') -replace 'BLENDER_PATH_PLACEHOLDER', '!ESCAPED!' | Set-Content '.vscode\settings.json'"
        echo Blender: !BLENDER_PATH!
    ) else (
        echo WARNING: Blender not found - set blender.executable in .vscode\settings.json manually
    )
    echo .vscode\settings.json written
) else (
    echo WARNING: .vscode\settings_template.json missing
)

echo.
echo Done. In VSCode: Ctrl+Shift+P -^> "Blender: Start".
endlocal
