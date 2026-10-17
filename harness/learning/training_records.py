"""Build private director record candidates; never approve or publish them."""
import hashlib
import hmac
import json
import re
import math

EMAIL=re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
URL=re.compile(r"https?://[^\s)]+",re.I)
PHONE=re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
CONTROL=re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def safe_text(value,limit=4000):
    """Keep creative language while removing common contact and URL identifiers."""
    text=CONTROL.sub("",str(value or ""))
    text=EMAIL.sub("[REDACTED_EMAIL]",text)
    text=URL.sub("[REDACTED_URL]",text)
    text=PHONE.sub("[REDACTED_PHONE]",text)
    return text[:limit]


def sanitize_plan(plan):
    """Whitelist plan fields; provider payloads, IDs, paths and references are omitted."""
    brief=plan.get('brief') or {}
    shots=[]
    for shot in plan.get('shots') or []:
        if not isinstance(shot,dict):continue
        item={}
        for key in ('start','duration'):
            value=shot.get(key)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):item[key]=value
        for key in ('prompt','audio_prompt','caption'):
            if shot.get(key) is not None:item[key]=safe_text(shot[key])
        shots.append(item)
    questions=[]
    for question in plan.get('questions') or []:
        if isinstance(question,dict):
            questions.append({key:safe_text(question[key],1200) for key in ('question','why') if question.get(key) is not None})
    decisions=[]
    for decision in plan.get('decisions') or []:
        if isinstance(decision,dict):
            # The live director schema calls the decision label ``title``;
            # accept the older ``decision`` spelling while keeping one stable
            # field in training records so the rationale is not detached from
            # the choice that produced it.
            label=decision.get('title',decision.get('decision'))
            item={}
            if label is not None:item['decision']=safe_text(label,1200)
            if decision.get('reason') is not None:item['reason']=safe_text(decision['reason'],1200)
            if item:decisions.append(item)
    strategies=[]
    for candidate in plan.get('strategy_candidates') or []:
        if not isinstance(candidate,dict):continue
        item={}
        for key,limit in (('confidence',16),('principle',240),('mechanism',1200),('evidence_scope',120),):
            if candidate.get(key) is not None:item[key]=safe_text(candidate[key],limit)
        if isinstance(candidate.get('relevance_score'), (int, float)) and not isinstance(candidate.get('relevance_score'), bool) and math.isfinite(candidate['relevance_score']):
            item['relevance_score']=candidate['relevance_score']
        if candidate.get('selection_reason') is not None:
            item['selection_reason']=safe_text(candidate['selection_reason'],120)
        tags=candidate.get('mechanism_tags')
        if isinstance(tags,list):
            item['mechanism_tags']=[safe_text(tag,48) for tag in tags[:5] if isinstance(tag,str)]
        for key,limit,count in (('grill_questions',600,3),('transfer_rules',700,3),('avoid',500,2)):
            values=candidate.get(key)
            if isinstance(values,list):item[key]=[safe_text(v,limit) for v in values[:count] if isinstance(v,str)]
        grammar=candidate.get('shooting_grammar')
        if isinstance(grammar,dict):
            windows=[]
            for window in grammar.get('windows',[])[:8]:
                if not isinstance(window,dict):continue
                start,end=window.get('start'),window.get('end')
                if type(start) not in (int,float) or type(end) not in (int,float) or not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end:continue
                windows.append({'start':start,'end':end,'role':safe_text(window.get('role'),32),
                                'purpose':safe_text(window.get('purpose'),260),
                                'observation':safe_text(window.get('observation'),420)})
            item['shooting_grammar']={'schema':'visualagent.sampled-shooting-grammar.v1',
                                      'evidence_type':'timecoded_sampled_windows','windows':windows,
                                      'warning':safe_text(grammar.get('warning'),240)}
        if item:strategies.append(item)
    selections=[]
    for choice in plan.get('strategy_selection') or []:
        if not isinstance(choice,dict) or type(choice.get('candidate_index')) is not int:continue
        selections.append({'candidate_index':choice['candidate_index'],
                           'reason':safe_text(choice.get('reason'),800)})
    return {'schema':'visualagent.sanitized-director-example.v1',
        'duration':plan.get('duration') if type(plan.get('duration')) in (int,float) and math.isfinite(plan['duration']) else None,
        'aspect':safe_text(plan.get('aspect'),32),
        'generation_mode':safe_text(plan.get('generation_mode'),32),
        'brief':{key:safe_text(brief[key]) for key in ('message','product','audience','claim') if brief.get(key) is not None},
        'shots':shots,'questions':questions,'decisions':decisions,'strategy_candidates':strategies[:3],
        'strategy_selection':selections[:3],
        'playbook_version':safe_text(plan.get('playbook_version'),80)}


