"""Consistent, non-overwriting snapshots and a remote readback/restore check."""
import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import threading
import secrets
import shutil
import sqlite3
import time
import fcntl
import re
import tempfile
import logging
import traceback
import os
import tarfile
from harness.library import store

logger = logging.getLogger(__name__)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def copy_checked(source, destination, expected=None):
    """Hash the copied stream once; remote readback independently verifies it."""
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.part')
    h=hashlib.sha256();size=0
    try:
        with Path(source).open('rb') as src, temporary.open('xb') as dst:
            for block in iter(lambda:src.read(1024*1024),b''):
                dst.write(block);h.update(block);size+=len(block)
        checksum=h.hexdigest()
        if expected is not None and checksum!=expected:
            raise RuntimeError('source_asset_checksum_failed')
        temporary.replace(destination)
        return {'sha256':checksum,'bytes':size}
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def copy_sqlite_snapshot(source, destination):
    """Copy a SQLite file while holding a read transaction on the source."""
    guard = sqlite3.connect(source, timeout=30)
    try:
        guard.execute('BEGIN')
        # Force SQLite to acquire the shared read lock before the external
        # sequential copy starts. Writers then wait until the bytes are fixed.
        guard.execute('SELECT name FROM sqlite_master').fetchall()
        return copy_checked(source, destination)
    finally:
        guard.rollback()
        guard.close()


def retain_verified():
    """Bound local copies; remote immutable snapshots and failed copies are retained."""
    with store.connection() as c:
        verified=[r[0] for r in c.execute("SELECT id FROM backups WHERE state='verified' ORDER BY created DESC")]
    for name,keep in (('snapshots',8),('restore_checks',2)):
        for identity in verified[keep:]:
            if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}',identity):continue
            folder=store.ROOT/name/identity
            try:
                if folder.is_dir() and not folder.is_symlink():shutil.rmtree(folder)
            except OSError:
                pass  # A cleanup failure must not relabel a verified remote snapshot.


