#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-}"
PLATFORM="$(uname -s)"
SPEC_FILE="packaging/pyinstaller/contexta.spec"
OUTPUT_PATH="dist/contexta"
PACKAGE_ROOT="dist/contexta-linux"
PACKAGE_ARCHIVE="dist/contexta-linux.tar.gz"
BUILD_ROOT="$(pwd)"
PYI_DISTPATH="dist"
PYI_WORKPATH="build"

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

echo ""
echo " ========================================="
echo "  Contexta 1.6 - Build Unix Executable"
echo " ========================================="
echo ""

if [ ! -f "requirements-build.txt" ]; then
    echo " [ERROR] Missing requirements-build.txt"
    exit 1
fi

echo " Installing runtime and build dependencies..."
"$PYTHON_BIN" -m pip install -r requirements-build.txt

if ! "$PYTHON_BIN" -c "import tkinter" >/dev/null 2>&1; then
    echo " [ERROR] tkinter is not available for $PYTHON_BIN."
    echo "         On Debian/Ubuntu, try: sudo apt install python3-tk"
    exit 1
fi

rm -rf build
rm -rf "$PACKAGE_ROOT"
rm -f dist/contexta dist/contexta-linux.tar.gz
mkdir -p dist

if [ ! -f "$SPEC_FILE" ]; then
    echo " Missing $SPEC_FILE"
    exit 1
fi

echo " Building executable..."
if [ "$PLATFORM" = "Linux" ] && [[ "$BUILD_ROOT" == /mnt/* ]]; then
    PYI_DISTPATH="${HOME}/builds/contexta/dist"
    PYI_WORKPATH="${HOME}/builds/contexta/build"
    rm -rf "$PYI_DISTPATH" "$PYI_WORKPATH"
    mkdir -p "$PYI_DISTPATH" "$PYI_WORKPATH"
fi

"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --distpath "$PYI_DISTPATH" --workpath "$PYI_WORKPATH" "$SPEC_FILE"

if [ "$PYI_DISTPATH" != "dist" ]; then
    cp "$PYI_DISTPATH/contexta" dist/contexta
fi

if [ "$PLATFORM" = "Linux" ]; then
    mkdir -p "$PACKAGE_ROOT"
    cp dist/contexta "$PACKAGE_ROOT/contexta"
    cp packaging/linux/install-contexta.sh "$PACKAGE_ROOT/install.sh"
    cp README.md "$PACKAGE_ROOT/README.md"
    cp LICENSE "$PACKAGE_ROOT/LICENSE"
    chmod +x "$PACKAGE_ROOT/contexta" "$PACKAGE_ROOT/install.sh"
    tar -czf "$PACKAGE_ARCHIVE" -C dist contexta-linux
fi

echo ""
echo " Done!"
echo "  - $OUTPUT_PATH"
if [ "$PLATFORM" = "Linux" ]; then
    echo "  - $PACKAGE_ARCHIVE"
fi
echo ""
