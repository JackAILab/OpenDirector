"""Safe private preparation manifest. This is not a released training dataset."""
from collections import Counter
import hashlib
import hmac
import json
import re
import sqlite3
from pathlib import Path
from harness.studio import store
from harness.learning import governance,curation
from harness.learning.episodes import inspect_episode
from harness.learning.splits import assign,assign_frozen

HEX=re.compile(r'^[a-f0-9]{64}$')


def token(salt,kind,value):return hmac.new(salt,(kind+':'+str(value)).encode(),hashlib.sha256).hexdigest()


def digest_file(path,root,cache):
    path=path.resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():raise ValueError('Invalid owned artifact')
    stat=path.stat();key=(path,stat.st_size,stat.st_mtime_ns)
    if key not in cache:
        digest=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
        after=path.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Artifact changed during inventory')
        cache[key]=digest.hexdigest()
    return cache[key]



def _fingerprint(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink():return None
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def _logical_sqlite_fingerprint(path, queries):
    """Hash stable table content instead of SQLite journal/header bytes."""
    path=Path(path)
    if not path.is_file() or path.is_symlink():return None
    digest=hashlib.sha256()
    try:
        connection=sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=2)
        try:
            for label,query in queries:
                digest.update(label.encode());digest.update(b'\0')
                try:rows=connection.execute(query).fetchall()
                except sqlite3.Error:rows=[]
                digest.update(json.dumps(rows,ensure_ascii=False,separators=(',',':'),default=str).encode())
                digest.update(b'\0')
        finally:connection.close()
    except sqlite3.Error:return None
    return digest.hexdigest()


def input_fingerprints(library_root=None):
    from harness.library import store as library
    root=Path(library_root or library.ROOT)
    library_fingerprint=_logical_sqlite_fingerprint(root/'library.sqlite3',(
        ('items','SELECT id,source_url,title,brand,industry,ad_type,data,revision,created,updated FROM items ORDER BY id'),
        ('assets','SELECT item,path,sha256,bytes,duration,audio,width,height,created FROM assets ORDER BY item'),))
    analyses_fingerprint=_logical_sqlite_fingerprint(root/'learning'/'analyses.sqlite3',(
        ('analyses','SELECT item,media_sha256,version,source_revision,model,data FROM analyses ORDER BY item,media_sha256,version'),))
    # SQLite journal/header bytes can change when a reader opens the database;
    # hash logical rows so a read-only preparation is not falsely unstable.
    projects_fingerprint=_logical_sqlite_fingerprint(store.DATA/'projects.sqlite3',(
        ('projects','SELECT id,owner,data FROM projects ORDER BY id'),
        ('events','SELECT seq,project,time,stage,code,shot FROM events ORDER BY seq'),))
    episodes_fingerprint=_logical_sqlite_fingerprint(store.DATA/'learning/episodes.sqlite3',(
        ('plans','SELECT project,owner,revision,digest,data,created FROM plans ORDER BY project,revision'),
        ('transitions','SELECT project,owner,event_seq,revision,previous,digest,data,created FROM transitions ORDER BY project,event_seq'),
        ('series','SELECT id,owner,label,created FROM series ORDER BY id'),
        ('learning_controls','SELECT seq,project,owner,revision,kind,data,created FROM learning_controls ORDER BY seq'),
        ('quality_reviews','SELECT seq,project,owner,reviewer,revision,artifact,data,created FROM quality_reviews ORDER BY seq'),
        ('curation_reviews','SELECT seq,project,owner,reviewer,revision,artifact,data,created FROM curation_reviews ORDER BY seq'),
        ('learning_feedback','SELECT seq,project,owner,revision,plan_sha256,data,created FROM learning_feedback ORDER BY seq'),))
    return {'projects':projects_fingerprint,
        'episodes':episodes_fingerprint,
        'library':library_fingerprint,'library_analyses':analyses_fingerprint}


def strategy_fingerprints(library_root=None):
    """Fingerprint only the two inputs consumed by the strategy index.

    Strategy refreshes do not need private project or episode databases. On a
    shared filesystem those unrelated databases can be large enough to block a
    harmless reference refresh, so keeping this scope explicit makes the
    refresh both faster and easier to fail closed.
    """
    from harness.library import store as library
    root=Path(library_root or library.ROOT)
    def metadata(path):
        """Use a cheap snapshot marker; full logical hashing belongs to release prep."""
        try:
            stat=path.stat()
            if not path.is_file() or path.is_symlink():return None
            marker=f'{path}:{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}'
            return hashlib.sha256(marker.encode()).hexdigest()
        except OSError:return None
    return {'library':metadata(root/'library.sqlite3'),
            'library_analyses':metadata(root/'learning'/'analyses.sqlite3')}


