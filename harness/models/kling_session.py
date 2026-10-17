"""Serialize credential refresh and submissions across image/video processes."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path

@contextmanager
def session_lock():
    path=Path(os.getenv('KLING_SESSION_LOCK','/tmp/visualagent-kling-session.lock'))
    with path.open('a', encoding='utf-8') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(handle, fcntl.LOCK_UN)
