from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "HiveBossDialog",
        "--collect-all",
        "PySide6",
        "--paths",
        str(repo_root),
        str(repo_root / "apps" / "desktop" / "polished_main.py"),
    ]
    subprocess.run(command, cwd=repo_root, check=True)
    print(repo_root / "dist" / "HiveBossDialog" / "HiveBossDialog.exe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
