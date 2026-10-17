import json
import types

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from harness.library import store
from harness.library.browse_groups import group_ids, options
from harness.studio.library_api import install


@pytest.mark.parametrize('category,expected', [
    ('TV/Cinema / Beauty', ('tv_cinema',)),
    ('AUDIO/RADIO / FILM / FILM CRAFT', ('film', 'sound', 'craft')),
    ('Branded Content & Entertainment / Entertainment: Music Videos', ('branded',)),
    ('Kyoorius · Film TV & Cinema > 15 to 30 Seconds', ('tv_cinema',)),
    ('Kyoorius · Film · Film Advertising · 15 to 30 Seconds', ('film',)),
    ('Kyoorius · Regional Film · Single', ('film',)),
    ('Kyoorius · Film Craft · Animation · Single', ('animation', 'craft')),
    ('Kyoorius · Film Craft · Sound Design / SFX · Single', ('sound', 'craft')),
    ('Kyoorius · Film Craft · Use Of Adapted Or Existing / Licensed Music · Single', ('sound', 'craft')),
    ('Kyoorius · Film Craft · Use Of Original Music or Compositions · Single', ('sound', 'craft')),
    ('Kyoorius · Film Craft · Cinematography · Single', ('craft',)),
    ('Kyoorius · Film · Other Screens & Events · Series', ('film',)),
    ('Kyoorius · Unknown · Animation', ('unconfirmed',)),
    ('CICLOPE · Animation', ('animation',)),
    ('Berlin Commercial · COMMERCIALS AND BRANDED CONTENT - LONG', ('film', 'branded')),
    ('Cresta · 16: Film Craft', ('craft',)),
    ('Music Video / Cinematography', ('sound',)),
    ('B23 Product and Launch Videos', ('product',)),
    ('Brand name containing Film Craft', ('unconfirmed',)),
    ('CICLOPE · Special Section', ('unconfirmed',)),
    ('', ('unconfirmed',)),
])
def test_recorded_medium_boundaries_and_ambiguous_categories(category, expected):
    assert group_ids(category) == expected


def test_group_filter_composes_before_dedup_and_preserves_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    categories = ['TV & Cinema / Automotive', 'Online Film / Automotive',
                  '电视/点播广告', 'FILM / FILM CRAFT', '']
    ids = []
    for n, category in enumerate(categories):
        identity, _ = store.ingest({'source_url': f'https://example.org/{n}',
            'title': '电视广告标题不作为分类依据', 'ad_type': category, 'industry': '汽车出行',
            'quality_evidence': [{'kind': 'official', 'text': category or '类别尚待核实'}]})
        ids.append(identity)
        with store.connection() as db:
            db.execute('UPDATE items SET created=? WHERE id=?', (n, identity))
            db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                       (identity, f'assets/{identity}/film.mp4', 'a'*64 if n<2 else str(n)*64,
                        100, 20+n*20, 1, 1280, 720, 0))
    store.review_item(ids[0], 1, 0, 'selected', {'craft': 5}, ['私有标签'], '个人选择')
    with store.connection() as db:
        before = {table: [tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in ('items', 'reviews')}
    app = FastAPI()
    def gate(request):
        if request.cookies.get('access') != 'yes': raise HTTPException(403)
    install(types.SimpleNamespace(app=app, require_site_access=gate,
        require_session=lambda token: {'id': 1 if token == 'Bearer one' else 2}))
    with TestClient(app) as client:
        url = '/creative/api/library'
        assert client.get(url, params={'ad_group': 'tv_cinema'}).status_code == 403
        client.cookies.set('access', 'yes')
        result = client.get(url, params={'ad_group': 'tv_cinema', 'unique_media': True}).json()
        assert {item['id'] for item in result['items']} == {ids[0], ids[2]}
        assert result['total'] == 2
        # The newer online entry sharing the file does not hide its TV source.
        first = next(i for i in result['items'] if i['id'] == ids[0])
        assert first['ad_type'] == categories[0]
        assert first['quality_evidence'][0]['text'] == categories[0]
        assert first['ad_groups'] == [{'id': 'tv_cinema', 'label': '电视与影院'}]
        assert {f['id'] for f in result['facets']['ad_groups']} == {'tv_cinema', 'online_social', 'film', 'craft', 'unconfirmed'}
        assert client.get(url, params={'ad_group': 'tv_cinema', 'duration_band': 'short', 'local_only': True}).json()['total'] == 1
        assert client.get(url, params={'ad_group': 'tv_cinema', 'industry': '其他'}).json()['total'] == 0
        assert client.get(url, params={'ad_group': 'tv_cinema', 'ad_type': categories[1]}).json()['total'] == 0
        for token, total in [('one', 1), ('two', 0)]:
            result = client.get(url, params={'ad_group': 'tv_cinema', 'state': 'selected'}, headers={'Authorization': 'Bearer '+token}).json()
            assert result['total'] == total
        pages = [client.get(url, params={'ad_group': 'tv_cinema', 'limit': 1, 'offset': offset}).json() for offset in (0, 1)]
        assert {p['items'][0]['id'] for p in pages} == {ids[0], ids[2]}
        assert all(p['total'] == 2 for p in pages)
        assert client.get(url, params={'ad_group': 'unconfirmed'}).json()['items'][0]['id'] == ids[4]
        assert client.get(url, params={'ad_group': 'invalid'}).status_code == 422
        assert client.get(url, params={'ad_group': 'sound'}).json()['total'] == 0
        assert client.get(url, params={'ad_type': categories[1]}).json()['total'] == 1
    with store.connection() as db:
        assert before == {table: [tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in before}
        assert all(json.loads(r[0])['training_eligible'] is False for r in db.execute('SELECT data FROM items'))


def test_empty_library_has_no_synthetic_group(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    assert store.list_items(0)['facets']['ad_groups'] == []
    assert options(['Unknown category']) == [{'id': 'unconfirmed', 'label': '类别待确认'}]
def test_explicit_non_ad_gate_does_not_exclude_advertising_sound_or_unknown_craft():
    from harness.library.browse_groups import is_explicit_non_ad
    for value in ('Berlin Commercial · MUSIC VIDEOS / CRAFT: IDEA',
                  'Berlin Commercial · Music Video',
                  ' Berlin Commercial  ·  Personal Work / Craft: Direction '):
        assert is_explicit_non_ad(value)
    for value in ('Berlin Commercial · Commercial Work / Craft: Use of Sound & Music',
                  'Berlin Commercial · Craft: Idea', 'Music & Sound / TV & Cinema',
                  '音乐影像参考', 'Artist - music video', '', None):
        assert not is_explicit_non_ad(value)