def sanitize_episode(episode, revision):
    """Keep the ordered creation decisions without IDs, timestamps or payloads."""
    if not isinstance(episode, dict) or episode.get('chain_verified') is not True:
        raise ValueError('Episode integrity is required')
    selected=next((item for item in episode.get('revisions', [])
                   if item.get('revision') == revision), None)
    if not selected:
        raise ValueError('Episode revision is missing')
    events=[]
    for event in selected.get('events', []):
        stage=event.get('stage');code=event.get('code')
        if not isinstance(stage, str) or not isinstance(code, str):
            raise ValueError('Episode event is malformed')
        events.append({'stage':safe_text(stage,64),'code':safe_text(code,96),
                       'revision':revision})
    observations=[]
    for artifact in selected.get('artifacts', []):
        qa=artifact.get('qa') or {}
        safe_qa={}
        for key in ('technical','audio','semantic','human'):
            if key in qa and isinstance(qa[key], (bool, str)):
                safe_qa[key]=qa[key]
        for key in ('duration','width','height'):
            value=qa.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                safe_qa[key]=value
        observations.append({'qa':safe_qa,'training_eligible':False})
    feedback=[]
    for item in selected.get('feedback', []):
        if not isinstance(item, dict):
            continue
        clean={'decision':safe_text(item.get('decision'),16),
               'rating':item.get('rating') if type(item.get('rating')) is int and 1<=item['rating']<=5 else None,
               'strategy_indices':[i for i in item.get('strategy_indices',[]) if type(i) is int and 0<=i<3],
               'changed_dimensions':[safe_text(i,24) for i in item.get('changed_dimensions',[]) if isinstance(i,str)][:8],
               'note':safe_text(item.get('note'),500),'training_eligible':False}
        feedback.append(clean)
    return {'schema':'visualagent.sanitized-creation-trajectory.v1',
            'events':events,'artifact_observations':observations,
            'owner_feedback':feedback,
            'missing_evidence':sorted(set(str(v) for v in selected.get('missing_evidence', []))),
            'unrecorded_event_count':int(episode.get('unrecorded_event_count', 0)),
            'chain_verified':True,'training_eligible':False}


