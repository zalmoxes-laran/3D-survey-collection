@echo off
setlocal enabledelayedexpansion
:: 3D Survey Collection - Windows developer CLI (mirrors em.sh).
::   em first_setup                       create .venv for VSCode IntelliSense
::   em setup [force] [3.11^|3.13^|all]     wheels + manifest + .vscode\settings.json
::   em manifest [3.11^|3.13]              regenerate blender_manifest.toml
::   em build [3.11^|3.13]                 build a dev .blext into ..\3DSC_Releases
::   em dev [3.11^|3.13]                   increment dev build + build
::   em inc [dev_build^|patch^|minor^|major]  bump version
::   em stable                            build stable + git tag
::   em devrel [3.11^|3.13]                bump dev + commit + tag + PUSH (CI)
::   em ghrelease                          stable release: bump + tag + PUSH (CI + Zenodo)
::   em current ^| status                  show version (+ git status)
::   em clean                             remove __pycache__
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PY=python"
set "CMD=%1"
if "%CMD%"=="" set "CMD=help"

if /i "%CMD%"=="first_setup" goto :first_setup
if /i "%CMD%"=="setup"       goto :setup
if /i "%CMD%"=="manifest"    goto :manifest
if /i "%CMD%"=="build"       goto :build
if /i "%CMD%"=="dev"         goto :dev
if /i "%CMD%"=="inc"         goto :inc
if /i "%CMD%"=="stable"      goto :stable
if /i "%CMD%"=="devrel"      goto :devrel
if /i "%CMD%"=="ghrelease"   goto :ghrelease
if /i "%CMD%"=="current"     goto :current
if /i "%CMD%"=="status"      goto :status
if /i "%CMD%"=="clean"       goto :clean
goto :help

:first_setup
cd /d "%ROOT%"
if not exist ".venv" python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip wheel >nul
echo Installing runtime + dev deps into .venv (IntelliSense only) ...
.venv\Scripts\python -m pip install -r scripts\requirements_wheels.txt || ( echo dep install failed & exit /b 1 )
.venv\Scripts\python -m pip install -r scripts\requirements_dev.txt
python scripts\configure_dev_venv.py ".\.venv\Scripts\python.exe"
echo Dev venv ready. Blender loads wheels\cp* - run: em setup all
goto :eof

:setup
set "FORCE="
set "PV=3.11"
for %%x in (%2 %3) do (
    if /i "%%x"=="force" set "FORCE=force"
    if "%%x"=="3.11" set "PV=3.11"
    if "%%x"=="3.13" set "PV=3.13"
    if "%%x"=="all"  set "PV=all"
)
if "!PV!"=="all" (
    call "%ROOT%\scripts\setup_dev_windows.bat" !FORCE! 3.11
    call "%ROOT%\scripts\setup_dev_windows.bat" !FORCE! 3.13
) else (
    call "%ROOT%\scripts\setup_dev_windows.bat" !FORCE! !PV!
)
goto :eof

:manifest
set "PV=%2"
if "!PV!"=="" set "PV=3.11"
"%PY%" "%ROOT%\scripts\version_manager.py" update --python-version=!PV!
goto :eof

:build
set "PV=%2"
if "!PV!"=="" set "PV=3.11"
"%PY%" "%ROOT%\scripts\build.py" --mode dev --python-version=!PV!
goto :eof

:dev
set "PV=%2"
if "!PV!"=="" set "PV=3.11"
"%PY%" "%ROOT%\scripts\version_manager.py" increment --part dev_build >nul
"%PY%" "%ROOT%\scripts\build.py" --mode dev --python-version=!PV!
goto :eof

:inc
set "PART=%2"
if "!PART!"=="" set "PART=dev_build"
"%PY%" "%ROOT%\scripts\version_manager.py" increment --part !PART!
goto :eof

:stable
"%PY%" "%ROOT%\scripts\build.py" --mode stable
goto :eof

:devrel
echo == 3DSC dev release: push a dev tag -^> CI builds .zip x4 platforms ==
for /f "tokens=*" %%v in ('python "%ROOT%\scripts\version_manager.py" next --part dev_build') do set "NEXT=%%v"
"%PY%" "%ROOT%\scripts\version_manager.py" current
echo Will commit, tag and push: v!NEXT!   - CI builds 8 zips
set /p REPLY=Continue? (y/N):
if /i not "!REPLY!"=="y" ( echo cancelled & goto :eof )
"%PY%" "%ROOT%\scripts\version_manager.py" increment --part dev_build >nul
for /f "tokens=3" %%v in ('python "%ROOT%\scripts\version_manager.py" current') do set "VER=%%v"
for /f "tokens=*" %%b in ('git -C "%ROOT%" rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"
git -C "%ROOT%" add -A
git -C "%ROOT%" commit -m "build: dev release !VER!"
git -C "%ROOT%" tag "v!VER!"
git -C "%ROOT%" push origin !BRANCH!
git -C "%ROOT%" push origin "v!VER!"
echo Pushed v!VER! on !BRANCH!.
echo   Actions: https://github.com/zalmoxes-laran/3D-survey-collection/actions
goto :eof

:ghrelease
echo == 3DSC stable release: push a stable tag -^> CI builds + Zenodo ==
"%PY%" "%ROOT%\scripts\version_manager.py" current
set /p INC=Increment (patch/minor/major) [patch]:
if "!INC!"=="" set "INC=patch"
for /f "tokens=*" %%v in ('python "%ROOT%\scripts\version_manager.py" next --part !INC! --mode stable') do set "NEXT=%%v"
echo Will commit, tag and push STABLE: v!NEXT!
set /p REPLY=Create STABLE release and PUSH? (y/N):
if /i not "!REPLY!"=="y" ( echo cancelled & goto :eof )
"%PY%" "%ROOT%\scripts\version_manager.py" increment --part !INC! >nul
"%PY%" "%ROOT%\scripts\version_manager.py" set-mode --mode stable >nul
for /f "tokens=3" %%v in ('python "%ROOT%\scripts\version_manager.py" current') do set "VER=%%v"
for /f "tokens=*" %%b in ('git -C "%ROOT%" rev-parse --abbrev-ref HEAD') do set "BRANCH=%%b"
git -C "%ROOT%" add -A
git -C "%ROOT%" commit -m "release: !VER!"
git -C "%ROOT%" tag "v!VER!"
git -C "%ROOT%" push origin !BRANCH!
git -C "%ROOT%" push origin "v!VER!"
echo Pushed stable v!VER!.
goto :eof

:current
"%PY%" "%ROOT%\scripts\version_manager.py" current
goto :eof

:status
"%PY%" "%ROOT%\scripts\version_manager.py" current
git -C "%ROOT%" status --short
goto :eof

:clean
for /d /r "%ROOT%" %%p in (__pycache__) do if exist "%%p" rd /s /q "%%p"
echo cleaned __pycache__
goto :eof

:help
echo 3DSC dev CLI (Windows). Commands:
echo   em first_setup ^| setup [force] [3.11^|3.13^|all] ^| manifest [ver] ^| build [ver]
echo   em dev [ver] ^| inc [part] ^| stable ^| devrel [ver] ^| ghrelease
echo   em current ^| status ^| clean
goto :eof
