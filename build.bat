@echo off
echo.
echo  =========================================
echo   mdcodebrief - Build Executable
echo  =========================================
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

echo  Installing PyInstaller...
py -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo  [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo  Building executable...
echo.

REM --noupx: avoids false antivirus positives
REM No --add-data: keeps exe clean and trusted by SmartScreen
if exist "icon.ico" (
    py -m PyInstaller --onefile --windowed --noupx --icon=icon.ico --name=mdcodebrief mdcodebrief.py
) else (
    py -m PyInstaller --onefile --windowed --noupx --name=mdcodebrief mdcodebrief.py
)

if errorlevel 1 (
    echo.
    echo  [ERROR] Build failed. Check the output above.
    pause
    exit /b 1
)

echo.
echo  =========================================
echo   Done! Executable: dist\mdcodebrief.exe
echo  =========================================
echo.

explorer dist
pause
