"""ModelScope transport. Credentials never enter library records or manifests."""
from pathlib import Path
import json
import os
import re
import time

class ModelScopeBackup:
    def __init__(self, revisions_dir=None):
        self.repo='JackAILab/AdvertiseAgent'
        self.revisions_dir=Path(revisions_dir) if revisions_dir else None

    def revision_for(self,identity):
        pin=getattr(self,'_readback_pin',None)
        if pin and pin[0]==identity:return pin[1]
        if not self.revisions_dir:return 'master'
        if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}',identity):raise RuntimeError('invalid_snapshot_id')
        path=self.revisions_dir/(identity+'.json')
        if not path.exists():return 'master'
        try:
            record=json.loads(path.read_text())
            revision=record['revision']
            if record['snapshot']!=identity or not re.fullmatch(r'[0-9a-f]{40,64}',revision):raise ValueError()
        except (OSError,ValueError,KeyError,TypeError):raise RuntimeError('invalid_remote_revision') from None
        return revision

    def fork_for_readback(self,identity):
        """Give each read worker an independent session at the same revision."""
        revision=self.revision_for(identity)
        # A branch name can move between requests. Parallel workers must
        # share an immutable commit, including when reading older snapshots.
        if not re.fullmatch(r'[0-9a-f]{40,64}',revision):
            raise RuntimeError('invalid_remote_revision')
        worker=ModelScopeBackup(revisions_dir=self.revisions_dir)
        worker._readback_pin=(identity,revision)
        return worker

    def record_revision(self,identity,revision):
        if not self.revisions_dir:return
        if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}',identity) or not isinstance(revision,str) or not re.fullmatch(r'[0-9a-f]{40,64}',revision):
            raise RuntimeError('invalid_remote_revision')
        self.revisions_dir.mkdir(parents=True,exist_ok=True)
        path=self.revisions_dir/(identity+'.json');temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'snapshot':identity,'revision':revision}))
        os.replace(temporary,path)

    def connect(self):
        from modelscope_hub import HubApi
        token=Path('/var/lib/visualstation-local/secrets/modelscope-token').read_text().strip()
        self.api=HubApi(token=token)
        self.repo='JackAILab/AdvertiseAgent'
        info=self.api.get_repo(self.repo,'dataset')
        if not info.private:raise RuntimeError('backup_repository_not_private')

    def upload(self,folder,identity):
        self.connect()
        result=self.api.upload_folder(self.repo,'dataset',folder,path_in_repo='snapshots/'+identity,
                               commit_message='Advertising reference library snapshot '+identity,
                               # Keep memory bounded on the shared node. The
                               # archive is large and parallel workers have
                               # previously pushed the process above 20 GB.
                               max_workers=1,disable_tqdm=True,sync_remote_repo=False)
        if self.revisions_dir:
            commits=result if isinstance(result,list) else [result]
            if not commits or not isinstance(commits[-1],dict):raise RuntimeError('invalid_remote_revision')
            self.record_revision(identity,commits[-1].get('commit_id'))

    def inventory(self,identity):
        if not hasattr(self,'api'):self.connect()
        prefix='snapshots/'+identity+'/'
        try:
            from modelscope_hub.errors import PermissionDeniedError
        except ModuleNotFoundError:
            class PermissionDeniedError(Exception): pass
        try:
            entries=self.api.legacy.list_repo_files(self.repo,'dataset',root=prefix.rstrip('/'),recursive=True,revision=self.revision_for(identity))
        except PermissionDeniedError:
            # Listing is an ordering hint, never proof of file integrity. An
            # empty inventory makes the verifier read and hash every file.
            return set()
        paths={e.get('Path') or e.get('path') for e in entries}
        return {p[len(prefix):] for p in paths if isinstance(p,str) and p.startswith(prefix)}

    def download(self,name,identity,directory):
        try:
            from modelscope_hub.errors import (NetworkError, RateLimitError, ServerError,
                FileIntegrityError, AuthenticationError, PermissionDeniedError, NotExistError)
        except ModuleNotFoundError:
            # The transport is optional for local inventory/restore tests. Keep the
            # exception contract available when only a mocked API is present.
            class NetworkError(Exception): pass
            class RateLimitError(Exception): pass
            class ServerError(Exception): pass
            class FileIntegrityError(Exception): pass
            class AuthenticationError(Exception): pass
            class PermissionDeniedError(Exception): pass
            class NotExistError(Exception): pass
        revision=self.revision_for(identity)
        for attempt in range(3):
            try:
                if not hasattr(self,'api'):self.connect()
                return self.api.download_file(self.repo,'dataset','snapshots/'+identity+'/'+name,
                                              local_dir=directory,force=True,revision=revision)
            except (NetworkError, RateLimitError, ServerError):
                if attempt==2:raise RuntimeError('remote_download_unavailable') from None
                time.sleep((2,5)[attempt])
            except NotExistError:
                remote='snapshots/'+identity+'/'+name
                # Some authorized ModelScope accounts can download a known
                # path but cannot list its parent directory. Treat that as a
                # transient readback condition and retry the direct download;
                # directory listing is only an existence hint.
                try:
                    entries=self.api.legacy.list_repo_files(self.repo,'dataset',root=str(Path(remote).parent),recursive=False,revision=revision)
                except PermissionDeniedError:
                    if attempt==2:raise RuntimeError('remote_download_unavailable') from None
                    self.connect()
                    time.sleep((2,5)[attempt])
                    continue
                if remote not in {e.get('Path') or e.get('path') for e in entries}:
                    raise RuntimeError('remote_file_missing') from None
                if attempt==2:raise RuntimeError('remote_download_inconsistent') from None
                self.connect()
                time.sleep((2,5)[attempt])
            except (FileIntegrityError, AuthenticationError, PermissionDeniedError) as exc:
                code={FileIntegrityError:'remote_file_integrity_failed',AuthenticationError:'remote_authentication_failed',
                      PermissionDeniedError:'remote_permission_denied'}
                raise RuntimeError(next(value for cls,value in code.items() if isinstance(exc,cls))) from None