def build_record(sample_id,partition,family_id,plan,trajectory=None):
    if any(not re.fullmatch(r'[a-f0-9]{64}',value) for value in (sample_id,family_id)):
        raise ValueError('Anonymous digest bindings are required')
    if partition not in ('train','validation','test','quarantine'):
        raise ValueError('Invalid partition')
    clean=sanitize_plan(plan)
    payload={'schema':'visualagent.training-record-candidate.v1','sample_id':sample_id,
        'partition':partition,'family_id':family_id,'plan':clean,
        'provenance':{
            'plan':'actual_agent_plan_snapshot',
            'strategy_context':'external_reference_strategy_observation',
            'trajectory':'actual_agent_observed_events' if trajectory is not None else 'missing_until_runner_observation',
            'policy':'reference observations and user episodes must never be mixed as supervision',
        },
        'training_eligible':False,'public_release':False,
        'review_status':'pending_exact_content_review',
        'limitations':['Pattern redaction is incomplete; independent review of this exact candidate is required.',
                       'The trajectory is an allowlisted event summary, not original hidden reasoning.']}
    if trajectory is not None:
        payload['trajectory']=sanitize_episode(trajectory, plan.get('revision'))
    payload['record_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return payload


def prepare_candidate(project_id,owner,sample_id,partition,family_id):
    """Read an owner-scoped, consented, immutable current plan as a private draft."""
    import sqlite3
    from harness.studio import store
    from harness.learning import governance
    with store.connection() as connection:
        row=connection.execute('SELECT data FROM projects WHERE id=? AND owner=?',(project_id,owner)).fetchone()
    if not row:raise ValueError('Owned project not found')
    project=json.loads(row[0]);artifact=governance.current_artifact(project)
    if not artifact or not governance.status(project,owner,artifact)['training']:
        raise ValueError('Current artifact requires explicit training consent')
    with sqlite3.connect(store.DATA/'learning/episodes.sqlite3') as connection:
        row=connection.execute('SELECT digest,data FROM plans WHERE project=? AND owner=? AND revision=?',
                               (project_id,owner,project['revision'])).fetchone()
    if not row:raise ValueError('Immutable plan snapshot missing')
    if hashlib.sha256(row[1].encode()).hexdigest()!=row[0]:
        raise ValueError('Immutable plan snapshot integrity failed')
    snapshot=json.loads(row[1])
    if snapshot.get('id')!=project_id or snapshot.get('revision')!=project['revision']:
        raise ValueError('Plan snapshot binding failed')
    from harness.learning.episodes import inspect_episode
    episode=inspect_episode(project_id,owner)
    # This helper is also used for a private draft before the first runner
    # event. Queue collection remains strict because eligible records require
    # a complete observed episode.
    trajectory=episode if any(item.get('revision') == project['revision']
                              for item in episode.get('revisions', [])) else None
    candidate=build_record(sample_id,partition,family_id,snapshot,trajectory)
    candidate.pop('record_sha256')
    candidate.update(source_plan_sha256=row[0],artifact_sha256=artifact)
    candidate['record_sha256']=hashlib.sha256(json.dumps(candidate,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return candidate


def collect_candidates(manifest,salt_file):
    """Collect eligible plan snapshots into a private review queue.

    The returned objects intentionally remain ineligible. Exact-content review
    must happen after this transformation and before any training release.
    """
    import sqlite3
    from harness.studio import store
    salt_path=__import__('pathlib').Path(salt_file)
    if salt_path.is_symlink() or not salt_path.is_file() or salt_path.stat().st_mode & 0o077:
        raise ValueError('Invalid private pseudonymization key')
    eligible={r['sample_id']:r for r in manifest.get('records',[]) if r.get('training_eligible') is True}
    if not eligible:return []
    with sqlite3.connect(store.DATA/'projects.sqlite3') as c:
        projects=[(owner,json.loads(data)) for owner,data in c.execute('SELECT owner,data FROM projects')]
    plan_db=store.DATA/'learning/episodes.sqlite3'
    with sqlite3.connect(plan_db) as c:
        snapshots={(project,revision):(digest,json.loads(data)) for project,revision,digest,data in
                   c.execute('SELECT project,revision,digest,data FROM plans')}
    output=[];salt=salt_path.read_bytes();episode_cache={}
    for owner,project in projects:
        versions=[dict(project)]+[dict(project,**{k:v for k,v in item.items() if k in ('revision','artifact')}) for item in project.get('versions',[])]
        for version in versions:
            artifact=version.get('artifact','no-artifact')
            sample=hmac.new(salt,f"sample:{owner}:{project['id']}:{version['revision']}:{artifact}".encode(),hashlib.sha256).hexdigest()
            target=eligible.get(sample)
            if not target:continue
            snapshot=snapshots.get((project['id'],version['revision']))
            if not snapshot:raise ValueError('Eligible sample has no immutable plan snapshot')
            digest,plan=snapshot
            key=(project['id'],owner)
            if key not in episode_cache:
                from harness.learning.episodes import inspect_episode
                episode_cache[key]=inspect_episode(project['id'],owner)
            candidate=build_record(sample,target['partition'],target['family_id'],plan,episode_cache[key])
            candidate['creator_token']=hmac.new(salt,f"creator:{owner}".encode(),hashlib.sha256).hexdigest()
            candidate.update(source_plan_sha256=digest,review_status='pending_exact_content_review',
                             quality_mean_score=target.get('quality_mean_score'),
                             quality_min_score=target.get('quality_min_score'))
            candidate['record_sha256']=hashlib.sha256(json.dumps(candidate,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            output.append(candidate)
    if len(output)!=len(eligible):raise ValueError('Eligible manifest record could not be bound to a plan')
    return sorted(output,key=lambda r:r['sample_id'])
