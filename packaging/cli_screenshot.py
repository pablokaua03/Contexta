#!/usr/bin/env python3
"""
Regenerate assets/cli.png from a real run of the CLI.

    python packaging/cli_screenshot.py [OUT.png]

Runs `contexta sample-app --pack onboarding` in a pseudo-terminal on a throwaway project with
relative paths (no machine-specific path in the picture), keeps the ANSI colors the CLI wrote,
and draws them with DejaVu Sans Mono. Needs Linux and Pillow.
"""

from __future__ import annotations

import os
import pty
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BG, FG = (12, 18, 16), (200, 210, 205)
BASIC = {"31": (230, 90, 90), "32": (60, 190, 90), "33": (220, 180, 60), "36": (50, 200, 200)}
SAMPLE = {
    "README.md": "# sample-app\n",
    "pyproject.toml": '[project]\nname = "sample-app"\nversion = "0.1.0"\n',
    "src/utils.py": "def slugify(text):\n    return text.lower()\n",
    "src/app.py": "from src.utils import slugify\n",
    "tests/test_app.py": "from src.utils import slugify\n\n\ndef test_slugify():\n    assert slugify('A') == 'a'\n",
}
COMMAND = ["sample-app", "--pack", "onboarding", "-o", "contexta-out/pack.md"]


def run_in_pty(work: Path) -> str:
    env = {**os.environ, "CONTEXTA_COLOR": "1", "TERM": "xterm-256color", "HOME": str(work / "home")}
    env.pop("NO_COLOR", None)
    (work / "home").mkdir(exist_ok=True)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(work)
        os.execvpe(sys.executable, [sys.executable, str(ROOT / "contexta.py"), *COMMAND], env)
    data = b""
    while True:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        data += chunk
    os.waitpid(pid, 0)
    text = data.decode("utf-8", "replace").replace("\r\n", "\n")
    return text.replace(str(work.resolve()) + os.sep, "").replace(str(work) + os.sep, "")  # the CLI prints absolute paths


def parse(text: str) -> list[list[tuple[str, tuple, bool]]]:
    lines, color, dim, bold = [], FG, False, False
    for raw in text.split("\n"):
        runs = []
        for part in re.split(r"(\x1b\[[0-9;]*m)", raw):
            if part.startswith("\x1b["):
                codes = part[2:-1].split(";") or ["0"]
                if codes[:2] == ["38", "2"] and len(codes) >= 5:
                    color = tuple(int(c) for c in codes[2:5])
                elif codes == ["0"] or codes == [""]:
                    color, dim, bold = FG, False, False
                else:
                    for code in codes:
                        if code == "1":
                            bold = True
                        elif code == "2":
                            dim = True
                        elif code in BASIC:
                            color = BASIC[code]
            elif part:
                shade = tuple(int(c * 0.6 + b * 0.4) for c, b in zip(color, BG)) if dim else color
                runs.append((part, shade, bold))
        lines.append(runs)
    return lines


def draw(lines, prompt: str, out: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    regular = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
    heavy = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 17)
    advance = regular.getlength("M")
    rows = [[(prompt, FG, False)], []] + [r for r in lines]
    while rows and not rows[-1]:
        rows.pop()
    height = 28 + 24 * len(rows) + 16
    image = Image.new("RGB", (1049, height), BG)
    pen = ImageDraw.Draw(image)
    for row, runs in enumerate(rows):
        x, y = 2.0, 14 + 24 * row
        for text, color, bold in runs:
            pen.text((x, y), text, font=heavy if bold else regular, fill=color)
            x += advance * len(text)
    image.save(out)
    print(f"wrote {out} {image.size}")


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets" / "cli.png"
    work = Path(tempfile.mkdtemp(prefix="contexta-cli-"))
    try:
        for rel, body in SAMPLE.items():
            target = work / "sample-app" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        (work / "contexta-out").mkdir()
        output = run_in_pty(work)
        draw(parse(output), "$ contexta " + " ".join(COMMAND[:3]), out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
