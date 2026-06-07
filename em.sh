#!/usr/bin/env bash
# 3D Survey Collection — developer CLI (mirrors the EM-tools workflow).
#
#   ./em.sh setup [3.11|3.13] [--force]   download dependency wheels (host)
#   ./em.sh manifest [3.11|3.13]          regenerate blender_manifest.toml
#   ./em.sh build [3.11|3.13]             build a dev .blext into ../3DSC_Releases
#   ./em.sh inc [dev_build|patch|minor|major]   bump version
#   ./em.sh stable                        build stable + git tag
#   ./em.sh current                       print current version
#   ./em.sh clean                         remove __pycache__ dirs
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
cmd="${1:-help}"
[ $# -gt 0 ] && shift

case "$cmd" in
  setup)
    pyver="3.11"; case "${1:-}" in 3.1*) pyver="$1"; shift;; esac
    "$PY" "$ROOT/scripts/setup_development.py" --python-version="$pyver" "$@"
    ;;
  manifest)
    pyver="${1:-3.11}"
    "$PY" "$ROOT/scripts/version_manager.py" update --python-version="$pyver"
    ;;
  build)
    pyver="${1:-3.11}"
    "$PY" "$ROOT/scripts/build.py" --mode dev --python-version="$pyver"
    ;;
  inc)
    "$PY" "$ROOT/scripts/version_manager.py" increment --part "${1:-dev_build}"
    ;;
  stable)
    "$PY" "$ROOT/scripts/build.py" --mode stable
    ;;
  current)
    "$PY" "$ROOT/scripts/version_manager.py" current
    ;;
  clean)
    find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
    echo "cleaned __pycache__"
    ;;
  *)
    sed -n '2,12p' "$ROOT/em.sh"
    ;;
esac
