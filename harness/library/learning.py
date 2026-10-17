"""Evidence-backed strategy annotations; observed films are never agent trajectories."""
import json
from contextlib import closing, contextmanager
import sqlite3
import time
from harness.library import store
from harness.library.mechanisms import annotate

ROLES = ('original_ad','case_film','music_video','mixed','unknown')


def summarize_analysis_rows(rows):
    """Build privacy-safe coverage metrics from validated analysis rows.

    This is an offline descriptive summary. It does not turn coverage into a
    quality label and never includes source IDs or free-form analysis text.
    """
    from collections import Counter
    role=Counter();confidence=Counter();tags=Counter();scopes=Counter();audio=0;motion=0
    total=0
    for row in rows:
        data=row
        if hasattr(row,'keys') and 'data' in row.keys():
            data=row['data']
        elif isinstance(row,(tuple,list)) and row and isinstance(row[0],str):
            data=row[0]
        if isinstance(data,str):
            try:data=json.loads(data)
            except (TypeError,ValueError):continue
        if not isinstance(data,dict):continue
        total+=1;role[data.get('media_role','unknown')]+=1;confidence[data.get('confidence','low')]+=1
        scopes[data.get('evidence_scope','unknown')]+=1
        audio+=int(data.get('audio_semantics_reviewed') is True);motion+=int(data.get('full_motion_reviewed') is True)
        tags.update(annotate({'principle':data.get('principle'),'mechanism':data.get('mechanism'),
                              'transfer_rules':data.get('transfer_rules'),'avoid':data.get('avoid')}).get('mechanism_tags',[]))
    return {'analysis_count':total,'media_roles':dict(role),'confidence':dict(confidence),
            'evidence_scopes':dict(scopes),'mechanism_coverage':dict(tags),
            'audio_semantics_reviewed':audio,'full_motion_reviewed':motion,
            'method':'bounded heuristic coverage; not quality or conversion labels',
            'limitations':['sampled frames and source metadata only','coverage does not imply preference or causal effect']}


def analysis_summary():
    """Summarize only the latest analysis bound to each current media asset."""
    try:
        with sqlite3.connect(f'file:{store.ROOT / "library.sqlite3"}?mode=ro',uri=True,timeout=2) as library_db:
            current=dict(library_db.execute('SELECT item,sha256 FROM assets'))
        with connection() as c:
            rows=c.execute('SELECT item,media_sha256,version,data FROM analyses ORDER BY item,version DESC').fetchall()
        selected=[];seen=set()
        for row in rows:
            if row['item'] in seen or current.get(row['item'])!=row['media_sha256']:continue
            seen.add(row['item']);selected.append(row)
        return summarize_analysis_rows(selected)
    except (OSError,sqlite3.Error):
        return summarize_analysis_rows([])


