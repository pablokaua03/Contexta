#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${CONTEXTA_INSTALL_DIR:-$HOME/.local/bin}"
TARGET_PATH="$TARGET_DIR/contexta"

mkdir -p "$TARGET_DIR"
install -m 755 "$SCRIPT_DIR/contexta" "$TARGET_PATH"

echo "Contexta installed to: $TARGET_PATH"
echo "If needed, add $TARGET_DIR to your PATH before launching 'contexta'."
