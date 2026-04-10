#!/usr/bin/env bash
set -e
echo ""
echo " ========================================="
echo "  mdcodebrief - Build Executable"
echo " ========================================="
echo ""

if ! pip show pyinstaller &>/dev/null; then
    echo " Installing PyInstaller..."
    pip install pyinstaller
fi

echo " Building..."
echo ""

if [ -f "icon.ico" ]; then
    pyinstaller --onefile --windowed --icon=icon.ico --name=mdcodebrief mdcodebrief.py
else
    pyinstaller --onefile --windowed --name=mdcodebrief mdcodebrief.py
fi

echo ""
echo " Done! → dist/mdcodebrief"
echo ""
