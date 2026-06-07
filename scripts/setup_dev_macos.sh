#!/usr/bin/env bash
# 3D Survey Collection — macOS dev setup.
# Downloads dependency wheels, regenerates the manifest, and writes
# .vscode/settings.json (autodetecting the Blender executable) so the VSCode
# "Blender Development" extension can launch 3DSC live from this repo.
#
# Usage (from repo root):  ./scripts/setup_dev_macos.sh [force] [3.11|3.13]
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

echo "=== 3DSC dev setup (macOS) — Python $PY_VER ==="

# 1) Download wheels for the target Python (host platform).
"$PYTHON_CMD" scripts/setup_development.py --python-version="$PY_VER" $FORCE_ARG \
  || { echo "ERROR: wheel download failed"; exit 1; }

# 2) Regenerate the manifest for that Python version.
"$PYTHON_CMD" scripts/version_manager.py set-mode --mode dev --python-version "$PY_VER" >/dev/null
"$PYTHON_CMD" scripts/version_manager.py update --python-version "$PY_VER"

# 3) Autodetect a Blender executable.
BLENDER_PATH=""
# nullglob + direct globbing so paths with spaces (e.g. "Blender 510.app")
# are matched as a single word and non-matching globs vanish.
shopt -s nullglob
# Glob expansion is sorted, so keeping the LAST match (no break) prefers the
# highest-versioned Blender (e.g. "Blender 510.app" over "Blender 501.app").
for p in \
    /Applications/Blender.app/Contents/MacOS/Blender \
    /Applications/Blender*.app/Contents/MacOS/Blender \
    "$HOME"/Applications/Blender.app/Contents/MacOS/Blender \
    "$HOME"/Applications/Blender*.app/Contents/MacOS/Blender; do
  [ -x "$p" ] && BLENDER_PATH="$p"
done
shopt -u nullglob

# 4) Write .vscode/settings.json from the template.
mkdir -p .vscode
if [ -f .vscode/settings_template.json ]; then
  cp .vscode/settings_template.json .vscode/settings.json
  if [ -n "$BLENDER_PATH" ]; then
    ESC=$(printf '%s' "$BLENDER_PATH" | sed 's/[&/]/\\&/g')
    sed -i '' "s|BLENDER_PATH_PLACEHOLDER|$ESC|g" .vscode/settings.json
    echo "Blender executable: $BLENDER_PATH"
  else
    echo "WARNING: Blender not found in /Applications — set blender.executable"
    echo "         manually in .vscode/settings.json"
  fi
  echo ".vscode/settings.json written"
else
  echo "WARNING: .vscode/settings_template.json missing"
fi

echo
echo "Done. In VSCode: Cmd+Shift+P -> 'Blender: Start' (loads 3DSC live)."
echo "For multiple Blender versions, change blender.executable and reload."
