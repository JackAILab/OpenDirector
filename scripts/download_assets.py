"""Download a pinned private asset bundle, verify hashes, and safely restore files."""
import argparse,hashlib,json,os,shutil,tarfile,tempfile
from pathlib import Path
from modelscope_hub.api import HubApi
p=argparse.ArgumentParser();p.add_argument('--bundle',choices=['showcase','library','all'],default='showcase');p.add_argument('--revision',default=None);p.add_argument('--destination',default=str(Path(__file__).resolve().parents[1]));args=p.parse_args()
lock=json.loads((Path(__file__).resolve().parents[1]/'assets.lock.json').read_text());revision=args.revision or lock['revision'];api=HubApi(token=os.environ.get('MODELSCOPE_API_TOKEN'))
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
bundles=[b for b in lock['bundles'] if args.bundle=='all' or b['name']==args.bundle]
if not bundles:raise SystemExit('This release has no matching bundle.')
root=Path(args.destination).resolve();root.mkdir(parents=True,exist_ok=True)
for bundle in bundles:
 if bundle.get('kind')=='library-tree':
  prefix=bundle['prefix'];cache=api.download_repo(lock['dataset'],'dataset',revision=bundle.get('revision',revision),allow_patterns=[prefix+'files.json',prefix+'library.sqlite3'])
  index=cache/(prefix+'files.json');database=cache/(prefix+'library.sqlite3')
  if sha(index)!=bundle['index_sha256'] or sha(database)!=bundle['database_sha256']:raise SystemExit('Library metadata checksum mismatch')
  entries=json.loads(index.read_text());target=root/'assets/library';target.mkdir(parents=True,exist_ok=True)
  for entry in entries:
   rel=Path(entry['path'])
   if rel.is_absolute() or '..' in rel.parts:raise SystemExit('Unsafe library path')
   dest=target/rel
   if not dest.resolve().is_relative_to(target.resolve()):raise SystemExit('Unsafe destination')
   if dest.exists() and sha(dest)!=entry['sha256']:raise SystemExit('Existing library file differs: '+str(dest))
  with tempfile.TemporaryDirectory(dir=root,prefix='.library-download-') as tmp:
   downloaded=api.download_repo(lock['dataset'],'dataset',revision=bundle.get('revision',revision),local_dir=tmp,allow_patterns=[prefix+e['path'] for e in entries])
   for entry in entries:
    source=downloaded/(prefix+entry['path']);dest=target/entry['path']
    if sha(source)!=entry['sha256']:raise SystemExit('Library media checksum mismatch: '+entry['path'])
    dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():shutil.move(source,dest)
  dest=target/'library.sqlite3'
  if dest.exists() and sha(dest)!=bundle['database_sha256']:raise SystemExit('Existing library DB differs; restore into a fresh destination')
  if not dest.exists():shutil.copy2(database,dest)
  print('Restored library',len(entries),'media files');continue
 cache=api.download_repo(lock['dataset'],'dataset',revision=revision,allow_patterns=[bundle['file']])
 archive=cache/bundle['file']
 if sha(archive)!=bundle['sha256']:raise SystemExit('Archive checksum mismatch: '+bundle['file'])
 with tempfile.TemporaryDirectory(dir=root,prefix='.asset-restore-') as temp:
  staging=Path(temp)
  with tarfile.open(archive) as tar:
   members=tar.getmembers();regular={m.name for m in members if m.isfile()}
   for m in members:
    rel=Path(m.name)
    if rel.is_absolute() or '..' in rel.parts or not (m.isfile() or m.isdir() or (m.islnk() and m.linkname in regular)):raise SystemExit('Unsafe archive member')
   tar.extractall(staging,filter='data')
  files=[f for f in staging.rglob('*') if f.is_file()]
  for f in files:
   dest=root/f.relative_to(staging)
   if not dest.resolve().is_relative_to(root):raise SystemExit('Destination escapes restore root')
   if dest.exists() and (not dest.is_file() or sha(dest)!=sha(f)):raise SystemExit('Existing file differs; restore to a new directory: '+str(dest))
  for f in files:
   dest=root/f.relative_to(staging);dest.parent.mkdir(parents=True,exist_ok=True)
   if not dest.exists():shutil.move(f,dest)
 print('Restored',bundle['name'],len(files),'files')