def snapshot_learning(folder, legacy_loose=False, progress=None):
    """Freeze only the analysis snapshot and its cited evidence into a bundle."""
    source=store.ROOT/'learning/analyses.sqlite3'
    if not source.is_file():return 0,{}
    _report_backup_progress(progress,{'phase':'learning_database'})
    # All small-file writes happen on local disk. Only the completed bundle
    # is published to shared storage. Never recursively archive the live
    # learning directory: it also contains attempts and unreviewed payloads.
    with tempfile.TemporaryDirectory(prefix='visualagent-learning-snapshot-') as staging:
        stage=Path(staging)
        local=stage/'learning/analyses.sqlite3'
        local.parent.mkdir()
        # A sequential copy avoids the many random FUSE metadata reads caused
        # by sqlite3.Connection.backup on the shared disk. The copied file is
        # accepted only after SQLite integrity and row-count checks below;
        # anything inconsistent fails closed before a snapshot is published.
        copy_sqlite_snapshot(source, local)
        database=sqlite3.connect(local)
        try:
            if database.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise RuntimeError('learning_integrity_failed')
            rows=database.execute('SELECT item,media_sha256 FROM analyses').fetchall()
        finally:database.close()
        members={'learning/analyses.sqlite3':{'sha256':digest(local),'bytes':local.stat().st_size}}
        processed=0
        last_report=0
        def report(phase='learning_evidence',force=False):
            nonlocal last_report
            now=time.monotonic()
            if not force and now-last_report<5:
                return
            last_report=now
            _report_backup_progress(progress,{
                'phase':phase,'processed_analysis_versions':processed,
                'total_analysis_versions':len(rows),'copied_learning_files':len(members),
                'copied_learning_bytes':sum(meta['bytes'] for meta in members.values()),
            })
        report(force=True)
        evidence_root=(store.ROOT/'learning/evidence').resolve()
        for identity,sha in rows:
            if not re.fullmatch(r'[a-f0-9]{24}',identity):raise RuntimeError('invalid_learning_identity')
            directory=store.ROOT/'learning/evidence'/identity
            evidence=directory/'evidence.json'
            if directory.is_symlink() or not directory.resolve().is_relative_to(evidence_root):
                raise RuntimeError('invalid_learning_path')
            if evidence.is_symlink():raise RuntimeError('invalid_learning_path')
            if not evidence.is_file():raise RuntimeError('learning_evidence_missing')
            # Validate exactly the evidence.json bytes that enter the bundle.
            key=f'learning/evidence/{identity}/evidence.json'
            frozen=stage/key
            if key not in members:members[key]=copy_checked(evidence,frozen)
            details=json.loads(frozen.read_text())
            if details.get('media_sha256')!=sha:raise RuntimeError('learning_source_mismatch')
            for frame in details['frames']:
                name=frame['path']; relative=Path(name)
                if (relative.is_absolute() or '..' in relative.parts or len(relative.parts)!=1
                        or name!=relative.as_posix() or name=='evidence.json'):
                    raise RuntimeError('invalid_learning_path')
                asset=directory/relative
                if asset.is_symlink() or not asset.resolve().is_relative_to(directory.resolve()):
                    raise RuntimeError('invalid_learning_path')
                if not asset.is_file():raise RuntimeError('learning_evidence_missing')
                key=f'learning/evidence/{identity}/{name}'
                if key not in members:members[key]=copy_checked(asset,stage/key)
                report()
            processed+=1
            report()
        report(phase='learning_bundle',force=True)
        local_bundle=stage/'learning.bundle.tar'
        with tarfile.open(local_bundle,'w') as archive:
            for name in sorted(members):
                # TarFile.add resolves account/group names for every file.
                # Cluster NSS lookups can be slow or unavailable; portable
                # evidence needs only the frozen bytes and a safe file mode.
                member=tarfile.TarInfo(name)
                member.size=members[name]['bytes']
                member.mode=0o600
                member.mtime=0
                member.uid=member.gid=0
                member.uname=member.gname=''
                with (stage/name).open('rb') as content:
                    archive.addfile(member,content)
        # Full snapshots keep one direct analysis-database copy for older
        # manifest readers. Learning-only snapshots stay bundle-only so the
        # shared-disk backup path never publishes a loose learning directory.
        if legacy_loose:
            copy_checked(local,folder/'learning/analyses.sqlite3')
        copy_checked(local_bundle,folder/'learning.bundle.tar')
        report(phase='learning_snapshot_ready',force=True)
    return len(rows),members


def _report_backup_progress(progress, value):
    if progress is not None:
        try:
            progress(value)
        except Exception:
            pass  # Observation failures must not bypass the backup or its checks.


def check_snapshot_space(include_media=True, include_learning=True):
    """Reserve an estimate for both the snapshot and independent readback.

    This is a preflight, not a filesystem reservation: other shared-disk users
    can still consume space later, and any copy failure must fail the run.
    """
    metadata_bytes=(store.ROOT/'library.sqlite3').stat().st_size
    media_bytes=0
    if include_media:
        with store.connection() as c:
            media_bytes=store.registered_media_bytes(c)
    # Covers exports, posters and working files, plus learning evidence when
    # requested. Keep metadata-only snapshots possible on a nearly full disk.
    overhead=max(2*1024**3,media_bytes//5) if include_learning else 512*1024**2
    required=int(2*(metadata_bytes+media_bytes)+overhead)
    if shutil.disk_usage(store.ROOT).free < required:
        raise RuntimeError('backup_space_limit')
    return required


def snapshot_record_counts(db):
    """Count logical records in the frozen database, without reading private values."""
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    names = {'human_reviews': 'reviews', 'reference_skill_versions': 'reference_skill_versions',
             'reference_skill_releases': 'reference_skill_releases'}
    return {label: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] if table in tables else 0
            for label, table in names.items()}


