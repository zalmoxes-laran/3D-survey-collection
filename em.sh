#!/usr/bin/env bash
# 3D Survey Collection — developer CLI (mirrors the EM-tools workflow).
#
#   ./em.sh first_setup                     create .venv for VSCode IntelliSense (one-time)
#   ./em.sh setup [force] [3.11|3.13|all]   download wheels + manifest + .vscode/settings.json
#   ./em.sh manifest [3.11|3.13]            regenerate blender_manifest.toml
#   ./em.sh build [3.11|3.13]               build a dev .blext into ../3DSC_Releases
#   ./em.sh dev [3.11|3.13]                 increment dev build + build
#   ./em.sh inc [dev_build|patch|minor|major]   bump version
#   ./em.sh stable                          build stable + git tag
#   ./em.sh current | status                show version (+ git status)
#   ./em.sh clean                           remove __pycache__ dirs
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
cmd="${1:-help}"
[ $# -gt 0 ] && shift

# Set up wheels + manifest (+ .vscode on macOS) for ONE Python version.
_setup_one() {
  local pv="$1" force="$2"
  if [ "$(uname)" = "Darwin" ] && [ -f "$ROOT/scripts/setup_dev_macos.sh" ]; then
    bash "$ROOT/scripts/setup_dev_macos.sh" $force "$pv"
  else
    "$PY" "$ROOT/scripts/setup_development.py" --python-version="$pv" $force \
      && "$PY" "$ROOT/scripts/version_manager.py" update --python-version="$pv"
  fi
}

case "$cmd" in
  first_setup)
    cd "$ROOT"
    VPY=""
    for c in python3.13 python3.11 python3; do command -v "$c" >/dev/null 2>&1 && VPY="$c" && break; done
    [ -z "$VPY" ] && { echo "Python 3.11+ not found in PATH"; exit 1; }
    [ -d .venv ] || { echo "Creating .venv ($VPY) ..."; "$VPY" -m venv .venv || exit 1; }
    .venv/bin/pip install --upgrade pip wheel >/dev/null
    echo "Installing runtime + dev deps into .venv (IntelliSense only) ..."
    .venv/bin/pip install -r scripts/requirements_wheels.txt || { echo "dep install failed"; exit 1; }
    .venv/bin/pip install -r scripts/requirements_dev.txt || true
    "$PY" scripts/configure_dev_venv.py "./.venv/bin/python"
    echo "Dev venv ready. Blender loads wheels/cp* — run: ./em.sh setup all"
    ;;
  setup)
    pyver="3.11"; force=""
    for a in "$@"; do
      case "$a" in
        force|--force) force="--force" ;;
        3.11|3.13|all) pyver="$a" ;;
      esac
    done
    if [ "$pyver" = "all" ]; then
      for pv in 3.11 3.13; do echo "=== setup wheels for Python $pv ==="; _setup_one "$pv" "$force"; done
    else
      _setup_one "$pyver" "$force"
    fi
    ;;
  manifest) "$PY" "$ROOT/scripts/version_manager.py" update --python-version="${1:-3.11}" ;;
  build)    "$PY" "$ROOT/scripts/build.py" --mode dev --python-version="${1:-3.11}" ;;
  dev)
    "$PY" "$ROOT/scripts/version_manager.py" increment --part dev_build >/dev/null
    "$PY" "$ROOT/scripts/build.py" --mode dev --python-version="${1:-3.11}"
    ;;
  inc)      "$PY" "$ROOT/scripts/version_manager.py" increment --part "${1:-dev_build}" ;;
  stable)   "$PY" "$ROOT/scripts/build.py" --mode stable ;;
  current)  "$PY" "$ROOT/scripts/version_manager.py" current ;;
  status)   "$PY" "$ROOT/scripts/version_manager.py" current; git -C "$ROOT" status --short ;;
  clean)    find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} + ; echo "cleaned __pycache__" ;;
  *)        sed -n '2,13p' "$ROOT/em.sh" ;;
esac
