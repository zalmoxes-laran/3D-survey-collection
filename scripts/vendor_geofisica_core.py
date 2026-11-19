# scripts/vendor_geofisica_core.py
"""The geophysics reading core, embedded from its one source (G-1, row G6).

The code that reads GPR / ERT / magnetometry stacks lives in em-profiles
(``profiles/geofisica/code/geofisica_core``), the geophysics package of the
extension system. 3DSC does not import it from an installed package (it
carries neither s3dgraphy nor the extension system): it embeds a copy in
``importer/_vendor/geofisica_core/``, taken from a commit fixed in
``scripts/geofisica_core.lock.json``. No line of the core is written in 3DSC:
the copy is made by this script, and ``tests/test_geofisica_vendor.py`` and
``scripts/build.py`` refuse a copy whose digest is not the lock's.

    python scripts/vendor_geofisica_core.py check
    python scripts/vendor_geofisica_core.py update [--em-profiles ../em-profiles] [--commit SHA]

``update`` copies the core at ``--commit`` (default: em-profiles' HEAD) with
``git archive`` — the committed tree, never the working files — writes
``SOURCE.json`` beside it (the core names that commit in its stamps) and the
lock. The tree digest: sha256 over the sorted ``<relative path>\\0<sha256 of
the file>\\n`` lines of the ``.py`` files.
"""
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "importer" / "_vendor" / "geofisica_core"
LOCK = ROOT / "scripts" / "geofisica_core.lock.json"
SOURCE_NAME = "SOURCE.json"
CORE_PATH = "profiles/geofisica/code/geofisica_core"
REPO_NAME = "em-profiles"


def tree_digest(folder):
    """sha256 of the ``.py`` files under ``folder`` (paths and bytes)."""
    folder = Path(folder)
    lines = []
    for p in sorted(folder.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(folder).as_posix()
        lines.append("%s\0%s\n" % (rel, hashlib.sha256(p.read_bytes()).hexdigest()))
    return "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if out.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), out.stderr.decode(errors="replace").strip()))
    return out.stdout if binary else out.stdout.decode().strip()


def export_core(em_profiles, commit, dest):
    """The core's ``.py`` files at ``commit`` of ``em_profiles`` into ``dest``."""
    data = _git(em_profiles, "archive", "--format=tar", commit, CORE_PATH, binary=True)
    dest = Path(dest)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            if not (m.isfile() and m.name.endswith(".py")):
                continue
            rel = Path(m.name).relative_to(CORE_PATH)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(m).read())
    return dest


def source_digest(em_profiles, commit):
    """The tree digest of the core at ``commit`` (nothing written here)."""
    with tempfile.TemporaryDirectory() as tmp:
        return tree_digest(export_core(em_profiles, commit, Path(tmp) / "core"))


def check(em_profiles=None):
    """Problems of the embedded copy (empty = the copy is the lock's)."""
    problems = []
    lock = read_json(LOCK)
    if not lock:
        return ["no lock: %s" % LOCK]
    if not VENDOR.is_dir():
        return ["no embedded core: %s (run: python scripts/vendor_geofisica_core.py update)" % VENDOR]
    got = tree_digest(VENDOR)
    if got != lock.get("tree_digest"):
        problems.append("the embedded core differs from the lock: %s, lock %s — edit the core in "
                        "em-profiles, then update" % (got, lock.get("tree_digest")))
    src = read_json(VENDOR / SOURCE_NAME) or {}
    for key in ("repo", "path", "commit", "tree_digest"):
        if src.get(key) != lock.get(key):
            problems.append("%s says %s=%r, the lock %r" % (SOURCE_NAME, key, src.get(key), lock.get(key)))
    if em_profiles and Path(em_profiles, ".git").exists():
        try:
            there = source_digest(em_profiles, lock["commit"])
        except RuntimeError as exc:
            problems.append("em-profiles has not the locked commit: %s" % exc)
        else:
            if there != lock["tree_digest"]:
                problems.append("the lock's digest is not em-profiles' core at %s: %s"
                                % (lock["commit"][:7], there))
    return problems


def update(em_profiles, commit=None):
    """Embed the core at ``commit`` (default HEAD) and write SOURCE.json and the lock."""
    em_profiles = Path(em_profiles).resolve()
    commit = _git(em_profiles, "rev-parse", (commit or "HEAD") + "^{commit}")
    with tempfile.TemporaryDirectory() as tmp:
        fresh = export_core(em_profiles, commit, Path(tmp) / "core")
        digest = tree_digest(fresh)
        if VENDOR.exists():
            shutil.rmtree(VENDOR)
        shutil.copytree(fresh, VENDOR)
    entry = {"repo": REPO_NAME, "path": CORE_PATH, "commit": commit, "tree_digest": digest}
    (VENDOR / SOURCE_NAME).write_text(json.dumps(dict(entry, note=(
        "A copy made by scripts/vendor_geofisica_core.py: do not edit; the one source is "
        "em-profiles.")), indent=2) + "\n", encoding="utf-8")
    LOCK.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="the embedded copy against the lock (and em-profiles if beside)")
    c.add_argument("--em-profiles", default=str(ROOT.parent / REPO_NAME))
    u = sub.add_parser("update", help="embed the core from em-profiles at a commit")
    u.add_argument("--em-profiles", default=str(ROOT.parent / REPO_NAME))
    u.add_argument("--commit", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "update":
        entry = update(args.em_profiles, args.commit)
        print("embedded geofisica_core @ %s (%s)" % (entry["commit"][:7], entry["tree_digest"]))
        return 0
    problems = check(args.em_profiles)
    for p in problems:
        print("ERROR", p)
    if not problems:
        print("geofisica_core: the embedded copy is the lock's")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
