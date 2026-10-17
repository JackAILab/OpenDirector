"""Bounded, account-project-scoped reference assets; no external URLs."""
import base64
import hashlib
import io
import re
import secrets
import warnings
from PIL import Image, ImageOps
from harness.studio import store

MAX_UPLOAD = 6 * 1024 * 1024
MAX_ENCODED_IMAGE = 500_000


def reference_path(project):
    ref = project.get('reference') or {}
    if not re.fullmatch(r'[a-f0-9]{24}', project['id']) or not re.fullmatch(r'[a-f0-9]{32}', ref.get('id', '')):
        raise ValueError('参考图标识无效')
    return store.DATA / 'references' / project['id'] / (ref['id'] + '.jpg')


def save_reference(project, content):
    if not content or len(content) > MAX_UPLOAD:
        raise ValueError('参考图需小于 6 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > 20_000_000:
                    raise ValueError('请选择不超过 2000 万像素的 JPEG、PNG 或 WebP 图片')
                if getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('请使用静态参考图')
                source.load()
                oriented = ImageOps.exif_transpose(source)
                rgba = oriented.convert('RGBA')
                image = Image.new('RGB', rgba.size, 'white')
                image.paste(rgba, mask=rgba.getchannel('A'))
        aspect = {'16:9':16/9, '9:16':9/16, '1:1':1}[project['aspect']]
        if abs(image.width / image.height / aspect - 1) > .05:
            raise ValueError('参考图比例与项目不一致，请选择相同比例的画面，避免裁掉商品')
        if min(image.size) < 128:
            raise ValueError('参考图短边至少需要 128 像素')
        image.thumbnail((1280, 1280))
        for quality in (90, 80, 65, 50):
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=quality, optimize=True)
            data = buffer.getvalue()
            if len(data) <= MAX_ENCODED_IMAGE:
                break
        else:
            raise ValueError('参考图过于复杂，请使用更小的图片')
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('无法读取参考图，请使用有效的 JPEG、PNG 或 WebP') from exc
    ref = {'id':secrets.token_hex(16), 'sha256':hashlib.sha256(data).hexdigest(),
           'width':image.width, 'height':image.height, 'media_type':'image/jpeg'}
    path = reference_path({**project, 'reference':ref})
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('xb') as output:
        output.write(data)
    path.chmod(0o600)
    return ref


def reference_uri(project):
    data = reference_path(project).read_bytes()
    if len(data) > MAX_ENCODED_IMAGE or hashlib.sha256(data).hexdigest() != project['reference']['sha256']:
        raise ValueError('参考图校验失败，请重新上传')
    return 'data:image/jpeg;base64,' + base64.b64encode(data).decode('ascii')
