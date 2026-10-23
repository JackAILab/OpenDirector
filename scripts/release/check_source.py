"""Enforce the public-source/private-assets boundary on Git-tracked files."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 2 * 1024 * 1024
# Required for first-boot Chinese UI; licensed separately, under GitHub size limits.
EXCEPTIONS = {'tools/asset_studio/public/fonts/studio-chinese.woff2': 6 * 1024 * 1024}
HEAVY = {'.mp4', '.mov', '.webm', '.wav', '.mp3', '.m4a', '.sqlite', '.sqlite3',
         '.db', '.pt', '.pth', '.safetensors', '.ckpt', '.zip', '.gz', '.tar', '.ttf'}
PRIVATE_DIRS = {'secrets', 'outputs', 'node_modules', '__pycache__', '.venv'}
PATTERNS = [r'ms-[a-f0-9]{8}-[a-f0-9-]{27,}', r'gh[pousr]_[A-Za-z0-9]{30,}',
            r'github_pat_[A-Za-z0-9_]{30,}', r'sk-[A-Za-z0-9_-]{28,}',
            r'BEGIN (?:RSA |OPENSSH )?PRIVATE KEY']


def main():
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    errors = []
    total = 0
    for name in filter(None, paths):
        path = ROOT / name
        if path.is_symlink():
            if not path.resolve().is_relative_to(ROOT):
                errors.append((name, 'symlink leaves source tree'))
            continue
        if not path.is_file():
            errors.append((name, 'tracked file missing'))
            continue
        size = path.stat().st_size
        total += size
        if PRIVATE_DIRS.intersection(Path(name).parts) or Path(name).name == '.env':
            errors.append((name, 'runtime/private directory'))
        if path.suffix.lower() in HEAVY or size > EXCEPTIONS.get(name, MAX_BYTES):
            errors.append((name, 'move heavy assets to ModelScope'))
        try:
            text = path.read_text()
        except UnicodeError:
            continue
        if any(re.search(pattern, text) for pattern in PATTERNS):
            errors.append((name, 'credential-shaped content'))
    for name, reason in errors:
        print(f'{name}: {reason}')  # Never print matching secret values.
    print(f'Tracked source: {total / 1024 / 1024:.1f} MiB; violations: {len(errors)}')
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
