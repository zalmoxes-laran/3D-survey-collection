#!/usr/bin/env bash
# 3D Survey Collection — Linux dev setup.
# Downloads dependency wheels, regenerates the manifest, and writes
# .vscode/settings.json (autodetecting the Blender executable) so the VSCode
# "Blender Development" extension can launch 3DSC live from this repo.
#
# Usage (from repo root):  ./scripts/setup_dev_linux.sh [force] [3.11|3.13]
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FORCE_ARG=""
PY_VER="3.11"
for a in "$@"; do
  case "$a" in
    force|--force) FORCE_ARG="--force" ;;
    3.11|3.13)     PY_VER="$a" ;;
  esac
done
PYTHON_CMD="${PYTHON:-python3}"

echo "=== 3DSC dev setup (Linux) — Python $PY_VER ==="

"$PYTHON_CMD" scripts/setup_development.py --python-version="$PY_VER" $FORCE_ARG \
  || { echo "ERROR: wheel download failed"; exit 1; }

"$PYTHON_CMD" scripts/version_manager.py set-mode --mode dev --python-version "$PY_VER" >/dev/null
"$PYTHON_CMD" scripts/version_manager.py update --python-version "$PY_VER"

# Autodetect a Blender executable.
BLENDER_PATH=""
if command -v blender >/dev/null 2>&1; then
  BLENDER_PATH="$(command -v blender)"
fi
if [ -z "$BLENDER_PATH" ]; then
  shopt -s nullglob
  for p in \
      /usr/bin/blender /usr/local/bin/blender /snap/bin/blender \
      /opt/blender*/blender "$HOME"/blender*/blender "$HOME"/.local/bin/blender; do
    [ -x "$p" ] && BLENDER_PATH="$p"
  done
  shopt -u nullglob
fi

mkdir -p .vscode
if [ -f .vscode/settings_template.json ]; then
  cp .vscode/settings_template.json .vscode/settings.json
  if [ -n "$BLENDER_PATH" ]; then
    ESC=$(printf '%s' "$BLENDER_PATH" | sed 's/[&/]/\\&/g')
    sed -i "s|BLENDER_PATH_PLACEHOLDER|$ESC|g" .vscode/settings.json   # GNU sed
    echo "Blender executable: $BLENDER_PATH"
  else
    echo "WARNING: Blender not found — set blender.executable in .vscode/settings.json"
  fi
  echo ".vscode/settings.json written"
else
  echo "WARNING: .vscode/settings_template.json missing"
fi

echo
echo "Done. In VSCode: Ctrl+Shift+P -> 'Blender: Start' (loads 3DSC live)."
