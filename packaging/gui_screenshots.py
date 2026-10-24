#!/usr/bin/env python3
"""
Regenerate the README screenshots of the desktop app (1200x820) from the real GUI.

    xvfb-run -a -s "-screen 0 1200x820x24" python packaging/gui_screenshots.py [OUT_DIR]

Writes dark.png, white.png, empty.png, result.png and error.png into OUT_DIR (default: assets/,
error.png goes to docs/images/ when OUT_DIR is the default). Uses a throwaway project called
sample-app and relative paths, so no machine-specific path shows up in the images.
Needs Linux with Xvfb, Tk and Pillow. Run it from the repository root.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SAMPLE = {
    "README.md": "# sample-app\n\nA tiny web service used to show Contexta.\n",
    "pyproject.toml": '[project]\nname = "sample-app"\nversion = "0.1.0"\ndependencies = ["flask>=3"]\n',
    "src/app.py": 'from flask import Flask\n\nfrom src.utils import slugify\n\napp = Flask(__name__)\n\n\n@app.get("/<title>")\ndef show(title):\n    return slugify(title)\n',
    "src/utils.py": "def slugify(text: str) -> str:\n    return \"-\".join(text.lower().split())\n",
    "tests/test_app.py": "from src.utils import slugify\n\n\ndef test_slugify():\n    assert slugify('Hello World') == 'hello-world'\n",
}


def grab(path: Path) -> None:
    from PIL import ImageGrab

    image = ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).convert("RGB")
    image.save(path)
    print(f"wrote {path} {image.size}")


def main() -> int:
    from contexta_app import theme, ui

    out_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    out_dir = out_arg or ROOT / "assets"
    error_dir = out_arg or ROOT / "docs" / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    error_dir.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="contexta-shots-"))
    for rel, text in SAMPLE.items():
        target = work / "sample-app" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (work / "contexta-out").mkdir()
    os.chdir(work)  # relative paths below keep the machine's folders out of the pictures
    ui.get_desktop = lambda: Path("contexta-out")

    app = ui.App()
    app.geometry("1200x820+0+0")

    def settle(seconds: float = 0.8) -> None:
        end = time.time() + seconds
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def choose_project() -> None:
        app._project_path = Path("sample-app")
        app._preview_snapshot = None
        app._path_var.set("sample-app")
        app._btn_generate.configure(state="normal")
        app._hide_banner()
        app._log_clear()
        app._log_write("Project folder selected: sample-app", "info")
        app._set_status("sample-app", "tag_bg", "tag_fg")
        app._set_view("preview")
        app._refresh_preview()

    settle(1.2)
    if theme.C["mode"] != "dark":
        app._toggle_theme()
    settle()
    grab(out_dir / "empty.png")

    choose_project()
    settle()
    grab(out_dir / "dark.png")

    app._toggle_theme()
    settle(1.0)
    grab(out_dir / "white.png")
    app._toggle_theme()
    settle(0.6)

    # Same work as the Create button, run in this thread so the screenshot script needs no main loop.
    markdown = ui.generate_markdown(
        app._project_path, pack_profile=app._pack_var.get(), context_mode=app._mode_var.get(),
        ai_profile=app._ai_var.get(), task_profile=app._task_var.get(), compression=app._compression_var.get(),
        log_cb=app._log_write,
    )
    out_file = ui.get_desktop() / "contexta - sample-app.md"
    out_file.write_text(markdown, encoding="utf-8")
    app._finish_success(markdown, out_file, False)
    settle(1.0)
    app._set_view("result")
    settle(0.8)
    grab(out_dir / "result.png")

    app._show_error("Could not read the project folder.")
    settle(0.8)
    grab(error_dir / "error.png")

    app.destroy()
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
