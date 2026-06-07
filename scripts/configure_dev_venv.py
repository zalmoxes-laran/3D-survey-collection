#!/usr/bin/env python3
"""Update .vscode/settings.json so VSCode picks up the dev venv interpreter.

Called by `em.sh first_setup`. Preserves all existing keys and only sets
`python.defaultInterpreterPath`. Seeds from .vscode/settings_template.json if
settings.json doesn't exist yet.

Usage:
    python scripts/configure_dev_venv.py <interpreter_relpath>
"""
import json
import sys
from pathlib import Path


def main(interpreter_relpath: str) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    vscode_dir = repo_root / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    settings = vscode_dir / "settings.json"
    template = vscode_dir / "settings_template.json"

    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"ERROR: {settings} is not valid JSON ({exc}); leaving alone", file=sys.stderr)
            return 1
    elif template.exists():
        try:
            data = json.loads(template.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"ERROR: {template} invalid JSON ({exc}); starting from {{}}", file=sys.stderr)
            data = {}
    else:
        data = {}

    data["python.defaultInterpreterPath"] = interpreter_relpath
    settings.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    print(f"   python.defaultInterpreterPath -> {interpreter_relpath}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: configure_dev_venv.py <interpreter_relpath>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
