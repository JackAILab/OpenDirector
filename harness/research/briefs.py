"""Separate model-visible briefing from stipulated oracle facts and evaluation labels."""
from copy import deepcopy
import hashlib
import json

CONDITIONS = ('direct', 'fixed_playbook', 'caption_rag', 'mechanism_rag', 'evidence_constrained_mechanism')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate(dataset):
    if dataset.get('schema') != 'visualagent.synthetic-briefs.v1' or dataset.get('synthetic') is not True:
        raise ValueError('Only declared synthetic pilot cards are accepted')
    cards = dataset.get('cards')
    if not isinstance(cards, list) or not cards:
        raise ValueError('Missing cards')
    seen = set()
    for card in cards:
        for field in ('id', 'family_id', 'category', 'product', 'brief'):
            if not isinstance(card.get(field), str) or not card[field].strip():
                raise ValueError('Missing card identity or brief')
        if card['id'] in seen:
            raise ValueError('Duplicate card ID')
        seen.add(card['id'])
        facts = card.get('facts')
        if not isinstance(facts, dict) or not facts or any(not isinstance(v, str) or not v.strip() for v in facts.values()):
            raise ValueError('Invalid facts')
        hidden = card.get('hidden_fact_ids')
        if not isinstance(hidden, list) or not hidden or len(set(hidden)) != len(hidden) or any(k not in facts for k in hidden):
            raise ValueError('Invalid hidden fact IDs')
        oracle = card.get('oracle', {})
        if oracle.get('fact_id') not in hidden or not isinstance(oracle.get('question'), str):
            raise ValueError('Invalid oracle mapping')
        if card.get('evaluation_only', {}).get('capability_status') not in ('supported', 'unsupported', 'unknown'):
            raise ValueError('Invalid stipulated capability status')
    return cards


def visible_input(card, information):
    if information not in ('complete', 'underspecified'):
        raise ValueError('Invalid information condition')
    hidden = set(card['hidden_fact_ids']) if information == 'underspecified' else set()
    return {'brief': card['brief'], 'product': card['product'],
            'facts': {k:v for k,v in card['facts'].items() if k not in hidden},
            'duration_seconds': 15, 'synthetic_research_task': True}


class FactOracle:
    """Controlled fact-slot simulator, not a substitute for human interaction.

    Every request costs a question, including repeated or unknown slots. No semantic
    matching is done here; natural-language-to-slot mapping requires separate review.
    """
    def __init__(self, card, max_questions=3):
        if type(max_questions) is not int or max_questions < 0:
            raise ValueError('Invalid question budget')
        self._card = deepcopy(card)
        self._budget = max_questions
        self.used = 0

    def ask(self, fact_id):
        if self.used >= self._budget:
            raise ValueError('Question budget exhausted')
        self.used += 1
        if fact_id not in self._card['facts']:
            return {'fact_id': fact_id, 'answer': '该信息未提供。', 'state': 'not_provided'}
        return {'fact_id': fact_id, 'answer': self._card['facts'][fact_id], 'state': 'provided'}


def build_manifest(dataset):
    cards = validate(dataset)
    tasks = []
    for card in cards:
        for information in ('complete', 'underspecified'):
            visible = visible_input(card, information)
            for condition in CONDITIONS:
                identity = {'card_id': card['id'], 'information': information, 'condition': condition}
                tasks.append({'task_id': digest(identity)[:24], **identity,
                              'family_id': card['family_id'], 'partition': 'development_pilot',
                              'visible_input': deepcopy(visible), 'visible_input_sha256': digest(visible),
                              'comparison_key': digest({'card_id': card['id'], 'information': information})[:24],
                              'run_state': 'not_started'})
    return {'schema': 'visualagent.planning-manifest.v1', 'state': 'dry_run',
            'dataset_sha256': digest(dataset), 'task_count': len(tasks),
            'family_count': len({c['family_id'] for c in cards}),
            'model': None, 'reference_snapshot': None, 'prompt_version': None,
            'execution_ready': False, 'paid_calls': 0, 'tasks': tasks,
            'limitations': ['All cards are development pilot data, not a held-out benchmark.',
                           'Task metadata must not be forwarded to a model; use only visible_input.',
                           'Reference packages and model budgets are not yet frozen.',
                           'Underspecified no-question plans must be judged only on disclosed facts.']}
