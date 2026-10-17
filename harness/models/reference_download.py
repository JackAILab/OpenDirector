"""Bounded public MP4 transport, optionally preserving a checked byte prefix."""
import hashlib
import json
import re
import time
from urllib.parse import urlsplit

import httpx

HOSTS = {'dpk6zrxldcuco.cloudfront.net', 'd2rmu1yblu9p0.cloudfront.net', 'media.dandad.org'}
PUBLIC_AWARD_HOST = re.compile(r'bv-[a-z0-9-]+\.bubblevault\.com')
KYOORIUS_MEDIA_HOSTS = frozenset({
    'kyoorius-prod-media.awards-360.com',
    'kyoorius-prod2-resized-media.awards-360.com',
})
ADFEST_MEDIA_HOST = 'adfest.d-energy.cn'


def validate_url(url):
    p = urlsplit(url)
    host = (p.hostname or '').lower()
    if host == 'winners.cannescorporate.com':
        if (p.scheme != 'https' or p.netloc != host or p.query or p.fragment
                or not re.fullmatch(r'/external_drive/(202[3-6])/([1-9][0-9]{0,7})/\2_\1_[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{2}_[0-9]{2}_(?:comp|og)\.mp4', p.path)):
            raise ValueError('unsupported_media_locator')
        return url
    if host == ADFEST_MEDIA_HOST:
        if (p.scheme != 'https' or p.port not in (None, 443) or p.username or p.password
                or p.query or p.fragment
                or not re.fullmatch(r'/adfest/works2026/(?:F|CF|EN)[0-9]{2}_[0-9]{3}(?:_[A-Za-z0-9-]{1,32})?\.mp4', p.path)):
            raise ValueError('unsupported_media_locator')
        return url
    if host in KYOORIUS_MEDIA_HOSTS:
        if (p.scheme != 'https' or p.port not in (None, 443) or p.username or p.password
                or p.query or p.fragment
                or not re.fullmatch(r'/companies/\d+/media/[0-9a-f-]{36}\.mp4', p.path)):
            raise ValueError('unsupported_media_locator')
        return url
    if (p.scheme != 'https' or (host not in HOSTS and not PUBLIC_AWARD_HOST.fullmatch(host))
            or p.port not in (None, 443) or p.username or p.password or p.query):
        raise ValueError('unsupported_media_locator')
    return url


def strong_etag(value):
    return isinstance(value, str) and bool(re.fullmatch(r'"[\x21\x23-\x7e]{1,256}"', value))


def discard_prefix(directory):
    # Only our fixed files; never remove arbitrary contents or final assets.
    for name in ('checkpoint.json', 'checkpoint.tmp', 'source.mp4'):
        (directory / name).unlink(missing_ok=True)


def checkpoint_info(directory, max_bytes):
    """Cheap scheduling hint. The downloader independently hashes the prefix."""
    try:
        checkpoint = directory / 'checkpoint.json'
        source = directory / 'source.mp4'
        if directory.is_symlink() or checkpoint.is_symlink() or source.is_symlink():
            return None
        if checkpoint.stat().st_size > 2048:
            return None
        info = json.loads(checkpoint.read_text())
        size, count = info['size'], info['bytes']
        if (type(size) is not int or type(count) is not int or not 0 < count <= size <= max_bytes
                or not strong_etag(info['etag'])
                or not re.fullmatch(r'[0-9a-f]{64}', info['source_hash'])
                or not re.fullmatch(r'[0-9a-f]{64}', info['sha256'])
                or not count <= source.stat().st_size <= max_bytes):
            return None
        return info
    except (OSError, ValueError, KeyError, TypeError):
        return None


