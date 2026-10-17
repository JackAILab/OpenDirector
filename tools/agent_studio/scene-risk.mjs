function stationPositionAt(sourceShot, object, at) {
  const base = (object.position || [0, 0, 0]).map(Number);
  const frames = (sourceShot?.station_keyframes || [])
    .filter(frame => frame.object_id === object.id)
    .sort((a, b) => Number(a.at) - Number(b.at));
  if (!frames.length || at < Number(frames[0].at)) return base;
  const rightIndex = frames.findIndex(frame => Number(frame.at) >= at);
  if (rightIndex === 0) return (frames[0].position || base).map(Number);
  const left = rightIndex < 0 ? frames.at(-1) : frames[rightIndex - 1];
  const right = rightIndex < 0 ? left : frames[rightIndex];
  const span = Math.max(.001, Number(right.at) - Number(left.at));
  const ratio = right === left ? 0 : Math.max(0, Math.min(1, (at - Number(left.at)) / span));
  return base.map((value, index) => {
    const leftValue = Number(left.position?.[index] ?? value);
    const rightValue = Number(right.position?.[index] ?? value);
    return leftValue + (rightValue - leftValue) * ratio;
  });
}

function stationAabb(object, position) {
  if (['light', 'plane', 'glb'].includes(object.kind)) return null;
  const scale = (object.scale || [1, 1, 1]).map(value => Math.abs(Number(value) || 1));
  const radius = .5 * scale[0], height = .5 * scale[1], depth = .5 * scale[2];
  return {
    min: [position[0] - radius, position[1] - height, position[2] - depth],
    max: [position[0] + radius, position[1] + height, position[2] + depth],
  };
}

function stationAabbOverlap(left, right) {
  return left && right && [0, 1, 2].every(axis =>
    Math.min(left.max[axis], right.max[axis]) - Math.max(left.min[axis], right.min[axis]) > 1e-4);
}

/** Group repeated primitive object pairs into bounded, coordinate-free risk intervals. */
export function aggregateRiskPairs(points = [], duration = 0) {
  const rows = [];
  const sorted = points.slice().sort((left, right) => Number(left.at) - Number(right.at));
  const step = sorted.length > 1
    ? Math.max(.001, (Number(duration) || Number(sorted.at(-1)?.at) || 0) / Math.max(1, sorted.length - 1))
    : Math.max(.001, Number(duration) || 1);
  for (const point of sorted) {
    for (const pair of point.pairs || []) {
      if (!Array.isArray(pair) || pair.length !== 2) continue;
      const ordered = pair.map(String).sort();
      const key = ordered.join(':');
      const at = Number(point.at) || 0;
      const start = Math.max(0, at - step / 2);
      const end = Math.min(Math.max(0, Number(duration) || at + step / 2), at + step / 2);
      const previous = [...rows].reverse().find(row => row.key === key);
      if (previous && start <= previous.end + .001) {
        previous.end = end;
        previous.samples += 1;
        previous.peak = Math.max(previous.peak, Number(point.count) || 0);
      } else {
        rows.push({key, pair: ordered, start, end, samples: 1, peak: Number(point.count) || 0});
      }
    }
  }
  return rows.map(({key, ...row}) => row).sort((left, right) => left.start - right.start || left.pair.join(':').localeCompare(right.pair.join(':')));
}

/** Read-only, bounded station risk sampling. It never edits the scene. */
export function sampleStationRisk(source, currentShot, duration, assets = {}) {
  if (!source || !currentShot) return {intervals: [], peak: 0, unknown: 0, samples: 0, points: [], pairIntervals: []};
  const objects = (source.objects || []).filter(object => object.visible !== false && !['light', 'plane'].includes(object.kind));
  const sourceShot = source.shots?.find(item => item.id === currentShot.id) || currentShot;
  const samples = 17;
  const step = duration / Math.max(1, samples - 1);
  const flags = [], counts = [], pairSamples = [];
  const unknown = objects.filter(object => object.kind === 'glb' && !assets?.[object.asset]?.bounds_status).length;
  for (let index = 0; index < samples; index++) {
    const at = step * index;
    const boxes = objects.map(object => ({object, box: stationAabb(object, stationPositionAt(sourceShot, object, at))})).filter(item => item.box);
    const seen = [];
    for (let left = 0; left < boxes.length; left++) {
      for (let right = left + 1; right < boxes.length; right++) {
        if (stationAabbOverlap(boxes[left].box, boxes[right].box)) seen.push(`${boxes[left].object.id}:${boxes[right].object.id}`);
      }
    }
    flags.push(Boolean(seen.length));
    counts.push(seen.length);
    pairSamples.push(seen.map(pair => pair.split(':')));
  }
  const intervals = [];
  for (let index = 0; index < flags.length; index++) {
    if (!flags[index]) continue;
    const start = Math.max(0, index === 0 ? 0 : (index - .5) * step);
    const end = Math.min(duration, index === flags.length - 1 ? duration : (index + .5) * step);
    const last = intervals.at(-1);
    if (last && start <= last.end + .001) last.end = end;
    else intervals.push({start, end});
  }
  const points = counts.map((count, index) => ({at: step * index, count, pairs: pairSamples[index]}));
  return {intervals, peak: Math.max(0, ...counts), unknown, samples, points, pairIntervals: aggregateRiskPairs(points, duration)};
}
