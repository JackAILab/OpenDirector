#!/usr/bin/env python3
"""Freeze equal-information development references; never promote model analysis to gold."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library.store import ROOT
from tools.prepare_paper_reference_review import digest, read


def reference_input(selected, analysis):
    if digest(analysis) != selected['analysis_sha256']:
        raise ValueError('frozen_analysis_mismatch')
    if analysis.get('media_sha256') != selected['sha256']:
        raise ValueError('frozen_media_mismatch')
    events = []
    interpretations = []
    for index, beat in enumerate(analysis.get('beats', [])):
        event_id = f"{selected['review_id']}:E{index + 1:02d}"
        events.append({'event_id': event_id, 'start': beat['start'], 'end': beat['end'],
                       'visual_observation': beat['observation'],
                       'sampled_frame_indices': beat.get('frames', []),
                       'status': 'machine_observation_unverified'})
        interpretations.append({'event_id': event_id, 'narrative_function': beat.get('purpose', ''),
                                'status': 'machine_interpretation_not_observed_fact'})
    return {'reference_id': selected['review_id'],
            'evidence': {'events': events, 'scope': analysis.get('evidence_scope'),
                         'audio_semantics_reviewed': analysis.get('audio_semantics_reviewed') is True,
                         'full_motion_reviewed': analysis.get('full_motion_reviewed') is True,
                         'independent_review': 'pending'},
            'interpretation': {'event_functions': interpretations,
                               'principle': analysis.get('principle', ''),
                               'mechanism': analysis.get('mechanism', ''),
                               'transfer_rules': analysis.get('transfer_rules', []),
                               'contraindications': analysis.get('avoid', []),
                               'status': 'hypotheses_from_automatic_analysis'},
            'training_eligible': False}


def build(root, selection_path, out):
    selection = json.loads(selection_path.read_text())
    references = []
    with read(root / 'learning' / 'analyses.sqlite3') as c:
        for row in selection['selected']:
            found = c.execute('select data from analyses where item=? and media_sha256=? and version=?',
                              (row['item'], row['sha256'], row['analysis_version'])).fetchall()
            if len(found) != 1:
                raise ValueError('frozen_analysis_missing_or_ambiguous')
            references.append(reference_input(row, json.loads(found[0][0])))
    payload = {'schema': 'visualagent.equal-information-references.v1',
               'use': 'automatic_analysis_development_only', 'references': references}
    summary = {'schema': 'visualagent.reference-input-summary.v1',
               'selection_sha256': digest(selection), 'reference_input_sha256': digest(payload),
               'reference_count': len(references),
               'event_count': sum(len(r['evidence']['events']) for r in references),
               'audio_semantics_reviewed': sum(r['evidence']['audio_semantics_reviewed'] for r in references),
               'full_motion_reviewed': sum(r['evidence']['full_motion_reviewed'] for r in references),
               'gold_ready': False, 'training_eligible': False,
               'policy': 'Both conditions receive identical reference objects. Relation construction is method output, not extra gold input.',
               'limitations': ['Stored analysis hashes verified; media bytes not verified.',
                              'Source captions and mechanism interpretations remain independently unreviewed.',
                              'No retrieval experiment or causal effect identified by this package.']}
    out.mkdir(parents=True, exist_ok=False)
    out.chmod(0o700)
    for name, data in [('references.json', payload), ('summary.json', summary)]:
        with (out / name).open('x') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(build(args.root, args.selection, args.out), ensure_ascii=False, indent=2))
