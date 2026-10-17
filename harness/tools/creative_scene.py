"""Bounded scene operations shared by the scene UI and agents; no model calls."""
import hashlib
import json
import math
import struct
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_GLB = 30 * 1024 * 1024


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_default=True)


class Object(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    name: str = Field(min_length=1, max_length=80)
    kind: Literal['box', 'sphere', 'cylinder', 'plane', 'glb', 'light']
    position: list[float] = Field(min_length=3, max_length=3)
    rotation: list[float] = Field(default=[0, 0, 0], min_length=3, max_length=3)
    scale: list[float] = Field(default=[1, 1, 1], min_length=3, max_length=3)
    color: str = Field(default='#b6c7ca', pattern=r'^#[a-fA-F0-9]{6}$')
    roughness: float = Field(default=.4, ge=0, le=1, allow_inf_nan=False)
    metalness: float = Field(default=.1, ge=0, le=1, allow_inf_nan=False)
    intensity: float = Field(default=40, ge=0, le=500, allow_inf_nan=False)
    asset: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    visible: bool = True

    @field_validator('position', 'rotation', 'scale')
    @classmethod
    def bounded_vector(cls, value, info):
        low, high = (.01, 100) if info.field_name == 'scale' else (-1000, 1000) if info.field_name == 'rotation' else (-100, 100)
        if any(not math.isfinite(v) or not low <= v <= high for v in value):
            raise ValueError('变换数值超出范围')
        return value


class Camera(Strict):
    fov: float = Field(default=38, ge=15, le=100, allow_inf_nan=False)
    target: list[float] = Field(default=[0, 1, 0], min_length=3, max_length=3)
    points: list[list[float]] = Field(min_length=2, max_length=64)
    closed: bool = False
    easing: Literal['linear', 'smooth'] = 'smooth'

    @field_validator('points', 'target')
    @classmethod
    def finite_points(cls, value, info):
        points = value if info.field_name == 'points' else [value]
        if any(len(p) != 3 or any(not math.isfinite(v) or abs(v) > 100 for v in p) for p in points):
            raise ValueError('路径坐标无效')
        return value


class LegacyScene(Strict):
    version: Literal[1] = 1
    title: str = Field(default='商品运镜预演', min_length=1, max_length=120)
    duration: float = Field(default=10, ge=1, le=60, allow_inf_nan=False)
    aspect: Literal['16:9', '9:16', '1:1'] = '16:9'
    background: str = Field(default='#252a31', pattern=r'^#[a-fA-F0-9]{6}$')
    objects: list[Object] = Field(max_length=32)
    camera: Camera


class StationKeyframe(Strict):
    object_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    at: float = Field(ge=0, le=60, allow_inf_nan=False)
    position: list[float] = Field(min_length=3, max_length=3)
    rotation: list[float] = Field(default=[0, 0, 0], min_length=3, max_length=3)

    @field_validator('position', 'rotation')
    @classmethod
    def bounded_transform(cls, value, info):
        low, high = (-100, 100) if info.field_name == 'position' else (-1000, 1000)
        if any(not math.isfinite(v) or not low <= v <= high for v in value):
            raise ValueError('对象关键帧变换数值超出范围')
        return value


class Shot(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,48}$')
    name: str = Field(min_length=1, max_length=80)
    duration: float = Field(ge=.5, le=60, allow_inf_nan=False)
    camera: Camera
    station_keyframes: list[StationKeyframe] = Field(default_factory=list, max_length=24)


class Scene(Strict):
    version: Literal[2] = 2
    title: str = Field(default='商品运镜预演', min_length=1, max_length=120)
    duration: float = Field(ge=1, le=60, allow_inf_nan=False)
    aspect: Literal['16:9', '9:16', '1:1'] = '16:9'
    background: str = Field(default='#252a31', pattern=r'^#[a-fA-F0-9]{6}$')
    objects: list[Object] = Field(max_length=32)
    shots: list[Shot] = Field(min_length=1, max_length=12)


def validate_scene(document, assets):
    if document.get('version',1)==1:
        old=LegacyScene.model_validate(document).model_dump()
        camera=old.pop('camera');document=dict(old,version=2,shots=[dict(id='main',name='主机位',duration=old['duration'],camera=camera)])
    spec = Scene.model_validate(document).model_dump()
    if len({s['id'] for s in spec['shots']})!=len(spec['shots']):raise ValueError('镜头标识重复')
    if abs(sum(s['duration'] for s in spec['shots'])-spec['duration'])>1e-6:raise ValueError('镜头时长之和必须等于预演总时长')
    ids = set()
    for obj in spec['objects']:
        if obj['id'] in ids:
            raise ValueError('对象标识重复')
        ids.add(obj['id'])
        if obj['kind'] == 'glb' and obj['asset'] not in assets:
            raise ValueError('3D 资产不属于此项目')
        if obj['kind'] != 'glb' and obj['asset']:
            raise ValueError('基础几何体不能引用模型文件')
    object_by_id = {obj['id']: obj for obj in spec['objects']}
    for shot in spec['shots']:
        seen_keyframes = set()
        for keyframe in shot.get('station_keyframes', []):
            key = (keyframe['object_id'], round(keyframe['at'], 6))
            if key in seen_keyframes:
                raise ValueError('对象关键帧时间重复')
            seen_keyframes.add(key)
            obj = object_by_id.get(keyframe['object_id'])
            if obj is None:
                raise ValueError('对象关键帧引用了不存在的对象')
            if obj['kind'] in ('light', 'plane'):
                raise ValueError('灯光和平面不能添加对象站位关键帧')
            if keyframe['at'] > shot['duration']:
                raise ValueError('对象关键帧超出镜头时长')
    return spec


def default_scene(aspect='16:9'):
    objects = [
        dict(id='floor', name='地面', kind='plane', position=[0, 0, 0], rotation=[-90, 0, 0], scale=[12, 12, 1], color='#4e5662', roughness=.85),
        dict(id='plinth', name='圆形展台', kind='cylinder', position=[0, .15, 0], scale=[2.2, .3, 2.2], color='#30373d', metalness=.6),
        dict(id='bottle', name='概念瓶身 · 几何占位', kind='box', position=[0, 1.2, 0], scale=[.85, 1.8, .5], color='#87bec9', roughness=.18, metalness=.35),
        dict(id='cap', name='瓶盖 · 几何占位', kind='cylinder', position=[0, 2.3, 0], scale=[.5, .4, .5], color='#d1ac67', metalness=.8),
        dict(id='key', name='主光', kind='light', position=[3, 5, 3], color='#ffe6bd', intensity=180),
        dict(id='rim', name='轮廓光', kind='light', position=[-3, 3, -2], color='#a8dfff', intensity=150),
    ]
    points = [[math.sin(i*math.pi/4)*4.5, 2.8, math.cos(i*math.pi/4)*4.5] for i in range(8)]
    return validate_scene(dict(title='商品环绕预演', aspect=aspect, objects=objects, camera=dict(points=points, target=[0, 1.25, 0], closed=True)), {})


def layout_observation(spec, assets=None):
    """Return a bounded, coordinate-free observation of object placement.

    Primitive bounds are conservative estimates from their transform.  GLB
    geometry uses safe POSITION accessor metadata when the imported asset
    provides it; otherwise it remains unknown rather than inventing a mesh
    bound.  The asset projection is conservative and is still only a review
    signal, not a collision solver.
    This is an Observation only and never mutates the scene or approves a
    render.
    """
    assets = assets if isinstance(assets, dict) else {}
    def bounds(obj):
        if obj.get('kind') == 'box':
            half = [0.5 * abs(float(v)) for v in obj.get('scale', [1, 1, 1])]
        elif obj.get('kind') == 'sphere':
            radius = 0.5 * max(abs(float(v)) for v in obj.get('scale', [1, 1, 1]))
            half = [radius, radius, radius]
        elif obj.get('kind') == 'cylinder':
            scale = [abs(float(v)) for v in obj.get('scale', [1, 1, 1])]
            radius = 0.5 * max(scale[0], scale[2])
            half = [radius, 0.5 * scale[1], radius]
        elif obj.get('kind') == 'glb':
            meta = assets.get(obj.get('asset'))
            raw_bounds = meta.get('bounds') if isinstance(meta, dict) else None
            if not isinstance(raw_bounds, dict) or meta.get('bounds_status') != 'available':
                return None
            size = raw_bounds.get('size')
            scale = obj.get('scale', [1, 1, 1])
            if (not isinstance(size, list) or len(size) != 3 or
                    not isinstance(scale, list) or len(scale) != 3):
                return None
            if any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0 for value in size):
                return None
            # Rotation is deliberately reduced to a bounding sphere here. It
            # is conservative for every orientation and keeps this review
            # projection independent from a renderer's Euler convention.
            radius = math.sqrt(sum((0.5 * float(size[i]) * abs(float(scale[i]))) ** 2 for i in range(3)))
            if not math.isfinite(radius) or radius > 100000:
                return None
            half = [radius, radius, radius]
        else:
            return None
        position = [float(v) for v in obj.get('position', [0, 0, 0])]
        return [(position[i] - half[i], position[i] + half[i]) for i in range(3)]

    candidates = []
    unknown = []
    for obj in spec.get('objects', []):
        if not obj.get('visible', True) or obj.get('kind') == 'light':
            continue
        if obj.get('kind') == 'plane':
            continue
        box = bounds(obj)
        if box is None:
            if obj.get('kind') == 'glb':
                meta = assets.get(obj.get('asset'))
                if not isinstance(meta, dict) or meta.get('bounds_status') != 'available':
                    unknown.append({'id': str(obj.get('id', ''))[:48], 'name': str(obj.get('name') or '未命名 GLB')[:80]})
            continue
        candidates.append((obj, box))

    collisions = []
    for index, (left, left_box) in enumerate(candidates):
        for right, right_box in candidates[index + 1:]:
            overlap = all(min(left_box[axis][1], right_box[axis][1]) - max(left_box[axis][0], right_box[axis][0]) > 1e-6
                          for axis in range(3))
            if overlap:
                collisions.append({
                    'a': str(left.get('id', ''))[:48],
                    'a_name': str(left.get('name') or '未命名对象')[:80],
                    'b': str(right.get('id', ''))[:48],
                    'b_name': str(right.get('name') or '未命名对象')[:80],
                })
    return {
        'version': 1,
        'status': 'needs_check' if collisions or unknown else 'clear',
        'collisions': collisions[:32],
        'unknown_bounds': unknown[:32],
        'training_eligible': False,
    }


