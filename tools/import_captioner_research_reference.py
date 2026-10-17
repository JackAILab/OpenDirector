#!/usr/bin/env python3
"""Read one complete three-stream task; write an immutable research-only snapshot."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.captioner_bridge import convert
from harness.research.briefs import digest
from tools.run_paper_smoke import save


def build(run,out):
    ids=json.loads((run/'tasks.json').read_text())
    for tid in ids:
        directory=run/'tasks'/tid
        paths={role:directory/'observations'/f'{role}.json' for role in ('vision','audio','omni')}
        if not all(p.exists() for p in paths.values()):continue
        task=json.loads((directory/'task.json').read_text())
        observations={role:json.loads(p.read_text()) for role,p in paths.items()}
        reference=convert(task,observations,'C001')
        provenance={'task_sha256':digest(task),'observation_sha256':{k:digest(v) for k,v in observations.items()}}
        summary={'schema':'visualagent.captioner-import-summary.v1','selection':'first complete three-stream task in stored order; convenience interface probe',
            'reference_sha256':digest(reference),'provenance':provenance,
            'source_window':reference['evidence']['source_window'],
            'claims_by_role':reference['evidence']['available_observer_claim_counts'],
            'observer_warnings':{role:{'generation_truncated':v['generation_truncated'],'uncertainty_count':len(v['uncertainties'])}
                for role,v in reference['evidence']['observer_warnings'].items()},
            'media_bytes_rehashed':False,'semantic_review':'pending','training_eligible':False,
            'limitations':['Single clip, not a whole-ad interpretation.','No semantic or approval state promoted from source.',
                'No provider call or production database modification.','Concurrent source reads are not a globally atomic campaign snapshot.']}
        out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
        save(out/'references.json',{'schema':'visualagent.captioner-references.v1','references':[reference]})
        save(out/'summary.json',summary)
        return summary
    raise ValueError('No complete three-stream task found')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.run,a.out),ensure_ascii=False,indent=2))
