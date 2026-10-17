import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_camera_research_batch.py"


def test_dry_run_encodes_three_bounded_non_retrying_calls():
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "seg_000_075", "seg_075_150", "seg_150_225", "--dry-run"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    payload = json.loads(process.stdout)
    assert payload["limit"] == 3
    assert payload["automatic_retry"] is False
    assert [item["call_index"] for item in payload["calls"]] == [1, 2, 3]
    assert [item["command"][-1] for item in payload["calls"]] == ["0", "1", "2"]


def test_fourth_call_is_rejected_before_provider_execution():
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "seg_000_075", "seg_075_150", "seg_150_225", "seg_225_300", "--dry-run"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert process.returncode == 2
    assert "at most three" in process.stderr
