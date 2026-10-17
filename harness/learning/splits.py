"""Private, persistent relationship graph for train/evaluation isolation."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path

PARTITIONS=('train','validation','test','quarantine')
VERSION='creation-family-splits-v1'


class Components:
    def __init__(self):self.parents={}
    def find(self,key):
        self.parents.setdefault(key,key)
        parent=self.parents[key]
        if parent!=key:self.parents[key]=self.find(parent)
        return self.parents[key]
    def link(self,a,b):
        a,b=self.find(a),self.find(b)
        if a!=b:self.parents[max(a,b)]=min(a,b)


def assign(records,registry:Path,seed:str=None,frozen:bool=False):
    """Retain old edges. Newly discovered cross-partition families are quarantined."""
    if not frozen and (not seed or len(seed)>200):raise ValueError('Invalid split seed')
    if len({r['sample_id'] for r in records})!=len(records):raise ValueError('Duplicate sample')
    registry=Path(registry)
    if not registry.exists():
        fd=os.open(registry,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    if registry.is_symlink() or registry.stat().st_mode & 0o077:raise ValueError('Registry must be private')
    c=sqlite3.connect(registry,timeout=5)
    try:
        with c:
            c.execute('CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS edges(a TEXT,b TEXT,PRIMARY KEY(a,b))')
            c.execute('CREATE TABLE IF NOT EXISTS assignments(token TEXT PRIMARY KEY,partition TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS history(seq INTEGER PRIMARY KEY AUTOINCREMENT,token TEXT,previous TEXT,current TEXT)')
            existing=dict(c.execute('SELECT key,value FROM config'))
            if frozen:
                if not existing or existing.get('version')!=VERSION or 'seed_sha256' not in existing:
                    raise ValueError('Frozen split registry is not initialized')
                expected=existing
            else:
                expected={'version':VERSION,'seed_sha256':hashlib.sha256(seed.encode()).hexdigest()}
            if existing and existing!=expected:raise ValueError('Cannot change a frozen split policy')
            for k,v in expected.items():c.execute('INSERT OR IGNORE INTO config VALUES(?,?)',(k,v))
            graph=Components();links=set()
            for r in records:
                tokens=sorted(set(r['link_tokens'])|{r['sample_id']})
                if any(not isinstance(t,str) or len(t)!=64 or any(ch not in '0123456789abcdef' for ch in t) for t in tokens):raise ValueError('Invalid relationship token')
                graph.find(tokens[0])
                links.update((tokens[0],t) for t in tokens[1:])
            for a,b in links:c.execute('INSERT OR IGNORE INTO edges VALUES(?,?)',(min(a,b),max(a,b)))
            for a,b in c.execute('SELECT a,b FROM edges'):graph.link(a,b)
            old=dict(c.execute('SELECT token,partition FROM assignments'))
            if any(p not in PARTITIONS for p in old.values()):raise ValueError('Invalid registry assignment')
            for token in old:graph.find(token)
            groups={}
            for token in graph.parents:groups.setdefault(graph.find(token),[]).append(token)
            decisions={}
            for root,tokens in groups.items():
                known={old[t] for t in tokens if t in old}
                if 'quarantine' in known or len(known)>1:partition='quarantine'
                elif known:partition=next(iter(known))
                elif frozen:
                    partition='quarantine'
                else:
                    bucket=int(hashlib.sha256((seed+':'+root).encode()).hexdigest(),16)%100
                    partition='train' if bucket<80 else 'validation' if bucket<90 else 'test'
                decisions[root]=partition
                for token in tokens:
                    prior=old.get(token)
                    if prior!=partition:
                        if prior and partition!='quarantine':raise ValueError('Cannot move an assigned family')
                        c.execute('INSERT INTO history(token,previous,current) VALUES(?,?,?)',(token,prior,partition))
                        c.execute('INSERT INTO assignments VALUES(?,?) ON CONFLICT(token) DO UPDATE SET partition=excluded.partition',(token,partition))
            result=[]
            for r in records:
                root=graph.find(r['sample_id'])
                result.append(dict(r,family_id=root,partition=decisions[root]))
            # Verify actual relations, rather than only counting groups.
            seen={}
            for r in result:
                for token in r['link_tokens']+[r['sample_id']]:
                    if token in seen and seen[token]!=r['partition']:raise ValueError('Split leakage detected')
                    seen[token]=r['partition']
            return {'policy':VERSION,'ratios':{'train':80,'validation':10,'test':10},'seed_sha256':expected['seed_sha256'],
                'relationships_checked':True,'records':sorted(result,key=lambda r:r['sample_id'])}
    finally:c.close()


def assign_frozen(records,registry:Path):
    """Reuse assignments without guessing an unavailable original seed."""
    return assign(records,registry,seed=None,frozen=True)
