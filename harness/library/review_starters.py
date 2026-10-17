"""Small editorial viewing exercises, checked against current library evidence.

These are comparison candidates, never personal selections or quality scores.
Only registered short videos with a matching latest original-ad analysis appear.
"""
import json
import re
import sqlite3

from harness.library import store


STARTERS = (
    ('0037fda2b973a46f9555f4c8', '商品推动情节',
     '如果拿掉商品，故事还能成立吗？它在哪个时刻改变了局面？'),
    ('00f452c473db962d0a300ee1', '把痛点拍成反转',
     '你何时看懂人物的困境？反转之后，商品的作用是否更清楚？'),
    ('01b6f57979b9370949cf5b4f', '让工艺成为主角',
     '材料与制作过程让你记住了什么？哪些画面真正支持商品价值？'),
    ('036bd357cfc401db11edc45c', '从沉浸走回现实',
     '故事世界与使用场景如何连接？揭示之后，你能复述一个主张吗？'),
    ('00c63b4961e2f89c42a53f20', '用情绪建立品牌',
     '人物与商品是什么关系？打动你的情绪，是否也让你记住品牌？'),
    ('03d45be0f1dc6288fa9c484d', '听声音如何叙事',
     '先完整听看一遍，再静音对照：声音改变了哪些理解与情绪？'),
)


def review_starters():
    """Bounded read-only projection; missing/stale evidence removes a card."""
    unavailable = {'state': 'unavailable', 'items': [], 'training_eligible': False}
    identities = [item for item, _, _ in STARTERS]
    if not identities:
        return {**unavailable, 'state': 'ready'}
    placeholders = ','.join('?' for _ in identities)
    try:
        with sqlite3.connect(f'file:{store.ROOT / "library.sqlite3"}?mode=ro',
                             uri=True, timeout=2) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('''SELECT i.id,i.title,i.brand,i.ad_type,i.data,
                a.sha256,a.duration,a.audio FROM items i JOIN assets a ON a.item=i.id
                WHERE i.id IN (''' + placeholders + ')', identities).fetchall()
        current = {row['id']: row for row in rows}
        latest = {}
        with sqlite3.connect(f'file:{store.ROOT / "learning" / "analyses.sqlite3"}?mode=ro',
                             uri=True, timeout=2) as db:
            for item, asset in current.items():
                # Read one latest version per current file, never the full history.
                row = db.execute('''SELECT data FROM analyses WHERE item=? AND media_sha256=?
                    ORDER BY version DESC LIMIT 1''', (item, asset['sha256'])).fetchone()
                # A malformed/reclassified new version must not revive old data.
                if row:
                    latest[item] = row[0]
        cards, seen_media = [], set()
        for item, focus, question in STARTERS:
            asset = current.get(item)
            if asset is None or item not in latest:
                continue
            if (not re.fullmatch(r'[0-9a-f]{64}', asset['sha256'] or '')
                    or not asset['audio'] or not 15 <= asset['duration'] <= 65
                    or asset['sha256'] in seen_media):
                continue
            try:
                analysis, metadata = json.loads(latest[item]), json.loads(asset['data'])
                if (not isinstance(analysis, dict) or not isinstance(metadata, dict)
                        or analysis.get('media_role') != 'original_ad'
                        or analysis.get('confidence') != 'high'):
                    continue
                evidence = metadata.get('quality_evidence', [])
                source = next((e['text'] for e in evidence if isinstance(e, dict)
                               and isinstance(e.get('text'), str) and e['text'].strip()), '')
                if not source:
                    continue
            except (TypeError, ValueError):
                continue
            seen_media.add(asset['sha256'])
            cards.append({'id': item, 'title': asset['title'], 'brand': asset['brand'],
                          'duration': asset['duration'], 'focus': focus, 'question': question,
                          'source_evidence': source[:500], 'training_eligible': False})
        return {'state': 'ready', 'items': cards, 'training_eligible': False}
    except (OSError, sqlite3.Error):
        return unavailable
