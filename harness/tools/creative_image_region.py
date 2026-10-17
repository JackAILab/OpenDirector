"""Bounded region composition: models generate a candidate; only the chosen pixels are applied."""
import io
import hashlib
import math
from PIL import Image, ImageDraw, ImageOps, ImageFilter, ImageChops


def brush_mask(size, strokes):
    mask=Image.new('L',size,0);draw=ImageDraw.Draw(mask);width,height=size
    for stroke in strokes:
        points=[(round(x*(width-1)),round(y*(height-1))) for x,y in stroke['points']]
        diameter=max(1,round(stroke['size']*min(size)));radius=diameter/2
        color=0 if stroke['erase'] else 255
        if len(points)>1:draw.line(points,fill=color,width=diameter,joint='curve')
        for x,y in points:draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
    return mask


def normalized_strokes(value):
    if not isinstance(value,list) or not 1<=len(value)<=32:raise ValueError('手绘选区需为 1–32 笔')
    strokes=[];total=0
    for stroke in value:
        if not isinstance(stroke,dict) or set(stroke)!={'points','size','erase'}:raise ValueError('手绘笔画参数无效')
        points=stroke['points'];size=stroke['size'];total+=len(points) if isinstance(points,list) else 0
        if not isinstance(points,list) or not 1<=len(points)<=256 or total>4096:raise ValueError('手绘选区轨迹过多，请简化选区')
        if type(size) not in (int,float) or not math.isfinite(size) or not .005<=size<=.3 or type(stroke['erase']) is not bool:raise ValueError('画笔参数无效')
        for point in points:
            if not isinstance(point,(list,tuple)) or len(point)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in point):raise ValueError('画笔轨迹超出原图')
        strokes.append(dict(points=[list(p) for p in points],size=size,erase=stroke['erase']))
    return strokes


def prepare_region(path, region):
    if not isinstance(region, dict) or set(region)-{'x','y','width','height','feather','shape','strokes'}:
        raise ValueError('局部修改区域无效')
    values=[region.get(k) for k in ('x','y','width','height')]
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
        raise ValueError('局部修改区域需为有限数值')
    x,y,w,h=values;feather=region.get('feather',8)
    if not 0<=x<1 or not 0<=y<1 or not 0<w<=1 or not 0<h<=1 or x+w>1.00000001 or y+h>1.00000001:
        raise ValueError('局部修改区域必须在原图范围内')
    if isinstance(feather,bool) or not isinstance(feather,int) or not 0<=feather<=32:
        raise ValueError('选区边缘过渡需为 0–32 像素')
    with Image.open(path) as source:
        size=ImageOps.exif_transpose(source).size
    width,height=size
    shape=region.get('shape','rectangle')
    if shape not in ('rectangle','brush'):raise ValueError('选区形状无效')
    if shape=='brush':
        strokes=normalized_strokes(region.get('strokes'))
        mask=brush_mask(size,strokes);box=mask.getbbox()
        if not box or sum(mask.histogram()[1:])<256 or min(box[2]-box[0],box[3]-box[1])<16:raise ValueError('请涂抹至少 16×16 像素大小的有效选区')
        return dict(shape='brush',box=list(box),dimensions=list(size),feather=feather,strokes=strokes,mask_sha256=hashlib.sha256(mask.tobytes()).hexdigest())
    if region.get('strokes'):raise ValueError('矩形选区不能同时提交手绘笔画')
    box=[round(x*width),round(y*height),min(width,round((x+w)*width)),min(height,round((y+h)*height))]
    if min(box[2]-box[0],box[3]-box[1])<16:raise ValueError('局部修改区域至少为 16 × 16 像素')
    return dict(box=box,dimensions=list(size),feather=min(feather,(min(box[2]-box[0],box[3]-box[1])-1)//2))


def compose_region(path, raw, region):
    with Image.open(path) as image:original=ImageOps.exif_transpose(image).convert('RGB')
    if list(original.size)!=region['dimensions']:raise ValueError('原图尺寸已变化')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>20_000_000 or getattr(image,'n_frames',1)!=1:
            raise ValueError('局部修改候选不是有效静态图片')
        candidate=ImageOps.exif_transpose(image).convert('RGB').resize(original.size,Image.Resampling.LANCZOS)
    x,y,right,bottom=region['box'];w,h=right-x,bottom-y;feather=region['feather']
    if region.get('shape')=='brush':
        hard_mask=brush_mask(original.size,region['strokes'])
        if hashlib.sha256(hard_mask.tobytes()).hexdigest()!=region['mask_sha256']:raise ValueError('已确认选区发生变化')
        full_mask=ImageChops.darker(hard_mask,hard_mask.filter(ImageFilter.GaussianBlur(feather))) if feather else hard_mask
    else:
        mask=Image.new('L',(w,h),255)
        if feather:
            mask.paste(0,(0,0,w,h));draw=ImageDraw.Draw(mask)
            for inset in range(feather+1):draw.rectangle((inset,inset,w-1-inset,h-1-inset),fill=round(255*inset/feather))
        hard_mask=Image.new('L',original.size,0);hard_mask.paste(255,(x,y,right,bottom))
        full_mask=Image.new('L',original.size,0);full_mask.paste(mask,(x,y))
    result=Image.composite(candidate,original,full_mask)
    output=io.BytesIO();result.save(output,'PNG');data=output.getvalue()
    with Image.open(io.BytesIO(data)) as saved:
        difference=ImageChops.difference(saved.convert('RGB'),original)
        outside=Image.composite(difference,Image.new('RGB',original.size),ImageOps.invert(hard_mask))
        if outside.getbbox():raise ValueError('选区外像素检查未通过')
    return data,dict(**region,outside_preserved=True,human_review_required=True)
