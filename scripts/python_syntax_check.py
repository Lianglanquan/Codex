from __future__ import annotations

import ast
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv] or [Path("orchestrator"), Path("apps/api"), Path("tests")]
    errors: list[str] = []

    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files = [root]
        else:
            files = sorted(root.rglob("*.py")) if root.exists() else []

        for path in files:
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                errors.append(f"{path}:{exc.lineno}:{exc.offset}: {exc.msg}")

    if errors:
        for error in errors:
            print(error)
        return 1

    print("python syntax check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
