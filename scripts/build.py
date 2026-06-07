# scripts/build.py
# Build a 3D Survey Collection .blext package (mirrors EM-tools).
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path
from version_manager import VersionManager

# Items (by top-level name) excluded from the shipped package.
EXCLUDE_NAMES = {
    '.git', '.github', '.vscode', '.gitignore', '.DS_Store',
    '__pycache__', 'build', 'dist', 'scripts',
    'dev_utils', 'README_images', 'exporter_cesium',
    'blender_manifest_template.toml', 'version.json', '.zenodo.json',
    'em.sh', 'em.bat',
}
EXCLUDE_SUFFIXES = {'.blext', '.backup', '.pyc'}
# Patterns pruned from copied subdirectories.
DIR_IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '*.blext', 'dev_diag')

# Python version -> user-facing Blender compatibility tag (matches EM-tools).
# cp311 covers Blender 4.4–5.0, cp313 covers Blender 5.1+.
BLENDER_TAG_MAP = {'3.11': 'blender50', '3.13': 'blender51'}


def clean_build_directory(build_dir: Path):
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    print(f"Build directory ready: {build_dir}")


def copy_source_files(source_dir: Path, build_dir: Path):
    print(f"Copying source {source_dir} -> {build_dir}")
    for item in source_dir.iterdir():
        if item.name in EXCLUDE_NAMES or item.name.startswith('.'):
            continue
        if item.suffix in EXCLUDE_SUFFIXES:
            continue
        dest = build_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=DIR_IGNORE)
        else:
            shutil.copy2(item, dest)


def download_platform_wheels(platform: str, wheels_dir: Path, python_version: str = '3.11'):
    """Download per-platform wheels (used for production/CI cross-builds)."""
    platform_map = {
        'windows': 'win_amd64',
        'macos-intel': 'macosx_10_13_x86_64',
        'macos-arm': 'macosx_11_0_arm64',
        'linux': 'manylinux2014_x86_64',
    }
    cp_tag = f"cp{python_version.replace('.', '')}"
    pip_platform = platform_map.get(platform, 'win_amd64')
    requirements_file = Path(__file__).parent / 'requirements_wheels.txt'

    with open(requirements_file, 'r') as f:
        packages = [ln.strip() for ln in f if ln.strip() and not ln.startswith('#')]

    wheels_dir.mkdir(parents=True, exist_ok=True)
    for package in packages:
        cmd = [
            sys.executable, '-m', 'pip', 'download', package,
            '--only-binary=:all:', '--platform', pip_platform,
            '--python-version', python_version, '--implementation', 'cp',
            '--abi', cp_tag, '--no-deps', '-d', str(wheels_dir),
        ]
        if subprocess.run(cmd).returncode != 0:
            print(f"Warning: failed to download {package} for {platform} (py{python_version})")


def build_extension(mode: str = 'dev', platform: str = None, python_version: str = '3.11'):
    root_dir = Path(__file__).parent.parent
    build_dir = root_dir / "build"

    for old in root_dir.glob("*.blext"):
        old.unlink()

    vm = VersionManager(root_dir)
    if mode != 'dev':
        vm.set_mode(mode)
    version = vm.update_manifest(python_version)
    print(f"Building 3DSC v{version} ({mode}, py{python_version})")

    manifest_file = root_dir / "blender_manifest.toml"
    content = manifest_file.read_text() if manifest_file.exists() else ""
    if '{VERSION}' in content or 'id =' not in content:
        raise ValueError("blender_manifest.toml not generated correctly")

    clean_build_directory(build_dir)
    copy_source_files(root_dir, build_dir)

    wheels_dir = root_dir / "wheels"
    if not wheels_dir.exists() or not any(wheels_dir.rglob("*.whl")):
        print("WARNING: no wheels found. Run './em.sh setup <py>' first "
              "(extension will ship without bundled dependencies).")

    blender_tag = BLENDER_TAG_MAP.get(python_version, f"py{python_version.replace('.', '')}")
    if platform and mode != 'dev':
        package_name = f"dsc_tools-v{version}-{platform}-{blender_tag}.blext"
    else:
        package_name = f"dsc_tools-v{version}.blext"

    releases_dir = root_dir.parent / "3DSC_Releases"
    releases_dir.mkdir(exist_ok=True)
    package_path = releases_dir / package_name

    with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in build_dir.rglob('*'):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(build_dir))

    size_mb = package_path.stat().st_size / (1024 * 1024)
    with zipfile.ZipFile(package_path, 'r') as zf:
        names = zf.namelist()
        wheels_in_zip = [n for n in names if n.startswith('wheels/')]
        has_manifest = 'blender_manifest.toml' in names
    print(f"Built: {package_path} ({size_mb:.1f} MB)")
    print(f"   files: {len(names)}   wheels: {len(wheels_in_zip)}   manifest: {'OK' if has_manifest else 'MISSING'}")
    return package_path, version


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build 3D Survey Collection extension")
    parser.add_argument('--mode', choices=['dev', 'rc', 'stable'], default='dev')
    parser.add_argument('--increment', choices=['dev_build', 'patch', 'minor', 'major'])
    parser.add_argument('--platform', choices=['windows', 'macos-intel', 'macos-arm', 'linux'])
    parser.add_argument('--python-version', default='3.11',
                        help="Target Python version (3.11 for Blender 4.4/5.0, 3.13 for 5.1+)")
    args = parser.parse_args()

    if args.increment:
        VersionManager(Path(__file__).parent.parent).increment_version(args.increment)

    package_path, version = build_extension(args.mode, args.platform, args.python_version)

    if args.mode == 'stable' and not args.platform:
        tag = f"v{version}"
        subprocess.run(['git', 'tag', tag])
        print(f"Tagged {tag} (push with: git push origin --tags)")


if __name__ == "__main__":
    main()
