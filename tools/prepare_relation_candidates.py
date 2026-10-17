#!/usr/bin/env python3
"""Prepare private input variants and public metadata; selection never approves labels."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest
from harness.research.reference_ablation import project_reference


def active_pairs(config):
    if config.get('schema') == 'visualagent.relation-candidates.v1':
        return config['pairs']
    if config.get('schema') != 'visualagent.relation-candidates.v2':
        raise ValueError('unknown_candidate_schema')
    statuses = {'priority_for_independent_review', 'hold_source_relation_unestablished',
                'hold_target_mapping_unestablished'}
    if any(p.get('screening_status') not in statuses for p in config['pairs']):
        raise ValueError('unknown_screening_status')
    pairs = [p for p in config['pairs'] if p['screening_status']=='priority_for_independent_review']
    if not pairs:raise ValueError('no_active_candidate_pairs')
    return pairs


def build(references_path, candidates_path, out):
    source=json.loads(references_path.read_text())
    config=json.loads(candidates_path.read_text())
    refs={r['reference_id']:r for r in source['references']}
    pairs=active_pairs(config)
    ids=sorted({p[k] for p in pairs for k in ('candidate_reference','contrast_reference')})
    full=[project_reference(refs[i],'full') for i in ids]
    observations=[project_reference(refs[i],'observations') for i in ids]
    rows=[]
    for original, projected in zip(full,observations):
        ev=original['evidence']; interpretation=original.get('interpretation',{})
        rows.append({'reference_id':original['reference_id'], 'full_sha256':digest(original),
            'observations_sha256':digest(projected),'event_count':len(ev['events']),
            'last_event_end_seconds':max(e['end'] for e in ev['events']),
            'full_serialized_chars':len(json.dumps(original,ensure_ascii=False)),
            'observations_serialized_chars':len(json.dumps(projected,ensure_ascii=False)),
            'transfer_advice_count':len(interpretation.get('transfer_rules',[])),
            'independent_review':ev.get('independent_review'),
            'audio_semantics_reviewed':ev.get('audio_semantics_reviewed'),
            'full_motion_reviewed':ev.get('full_motion_reviewed')})
    report={'schema':'visualagent.relation-candidate-audit.v1',
        'source_sha256':digest(source),'candidate_config_sha256':digest(config),
        'all_source_references':len(refs),'active_candidate_pairs':len(pairs),
        'held_candidate_pairs':len(config['pairs'])-len(pairs),
        'source_references_with_transfer_advice':sum(bool(r.get('interpretation',{}).get('transfer_rules')) for r in refs.values()),
        'selected':rows,'gold_ready':False,'training_eligible':False,'calls':0,
        'limitations':['Candidate pairs are author hypotheses, not verified matched/mismatched labels.',
            'Event end is annotation coverage, not verified video duration.',
            'Serialized character counts are not tokenizer counts; input lengths are not matched.',
            'Observations are machine descriptions, not raw video or independent gold.',
            'Projection removes structured advice; semantic leakage within observation prose requires review.',
            'Full versus observations changes content and length together.']}
    out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
    for name, payload in [('full.json',{'references':full}),('observations.json',{'references':observations}),('audit.json',report)]:
        with (out/name).open('x') as f:json.dump(payload,f,ensure_ascii=False,indent=2);f.write('\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references',type=Path,required=True)
    p.add_argument('--candidates',type=Path,default=Path('data/research/relation_transfer_candidates_v1.json'))
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.references,a.candidates,a.out),ensure_ascii=False,indent=2))
