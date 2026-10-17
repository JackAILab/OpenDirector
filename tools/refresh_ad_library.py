#!/usr/bin/env python3
"""Periodic bounded discovery plus media caching; no generation or user messaging."""
import json
import argparse
import fcntl
import os
import sqlite3
import sys
import time
from contextlib import ExitStack
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.collect_ad_references import run as collect
from tools.collect_cannes_corporate import run as collect_corporate
from tools.collect_aicp import run as collect_aicp
from tools.collect_lia import run as collect_lia
from tools.collect_adfest import run as collect_adfest
from tools.collect_adfest_showcase import run as collect_adfest_showcase
from tools.collect_cannes_lions import run as collect_cannes_lions
from tools.collect_nyf import run as collect_nyf
from tools.collect_effie import run as collect_effie
from tools.collect_webby import run as collect_webby
from tools.collect_kyoorius import run as collect_kyoorius
from tools.collect_kyoorius_current import run as collect_kyoorius_current
from tools.collect_kinsale import run as collect_kinsale
from tools.collect_berlin_commercial import run as collect_berlin_commercial
from tools.collect_cresta import run as collect_cresta
from tools.collect_ciclope import run as collect_ciclope
from tools.collect_british_arrows import run as collect_british_arrows
from tools.collect_mother_london import run as collect_mother_london
from tools.cache_ad_reference_media import run as cache
from harness.library import store

SOFT_FAILURE_CODES = frozenset({
    'source_unavailable', 'deferred_backup_in_progress', 'page_repeated',
    'storage_limit', 'disk_space_limit',
})


def has_hard_failure(results):
    """Return whether a source failure should make the whole timer red.

    Every result remains printed and persisted. Provider outages, duplicate
    pagination and a backup overlap are observable partial progress, but they
    must not make a healthy multi-source crawl look completely stopped.
    """
    return any(result.get('state') == 'failed' and
               result.get('error_code') not in SOFT_FAILURE_CODES
               for result in results.values())


def recover_stale_collection_runs(max_age=1800):
    """Close abandoned receipts left by a worker killed after opening a run.

    Age alone is not evidence that a worker stopped. Hold BOTH worker locks
    throughout reconciliation; collectors and media caching use separate
    locks but share this receipt table. Rows are display state, not leases.
    """
    cutoff = time.time() - max_age
    try:
        store.ROOT.mkdir(parents=True, exist_ok=True)
        with ExitStack() as locks:
            for name in ('.collector.lock', '.media.lock'):
                handle = locks.enter_context((store.ROOT / name).open('a'))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with store.connection() as c:
                c.execute("""UPDATE collection_runs
                            SET finished=?, state='interrupted', error_code='stale_worker'
                            WHERE state='running' AND started < ?""", (time.time(), cutoff))
    except (OSError, sqlite3.Error):
        # Live worker, unavailable filesystem or busy database: leave every
        # receipt untouched. The next scheduled run can reconcile it.
        return False
    return True


def collect_sources(sources):
    """Run each source once; a failed source must not starve later sources."""
    results = {}
    for name, run in sources:
        try:
            result = run()
        except sqlite3.Error:
            result = {'state': 'failed', 'error_code': 'database_unavailable'}
        except Exception:
            # Exceptions may contain provider URLs or payloads. Only emit a
            # bounded error code; never retry the source in this rotation.
            result = {'state': 'failed', 'error_code': 'collector_error'}
        results[name] = result
        print(json.dumps({name: result}), flush=True)
    return results

def run(*, metadata_only=False):
    # Award metadata may be collected while a long media snapshot uploads;
    # the next backup validates copied SQLite integrity/counts before publish
    # and includes rows that were committed before that copy began.
    os.environ.setdefault('AD_LIBRARY_METADATA_OVERLAP', '1')
    try:
        ciclope_batches = int(os.getenv('AD_LIBRARY_CICLOPE_BATCHES', '1'))
    except ValueError:
        ciclope_batches = 1
    if not 1 <= ciclope_batches <= 32:
        ciclope_batches = 1
    try:
        berlin_batches = int(os.getenv('AD_LIBRARY_BERLIN_BATCHES', '1'))
    except ValueError:
        berlin_batches = 1
    if not 1 <= berlin_batches <= 32:
        berlin_batches = 1
    try:
        ciclope_year = int(os.getenv('AD_LIBRARY_CICLOPE_YEAR', ''))
    except ValueError:
        ciclope_year = None
    def collect_ciclope_rotation():
        if ciclope_year is None:
            # The runner chooses one rotating year at entry and keeps it for
            # the whole bounded burst, even across a clock rotation boundary.
            return collect_ciclope(batches=ciclope_batches) if ciclope_batches > 1 else collect_ciclope()
        if ciclope_batches == 1:
            return collect_ciclope(year=ciclope_year)
        return collect_ciclope(year=ciclope_year, batches=ciclope_batches)
    def collect_berlin_rotation():
        if berlin_batches == 1:
            return collect_berlin_commercial()
        # The adapter freezes the rotating year for this burst and resumes
        # its durable cursor. A partial batch stops the burst, not the rest
        # of the source rotation. Report each finished batch while running.
        return collect_berlin_commercial(
            batches=berlin_batches,
            on_batch=lambda batch: print(json.dumps({'berlin_commercial_batch': batch}), flush=True))
    recover_stale_collection_runs()
    sources = (
        ('discovery', lambda: collect(12)), ('corporate', collect_corporate),
        ('aicp', collect_aicp), ('lia', collect_lia), ('adfest', collect_adfest),
        ('adfest_showcase', collect_adfest_showcase),
        ('cannes_lions', collect_cannes_lions), ('nyf', collect_nyf),
        ('effie', collect_effie), ('webby', collect_webby),
        ('kyoorius', collect_kyoorius), ('kyoorius_2026', collect_kyoorius_current), ('kinsale', collect_kinsale),
        ('berlin_commercial', collect_berlin_rotation), ('cresta', collect_cresta),
        ('ciclope', collect_ciclope_rotation),
        ('british_arrows', collect_british_arrows),
        ('mother_london', collect_mother_london),
    )
    if not metadata_only:
        sources += (('media', lambda: cache(12)),)
    return collect_sources(sources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-only', action='store_true',
                        help='Discover references; an independent worker caches media')
    args = parser.parse_args(argv)
    return 1 if has_hard_failure(run(metadata_only=args.metadata_only)) else 0


if __name__=='__main__':
    sys.exit(main())