def backup(transport, include_media=True, include_learning=True, readback_workers=1, progress=None):
    _check_readback_options(transport,readback_workers)
    store.ROOT.mkdir(parents=True,exist_ok=True)
    with (store.ROOT/'.backup.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'already_running'}
        identity=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+secrets.token_hex(4)
        summary={'schema':1,'snapshot':identity,'created':time.time(),
                 'scope':'full' if include_media and include_learning else ('metadata+learning' if include_learning else 'metadata'),
                 'contains_account_credentials':False,'training_eligible':False,
                 'media_complete':False,'learning_complete':False}
        # Register before copying: shared-disk preparation can take hours and
        # must remain visible even when no uploadable manifest exists yet.
        # Only the exclusive backup lock authorizes recovery of old receipts.
        with store.connection() as c:
            c.execute("UPDATE backups SET state='interrupted' WHERE state IN ('preparing','uploading','verifying')")
            c.execute('INSERT INTO backups(id,created,manifest,state) VALUES(?,?,?,?)',
                      (identity,summary['created'],json.dumps(summary),'preparing'))
        try:
            _report_backup_progress(progress,{'snapshot':identity,'state':'preparing','phase':'metadata'})
            check_snapshot_space(include_media,include_learning)
            folder=store.ROOT/'snapshots'/identity;folder.mkdir(parents=True)
            database=folder/'library.sqlite3'
            # Shared FUSE storage can leave sqlite3.Connection.backup waiting on
            # random page metadata for minutes. A sequential copy is both faster
            # and easier on the mount; integrity and row-count checks below fail
            # closed if the source changed during the copy.
            copy_sqlite_snapshot(store.ROOT/'library.sqlite3', database)
            with sqlite3.connect(database) as c:
                if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('restore_integrity_failed')
                count=c.execute('SELECT COUNT(*) FROM items').fetchone()[0]
                record_counts=snapshot_record_counts(c)
                # Reused source records share a file. Copy that pair once;
                # differing registered checksums at one path still undergo
                # separate verification and cannot silently be collapsed.
                assets=c.execute('SELECT DISTINCT path,sha256 FROM assets').fetchall()
                rows=c.execute('SELECT id,source_url,title,data FROM items ORDER BY id').fetchall()
                with (folder/'items.jsonl').open('w') as output:
                    for iid,url,title,data in rows:
                        asset=c.execute('SELECT path,sha256,bytes,duration,audio,width,height FROM assets WHERE item=?',(iid,)).fetchone()
                        item={'id':iid,'source_url':url,'title':title,**json.loads(data)}
                        if asset:item['asset']=dict(zip(('path','sha256','bytes','duration','audio','width','height'),asset))
                        output.write(json.dumps(item,ensure_ascii=False)+'\n')
                with (folder/'preferences.jsonl').open('w') as output:
                    for seq,item,reviewer,version,state,scores,tags,note,created in c.execute('SELECT * FROM reviews ORDER BY seq'):
                        output.write(json.dumps({'item':item,'reviewer':hashlib.sha256(('ad-library:'+str(reviewer)).encode()).hexdigest()[:16],'version':version,'state':state,'scores':json.loads(scores),'tags':json.loads(tags),'note':note,'created':created},ensure_ascii=False)+'\n')
            summary['items']=count
            summary['record_counts']=record_counts
            with store.connection() as c:
                c.execute('UPDATE backups SET manifest=? WHERE id=?',(json.dumps(summary),identity))
            _report_backup_progress(progress,{'snapshot':identity,'state':'preparing','phase':'assets','items':count})
            analysis_count,learning_members=snapshot_learning(
                folder,legacy_loose=bool(include_media),
                progress=lambda event:_report_backup_progress(progress,{
                    'snapshot':identity,'state':'preparing',**event})) if include_learning else (0,{})
            files={str(p.relative_to(folder)):{'sha256':digest(p),'bytes':p.stat().st_size} for p in folder.rglob('*') if p.is_file()}
            for relative,expected in assets if include_media else []:
                path=(store.ROOT/relative).resolve()
                if not path.is_relative_to((store.ROOT/'assets').resolve()) or path.suffix not in ('.mp4','.jpg','.webp'):
                    raise RuntimeError('invalid_asset_path')
                destination=folder/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                files[relative]=copy_checked(path,destination,expected)
                poster=path.parent/'poster.jpg'
                if poster.is_file():
                    poster_destination=destination.parent/'poster.jpg'
                    files[str(poster_destination.relative_to(folder))]=copy_checked(poster,poster_destination)
            manifest={'schema':1,'snapshot':identity,'created':time.time(),'items':count,'analyses':analysis_count,
                      'record_counts':record_counts,
                      'files':files,'contains_account_credentials':False,'training_eligible':False,
                      'scope':'full' if include_media and include_learning else ('metadata+learning' if include_learning else 'metadata'),
                      'media_complete':bool(include_media),'learning_complete':bool(include_learning)}
            if include_learning and learning_members:
                # Logical member metadata remains in files for older clients and
                # for human audit; the bytes themselves live in the single bundle.
                if include_media:
                    files.update(learning_members)
                manifest['learning_bundle']='learning.bundle.tar'
                manifest['learning_members']=learning_members
            (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
            with store.connection() as c:c.execute('UPDATE backups SET manifest=?,state=? WHERE id=?',(json.dumps(manifest),'uploading',identity))
            transport.upload(folder,identity)
            with store.connection() as c:c.execute('UPDATE backups SET state=? WHERE id=?',('verifying',identity))
            restore=store.ROOT/'restore_checks'/identity;restore.mkdir(parents=True)
            verify_files(transport,identity,manifest,restore,readback_workers=readback_workers,progress=progress)
            with store.connection() as c:c.execute('UPDATE backups SET state=?,remote_revision=? WHERE id=?',('verified','snapshots/'+identity,identity))
            # Shared storage cleanup can block for minutes on large historical
            # media snapshots. Keep verified snapshots by default; operators
            # may opt into bounded cleanup explicitly during a maintenance
            # window with AD_LIBRARY_CLEANUP=1.
            if os.getenv('AD_LIBRARY_CLEANUP') == '1':
                retain_verified()
            return {'snapshot':identity,'state':'verified','items':count,'verified_files':len(files)}
        except Exception as exc:
            with store.connection() as c:c.execute('UPDATE backups SET state=? WHERE id=?',('failed',identity))
            code=str(exc) if str(exc) in SAFE_ERRORS else 'backup_failed'
            # Keep diagnostics actionable without persisting provider payloads,
            # credentials, URLs, or personal data.
            logger.error('backup_failed snapshot=%s code=%s',identity,code)
            if code=='backup_space_limit':raise RuntimeError(code) from None
            raise RuntimeError('backup_failed; local_snapshot_preserved') from None


SAFE_ERRORS={'backup_space_limit','invalid_readback_workers','parallel_readback_unsupported','remote_manifest_mismatch','remote_checksum_mismatch','restore_integrity_failed',
             'invalid_remote_revision',
             'restore_count_mismatch','remote_download_unavailable','invalid_restore_path',
             'invalid_snapshot_manifest','snapshot_not_found','invalid_snapshot_id',
             'remote_file_integrity_failed','remote_authentication_failed',
             'remote_permission_denied','remote_file_missing','remote_download_inconsistent',
             'remote_verification_failed','remote_media_readback_unavailable'}

def _check_readback_options(transport,workers):
    if type(workers) is not int or not 1<=workers<=4:
        raise RuntimeError('invalid_readback_workers')
    if workers>1 and not callable(getattr(transport,'fork_for_readback',None)):
        raise RuntimeError('parallel_readback_unsupported')


def _verify_file(transport,identity,name,meta,manifest,restore,reuse):
    relative=Path(name)
    if relative.is_absolute() or '..' in relative.parts:raise RuntimeError('invalid_snapshot_manifest')
    base=restore.resolve()
    for candidate in (restore/relative,restore/'snapshots'/identity/relative):
        if candidate.resolve()!=base/candidate.relative_to(restore):
            raise RuntimeError('invalid_restore_path')
    downloaded=None;cached_checked=False
    if reuse and downloaded is None:
        for candidate in (restore/relative,restore/'snapshots'/identity/relative):
            if candidate.is_file() and candidate.resolve().is_relative_to(restore.resolve()) and candidate.stat().st_size==meta['bytes'] and digest(candidate)==meta['sha256']:
                downloaded=candidate;cached_checked=True;break
    if downloaded is None:
        transient_codes={'remote_verification_failed','remote_media_readback_unavailable',
                         'remote_download_unavailable','remote_download_inconsistent'}
        # Shared-dataset reads occasionally return a transient upstream
        # verification error for a small blob. Keep the retry bounded and
        # limited to transport diagnostics; the manifest and checksums
        # still fail closed after the final attempt.
        for read_attempt in range(6):
            try:
                downloaded=Path(transport.download(name,identity,restore))
                break
            except Exception as exc:
                code=str(exc) if str(exc) in SAFE_ERRORS else 'remote_verification_failed'
                # Retry only bounded transport diagnostics. Unknown local
                # exceptions remain fail-closed and are not masked.
                if str(exc) in transient_codes and read_attempt<5:
                    time.sleep((5,10,20,40,60)[read_attempt])
                    continue
                frames='/'.join(frame.name for frame in traceback.extract_tb(exc.__traceback__)[-4:])
                kind='asset' if relative.parts[0]=='assets' else 'metadata'
                logger.error('readback_download_failed kind=%s file_id=%s error_type=%s code=%s functions=%s',kind,hashlib.sha256(name.encode()).hexdigest()[:16],type(exc).__name__,code,frames)
                if code in SAFE_ERRORS and code!='remote_verification_failed':
                    raise RuntimeError(code) from None
                if relative.parts and relative.parts[0]=='assets':
                    raise RuntimeError('remote_media_readback_unavailable') from None
                raise
    if not downloaded.resolve().is_relative_to(restore.resolve()):raise RuntimeError('invalid_restore_path')
    if not cached_checked and (downloaded.stat().st_size!=meta['bytes'] or digest(downloaded)!=meta['sha256']):raise RuntimeError('remote_checksum_mismatch')
    if name=='learning/analyses.sqlite3':
        with sqlite3.connect(downloaded) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('restore_integrity_failed')
            if c.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]!=manifest.get('analyses',0):raise RuntimeError('restore_count_mismatch')
    if name=='library.sqlite3':
        with sqlite3.connect(downloaded) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('restore_integrity_failed')
            if c.execute('SELECT COUNT(*) FROM items').fetchone()[0]!=manifest['items']:raise RuntimeError('restore_count_mismatch')
            if 'record_counts' in manifest:
                expected=manifest['record_counts']
                actual=snapshot_record_counts(c)
                if (not isinstance(expected,dict) or set(expected)!=set(actual)
                        or any(type(v) is not int or v<0 for v in expected.values())):
                    raise RuntimeError('invalid_snapshot_manifest')
                if actual!=expected:raise RuntimeError('restore_count_mismatch')
    return int(cached_checked)


def verify_files(transport,identity,manifest,restore,reuse=False,readback_workers=1,progress=None):
    _check_readback_options(transport,readback_workers)
    # Freeze the revision before reading the manifest. Worker forks inherit
    # that pin and never share mutable provider sessions.
    if readback_workers>1:transport=transport.fork_for_readback(identity)
    remote_manifest=transport.download('manifest.json',identity,restore)
    if json.loads(Path(remote_manifest).read_text())!=manifest:raise RuntimeError('remote_manifest_mismatch')
    bundle_name=manifest.get('learning_bundle')
    entries=[]
    for name,meta in manifest['files'].items():
        if bundle_name and name.startswith('learning/'):
            continue
        relative=Path(name)
        if (relative.is_absolute() or '..' in relative.parts or relative.as_posix()!=name
                or name=='.' or type(meta.get('bytes')) is not int or meta['bytes']<0):
            raise RuntimeError('invalid_snapshot_manifest')
        entries.append((name,meta))
    entries.sort(key=lambda entry:(entry[1]['bytes'],entry[0]))
    reused=completed=verified_bytes=0
    total_bytes=sum(meta['bytes'] for _,meta in entries)
    last_report=0
    learning_progress=None

    def report(phase='files',force=False):
        nonlocal last_report
        if progress and (force or (phase=='files' and completed==len(entries)) or time.monotonic()-last_report>=5):
            last_report=time.monotonic()
            try:
                event={'snapshot':identity,'state':'verifying','phase':phase,
                       'verified_files':completed,'total_files':len(entries),
                       'verified_bytes':verified_bytes,'total_bytes':total_bytes,
                       'reused_files':reused}
                if phase!='files' and learning_progress is not None:
                    event.update(learning_progress)
                progress(event)
            except Exception:
                # Observability is not a data integrity gate. Do not relabel
                # a valid snapshot because a progress consumer disconnected.
                logger.warning('readback_progress_unavailable snapshot=%s',identity)

    def checked(entry,reused_file):
        nonlocal reused,completed,verified_bytes
        reused+=reused_file;completed+=1;verified_bytes+=entry[1]['bytes']
        report()

    report(force=True)
    if readback_workers==1:
        # Preserve the small-file-first serial path for simple transports.
        for entry in entries:
            checked(entry,_verify_file(transport,identity,*entry,manifest,restore,reuse))
    else:
        # Validate core metadata before dispatching any large media reads.
        core={'library.sqlite3','items.jsonl','preferences.jsonl',
              'learning/analyses.sqlite3','learning.bundle.tar'}
        for entry in entries:
            if entry[0] in core:
                checked(entry,_verify_file(transport,identity,*entry,manifest,restore,reuse))
        remaining=iter(entry for entry in entries if entry[0] not in core)
        local=threading.local()
        def work(entry):
            if not hasattr(local,'transport'):
                local.transport=transport.fork_for_readback(identity)
            return _verify_file(local.transport,identity,*entry,manifest,restore,reuse)
        pool=ThreadPoolExecutor(max_workers=readback_workers,thread_name_prefix='reference-readback')
        pending={}
        def fill():
            while len(pending)<readback_workers:
                entry=next(remaining,None)
                if entry is None:break
                pending[pool.submit(work,entry)]=entry
        try:
            fill()
            while pending:
                done,_=wait(pending,return_when=FIRST_COMPLETED)
                # Inspect every completed outcome before scheduling more. On
                # any failure only the already bounded in-flight reads remain.
                outcomes=[(future,future.result()) for future in done]
                for future,reused_file in outcomes:
                    checked(pending.pop(future),reused_file)
                fill()
        finally:
            for future in pending:future.cancel()
            pool.shutdown(wait=True,cancel_futures=True)
    if bundle_name:
        report(phase='learning',force=True)
        bundle_meta=manifest['files'].get(bundle_name)
        if not bundle_meta:raise RuntimeError('invalid_snapshot_manifest')
        relative=Path(bundle_name)
        if relative.is_absolute() or '..' in relative.parts:raise RuntimeError('invalid_snapshot_manifest')
        bundle_path=None
        for candidate in (restore/relative,restore/'snapshots'/identity/relative):
            if candidate.is_file() and candidate.resolve().is_relative_to(restore.resolve()):
                bundle_path=candidate;break
        if bundle_path is None:
            bundle_path=Path(transport.download(bundle_name,identity,restore))
        if bundle_path.stat().st_size!=bundle_meta['bytes'] or digest(bundle_path)!=bundle_meta['sha256']:
            raise RuntimeError('remote_checksum_mismatch')
        expected=manifest.get('learning_members',
                              {name:meta for name,meta in manifest['files'].items() if name.startswith('learning/')})
        if not isinstance(expected,dict) or 'learning/analyses.sqlite3' not in expected:
            raise RuntimeError('invalid_snapshot_manifest')
        for name,meta in expected.items():
            path=Path(name)
            if (path.is_absolute() or '..' in path.parts or not name.startswith('learning/')
                    or path.as_posix()!=name or not isinstance(meta,dict)
                    or type(meta.get('bytes')) is not int or meta['bytes']<0
                    or not re.fullmatch(r'[0-9a-f]{64}',str(meta.get('sha256','')))):
                raise RuntimeError('invalid_snapshot_manifest')
        learning_progress={'verified_learning_files':0,'total_learning_files':len(expected),
                           'verified_learning_bytes':0,
                           'total_learning_bytes':sum(meta['bytes'] for meta in expected.values())}
        report(phase='learning',force=True)
        try:
            with tarfile.open(bundle_path,'r') as archive:
                members={}
                for member in archive.getmembers():
                    path=Path(member.name)
                    if (path.is_absolute() or '..' in path.parts or path.as_posix()!=member.name
                            or (member.name!='learning' and not member.name.startswith('learning/'))
                            or not (member.isfile() or member.isdir())):
                        raise RuntimeError('invalid_restore_path')
                    if member.isfile():
                        if member.name in members:raise RuntimeError('restore_count_mismatch')
                        members[member.name]=member
                if set(members)!=set(expected):raise RuntimeError('restore_count_mismatch')
                # Never let tar create links or special files. Verify each
                # member against its manifest hash as we restore the bytes.
                base=restore.resolve()
                for name,member in members.items():
                    destination=restore/name
                    if destination.is_symlink() or destination.resolve()!=base/name:
                        raise RuntimeError('invalid_restore_path')
                    if member.size!=expected[name]['bytes']:raise RuntimeError('remote_checksum_mismatch')
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    checksum=hashlib.sha256()
                    with archive.extractfile(member) as src, destination.open('wb') as dst:
                        for block in iter(lambda:src.read(1024*1024),b''):
                            checksum.update(block);dst.write(block)
                    if checksum.hexdigest()!=expected[name]['sha256']:
                        raise RuntimeError('remote_checksum_mismatch')
                    # Member counts describe verified restored bytes only.
                    # They do not certify the learning database's integrity.
                    learning_progress['verified_learning_files']+=1
                    learning_progress['verified_learning_bytes']+=member.size
                    report(phase='learning',force=learning_progress['verified_learning_files']==len(expected))
        except (tarfile.TarError,OSError):
            raise RuntimeError('restore_integrity_failed') from None
        analysis=restore/'learning/analyses.sqlite3'
        report(phase='learning_integrity',force=True)
        with sqlite3.connect(analysis) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('restore_integrity_failed')
            if c.execute('SELECT COUNT(*) FROM analyses').fetchone()[0]!=manifest.get('analyses',0):raise RuntimeError('restore_count_mismatch')
    return reused


def resume_verification(transport,identity,readback_workers=1,progress=None):
    """Verify the immutable uploaded snapshot; never creates or uploads a replacement."""
    _check_readback_options(transport,readback_workers)
    if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}',identity):raise RuntimeError('invalid_snapshot_id')
    with (store.ROOT/'.backup.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'already_running'}
        with store.connection() as c:
            row=c.execute('SELECT manifest FROM backups WHERE id=?',(identity,)).fetchone()
        if not row:raise RuntimeError('snapshot_not_found')
        manifest=json.loads(row[0])
        local=store.ROOT/'snapshots'/identity/'manifest.json'
        if manifest.get('snapshot')!=identity or json.loads(local.read_text())!=manifest:raise RuntimeError('invalid_snapshot_manifest')
        restore=store.ROOT/'restore_checks'/identity;restore.mkdir(parents=True,exist_ok=True)
        with store.connection() as c:c.execute("UPDATE backups SET state='verifying' WHERE id=?",(identity,))
        try:
            reused=verify_files(transport,identity,manifest,restore,reuse=True,readback_workers=readback_workers,progress=progress)
            with store.connection() as c:c.execute("UPDATE backups SET state='verified',remote_revision=? WHERE id=?",('snapshots/'+identity,identity))
            # Readback is often invoked after a long remote failure. Do not
            # hold the backup lock while recursively deleting old local media
            # unless an operator explicitly opens a cleanup window.
            if os.getenv('AD_LIBRARY_CLEANUP') == '1':
                retain_verified()
            return {'snapshot':identity,'state':'verified','items':manifest['items'],'verified_files':len(manifest['files']),'reused_files':reused}
        except Exception as exc:
            with store.connection() as c:c.execute("UPDATE backups SET state='failed' WHERE id=?",(identity,))
            code=str(exc) if str(exc) in SAFE_ERRORS else 'remote_verification_failed'
            missing=getattr(exc,'name',None) if isinstance(exc,ModuleNotFoundError) else None
            logger.error('remote_verification_failed snapshot=%s code=%s error_type=%s missing_module=%s', identity, code, type(exc).__name__, missing or '-')
            raise RuntimeError(code) from None