def input_markers(library_root=None):
    """Cheap shared-storage change markers used by the read-only health page.

    These markers do not replace logical fingerprints for release preparation;
    they only avoid rescanning large SQLite tables when nothing changed.
    """
    from harness.library import store as library
    root=Path(library_root or library.ROOT)
    paths={'library':root/'library.sqlite3',
           'library_analyses':root/'learning'/'analyses.sqlite3',
           'projects':store.DATA/'projects.sqlite3',
           'episodes':store.DATA/'learning'/'episodes.sqlite3'}
    result={}
    for key,path in paths.items():
        try:
            stat=path.stat()
            result[key]=f'{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}'
        except OSError:
            result[key]=None
    return result

def prepare(salt:bytes,registry:Path,seed:str=None,reuse_frozen_split:bool=False):
    if len(salt)<32:raise ValueError('Use a private pseudonymization key of at least 32 bytes')
    # A preparation manifest must describe one coherent source snapshot. The
    # live reference library can be refreshed while this relatively expensive
    # inventory is running, so compare the source fingerprints before and after
    # the scan and fail closed if they changed.
    with store.connection() as c:
        projects=[(owner,json.loads(data)) for owner,data in c.execute('SELECT owner,data FROM projects ORDER BY id')]
    controls=governance.connection()
    try:
        family_history={}
        for pid,owner,data in controls.execute("SELECT project,owner,data FROM learning_controls WHERE kind='family'"):
            family_history.setdefault((pid,owner),set()).add(json.loads(data)['family_id'])
    finally:controls.close()
    from harness.library import store as library
    source_digests={}
    library_db=library.ROOT/'library.sqlite3'
    if library_db.is_file():
        source_db=sqlite3.connect(f'file:{library_db}?mode=ro',uri=True,timeout=5)
        try:source_digests=dict(source_db.execute('SELECT item,sha256 FROM assets'))
        finally:source_db.close()
    records=[];cache={};states=Counter();blockers=Counter();errors=Counter();tiers=Counter()
    try:
        from harness.library import learning as library_learning
        with library_learning.connection() as analysis_db:tiers['library_strategy_candidates']=analysis_db.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]
    except Exception:tiers['library_strategy_candidates']=0
    # The read-only connection above may create the analysis schema on a new
    # library root. Take the baseline after that initialization so the
    # preparation check only observes external changes.
    initial_inputs=input_fingerprints()
    for owner,p in projects:
        try:episode=inspect_episode(p['id'],owner)
        except (ValueError,sqlite3.Error):episode={'revisions':[]};errors['episode_integrity_failed']+=1
        by_revision={r['revision']:r for r in episode['revisions']}
        variants=[dict(p,is_current=True)]+[dict(p,**{k:v for k,v in v.items() if k in ('revision','artifact','reference','shots','qa','reviews')},is_current=False,state='completed') for v in p.get('versions',[])]
        for v in variants:
            revision=v['revision'];key=token(salt,'sample',f"{owner}:{p['id']}:{revision}:{v.get('artifact','no-artifact')}")
            links={token(salt,'project',f"{owner}:{p['id']}")};relation_types=Counter({'project':1})
            for family in family_history.get((p['id'],owner),set()):
                links.add(token(salt,'series',f'{owner}:{family}'));relation_types['series']+=1
            # Source lineage cannot be inferred from titles or new product claims.
            lineage=p.get('library_learning',{})
            source_sha=lineage.get('source_media_sha256') or lineage.get('media_sha256')
            if source_sha and HEX.fullmatch(source_sha):links.add(token(salt,'source_media',source_sha));relation_types['source_media']+=1
            reference_source=p.get('library_reference')
            source_item=lineage.get('source_item') or (reference_source if isinstance(reference_source,str) else (reference_source or {}).get('item'))
            if source_item:
                links.add(token(salt,'source_item',source_item));relation_types['source_item']+=1
                source_digest=source_digests.get(source_item)
                if source_digest and HEX.fullmatch(source_digest):links.add(token(salt,'source_media',source_digest));relation_types['source_media']+=1
            ref=v.get('reference') or {}
            if HEX.fullmatch(ref.get('sha256','')):links.add(token(salt,'reference_media',ref['sha256']));relation_types['reference_media']+=1
            graph=p.get('canvas',{});connected={e.get('source') for e in graph.get('edges',[])}
            for node in graph.get('nodes',[]):
                if node.get('id') not in connected:continue
                asset=p.get('canvas_assets',{}).get(node.get('asset'),{})
                sha=asset.get('sha256','')
                if HEX.fullmatch(sha):links.add(token(salt,'canvas_media',sha));relation_types['canvas_media']+=1
            missing=[];artifact=None
            if v.get('artifact'):
                try:artifact=digest_file(store.DATA/v['artifact'],store.DATA/'artifacts',cache)
                except (ValueError,OSError):missing.append('artifact_unavailable')
            else:missing.append('artifact_missing')
            if artifact:links.add(token(salt,'artifact_media',artifact));relation_types['artifact_media']+=1
            observed=by_revision.get(revision)
            if observed:
                missing.extend(observed['missing_evidence'])
                actual_observation=next((a for a in observed['artifacts'] if a['artifact_sha256']==artifact),None)
                if not actual_observation:missing.append('artifact_observation_binding')
            else:missing.append('prospective_episode_missing')
            if not any(r.get('revision')==revision and r.get('artifact_sha256')==artifact and r.get('decision')=='approved' for r in v.get('reviews',[])):
                missing.append('artifact_bound_human_approval')
            data_controls=governance.status({'id':p['id'],'revision':revision},owner,artifact)
            if not data_controls['training']:missing.append('training_consent')
            try:curation_receipt=curation.latest({'id':p['id'],'revision':revision},owner,artifact) if data_controls['training'] else None
            except ValueError:curation_receipt={'integrity_failed':True}
            if not curation_receipt:
                missing.extend(curation.GATES)
            else:
                missing.extend(g for g in curation.GATES
                               if curation_receipt.get('decisions',{}).get(g) is not True)
            if (data_controls.get('independent_quality') or {}).get('decision')!='passed':missing.append('independent_quality_review')
            if not data_controls['public_dataset']:
                missing.append('public_dataset_consent')
            missing=sorted(set(missing));states['current' if v['is_current'] else 'archived']+=1;blockers.update(missing)
            if artifact:tiers['artifact_reviewable']+=1
            if data_controls['training']:tiers['consented_for_training']+=1
            if (data_controls.get('independent_quality') or {}).get('decision')=='passed':tiers['independent_quality_passed']+=1
            if not missing:tiers['release_gate_complete']+=1
            quality_summary=data_controls.get('independent_quality') or {}
            records.append({'sample_id':key,'revision':revision,'current':v['is_current'],'state':v.get('state') if v.get('state') in ('intake','planning','planning_failed','ready','running','rendering','completed','paused','failed') else 'unknown',
                'link_tokens':sorted(links),'relationships':dict(relation_types),'artifact_present':bool(artifact),
                'training_consent':data_controls['training'],'public_dataset_consent':data_controls['public_dataset'],'curation':{g:bool(curation_receipt and curation_receipt.get('decisions',{}).get(g) is True) for g in curation.GATES},
                'quality_mean_score':quality_summary.get('mean_score'),'quality_min_score':quality_summary.get('min_score'),
                'missing_evidence':missing,'training_eligible':False})
    split=assign_frozen(records,registry) if reuse_frozen_split else assign(records,registry,seed)
    # Eligibility is computed only in this immutable preparation manifest. It
    # never mutates the user's project state or consent records.
    eligible=0
    for record in split['records']:
        record['training_eligible']=not record['missing_evidence'] and record['partition']!='quarantine'
        eligible+=int(record['training_eligible'])
    split['summary']={'projects':len(projects),'versions':len(records),'current_versions':states['current'],'archived_versions':states['archived'],
        'actual_artifacts':sum(r['artifact_present'] for r in records),'training_eligible':eligible,
        'release_ready':bool(split['records']) and eligible==len(split['records']),
        'blocker_counts':dict(blockers),'integrity_errors':dict(errors),'partition_counts':dict(Counter(r['partition'] for r in split['records'])),
        'families':len({r['family_id'] for r in split['records']}),'evidence_tiers':dict(tiers)}
    final_inputs=input_fingerprints()
    if final_inputs!=initial_inputs:
        changed=','.join(key for key in final_inputs if final_inputs.get(key)!=initial_inputs.get(key))
        raise ValueError('Learning inputs changed during preparation; retry after sources settle ('+changed+')')
    split.update(schema='visualagent.private-dataset-preparation.v1',content_exported=False,
        salt_sha256=hashlib.sha256(salt).hexdigest(),privacy_scope='private_metadata_only',
        input_markers=input_markers(),
        input_fingerprints=final_inputs,limitations=['近重复视频与语义相似尚未检测','未声明的跨系列商品/活动关系需人工补充','当前只有私有元数据，不含训练文本或媒体'])
    return split