def download_mp4(client, url, directory, *, max_bytes, timeout, resume=False, clock=time.monotonic):
    validate_url(url)
    if directory.is_symlink():
        raise ValueError('invalid_partial_identity')
    if not urlsplit(url).path.lower().endswith('.mp4'):
        raise ValueError('unsupported_media_format')
    destination = directory / 'source.mp4'
    source_hash = hashlib.sha256(url.encode()).hexdigest()
    checkpoint = checkpoint_info(directory, max_bytes) if resume else None
    digest = hashlib.sha256()
    total = 0
    expected = None
    etag = None
    deadline = clock() + timeout

    if checkpoint and checkpoint['source_hash'] == source_hash:
        with destination.open('rb') as previous:
            remaining = checkpoint['bytes']
            while remaining:
                if clock() > deadline:
                    raise ValueError('download_timeout')
                block = previous.read(min(1024 * 1024, remaining))
                if not block:
                    break
                digest.update(block)
                remaining -= len(block)
        if not remaining and digest.hexdigest() == checkpoint['sha256']:
            total, expected, etag = checkpoint['bytes'], checkpoint['size'], checkpoint['etag']
            # A crash may leave a tail beyond the last durable checkpoint.
            with destination.open('r+b') as previous:
                previous.truncate(total)
            if total == expected:
                return destination
    if resume and not total:
        discard_prefix(directory)
        digest = hashlib.sha256()
    headers = {'Accept-Encoding': 'identity'}
    if total:
        headers.update(Range=f'bytes={total}-', **{'If-Range': etag})
    saved_bytes = total
    saved_at = clock()

    def save_prefix(output=None):
        nonlocal saved_bytes, saved_at
        if not resume or not total or expected is None or not strong_etag(etag):
            return
        if output is not None:
            output.flush()
        info = {'source_hash': source_hash, 'etag': etag, 'size': expected,
                'bytes': total, 'sha256': digest.hexdigest()}
        temporary = directory / 'checkpoint.tmp'
        if temporary.is_symlink():
            raise ValueError('invalid_partial_identity')
        temporary.write_text(json.dumps(info))
        temporary.replace(directory / 'checkpoint.json')
        saved_bytes, saved_at = total, clock()

    try:
        with client.stream('GET', url, headers=headers) as response:
            response.raise_for_status()
            if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                raise ValueError('invalid_media_range')
            length = response.headers.get('content-length', '')
            length = int(length) if length.isdecimal() else None
            if total and response.status_code == 206:
                found = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('content-range', ''))
                if (not found or tuple(map(int, found.groups())) != (total, expected - 1, expected)
                        or response.headers.get('etag') != etag
                        or (length is not None and length != expected - total)):
                    raise ValueError('invalid_media_range')
            elif response.status_code == 200:
                # If-Range may produce a full replacement. Start it at zero;
                # never append a changed file or a server's ignored Range.
                total, expected, etag = 0, length, response.headers.get('etag')
                digest = hashlib.sha256()
                saved_bytes, saved_at = 0, clock()
                if resume:
                    discard_prefix(directory)
            else:
                raise ValueError('invalid_media_range')
            if expected is not None and expected > max_bytes:
                raise ValueError('media_limit')
            mode = 'ab' if total else ('wb' if resume else 'xb')
            with destination.open(mode) as output:
                try:
                    for block in response.iter_bytes():
                        if total + len(block) > max_bytes:
                            raise ValueError('media_limit')
                        if expected is not None and total + len(block) > expected:
                            raise ValueError('invalid_media_range')
                        now = clock()
                        if now > deadline:
                            raise ValueError('download_timeout')
                        output.write(block)
                        total += len(block)
                        digest.update(block)
                        if total - saved_bytes >= 4 * 1024 * 1024 or now - saved_at >= 30:
                            save_prefix(output)
                except (httpx.TransportError, ValueError) as exc:
                    if isinstance(exc, httpx.TransportError) or str(exc) == 'download_timeout':
                        save_prefix(output)
                    raise
            if not total:
                raise ValueError('invalid_media')
            if expected is not None and total != expected:
                save_prefix()
                raise ValueError('incomplete_media')
            save_prefix()
            return destination
    except Exception as exc:
        transient = (isinstance(exc, httpx.TransportError)
                     or isinstance(exc, ValueError) and str(exc) in ('download_timeout', 'incomplete_media')
                     or isinstance(exc, httpx.HTTPStatusError) and (exc.response.status_code == 429 or exc.response.status_code >= 500))
        if resume and (not transient or checkpoint_info(directory, max_bytes) is None):
            discard_prefix(directory)
        raise
