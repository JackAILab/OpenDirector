import json
import subprocess
import sys


def test_manifest_parser_rejects_too_short_timeout(tmp_path):
    result = subprocess.run([
        sys.executable, 'tools/prepare_learning_manifest.py',
        '--salt-file', str(tmp_path / 'salt'), '--registry', str(tmp_path / 'registry'),
        '--reuse-frozen-split', '--timeout-seconds', '1', '--output', str(tmp_path / 'out.json'),
    ], capture_output=True, text=True)
    assert result.returncode != 0
    assert '--timeout-seconds must be at least 30' in result.stderr
