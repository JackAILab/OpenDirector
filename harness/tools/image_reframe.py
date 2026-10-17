"""Deterministic, bounded image reframing. Never edits the source or calls a model."""
import hashlib
import io
import math
from PIL import Image, ImageOps
from harness.tools.creative_canvas import asset_directory


def reframe(project, asset_id, crop, rotation=0, mirror=False):
    asset = project.get('canvas_assets', {}).get(asset_id)
    if not asset or asset.get('kind') != 'image':
        raise ValueError('请选择本项目的图片')
    if rotation not in (0, 90, 180, 270) or type(mirror) is not bool:
        raise ValueError('旋转或镜像参数无效')
    if len(crop) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in crop):
        raise ValueError('裁剪区域无效')
    x, y, w, h = crop
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.00000001 or y+h > 1.00000001:
        raise ValueError('裁剪区域超出图片')
    filename = asset.get('filename', '')
    if filename not in ('source.jpg', 'source.png', 'source.webp'):
        raise ValueError('图片来源无效')
    raw = (asset_directory(project, asset_id)/filename).read_bytes()
    if len(raw) > 30*1024*1024:
        raise ValueError('图片过大')
    with Image.open(io.BytesIO(raw)) as src:
        if src.width*src.height > 20_000_000 or getattr(src, 'n_frames', 1) != 1:
            raise ValueError('只支持 2000 万像素以内静态图片')
        original_size = list(src.size)
        img = ImageOps.exif_transpose(src).convert('RGB')
    if rotation:
        img = img.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}[rotation])
    if mirror:
        img = ImageOps.mirror(img)
    iw, ih = img.size
    pixel = lambda value: math.floor(value + .5)
    box = (pixel(x*iw), pixel(y*ih), min(iw, pixel((x+w)*iw)), min(ih, pixel((y+h)*ih)))
    if box[2]-box[0] < 16 or box[3]-box[1] < 16:
        raise ValueError('裁剪结果的宽和高至少需要 16 像素')
    result = img.crop(box)
    output = io.BytesIO(); result.save(output, format='JPEG', quality=95)
    return output.getvalue(), {'schema':'image-reframe-v1', 'source_sha256':hashlib.sha256(raw).hexdigest(),
        'crop':list(crop), 'pixel_box':list(box), 'rotation':rotation, 'mirror':mirror,
        'source_dimensions':original_size, 'result_dimensions':list(result.size), 'training_eligible':False}
