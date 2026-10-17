"""Scheduled archive bursts keep one year, bounded requests and source isolation."""
import pytest

from harness.tools import award_archive
from tools import collect_berlin_commercial as berlin
from tools import refresh_ad_library as refresh


@pytest.fixture
def rotation(monkeypatch):
    later = []
    for name in ('collect', 'collect_corporate', 'collect_aicp', 'collect_lia',
                 'collect_adfest', 'collect_adfest_showcase', 'collect_cannes_lions', 'collect_nyf',
                 'collect_effie', 'collect_webby', 'collect_kyoorius',
                 'collect_kyoorius_current', 'collect_kinsale', 'collect_cresta',
                 'collect_ciclope', 'collect_british_arrows', 'collect_mother_london', 'cache'):
        def unrelated(*args, _name=name, **kwargs):
            later.append(_name)
            return {'state': 'completed'}
        monkeypatch.setattr(refresh, name, unrelated)
    monkeypatch.setattr(refresh, 'recover_stale_collection_runs', lambda: True)
    monkeypatch.setattr(refresh, 'collect_berlin_commercial', berlin.run)
    return later


@pytest.mark.parametrize('stop,expected_batches', [('partial', 2), ('end', 2), ('budget', 4)])
def test_scheduled_burst_keeps_year_and_continues_other_sources(
        rotation, monkeypatch, capsys, stop, expected_batches):
    monkeypatch.setenv('AD_LIBRARY_BERLIN_BATCHES', '4')
    year_selections, calls = [], []

    def year(value):
        year_selections.append(value)
        # A second selection would move into another clock rotation slot.
        return 2026 if len(year_selections) == 1 else 2025

    def batch(adapter, source, key, selected_year, offset, request_delay):
        calls.append((selected_year, offset, request_delay))
        n = len(calls)
        partial, end = n == 2 and stop == 'partial', n == 2 and stop == 'end'
        start = 336 + (n - 1) * 12
        return {'state': 'partial' if partial else 'completed',
                'error_code': 'source_unavailable' if partial else '',
                'offset': start, 'next_offset': start if partial else 0 if end else start + 12,
                'discovered': 6 if partial else 12, 'inserted': 6 if partial else 12,
                'year_scan_complete': end}

    monkeypatch.setattr(berlin, '_year', year)
    monkeypatch.setattr(award_archive, 'collect_archive', batch)
    result = refresh.run(metadata_only=True)
    receipt = result['berlin_commercial']
    assert year_selections == [None]
    assert calls == [(2026, None, 10)] * expected_batches
    assert receipt['batches'] == expected_batches
    assert receipt['stop_reason'] == {'partial': 'partial', 'end': 'year_scan_complete',
                                      'budget': 'batch_limit'}[stop]
    assert receipt['inserted'] == (18 if stop == 'partial' else expected_batches * 12)
    assert capsys.readouterr().out.count('"berlin_commercial_batch"') == expected_batches
    assert rotation[-4:] == ['collect_cresta', 'collect_ciclope', 'collect_british_arrows',
                             'collect_mother_london']
    assert 'cache' not in rotation


@pytest.mark.parametrize('configured', [None, '0', '33', 'invalid'])
def test_invalid_or_unset_budget_does_not_expand_requests(rotation, monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv('AD_LIBRARY_BERLIN_BATCHES', raising=False)
    else:
        monkeypatch.setenv('AD_LIBRARY_BERLIN_BATCHES', configured)
    calls = []

    def batch(*args):
        calls.append(args)
        return {'state': 'completed', 'discovered': 12, 'inserted': 0}

    monkeypatch.setattr(berlin, 'collect_archive', batch)
    refresh.run(metadata_only=True)
    assert len(calls) == 1
    assert calls[0][-1] == 10
    assert rotation[-1] == 'collect_mother_london'
