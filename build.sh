#!/usr/bin/env bash
set -e

PYTHON_BIN="${PYTHON_BIN:-}"

if [ -z "$PYTHON_BIN" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        echo " [ERROR] Python 3 not found."
        exit 1
    fi
fi

PLATFORM="$(uname -s)"
OUTPUT_PATH="dist/contexta"

echo ""
echo " ========================================="
echo "  Contexta - Build Executable"
echo " ========================================="
echo ""

if ! "$PYTHON_BIN" -m pip show pyinstaller >/dev/null 2>&1; then
    echo " Installing PyInstaller..."
    "$PYTHON_BIN" -m pip install pyinstaller
fi

if ! "$PYTHON_BIN" -c "import tkinter" >/dev/null 2>&1; then
    echo " [ERROR] tkinter is not available for $PYTHON_BIN."
    echo "         On Debian/Ubuntu, try: sudo apt install python3-tk"
    exit 1
fi

echo " Building..."
echo ""

rm -rf build
rm -f dist/contexta dist/contexta.exe dist/contexta-onefile.exe
rm -rf dist/contexta-safe

if [ ! -f "contexta.spec" ]; then
    echo " Missing contexta.spec"
    exit 1
fi

"$PYTHON_BIN" -m PyInstaller --noconfirm --clean contexta.spec

if [ "$PLATFORM" = "Linux" ]; then
    OUTPUT_PATH="dist/contexta"
elif [ "$PLATFORM" = "Darwin" ]; then
    OUTPUT_PATH="dist/contexta"
else
    OUTPUT_PATH="dist/contexta.exe"
fi

echo ""
echo " Done!"
echo "  - $OUTPUT_PATH"
echo ""