def analysis_review_queue(limit=200):
    """List current analyses that still need semantic audio/motion review.

    This is an operator queue, not a quality ranking and not a training set.
    It is bound to the current asset digest so a replaced media file cannot
    inherit an old review task.
    """
    if type(limit) is not int or not 1 <= limit <= 5000:
        raise ValueError('Invalid review queue limit')
    try:
        with sqlite3.connect(f'file:{store.ROOT / "library.sqlite3"}?mode=ro',uri=True,timeout=2) as library_db:
            library_db.row_factory=sqlite3.Row
            assets={row['item']:dict(row) for row in library_db.execute(
                'SELECT item,sha256,duration,audio FROM assets')}
        with connection() as c:
            rows=c.execute('SELECT item,media_sha256,version,data FROM analyses ORDER BY item,version DESC').fetchall()
        latest={}
        for row in rows:
            if row['item'] in latest or assets.get(row['item'],{}).get('sha256')!=row['media_sha256']:
                continue
            latest[row['item']]=row
        queue=[]
        for item,asset in assets.items():
            row=latest.get(item)
            if row is None:
                queue.append({'item':item,'media_sha256':asset['sha256'],'analysis_version':None,
                              'missing':['analysis'],'priority':0,'priority_reason':'先补齐结构分析',
                              'training_eligible':False})
                continue
            data=json.loads(row['data']);missing=[]
            if data.get('audio_semantics_reviewed') is not True:missing.append('audio_semantics')
            if data.get('full_motion_reviewed') is not True:missing.append('full_motion')
            if missing:
                role=data.get('media_role','unknown');confidence=data.get('confidence','low');audio_present=bool(asset['audio'])
                if 'audio_semantics' in missing and 'full_motion' in missing:
                    priority=1 if audio_present and role=='original_ad' and confidence=='high' else 2
                elif 'audio_semantics' in missing:
                    priority=3 if audio_present else 4
                else:
                    priority=4
                reason={1:'高置信原广告且有音轨，适合先做完整复核',2:'已有分析和音轨，可先完成双重审阅',3:'已有音轨，优先补音频语义',4:'缺音轨或仅缺运动复核'}[priority]
                queue.append({'item':item,'media_sha256':asset['sha256'],'analysis_version':row['version'],
                              'duration':asset['duration'],'audio_present':audio_present,
                              'media_role':role,'confidence':confidence,'missing':missing,
                              'priority':priority,'priority_reason':reason,
                              'evidence_scope':data.get('evidence_scope','unknown'),
                              'training_eligible':False})
        queue.sort(key=lambda row:(row.get('priority',9), 0 if 15 <= float(row.get('duration',0) or 0) <= 30 else 1,
                                   row.get('item','')))
        analysis_pending=sum(1 for row in queue if 'analysis' in row.get('missing',[]))
        semantic_pending=len(queue)-analysis_pending
        return {'schema':'visualagent.ad-analysis-review-queue.v1','state':'ready','count':len(queue[:limit]),
                'total_pending':len(queue),'analysis_pending':analysis_pending,'semantic_review_pending':semantic_pending,
                'items':queue[:limit],
                'policy':'review tasks are bound to current media hashes; completion never grants training eligibility',
                'training_eligible':False}
    except (OSError,sqlite3.Error,ValueError,TypeError):
        return {'schema':'visualagent.ad-analysis-review-queue.v1','state':'unavailable','count':0,'total_pending':None,
                'analysis_pending':None,'semantic_review_pending':None,'items':[],'policy':'review queue unavailable; do not infer that no reviews are pending','training_eligible':False}


