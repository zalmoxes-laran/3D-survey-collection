# scripts/setup_development.py
# Download 3DSC runtime dependencies as wheels into wheels/cp<XY>/ (host
# platform), one-by-one with --no-deps. Mirrors EM-tools.
import os
import subprocess
import sys
import shutil
from pathlib import Path


def clean_wheels_directory(force=False, python_version='3.11'):
    script_dir = os.path.dirname(__file__)
    cp_tag = f"cp{python_version.replace('.', '')}"
    wheels_dir = os.path.join(script_dir, '..', 'wheels', cp_tag)

    if force and os.path.exists(wheels_dir):
        print(f"FORCE: cleaning wheels/{cp_tag} ...")
        shutil.rmtree(wheels_dir)

    os.makedirs(wheels_dir, exist_ok=True)
    return wheels_dir


def check_existing_wheels(wheels_dir):
    return list(Path(wheels_dir).glob("*.whl")) if os.path.exists(wheels_dir) else []


def check_and_clean_duplicates(wheels_dir, python_version='3.11'):
    from collections import defaultdict
    cp_tag = f"cp{python_version.replace('.', '')}"
    packages = defaultdict(list)
    for f in os.listdir(wheels_dir):
        if f.endswith('.whl'):
            packages[f.split('-')[0]].append(f)
    for package, versions in packages.items():
        if len(versions) > 1:
            target = [v for v in versions if cp_tag in v] or versions
            keep = target[0]
            for v in versions:
                if v != keep:
                    print(f"  removing duplicate: {v}")
                    os.remove(os.path.join(wheels_dir, v))


def download_wheels(force=False, python_version='3.11'):
    cp_tag = f"cp{python_version.replace('.', '')}"
    print(f"Target Python: {python_version} ({cp_tag})")

    script_dir = os.path.dirname(__file__)
    requirements_file = os.path.join(script_dir, 'requirements_wheels.txt')
    if not os.path.exists(requirements_file):
        print(f"ERROR: requirements file not found: {requirements_file}")
        return False

    wheels_dir = clean_wheels_directory(force, python_version)
    print(f"Wheels directory: {wheels_dir}")

    with open(requirements_file, 'r') as f:
        all_packages = [ln.strip() for ln in f if ln.strip() and not ln.startswith('#')]
    # numpy ships with Blender 4.x+ — never bundle it.
    packages = [p for p in all_packages if not p.lower().startswith('numpy')]

    if not force:
        existing = check_existing_wheels(wheels_dir)
        if existing and len(existing) >= len(packages):
            print(f"Sufficient wheels already present ({len(existing)}). Use --force to re-download.")
            return True

    print(f"Downloading {len(packages)} packages (numpy excluded):")
    success = 0
    for package in packages:
        print(f"  - {package}")
        cmd = [sys.executable, '-m', 'pip', 'download', package,
               '--only-binary=:all:', f'--python-version={python_version}',
               '--no-deps', '-d', wheels_dir]
        if subprocess.run(cmd).returncode == 0:
            success += 1
        else:
            name = package.split('==')[0].split('>=')[0].split('<')[0].strip()
            print(f"    retry without version constraint: {name}")
            cmd2 = [sys.executable, '-m', 'pip', 'download', name,
                    '--only-binary=:all:', f'--python-version={python_version}',
                    '--no-deps', '-d', wheels_dir]
            if subprocess.run(cmd2).returncode == 0:
                success += 1
            else:
                print(f"    FAILED: {name}")

    downloaded = list(Path(wheels_dir).glob("*.whl"))
    print(f"Downloaded {success}/{len(packages)}; wheels in dir: {len(downloaded)}")
    if downloaded:
        check_and_clean_duplicates(wheels_dir, python_version)
        return True
    print("ERROR: no wheels downloaded. Check connectivity / pip config.")
    return False


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Download 3DSC dependency wheels")
    parser.add_argument('--force', action='store_true', help='Force re-download')
    parser.add_argument('--python-version', default='3.11',
                        help='Target Python (3.11 for Blender 4.4/5.0, 3.13 for 5.1+)')
    args, _ = parser.parse_known_args()
    ok = download_wheels(args.force, args.python_version)
    if ok:
        print("Setup complete (numpy provided by Blender).")
    else:
        sys.exit(1)
