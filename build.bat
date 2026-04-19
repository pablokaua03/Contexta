@echo off
setlocal EnableExtensions EnableDelayedExpansion
echo.
echo  =========================================
echo   Contexta 1.6 - Build Windows Executable
echo  =========================================
echo.

set "OUTPUT_DIR=dist"
set "BUILD_DIR=%OUTPUT_DIR%\nuitka-build"
set "OUTPUT_EXE=%OUTPUT_DIR%\contexta.exe"
set "INSTALLER_SCRIPT=packaging\windows\contexta.iss"
set "INSTALLER_EXE=%OUTPUT_DIR%\contexta-setup.exe"
set "ICON_PATH=assets\icon.ico"
set "PYTHON=py"
set "VCVARS="
set "ISCC_PATH="

%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python launcher not found. Install Python from https://python.org
    pause
    exit /b 1
)

if exist "requirements-build.txt" (
    echo  Installing runtime and build dependencies...
    %PYTHON% -m pip install -r requirements-build.txt
) else (
    echo  [ERROR] Missing requirements-build.txt.
    pause
    exit /b 1
)
if errorlevel 1 (
    echo  [ERROR] Failed to install build dependencies.
    pause
    exit /b 1
)

where cl >nul 2>&1
if errorlevel 1 call :find_vcvars

if exist "%OUTPUT_EXE%" del /f /q "%OUTPUT_EXE%"
if exist "%BUILD_DIR%" rd /s /q "%BUILD_DIR%"
if exist "build" rd /s /q "build"

echo.
echo  Building Windows executable with Nuitka...
echo.

set "NUITKA_ARGS=--mode=onefile --windows-console-mode=disable --enable-plugins=tk-inter --windows-icon-from-ico=%ICON_PATH% --msvc=latest --assume-yes-for-downloads --output-dir=%BUILD_DIR% --output-filename=contexta.exe contexta.py"
set "BUILD_CMD=cd /d ""%CD%"" && %PYTHON% -m nuitka %NUITKA_ARGS%"

if defined VCVARS (
    set "BUILD_CMD=call ""%VCVARS%"" && !BUILD_CMD!"
)

cmd /c "!BUILD_CMD!"
if errorlevel 1 goto :build_error

if not exist "%BUILD_DIR%\contexta.exe" (
    echo  [ERROR] Nuitka did not produce %BUILD_DIR%\contexta.exe.
    goto :build_error
)

copy /y "%BUILD_DIR%\contexta.exe" "%OUTPUT_EXE%" >nul

where signtool >nul 2>&1
if errorlevel 1 goto :signing_skipped
if "%CONTEXTA_SIGN_PFX%"=="" goto :signing_skipped
if not exist "%CONTEXTA_SIGN_PFX%" goto :signing_skipped

echo.
echo  Signing executable...
if "%CONTEXTA_SIGN_PASSWORD%"=="" (
    signtool sign /fd SHA256 /f "%CONTEXTA_SIGN_PFX%" /tr http://timestamp.digicert.com /td SHA256 "%OUTPUT_EXE%"
) else (
    signtool sign /fd SHA256 /f "%CONTEXTA_SIGN_PFX%" /p "%CONTEXTA_SIGN_PASSWORD%" /tr http://timestamp.digicert.com /td SHA256 "%OUTPUT_EXE%"
)
if errorlevel 1 goto :build_error

:signing_skipped
where iscc >nul 2>&1
if errorlevel 1 call :find_iscc
if not defined ISCC_PATH goto :installer_skipped
if not exist "%INSTALLER_SCRIPT%" goto :installer_skipped

if exist "%INSTALLER_EXE%" del /f /q "%INSTALLER_EXE%"
echo.
echo  Building Windows installer...
"%ISCC_PATH%" /Qp "%INSTALLER_SCRIPT%"
if errorlevel 1 goto :build_error

:installer_skipped
echo.
echo  =========================================
echo   Done! Outputs:
echo     - %OUTPUT_EXE%
if exist "%INSTALLER_EXE%" echo     - %INSTALLER_EXE%
echo  =========================================
echo.

explorer dist
pause
exit /b 0

:find_vcvars
for /f "delims=" %%I in ('dir /s /b "%ProgramFiles%\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat" 2^>nul') do (
    set "VCVARS=%%I"
    goto :eof
)
for /f "delims=" %%I in ('dir /s /b "%ProgramFiles(x86)%\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat" 2^>nul') do (
    set "VCVARS=%%I"
    goto :eof
)
echo  [ERROR] Could not find vcvars64.bat. Install Visual Studio Build Tools with Desktop development with C++.
pause
exit /b 1

:find_iscc
for /f "delims=" %%I in ('dir /s /b "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" 2^>nul') do (
    set "ISCC_PATH=%%I"
    goto :eof
)
for /f "delims=" %%I in ('dir /s /b "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" 2^>nul') do (
    set "ISCC_PATH=%%I"
    goto :eof
)
for /f "delims=" %%I in ('dir /s /b "%ProgramFiles%\Inno Setup 6\ISCC.exe" 2^>nul') do (
    set "ISCC_PATH=%%I"
    goto :eof
)
exit /b 0

:build_error
echo.
echo  [ERROR] Build failed. Check the output above.
pause
exit /b 1
