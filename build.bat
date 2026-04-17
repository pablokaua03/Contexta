@echo off
setlocal
echo.
echo  =========================================
echo   Contexta - Build Executable
echo  =========================================
echo.

set "SPEC_FILE=contexta-onefile.spec"
set "OUTPUT_EXE=dist\contexta.exe"

py --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

py -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo  Installing PyInstaller...
    py -m pip install pyinstaller
)
if errorlevel 1 (
    echo  [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo  Building executable...
echo.

if exist "dist\contexta.exe" del /f /q "dist\contexta.exe"
if exist "dist\contexta" (
    if exist "dist\contexta\" (
        rd /s /q "dist\contexta"
    ) else (
        del /f /q "dist\contexta"
    )
)
if exist "build" rd /s /q "build"
if not exist "%SPEC_FILE%" (
    echo  [ERROR] Missing %SPEC_FILE%.
    pause
    exit /b 1
)

py -m PyInstaller --noconfirm --clean "%SPEC_FILE%"

if errorlevel 1 goto :build_error

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

echo.
echo  =========================================
echo   Done! Outputs:
echo     - %OUTPUT_EXE%
echo  =========================================
echo.

explorer dist
pause
exit /b 0

:build_error
echo.
echo  [ERROR] Build failed. Check the output above.
pause
exit /b 1
