"""Bounded provider progress observations; never transport provider payloads."""
from contextvars import ContextVar
from contextlib import contextmanager
import math

_observer=ContextVar('generation_progress_observer',default=None)

@contextmanager
def observing(callback):
    token=_observer.set(callback)
    try:yield
    finally:_observer.reset(token)

def report(phase,percent=None):
    if phase not in {'queued','preparing','submitting','generating','downloading'}:return
    observation={'phase':phase}
    if isinstance(percent,(int,float)) and not isinstance(percent,bool) and math.isfinite(percent) and 0<=percent<=100:
        observation['percent']=percent
    callback=_observer.get()
    if callback:
        try:callback(observation)
        except Exception:pass  # UI observation failures must not repeat or abort a paid request.
