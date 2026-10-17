import benchmark from "../../../data/tvc-benchmark.json";

const MEDIA: Record<string, string> = {
  "visualagent-gpu-15s-v2.mp4": "/case-assets/productions__pilot_ads_15s_v1__renders__visualagent-gpu-15s-v2.mp4",
  "visualagent-phone-15s-v2.mp4": "/case-assets/productions__pilot_ads_15s_v1__renders__visualagent-phone-15s-v2.mp4",
  "visualagent-mobility-15s-v2.mp4": "/case-assets/productions__pilot_ads_15s_v1__renders__visualagent-mobility-15s-v2.mp4",
  ...Object.fromEntries(benchmark.cases.filter(item => item.video).map(item => [
    `${item.id}-attempt-01.mp4`, `/tvc/${item.id}-attempt-01.mp4`,
  ])),
};

function rangeBounds(header: string | null, size: number): [number, number] | null {
  if (!header) return null;
  const match = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!match) return null;
  const [, startText, endText] = match;
  if (!startText && !endText) return null;
  if (!startText) {
    const suffix = Number(endText);
    if (!Number.isFinite(suffix) || suffix <= 0) return null;
    return [Math.max(0, size - suffix), size - 1];
  }
  const start = Number(startText);
  const end = endText ? Math.min(Number(endText), size - 1) : size - 1;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || start >= size || end < start) return null;
  return [start, end];
}

export async function GET(
  request: Request,
  context: { params: Promise<{ name: string }> },
) {
  const { name } = await context.params;
  const mediaPath = MEDIA[name];
  if (!mediaPath) return new Response("Not found", { status: 404 });

  const source = await fetch(new URL(mediaPath, request.url));
  if (!source.ok) return new Response("Media unavailable", { status: 502 });
  const bytes = new Uint8Array(await source.arrayBuffer());
  const headers = new Headers({
    "Accept-Ranges": "bytes",
    "Cache-Control": "public, max-age=31536000, immutable",
    "Content-Type": "video/mp4",
  });
  const bounds = rangeBounds(request.headers.get("range"), bytes.byteLength);
  if (!bounds) {
    headers.set("Content-Length", String(bytes.byteLength));
    return new Response(bytes, { status: 200, headers });
  }

  const [start, end] = bounds;
  const chunk = bytes.slice(start, end + 1);
  headers.set("Content-Length", String(chunk.byteLength));
  headers.set("Content-Range", `bytes ${start}-${end}/${bytes.byteLength}`);
  return new Response(chunk, { status: 206, headers });
}
