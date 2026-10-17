import json
import pytest

from harness.library import store
from harness.library.taxonomy import classified_metadata
from harness.tools.reference_industries import enrich_industries


URL = 'https://2025.liaentries.com/winners/?id_entry=1'


@pytest.mark.parametrize('category,expected', [
    ('Foods', '食品饮料'), ('Beverages - Alcoholic', '食品饮料'),
    ('Banking & Finance Campaign', '金融保险'), ('AUTOMOTIVE', '汽车出行'),
    ('Technology & Tech Equipment', '科技互联网'), ('Retail', '零售电商'),
    ('Health Care Services', '医疗健康'), ('Fashion & Accessories', '奢侈时尚'),
    ('SPECIAL SECTION - FASHION & LUXURY', '奢侈时尚'), ('Beauty', '美妆个护'),
    ('Public Service/Charity/NGO Campaign', '公益与公共服务'),
    ('Travel & Tourism', '文旅休闲'), ('Home Products', '家居生活'),
])
def test_industry_uses_exact_source_category(category, expected):
    original = {'industry': '待分类', 'creative_structure': {'category': category}}
    enriched = classified_metadata(URL, original)
    assert enriched['industry'] == expected
    assert enriched['industry_evidence']['categories'] == [category]
    assert enriched['industry_evidence']['human_confirmed'] is False
    assert original['industry'] == '待分类'


@pytest.mark.parametrize('category', ['Gaming', 'Entertainment', 'Sports', 'Use of Music',
    'Corporate Purpose/Social Responsibility', 'Creative Use of Data', 'Automotive Cinematography', ''])
def test_craft_themes_and_titles_do_not_become_industry_evidence(category):
    original = {'industry': '待分类', 'brand': 'Automotive Foods',
                'title': 'Retail Beauty', 'creative_structure': {'category': category}}
    assert classified_metadata(URL, original) == original


def test_untrusted_hosts_known_labels_and_conflicting_categories_stay_unchanged():
    original = {'industry': '待分类', 'creative_structure': {'category': 'Foods'}}
    for url in ['https://example.org/', 'https://2025.liaentries.com.evil.test/',
                'https://awards.ciclopefestival.com.evil.test/']:
        assert classified_metadata(url, original) == original
    known = {**original, 'industry': '已确认分类'}
    assert classified_metadata(URL, known) == known
    conflict = {**original, 'tags': ['Film / Beauty']}
    assert classified_metadata('https://www.dandad.org/work/example', conflict) == conflict
    charity = {'industry': '待分类', 'tags': ['TV & Cinema Advertising / Public Service and Charities']}
    assert classified_metadata('https://www.dandad.org/work/example', charity)['industry'] == '公益与公共服务'


def test_ingestion_and_enrichment_preserve_review_history_and_repeated_collection(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    record = {'source_url': URL, 'title': 'Case', 'industry': '待分类',
              'creative_structure': {'category': 'Foods'}, 'quality_evidence': []}
    identity, _ = store.ingest(record)
    assert store.get_item(identity, 7)['industry'] == '食品饮料'
    # Model the existing library before classification was introduced.
    with store.connection() as db:
        payload = json.loads(db.execute('SELECT data FROM items WHERE id=?', (identity,)).fetchone()[0])
        payload.pop('industry_evidence')
        payload['industry'] = '待分类'
        db.execute('UPDATE items SET industry=?,data=? WHERE id=?',
                   ('待分类', json.dumps(payload), identity))
    store.review_item(identity, 7, 0, 'selected', {'craft': 5}, ['lighting'], 'my preference')
    before = store.get_item(identity, 7)
    assert enrich_industries()['changed'] == 1
    assert store.get_item(identity, 7) == before
    result = enrich_industries(apply=True)
    assert result['changed'] == 1 and result['industries'] == {'食品饮料': 1}
    after = store.get_item(identity, 7)
    assert after['revision'] == before['revision'] + 1
    assert after['review'] == before['review'] and after['training_eligible'] is False
    assert store.list_items(7, industry='食品饮料', state='selected')['total'] == 1
    assert store.list_items(8, industry='食品饮料', state='selected')['total'] == 0
    assert enrich_industries(apply=True)['changed'] == 0
    assert store.ingest(record) == (identity, False)
    assert store.get_item(identity, 7) == after


def test_enrichment_respects_collector_lock_and_read_limit(tmp_path, monkeypatch):
    import fcntl
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    for n in range(3):
        store.ingest({'source_url': URL + str(n), 'title': str(n)})
    with (tmp_path / '.collector.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert enrich_industries(apply=True)['state'] == 'already_running'
    assert enrich_industries(max_records=2)['state'] == 'limit_reached'
    assert enrich_industries(max_records=2)['scanned'] == 2
    assert enrich_industries()['scanned'] == 3
    with pytest.raises(ValueError):
        enrich_industries(max_records=True)
