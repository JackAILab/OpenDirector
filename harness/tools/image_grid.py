"""Bounded deterministic grid slicing; original pixels and source remain intact."""
import hashlib
import io
from PIL import Image, ImageOps
from harness.tools.creative_canvas import asset_directory


def split_grid(project, asset_id, rows, columns):
    if type(rows) is not int or type(columns) is not int or (rows, columns) not in ((2, 2), (2, 3), (3, 3)):
        raise ValueError('请选择 2×2、2×3 或 3×3 宫格')
    asset = project.get('canvas_assets', {}).get(asset_id, {})
    filename = asset.get('filename')
    if asset.get('kind') != 'image' or filename not in ('source.jpg', 'source.png', 'source.webp'):
        raise ValueError('请选择本项目的静态图片')
    raw = (asset_directory(project, asset_id) / filename).read_bytes()
    if len(raw) > 30 * 1024 * 1024:
        raise ValueError('图片过大')
    with Image.open(io.BytesIO(raw)) as source:
        if source.width * source.height > 20_000_000 or getattr(source, 'n_frames', 1) != 1:
            raise ValueError('只支持 2000 万像素以内静态图片')
        img = ImageOps.exif_transpose(source).convert('RGB')
    w, h = img.size
    if w // columns < 16 or h // rows < 16:
        raise ValueError('每个宫格的宽和高至少需要 16 像素')
    tiles = []
    for row in range(rows):
        for column in range(columns):
            box = (column*w//columns, row*h//rows, (column+1)*w//columns, (row+1)*h//rows)
            out = io.BytesIO()
            img.crop(box).save(out, format='PNG')
            tiles.append((out.getvalue(), {'row':row+1, 'column':column+1, 'pixel_box':list(box)}))
    return tiles, {'schema':'image-grid-v1', 'source_sha256':hashlib.sha256(raw).hexdigest(),
                   'source_dimensions':[w,h], 'rows':rows, 'columns':columns, 'training_eligible':False}
