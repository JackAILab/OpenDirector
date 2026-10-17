"""Private immutable plan snapshots, separate from sanitized event trajectories."""
import hashlib
import json
import os
import sqlite3
import time
from harness.studio import store


def record_plan(project,owner):
    directory=store.DATA/'learning';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    payload={k:project.get(k) for k in ('id','revision','generation_mode','duration','aspect','model','brief','shots','questions','assumptions','decisions','strategy_candidates','strategy_selection','library_reference','library_learning','plan_evaluation')}
    payload['reference_id']=project.get('reference',{}).get('id') if project.get('reference') else None
    from harness.agents.creative_director import SYSTEM
    from harness.library.playbook import PLAYBOOK_VERSION
    payload['playbook_version']=PLAYBOOK_VERSION
    payload.update(provenance='actual_agent_plan_snapshot',director_model=os.getenv('CREATIVE_MODEL','unconfigured'),
        director_policy_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest(),
        training_eligible=False,privacy_review='pending',release_consent=False)
    data=json.dumps(payload,ensure_ascii=False,sort_keys=True)
    digest=hashlib.sha256(data.encode()).hexdigest()
    with sqlite3.connect(directory/'episodes.sqlite3',timeout=20) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS plans(project TEXT,owner INTEGER,revision INTEGER,digest TEXT,data TEXT,created REAL,PRIMARY KEY(project,revision))''')
        old=c.execute('SELECT digest FROM plans WHERE project=? AND revision=?',(project['id'],project['revision'])).fetchone()
        if old and old[0]!=digest:raise ValueError('Cannot overwrite an episode revision')
        c.execute('INSERT OR IGNORE INTO plans VALUES(?,?,?,?,?,?)',(project['id'],owner,project['revision'],digest,data,time.time()))
    return digest


def release_blockers(episode):
    """Fail closed: human approval of a film is distinct from permission to train."""
    gates=('technical_qa','independent_semantic_review','human_approval','training_consent','privacy_review','rights_review')
    blockers=[g for g in gates if episode.get('gates',{}).get(g) is not True]
    if episode.get('provenance')!='actual_agent_episode':blockers.append('actual_agent_provenance')
    if episode.get('reconstructed_trajectory'):blockers.append('reconstructed_trajectory')
    if not episode.get('artifact_sha256'):blockers.append('artifact_digest')
    if not episode.get('family_id'):blockers.append('split_family')
    return blockers


def _journal_connection():
    directory=store.DATA/'learning'
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    connection=sqlite3.connect(directory/'episodes.sqlite3',timeout=1)
    connection.execute("""CREATE TABLE IF NOT EXISTS transitions(
        project TEXT,owner INTEGER,event_seq INTEGER,revision INTEGER,
        previous TEXT,digest TEXT,data TEXT,created REAL,
        PRIMARY KEY(project,event_seq))""")
    return connection


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        allow_nan=False,separators=(',',':')).encode()).hexdigest()


def record_transition(project,owner,event_seq,stage,code):
    """Allowlisted, append-only observations; never raw messages/provider responses."""
    import re
    if not all(re.fullmatch(r'[a-z_]{1,64}',v) for v in (stage,code)):
        raise ValueError('Invalid transition code')
    revision=int(project['revision'])
    payload={'schema':'visualagent.creation-transition.v1','stage':stage,'code':code,
        'revision':revision,'plan_sha256':_hash({k:project.get(k) for k in
            ('brief','shots','questions','assumptions','decisions')}),
        'context_sha256':_hash({k:project.get(k) for k in ('messages','canvas','reference')}),
        'model_sha256':_hash({k:project.get(k) for k in ('provider','model')}),
        'run_sha256':_hash(project.get('run_id')) if project.get('run_id') else None,
        'job_sha256':_hash(project.get('film',{}).get('job_id')) if project.get('film',{}).get('job_id') else None,
        'generation_mode': 'single_native' if project.get('generation_mode')=='single_native' else 'other',
        'training_eligible':False}
    if code=='submit_requested' and project.get('generation_mode')=='single_native':
        from harness.tools.creative_video import film_prompt
        payload['prompt_sha256']=hashlib.sha256(film_prompt(project).encode()).hexdigest()
    data=json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False)
    c=_journal_connection()
    try:
        with c:
            c.execute('BEGIN IMMEDIATE')
            existing=c.execute('SELECT data,digest,owner FROM transitions WHERE project=? AND event_seq=?',
                (project['id'],event_seq)).fetchone()
            if existing:
                if existing[0]!=data or existing[2]!=owner:raise ValueError('Cannot overwrite transition')
                return existing[1]
            last=c.execute('SELECT event_seq,digest,owner FROM transitions WHERE project=? ORDER BY event_seq DESC LIMIT 1',
                (project['id'],)).fetchone()
            if last and (last[0]>=event_seq or last[2]!=owner):raise ValueError('Invalid transition lineage')
            previous=last[1] if last else ''
            digest=_hash({'previous':previous,'project':project['id'],'event_seq':event_seq,'revision':revision,'data':data})
            c.execute('INSERT INTO transitions VALUES(?,?,?,?,?,?,?,?)',
                (project['id'],owner,event_seq,revision,previous,digest,data,time.time()))
            return digest
    finally:c.close()


def record_artifact(project,owner,path):
    """Bind actual evaluator output to a file digest, without promoting eligibility."""
    import math
    path=path.resolve()
    if not path.is_file():raise ValueError('Missing artifact')
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    qa=project.get('qa',{})
    safe={'technical':'passed' if qa.get('technical')=='passed' else 'pending',
          'audio':qa.get('audio') is True,'semantic':'pending','human':'pending'}
    for key in ('duration','width','height'):
        value=qa.get(key)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):safe[key]=value
    payload={'schema':'visualagent.artifact-observation.v1','artifact_sha256':digest.hexdigest(),
        'bytes':path.stat().st_size,'qa':safe,'training_eligible':False}
    payload['observation_sha256']=_hash(payload)
    data=json.dumps(payload,sort_keys=True,allow_nan=False)
    c=_journal_connection()
    try:
        with c:
            c.execute("""CREATE TABLE IF NOT EXISTS artifacts(project TEXT,owner INTEGER,revision INTEGER,
                digest TEXT,data TEXT,created REAL,PRIMARY KEY(project,revision,digest))""")
            c.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?,?)',
                (project['id'],owner,project['revision'],digest.hexdigest(),data,time.time()))
    finally:c.close()
    return payload


def inspect_episode(project_id,owner):
    """Owner-scoped evidence report. Missing history stays missing; no backfill."""
    c=_journal_connection()
    try:
        rows=c.execute('SELECT event_seq,revision,previous,digest,data FROM transitions WHERE project=? AND owner=? ORDER BY event_seq',
            (project_id,owner)).fetchall()
        previous='';events=[]
        for seq,revision,link,digest,data in rows:
            expected=_hash({'previous':previous,'project':project_id,'event_seq':seq,'revision':revision,'data':data})
            if link!=previous or digest!=expected:raise ValueError('Transition integrity failed')
            events.append(dict(json.loads(data),event_seq=seq));previous=digest
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        artifacts=[dict(revision=r[0],**json.loads(r[1])) for r in c.execute(
            'SELECT revision,data FROM artifacts WHERE project=? AND owner=? ORDER BY created',(project_id,owner))] if 'artifacts' in tables else []
        for artifact in artifacts:
            checked={k:v for k,v in artifact.items() if k not in ('revision','observation_sha256')}
            if artifact.get('observation_sha256')!=_hash(checked):raise ValueError('Artifact observation integrity failed')
        unrecorded_events=[]
        event_db=store.DATA/'projects.sqlite3'
        if event_db.is_file():
            source=sqlite3.connect(f'file:{event_db}?mode=ro',uri=True,timeout=1)
            try:
                expected=source.execute('''SELECT e.seq FROM events e JOIN projects p ON e.project=p.id
                    WHERE p.id=? AND p.owner=? ORDER BY e.seq''',(project_id,owner)).fetchall()
                observed={e['event_seq'] for e in events}
                unrecorded_events=[seq for (seq,) in expected if seq not in observed]
            finally:source.close()
        revisions=[]
        required=('planning_started','plan_ready','submit_requested','generation_accepted','source_passed','technical_passed')
        for revision in sorted({e['revision'] for e in events}|{a['revision'] for a in artifacts}):
            selected=[e for e in events if e['revision']==revision];codes={e['code'] for e in selected}
            missing=[code for code in required if code not in codes]
            if unrecorded_events:missing.append('incomplete_capture_history')
            evidence=[a for a in artifacts if a['revision']==revision]
            if not evidence:missing.append('artifact_observation')
            elif not any(a['qa'].get('technical')=='passed' and a['qa'].get('audio') is True
                and a['qa'].get('duration',0)>=15 for a in evidence):missing.append('verified_audio_duration')
            indices=[next((i for i,e in enumerate(selected) if e['code']==code),-1) for code in required]
            if all(i>=0 for i in indices) and indices!=sorted(indices):missing.append('event_order')
            from harness.learning.governance import status as governance_status
            controls=[governance_status({'id':project_id,'revision':revision},owner,a['artifact_sha256']) for a in evidence]
            if not controls:controls=[governance_status({'id':project_id,'revision':revision},owner)]
            feedback_rows=[]
            if 'learning_feedback' in tables:
                # Verify each row while keeping only bounded, already-redacted fields.
                for seq, raw in c.execute('SELECT seq,data FROM learning_feedback WHERE project=? AND owner=? AND revision=? ORDER BY seq',
                                          (project_id,owner,revision)):
                    data=json.loads(raw)
                    checked={k:v for k,v in data.items() if k!='feedback_sha256'}
                    if data.get('feedback_sha256')!=_hash(checked):
                        raise ValueError('Feedback integrity failed')
                    feedback_rows.append(dict(data,feedback_id=seq))
            revisions.append({'revision':revision,'events':selected,'artifacts':evidence,'feedback':feedback_rows,'data_controls':controls,
                'missing_evidence':missing,'provenance':'actual_observed_creation_events',
                'training_eligible':False,'release_blockers':release_blockers({})})
        return {'project':project_id,'chain_verified':True,'unrecorded_event_count':len(unrecorded_events),'revisions':revisions,'training_eligible':False}
    finally:c.close()
