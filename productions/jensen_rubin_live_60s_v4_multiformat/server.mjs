import { createReadStream } from "node:fs";
import { realpath, stat } from "node:fs/promises";
import { createServer, request as httpRequest } from "node:http";
import { connect as netConnect } from "node:net";
import { extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL(".", import.meta.url)));
const migratedAssetRoot = resolve(root, "../jensen_rubin_live_60s_v3_tiktok_text/assets");
const allowedRoots = [root, migratedAssetRoot];
const port = Number(process.env.PORT || 3005);
const host = process.env.HOST || "127.0.0.1";
const studioHost = "127.0.0.1";
const studioPort = 50442;
const types = { ".html":"text/html; charset=utf-8", ".js":"text/javascript; charset=utf-8", ".css":"text/css; charset=utf-8", ".json":"application/json; charset=utf-8", ".png":"image/png", ".svg":"image/svg+xml", ".mp4":"video/mp4", ".m4a":"audio/mp4", ".ttf":"font/ttf" };

function insideAllowed(path) {
  return allowedRoots.some(base => path === base || path.startsWith(`${base}${sep}`));
}

function sendError(response, status, message) {
  response.writeHead(status, { "content-type":"text/plain; charset=utf-8", "cache-control":"no-store" });
  response.end(message);
}

function isPreviewPath(pathname) {
  return pathname === "/versions" || pathname.startsWith("/versions/") || pathname === "/viewer.html"
    || pathname.startsWith("/portrait-zh/") || pathname.startsWith("/portrait-en/")
    || pathname.startsWith("/landscape-zh/") || pathname.startsWith("/landscape-en/")
    || pathname.startsWith("/assets/fonts/");
}

function proxyStudio(request, response) {
  const upstream = httpRequest({
    hostname: studioHost,
    port: studioPort,
    method: request.method,
    path: request.url,
    headers: { ...request.headers, host: `${studioHost}:${studioPort}` },
  }, upstreamResponse => {
    response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
    upstreamResponse.pipe(response);
  });
  upstream.on("error", () => sendError(response, 502, "Asset Studio is starting"));
  request.pipe(upstream);
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
    let pathname = decodeURIComponent(url.pathname);
    if (!isPreviewPath(pathname)) return proxyStudio(request, response);
    if (pathname === "/versions") {
      response.writeHead(302, { location: "/versions/" });
      return response.end();
    }
    if (pathname.startsWith("/versions/")) pathname = `/${pathname.slice("/versions/".length)}`;
    if (pathname.endsWith("/")) pathname += "index.html";
    const candidate = pathname.startsWith("/assets/")
      ? join(migratedAssetRoot, normalize(pathname.slice("/assets/".length)).replace(/^(\.\.[/\\])+/, ""))
      : join(root, normalize(pathname).replace(/^(\.\.[/\\])+/, ""));
    const target = await realpath(candidate);
    if (!insideAllowed(target)) return sendError(response, 403, "Forbidden");
    const info = await stat(target);
    if (!info.isFile()) return sendError(response, 404, "Not found");
    const headers = { "content-type":types[extname(target).toLowerCase()] || "application/octet-stream", "accept-ranges":"bytes", "cache-control":"no-store" };
    const range = request.headers.range;
    if (range) {
      const match = /^bytes=(\d*)-(\d*)$/.exec(range);
      if (!match) return sendError(response, 416, "Invalid range");
      const start = match[1] ? Number(match[1]) : 0;
      const end = match[2] ? Math.min(Number(match[2]), info.size - 1) : info.size - 1;
      if (start > end || start >= info.size) { response.writeHead(416, { "content-range":`bytes */${info.size}` }); return response.end(); }
      response.writeHead(206, { ...headers, "content-length":end-start+1, "content-range":`bytes ${start}-${end}/${info.size}` });
      if (request.method === "HEAD") return response.end();
      return createReadStream(target, { start, end }).pipe(response);
    }
    response.writeHead(200, { ...headers, "content-length":info.size });
    if (request.method === "HEAD") return response.end();
    createReadStream(target).pipe(response);
  } catch (error) {
    sendError(response, error?.code === "ENOENT" ? 404 : 500, error?.code === "ENOENT" ? "Not found" : "Server error");
  }
});

server.on("upgrade", (request, socket, head) => {
  const upstream = netConnect(studioPort, studioHost, () => {
    const headers = Object.entries({ ...request.headers, host: `${studioHost}:${studioPort}` })
      .map(([name, value]) => `${name}: ${Array.isArray(value) ? value.join(", ") : value}`)
      .join("\r\n");
    upstream.write(`${request.method} ${request.url} HTTP/${request.httpVersion}\r\n${headers}\r\n\r\n`);
    if (head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.on("error", () => socket.destroy());
});

server.listen(port, host, () => console.log(`VisualAgent workbench gateway ready at http://${host}:${port}/`));
