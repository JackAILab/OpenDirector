import argparse
import json
from pathlib import Path
import shutil
from .compiler import export, evaluate, canonical, verify_bundle
from .schema import Evidence, Source
from .runner import Store, run


def main():
    parser = argparse.ArgumentParser(description='Video → timecoded evidence → reusable skill')
    sub = parser.add_subparsers(dest='command', required=True)
    compile_cmd = sub.add_parser('compile', help='Compile existing evidence offline, without model calls')
    compile_cmd.add_argument('evidence', type=Path)
    compile_cmd.add_argument('--out', type=Path, required=True)
    compile_cmd.add_argument('--duration', type=int, default=15)
    check = sub.add_parser('check', help='Validate evidence and report eligibility')
    check.add_argument('evidence', type=Path)
    verify = sub.add_parser('verify', help='Verify bundle hashes and reproduce its contents offline')
    verify.add_argument('bundle', type=Path)
    analyze = sub.add_parser('analyze', help='Analyze one local video, one paid request at most')
    analyze.add_argument('video', type=Path)
    analyze.add_argument('--source', type=Path, required=True)
    analyze.add_argument('--data', type=Path, default=Path('video2skill-data'))
    analyze.add_argument('--allow-model-call', action='store_true', required=True)
    analyze.add_argument('--duration', type=int, default=15, choices=range(5,181), metavar='5..180')
    analyze.add_argument('--language', choices=['zh','en'], default='zh')
    collect = sub.add_parser('collect', help='Normalize crawler exports into a deduplicated source manifest')
    collect.add_argument('manifest', type=Path, help='JSONL records matching Source schema')
    collect.add_argument('--out', type=Path, required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8088)
    args = parser.parse_args()
    if args.command == 'serve':
        import uvicorn
        from .service import create_app
        uvicorn.run(create_app(), host=args.host, port=args.port)
    elif args.command in ('compile', 'check'):
        evidence = Evidence.model_validate_json(args.evidence.read_text())
        result = export(evidence, args.out, args.duration) if args.command == 'compile' else evaluate(evidence)
        print(canonical(result))
    elif args.command == 'verify':
        print(canonical(verify_bundle(args.bundle)))
    elif args.command == 'collect':
        records, seen = [], set()
        for line in args.manifest.read_text().splitlines():
            if not line.strip(): continue
            source = Source.model_validate_json(line)
            key = source.source_url or canonical(source.model_dump())
            if key not in seen:
                seen.add(key)
                records.append(source.model_dump())
        with args.out.open('x') as handle:
            for record in records: handle.write(canonical(record) + '\n')
        print(json.dumps({'sources':len(records)}))
    else:
        from .harness.models.vision import configured
        if not configured(): parser.error('Set V2S_API_KEY and V2S_MODEL')
        if not args.video.is_file() or args.video.stat().st_size > 200*1024**2:
            parser.error('Video must be a local file no larger than 200 MiB')
        source = Source.model_validate_json(args.source.read_text())
        store = Store(args.data)
        identity = store.create()
        try:
            shutil.copyfile(args.video, store.root / identity / 'input.bin')
        except OSError:
            (store.root / identity / 'input.bin').unlink(missing_ok=True)
            store.update(identity, 'failed', 'copy_failed')
            raise SystemExit('Could not stage input video') from None
        run(store, identity, source, args.duration, args.language)
        result = store.get(identity)
        print(canonical(result))
        if result['state'] != 'completed': raise SystemExit(1)

if __name__ == '__main__': main()