@contextmanager
def connection(timeout=30):
    directory=store.ROOT/'learning';directory.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(directory/'analyses.sqlite3',timeout=timeout);c.row_factory=sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS analyses(
        item TEXT NOT NULL, media_sha256 TEXT NOT NULL, version INTEGER NOT NULL,
        source_revision INTEGER NOT NULL, model TEXT NOT NULL, data TEXT NOT NULL,
        created REAL NOT NULL, PRIMARY KEY(item,media_sha256,version))''')
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback();raise
    finally:c.close()


def validate(result,duration,frame_times):
    if not isinstance(result,dict) or result.get('media_role') not in ROLES:
        raise ValueError('Invalid film role')
    def text(value,limit):
        if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError('Invalid analysis text')
        return value.strip()
    clean={'media_role':result['media_role'],'mechanism':text(result.get('mechanism'),1800),
           'principle':text(result.get('principle'),160),'confidence':result.get('confidence','low')}
    if clean['confidence'] not in ('low','medium','high'):raise ValueError('Invalid confidence')
    for field in ('grill_questions','transfer_rules','avoid'):
        values=result.get(field,[])
        if not isinstance(values,list) or not 1<=len(values)<=12:raise ValueError('Missing transfer guidance')
        clean[field]=[text(v,600) for v in values]
    beats=result.get('beats',[])
    if not isinstance(beats,list) or not 1<=len(beats)<=12:raise ValueError('Invalid evidence beats')
    clean['beats']=[]
    clean['validation_repairs']=[]
    for beat_index,b in enumerate(beats):
        start,end=b.get('start'),b.get('end');indices=b.get('frames',[])
        if type(start) not in (int,float) or type(end) not in (int,float) or start < 0 or end > duration+.1 or end < start:
            raise ValueError('Invalid time range')
        # A sampled-frame model may collapse a beat to one timestamp. Keep
        # the evidence bounded and auditable by extending it to the next
        # sampled frame instead of discarding an otherwise valid analysis.
        if end == start:
            following=[timecode for timecode in frame_times if timecode > start]
            repaired=min(following[0] if following else duration, duration+.1)
            if repaired <= start:
                raise ValueError('Invalid time range')
            clean['validation_repairs'].append({'kind':'zero_length_beat','beat':beat_index,
                                                'original_end':end,'repaired_end':repaired})
            end=repaired
        if not start < end:raise ValueError('Invalid time range')
        if not isinstance(indices,list) or not indices or any(type(i)is not int or not 0<=i<len(frame_times) for i in indices):raise ValueError('Missing frame evidence')
        if any(not start-.15<=frame_times[i]<=end+.15 for i in indices):raise ValueError('Frame outside claimed beat')
        clean['beats'].append({'start':start,'end':end,'observation':text(b.get('observation'),800),'purpose':text(b.get('purpose'),600),'frames':indices})
    clean.update(audio_semantics_reviewed=False,full_motion_reviewed=False,
        evidence_scope='timecoded_sampled_frames_and_source_metadata',
        training_eligible=False,human_review='pending',reconstructed_trajectory=False)
    return clean


def save_analysis(item,sha,source_revision,model,result,frame_times):
    record={**result,'frame_times':frame_times,'source_item':item,'media_sha256':sha}
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM analyses WHERE item=? AND media_sha256=?',(item,sha)).fetchone()[0]
        c.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)',(item,sha,version,source_revision,model,json.dumps(record,ensure_ascii=False),time.time()))
    return version


def get_analysis(item, *, require_item=False):
    # This is also an interactive read path. Do not initialize schemas, load
    # source JSON or read personal reviews just to locate one current film.
    with closing(sqlite3.connect(f'file:{store.ROOT / "library.sqlite3"}?mode=ro',
                                 uri=True, timeout=2)) as c:
        asset=c.execute('''SELECT a.sha256 FROM items i LEFT JOIN assets a ON a.item=i.id
                           WHERE i.id=?''',(item,)).fetchone()
    if asset is None:
        if require_item:raise KeyError(item)
        return None
    if not asset[0]:return None
    path=store.ROOT/'learning'/'analyses.sqlite3'
    if not path.is_file():return None
    with closing(sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=2)) as c:
        c.row_factory=sqlite3.Row
        row=c.execute('SELECT version,model,data FROM analyses WHERE item=? AND media_sha256=? ORDER BY version DESC LIMIT 1',(item,asset[0])).fetchone()
    return {**json.loads(row['data']),'analysis_version':row['version'],'model':row['model']} if row else None


def _scan_strategy_candidates(limit=3,exclude_item=None):
    """Offline scan used by the index builder, never by a planning request."""
    if type(limit) is not int or not 1<=limit<=24:raise ValueError('Invalid strategy limit')
    try:
        analysis_db=store.ROOT/'learning'/'analyses.sqlite3'
        library_db=store.ROOT/'library.sqlite3'
        if not analysis_db.is_file() or not library_db.is_file():return []
        with sqlite3.connect(f'file:{analysis_db}?mode=ro',uri=True,timeout=1) as c:
            c.row_factory=sqlite3.Row
            rows=c.execute('SELECT item,media_sha256,version,data FROM analyses ORDER BY item,version DESC').fetchall()
        with sqlite3.connect(f'file:{library_db}?mode=ro',uri=True,timeout=1) as c:
            current={row[0]:row[1] for row in c.execute('SELECT item,sha256 FROM assets')}
    except Exception:
        return []
    rank={'high':0,'medium':1,'low':2};role_rank={'original_ad':0,'mixed':1,'case_film':2,'music_video':3,'unknown':4};seen_items=set();seen_principles=set();pool=[]
    # Read the complete current, latest-analysis pool before applying the
    # online bound. Sorting and stopping at the first 24 items made the index
    # depend on opaque item IDs and systematically hid later mechanisms.
    for row in sorted(rows,key=lambda r:(role_rank.get(json.loads(r['data']).get('media_role','unknown'),4),rank.get(json.loads(r['data']).get('confidence','low'),3),r['item'],-r['version'])):
        if row['item']==exclude_item or row['item'] in seen_items or current.get(row['item'])!=row['media_sha256']:continue
        data=json.loads(row['data']);principle=data.get('principle','').strip()
        if not principle or principle in seen_principles:continue
        seen_items.add(row['item']);seen_principles.add(principle)
        pool.append(annotate({'source_item':row['item'],'analysis_version':row['version'],'confidence':data.get('confidence'),
            'media_role':data.get('media_role','unknown'),
            'principle':principle,'mechanism':data.get('mechanism','')[:650],
            'grill_questions':data.get('grill_questions',[])[:3],'transfer_rules':data.get('transfer_rules',[])[:3],
            'avoid':data.get('avoid',[])[:2],'evidence_scope':data.get('evidence_scope','unknown'),
            'beats':data.get('beats',[])[:8]}))
    if len(pool)<=limit:return pool

    # Greedy coverage: favour original ads and confidence, while rewarding a
    # candidate that adds an unseen mechanism tag. This keeps the index small
    # for online planning without making the shortlist an item-ID prefix.
    selected=[];remaining=list(pool);covered=set()
    while remaining and len(selected)<limit:
        def key(candidate):
            tags=set(candidate.get('mechanism_tags',[]))
            gain=len(tags-covered)
            role=role_rank.get(candidate.get('media_role','unknown'),4)
            confidence=rank.get(candidate.get('confidence','low'),3)
            return (gain, -role, -confidence)
        best=max(remaining,key=lambda c:(key(c),-pool.index(c)))
        selected.append(best);remaining.remove(best);covered.update(best.get('mechanism_tags',[]))
    return selected


def _relevance(candidate, query):
    """Small explainable lexical signal; it never changes evidence or ranking facts."""
    if not isinstance(query, str) or not query.strip():return 0
    # Transfer guidance can mention a new benefit absent from the original
    # film (e.g. battery life). Match it as guidance, never as source evidence.
    # Negative applicability notes must not boost a candidate's relevance.
    primary=' '.join(str(candidate.get(key,'')) for key in ('principle','mechanism')).lower()
    guidance=' '.join(str(candidate.get(key,'')) for key in ('transfer_rules','grill_questions')).lower()
    words={word for word in query.lower().split() if len(word)>=2}
    # Keep Chinese bigrams within words; joining words creates false matches.
    import re
    for run in re.findall(r'[\u4e00-\u9fff]+',query):
        words.update(run[i:i+2] for i in range(len(run)-1))
    return sum(2*primary.count(word)+guidance.count(word) for word in words)


def strategy_candidates(limit=3,exclude_item=None,query=None):
    """Read a bounded local index; missing/stale index fails open immediately."""
    if type(limit) is not int or not 1<=limit<=24:raise ValueError('Invalid strategy limit')
    import time
    from harness.library.index_paths import strategy_index_path
    path=strategy_index_path()
    try:
        data=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else []
        if not isinstance(data,dict) or data.get('schema')!='visualagent.strategy-index.v1':return []
        generated=data.get('generated_at')
        if not isinstance(generated,(int,float)) or time.time()-generated>7*86400:return []
        data=data.get('records',[])
        if not isinstance(data,list):return []
        candidates=[annotate(item) for item in data if isinstance(item,dict) and item.get('source_item')!=exclude_item]
        role_rank={'original_ad':0,'mixed':1,'case_film':2,'music_video':3,'unknown':4}
        candidates=sorted(enumerate(candidates),key=lambda pair:(role_rank.get(pair[1].get('media_role','unknown'),4),pair[0]))
        candidates=[item for _,item in candidates]
        if query:
            ranked=[(index,-_relevance(item,query),role_rank.get(item.get('media_role','unknown'),4),item) for index,item in enumerate(candidates)]
            ranked.sort(key=lambda pair:(pair[1],pair[2],pair[0]))
            candidates=[]
            for _,negative_score,_,item in ranked:
                score=-negative_score
                selected=dict(item,relevance_score=score,
                              selection_reason='与机制描述或迁移建议存在关键词匹配；不代表原片证明了新商品功效' if score else '未找到关键词匹配；作为备选机制，待导演判断')
                candidates.append(selected)
        return candidates[:limit]
    except (OSError,ValueError,TypeError):
        return []


def build_strategy_index(limit=24):
    """Build a safe strategy index offline after the library analysis batch."""
    return _scan_strategy_candidates(limit)
