"""Resolve the newest private strategy snapshot without overwriting history."""
import os
from pathlib import Path

DEFAULT_DIR = Path('/var/lib/visualstation-local/creative/learning')
DEFAULT_NAME = 'strategy-candidates.json'


def strategy_index_path():
    explicit = os.getenv('AD_STRATEGY_INDEX')
    if explicit:
        return Path(explicit)
    candidates = [path for path in DEFAULT_DIR.glob('strategy-candidates*.json')
                  if path.is_file() and not path.is_symlink() and path.stat().st_size <= 2_000_000]
    if not candidates:
        return DEFAULT_DIR / DEFAULT_NAME
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)