def station_manifest(spec):
    """Return a coordinate-free digest of movable object placement.

    The digest is used to tell whether a confirmed render handoff still refers
    to the same object stations.  Coordinates stay in the owner-scoped scene;
    this projection exposes only bounded object IDs, kinds and transform
    digests for review.
    """
    rows = []
    for obj in spec.get('objects', [])[:32]:
        if not obj.get('visible', True) or obj.get('kind') in ('light', 'plane'):
            continue
        transform = {
            'id': str(obj.get('id') or '')[:48],
            'kind': str(obj.get('kind') or '')[:16],
            'position': obj.get('position', [0, 0, 0]),
            'rotation': obj.get('rotation', [0, 0, 0]),
            'scale': obj.get('scale', [1, 1, 1]),
        }
        digest = hashlib.sha256(json.dumps(transform, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        rows.append({'object_id': transform['id'], 'kind': transform['kind'], 'placement_sha256': digest})
    keyframe_rows = []
    for shot in spec.get('shots', [])[:12]:
        shot_id = str(shot.get('id') or '')[:48]
        for frame in (shot.get('station_keyframes') or [])[:24]:
            if not isinstance(frame, dict):
                continue
            payload = {
                'shot_id': shot_id,
                'object_id': str(frame.get('object_id') or '')[:48],
                'at': frame.get('at', 0),
                'position': frame.get('position', [0, 0, 0]),
                'rotation': frame.get('rotation', [0, 0, 0]),
            }
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            keyframe_rows.append({'shot_id': shot_id, 'object_id': payload['object_id'], 'keyframe_sha256': digest})
    stable = ([{'object_id': row['object_id'], 'placement_sha256': row['placement_sha256']} for row in rows] +
              [{'shot_id': row['shot_id'], 'object_id': row['object_id'], 'keyframe_sha256': row['keyframe_sha256']}
               for row in keyframe_rows])
    return {
        'version': 1,
        'sha256': hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'objects': rows,
        'keyframe_count': len(keyframe_rows),
        'training_eligible': False,
    }


def station_keyframe_observation(spec, assets=None):
    """Review keyframe poses without returning their transforms.

    Each bounded keyframe is checked against the same conservative layout
    observation used for the saved scene. The result is evidence for a human
    review, never a constraint solver or an approval signal.
    """
    assets = assets if isinstance(assets, dict) else {}
    objects = spec.get('objects', [])[:32]
    rows = []
    for shot in spec.get('shots', [])[:12]:
        frames = shot.get('station_keyframes') if isinstance(shot.get('station_keyframes'), list) else []
        collision_pairs = set()
        collision_times = set()
        pairs_by_time = {}
        unknown_ids = set()
        for frame in frames[:24]:
            if not isinstance(frame, dict):
                continue
            object_id = str(frame.get('object_id') or '')[:48]
            if not any(str(obj.get('id') or '') == object_id for obj in objects):
                continue
            moved = []
            for obj in objects:
                clone = dict(obj)
                if str(obj.get('id') or '') == object_id:
                    clone['position'] = list(frame.get('position') or obj.get('position', [0, 0, 0]))
                    clone['rotation'] = list(frame.get('rotation') or obj.get('rotation', [0, 0, 0]))
                moved.append(clone)
            observed = layout_observation({'objects': moved}, assets)
            for collision in observed.get('collisions', []):
                pair = tuple(sorted((str(collision.get('a') or ''), str(collision.get('b') or ''))))
                if pair != ('', ''):
                    collision_pairs.add(pair)
                    try:
                        at = round(max(0.0, float(frame.get('at', 0))), 3)
                        collision_times.add(at)
                        pairs_by_time.setdefault(at, set()).add(pair)
                    except (TypeError, ValueError):
                        pass
            unknown_ids.update(str(item.get('id') or '')[:48] for item in observed.get('unknown_bounds', []))
        rows.append({
            'shot_id': str(shot.get('id') or '')[:48],
            'keyframe_count': min(24, len(frames)),
            'status': 'needs_check' if collision_pairs or unknown_ids else 'clear',
            'collision_count': min(32, len(collision_pairs)),
            'collision_pairs': [list(pair) for pair in sorted(collision_pairs)[:32]],
            'collision_times': sorted(collision_times)[:24],
            'collision_pairs_by_time': [
                {'at': at, 'pairs': [list(pair) for pair in sorted(pairs_by_time[at])[:32]]}
                for at in sorted(pairs_by_time)[:24]
            ],
            'unknown_bounds_count': min(32, len(unknown_ids)),
        })
    return {'version': 1, 'shots': rows, 'training_eligible': False}


def station_keyframe_tracks(spec):
    """Project bounded, coordinate-free object keyframe coverage tracks.

    The projection is intentionally a read-only scheduling aid. It shows
    object identities, relative time coverage, synchronized timestamps and
    duplicate-time conflicts, but never exposes transforms or provider data.
    """
    objects = [obj for obj in spec.get('objects', [])[:32]
               if obj.get('visible', True) and obj.get('kind') not in ('light', 'plane')]
    object_meta = {
        str(obj.get('id') or '')[:48]: str(obj.get('name') or obj.get('id') or '')[:80]
        for obj in objects
    }
    rows = []
    for shot in spec.get('shots', [])[:12]:
        shot_id = str(shot.get('id') or '')[:48]
        try:
            duration = max(0.0, float(shot.get('duration') or 0))
        except (TypeError, ValueError):
            duration = 0.0
        frames = shot.get('station_keyframes') if isinstance(shot.get('station_keyframes'), list) else []
        by_object = {object_id: [] for object_id in object_meta}
        for frame in frames[:24]:
            if not isinstance(frame, dict):
                continue
            object_id = str(frame.get('object_id') or '')[:48]
            if object_id not in by_object or not isinstance(frame.get('at'), (int, float)):
                continue
            at = round(max(0.0, min(duration, float(frame.get('at')))), 3)
            by_object[object_id].append(at)
        tracks = []
        missing = []
        conflicts = []
        for object_id, name in object_meta.items():
            times = sorted(by_object[object_id])
            unique = sorted(set(times))
            duplicate_times = sorted({at for at in times if times.count(at) > 1})
            if duplicate_times:
                for at in duplicate_times[:8]:
                    conflicts.append({'object_id': object_id, 'at': at})
            if not times:
                missing.append(object_id)
            tracks.append({
                'object_id': object_id,
                'name': name,
                'keyframe_count': min(24, len(times)),
                'start': unique[0] if unique else None,
                'end': unique[-1] if unique else None,
                'times': unique[:24],
                'status': 'missing' if not times else 'covered' if len(unique) > 1 else 'single',
                'conflict_count': min(8, len(duplicate_times)),
            })
        sync_groups = []
        by_time = {}
        for object_id, times in by_object.items():
            for at in sorted(set(times)):
                by_time.setdefault(at, []).append(object_id)
        for at, object_ids in sorted(by_time.items()):
            if len(object_ids) > 1:
                sync_groups.append({'at': at, 'object_ids': sorted(object_ids)[:24]})
        rows.append({
            'shot_id': shot_id,
            'duration': round(duration, 3),
            'tracks': tracks,
            'missing_object_ids': missing[:24],
            'conflicts': conflicts[:32],
            'sync_groups': sync_groups[:24],
            'training_eligible': False,
        })
    return {'version': 1, 'shots': rows, 'training_eligible': False}


def shot_at(spec, at):
    if not math.isfinite(at) or not 0<=at<=spec['duration']:raise ValueError('预演时间超出范围')
    start=0
    for i,shot in enumerate(spec['shots']):
        end=start+shot['duration']
        if at<end or i==len(spec['shots'])-1:
            return dict(shot=shot,index=i,start=start,local=max(0,min(shot['duration'],at-start)))
        start=end


def shot_note(spec, at):
    state=shot_at(spec,at);s=state['shot'];cam=s['camera']
    return (f"3D 场景预演参考，不是真实商品照片；只供构图、光照与镜头节奏参考，不能据此虚构商品结构。"
            f"镜头 {state['index']+1}：{s['name']}，全片 {state['start']:g}–{state['start']+s['duration']:g} 秒；"
            f"当前镜头内 {state['local']:g} 秒；机位视角 {cam['fov']} 度，注视点 {cam['target']}，路径点 {cam['points']}。"
            "相邻镜头按硬切预演，AI 视频对商品与轨迹的遵从仍需审阅。")[:4000]


def scene_hash(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def trajectory_manifest(spec):
    """Return a bounded, deterministic projection of the saved camera paths.

    The manifest deliberately contains no raw path coordinates.  The full scene
    remains the owner-scoped source of truth; this projection is safe to show in
    render preparation and review so every handoff can prove which trajectory
    version it refers to without treating a provider output as trajectory proof.
    """
    rows = []
    for shot in spec.get('shots', []):
        camera = shot['camera']
        path = {
            'shot_id': shot['id'],
            'duration': shot['duration'],
            'fov': camera['fov'],
            'target': camera['target'],
            'points': camera['points'],
            'closed': camera['closed'],
            'easing': camera['easing'],
        }
        path_sha256 = hashlib.sha256(
            json.dumps(path, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        length = sum(
            math.sqrt(sum((right[i] - left[i]) ** 2 for i in range(3)))
            for left, right in zip(camera['points'], camera['points'][1:])
        )
        if camera['closed'] and len(camera['points']) > 1:
            left, right = camera['points'][-1], camera['points'][0]
            length += math.sqrt(sum((right[i] - left[i]) ** 2 for i in range(3)))
        rows.append({
            'shot_id': shot['id'],
            'path_sha256': path_sha256,
            'path_points': len(camera['points']),
            'path_closed': camera['closed'],
            'path_easing': camera['easing'],
            'path_length': round(length, 4),
            'duration': shot['duration'],
        })
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()
    return {'version': 1, 'sha256': digest, 'shots': rows}


def validate_glb(raw):
    """Accept self-contained static GLB files only, with bounded resource graphs."""
    if not 20 <= len(raw) <= MAX_GLB or struct.unpack_from('<4sII', raw) != (b'glTF', 2, len(raw)):
        raise ValueError('请选择 30 MB 以内的 GLB 2.0 文件')
    size, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4E4F534A or size > 2*1024*1024 or size+20 > len(raw):
        raise ValueError('GLB 场景描述无效')
    try:
        doc = json.loads(raw[20:20+size])
        if doc.get('asset', {}).get('version') != '2.0': raise ValueError()
        def check(value, depth=0):
            if depth > 40: raise ValueError()
            if isinstance(value, dict):
                if 'uri' in value: raise ValueError('请将贴图与缓冲区嵌入 GLB，不支持外部引用')
                for v in value.values(): check(v, depth+1)
            elif isinstance(value, list):
                for v in value: check(v, depth+1)
        check(doc)
        if len(doc.get('nodes', [])) > 512 or len(doc.get('meshes', [])) > 128 or len(doc.get('images', [])) > 32:
            raise ValueError('模型结构过大，请简化后导入')
        counts = [a['count'] for a in doc.get('accessors', [])]
        if any(type(n) is not int or not 0 <= n <= 3_000_000 for n in counts) or sum(counts) > 3_000_000:
            raise ValueError('模型面数过多，请简化后导入')
        if set(doc.get('extensionsRequired', [])) - {'KHR_materials_unlit', 'KHR_lights_punctual', 'KHR_materials_clearcoat', 'KHR_materials_transmission', 'KHR_materials_ior', 'KHR_materials_specular', 'KHR_materials_volume'}:
            raise ValueError('请导出不含压缩与特殊扩展的 GLB')
        nodes = doc.get('nodes', []); visited=set(); active=set(); parents=set()
        def walk(i, depth=0):
            if type(i) is not int or not 0 <= i < len(nodes) or i in active or depth > 64: raise ValueError('模型层级无效')
            if i in visited: return
            active.add(i)
            for child in nodes[i].get('children', []):
                if child in parents: raise ValueError('模型对象不能有多个父级')
                parents.add(child);walk(child, depth+1)
            active.remove(i);visited.add(i)
        for i in range(len(nodes)): walk(i)
        for scene in doc.get('scenes', []):
            for i in scene.get('nodes', []):
                if type(i) is not int or not 0 <= i < len(nodes): raise ValueError('场景对象无效')
        if not doc.get('meshes'): raise ValueError('GLB 中没有可见模型')
        bounds_status, bounds = _glb_position_bounds(doc)
    except (TypeError, KeyError, AttributeError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('无法读取 GLB 场景结构') from exc
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'nodes': len(doc.get('nodes', [])),
            'bounds_status': bounds_status, 'bounds': bounds}


def _glb_position_bounds(doc):
    """Read optional JSON accessor bounds without decoding arbitrary GLB data.

    Exporters are allowed to omit accessor min/max, so omission is reported as
    unknown.  Values that are present but malformed are rejected instead of
    being used to make a placement decision from untrusted metadata.
    """
    accessors = doc.get('accessors', [])
    meshes = doc.get('meshes', [])
    mesh_bounds = {}
    for mesh_index, mesh in enumerate(meshes):
        primitives = mesh.get('primitives', [])
        if not isinstance(primitives, list) or not primitives:
            return 'unknown', None
        mins = []
        maxs = []
        for primitive in primitives:
            attributes = primitive.get('attributes', {})
            if not isinstance(attributes, dict) or 'POSITION' not in attributes:
                return 'unknown', None
            index = attributes.get('POSITION')
            if type(index) is not int or not 0 <= index < len(accessors):
                raise ValueError('GLB POSITION 访问器无效')
            accessor = accessors[index]
            if not isinstance(accessor, dict):
                raise ValueError('GLB POSITION 访问器无效')
            lower, upper = accessor.get('min'), accessor.get('max')
            if lower is None or upper is None:
                return 'unknown', None
            if accessor.get('type', 'VEC3') != 'VEC3':
                raise ValueError('GLB POSITION 边界必须是三维向量')
            if (not isinstance(lower, list) or not isinstance(upper, list) or
                    len(lower) != 3 or len(upper) != 3):
                raise ValueError('GLB POSITION 边界无效')
            try:
                lo = [float(value) for value in lower]
                hi = [float(value) for value in upper]
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError('GLB POSITION 边界无效') from exc
            if (any(not math.isfinite(value) or abs(value) > 100000 for value in lo + hi) or
                    any(lo[axis] > hi[axis] for axis in range(3))):
                raise ValueError('GLB POSITION 边界无效')
            mins.append(lo)
            maxs.append(hi)
        mesh_bounds[mesh_index] = (
            [min(row[axis] for row in mins) for axis in range(3)],
            [max(row[axis] for row in maxs) for axis in range(3)],
        )

    def multiply(left, right):
        return [sum(left[row * 4 + index] * right[index * 4 + column] for index in range(4))
                for row in range(4) for column in range(4)]

    def finite_vector(node, key, length, limit, default):
        value = node.get(key, default)
        if not isinstance(value, list) or len(value) != length:
            raise ValueError(f'GLB 节点 {key} 变换无效')
        try:
            values = [float(item) for item in value]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f'GLB 节点 {key} 变换无效') from exc
        if any(not math.isfinite(item) or abs(item) > limit for item in values):
            raise ValueError(f'GLB 节点 {key} 变换无效')
        return values

    def local_matrix(node):
        if 'matrix' in node:
            matrix = finite_vector(node, 'matrix', 16, 100000, [])
            return [matrix[row + column * 4] for row in range(4) for column in range(4)]
        translation = finite_vector(node, 'translation', 3, 100000, [0, 0, 0])
        rotation = finite_vector(node, 'rotation', 4, 1.1, [0, 0, 0, 1])
        scale = finite_vector(node, 'scale', 3, 1000, [1, 1, 1])
        x, y, z, w = rotation
        rotation_matrix = [
            1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0,
            2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0,
            2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0,
            0, 0, 0, 1,
        ]
        scale_matrix = [scale[0], 0, 0, 0, 0, scale[1], 0, 0, 0, 0, scale[2], 0, 0, 0, 0, 1]
        result = multiply(rotation_matrix, scale_matrix)
        result[3], result[7], result[11] = translation
        return result

    nodes = doc.get('nodes', [])
    parents = {}
    for parent_index, node in enumerate(nodes):
        for child in node.get('children', []):
            if type(child) is not int or not 0 <= child < len(nodes):
                raise ValueError('模型层级无效')
            parents[child] = parent_index
    local = [local_matrix(node) for node in nodes]
    world_cache = {}

    def world_matrix(index):
        if index in world_cache:
            return world_cache[index]
        parent = parents.get(index)
        matrix = local[index] if parent is None else multiply(world_matrix(parent), local[index])
        world_cache[index] = matrix
        return matrix

    mins = []
    maxs = []
    for node_index, node in enumerate(nodes):
        if 'mesh' not in node:
            continue
        mesh_index = node.get('mesh')
        if type(mesh_index) is not int or mesh_index not in mesh_bounds:
            raise ValueError('GLB 节点模型引用无效')
        lower, upper = mesh_bounds[mesh_index]
        corners = [[x, y, z] for x in (lower[0], upper[0])
                   for y in (lower[1], upper[1]) for z in (lower[2], upper[2])]
        matrix = world_matrix(node_index)
        transformed = []
        for x, y, z in corners:
            values = [x, y, z, 1]
            transformed.append([
                sum(matrix[row * 4 + column] * values[column] for column in range(4))
                for row in range(3)
            ])
        mins.extend(transformed)
        maxs.extend(transformed)
    if not mins:
        return 'unknown', None
    lower = [min(row[axis] for row in mins) for axis in range(3)]
    upper = [max(row[axis] for row in maxs) for axis in range(3)]
    if any(not math.isfinite(value) or abs(value) > 100000 for value in lower + upper):
        raise ValueError('GLB 节点变换超出范围')
    return 'available', {'min': lower, 'max': upper, 'size': [upper[i] - lower[i] for i in range(3)]}
