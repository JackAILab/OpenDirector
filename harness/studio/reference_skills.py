"""Local, immutable-payload projection of published real-video creative skills."""
from copy import deepcopy
import json
from pathlib import Path

from harness.core.reference_skills import checksum
from harness.studio import store

_CACHE = {}


def catalog():
    path = store.DATA / 'reference_skills/catalog.json'
    try:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key not in _CACHE:
            if stat.st_size > 24 * 1024**2:
                raise ValueError('reference_skill_catalog_too_large')
            data = json.loads(path.read_text())
            payload = {k:v for k,v in data.items() if k != 'catalog_hash'}
            if (data.get('schema') != 'visualagent.reference-skill-catalog.v1'
                    or checksum(payload) != data.get('catalog_hash')
                    or not isinstance(data.get('skills'), list) or len(data['skills']) > 500
                    or len({s['id'] for s in data['skills']}) != len(data['skills'])):
                raise ValueError('invalid_reference_skill_catalog')
            for skill in data['skills']:
                if (skill.get('source') != 'reference' or skill.get('training_eligible') is not False
                        or checksum({k:v for k,v in skill.items() if k != 'content_hash'}) != skill.get('content_hash')):
                    raise ValueError('invalid_reference_skill_record')
            _CACHE.clear()
            _CACHE[key] = data
        return deepcopy(_CACHE[key])
    except FileNotFoundError:
        return {'skills': [], 'state': 'not_published'}


def summaries():
    """Keep home-page discovery light; fetch evidence only when a skill is opened."""
    result = []
    for skill in catalog()['skills']:
        row = {k:skill[k] for k in ('id','version','title','category','description','applies_to',
                                  'source','kind','duration','method_status','output','example_media',
                                  'reference_case','mechanism_tags','training_eligible','content_hash')}
        row.update(inputs=skill['inputs'][:2], steps=skill['steps'][:1], checks=[], detail_available=True)
        result.append(row)
    return result


def find(identity):
    return next((s for s in catalog()['skills'] if s['id'] == identity), None)
