const url = process.env.ASSET_STUDIO_URL || "http://127.0.0.1:50442/";
const mediaUrl = process.env.ASSET_STUDIO_MEDIA_URL || new URL(
  "/api/media/visualagent-gpu-15s-v2.mp4",
  url,
).href;
const versionsUrl = new URL("/versions", url).href;
const cybercabUrl = new URL("/cybercab", url).href;
const iphone18Url = new URL("/iphone18?variant=portrait-zh", url).href;
const iphone18EnUrl = new URL("/iphone18?variant=portrait-en", url).href;
const iphone18PrototypeUrl = new URL("/iphone18-live/index.html?variant=portrait-zh", url).href;
const legacyViewerUrl = new URL("/viewer.html?v=portrait-zh", url).href;
const deadline = Date.now() + Number(process.env.ASSET_STUDIO_HEALTH_TIMEOUT_MS || 30000);
let lastError;
while (Date.now() < deadline) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const body = await response.text();
    const studioReady = response.ok && body.includes("VisualAgent 广告制作台");
    const versionsResponse = await fetch(versionsUrl, { signal: controller.signal });
    const versionsBody = await versionsResponse.text();
    const versionsReady = versionsResponse.ok
      && versionsBody.includes("visualagent-versions-v1")
      && versionsBody.includes('href="/cybercab"')
      && versionsBody.includes('href="/iphone18?variant=portrait-zh"')
      && ["portrait-zh", "portrait-en", "landscape-zh", "landscape-en"]
        .every(variant => versionsBody.includes(`/?variant=${variant}`));
    const cybercabResponse = await fetch(cybercabUrl, { signal: controller.signal });
    const cybercabBody = await cybercabResponse.text();
    const cybercabReady = cybercabResponse.ok
      && cybercabBody.includes('data-studio="visualagent-canvas-v3"')
      && cybercabBody.includes("Cybercab")
      && cybercabBody.includes("training_eligible=false");
    const iphone18Response = await fetch(iphone18Url, { signal: controller.signal });
    const iphone18Body = await iphone18Response.text();
    const iphone18EnResponse = await fetch(iphone18EnUrl, { signal: controller.signal });
    const iphone18EnBody = await iphone18EnResponse.text();
    const iphone18PrototypeResponse = await fetch(iphone18PrototypeUrl, { signal: controller.signal });
    const iphone18PrototypeBody = await iphone18PrototypeResponse.text();
    const iphone18Ready = iphone18Response.ok
      && iphone18EnResponse.ok
      && iphone18PrototypeResponse.ok
      && iphone18Body.includes('data-studio="visualagent-iphone18-canvas-v1"')
      && iphone18EnBody.includes("English Portrait")
      && iphone18PrototypeBody.includes('data-composition-id="iphone18-concept-live-60s-v1"');
    const legacyViewerResponse = await fetch(legacyViewerUrl, {
      redirect: "manual",
      signal: controller.signal,
    });
    const legacyViewerLocation = legacyViewerResponse.headers.get("location") || "";
    const legacyViewerReady = legacyViewerResponse.status === 302
      && new URL(legacyViewerLocation, url).pathname === "/"
      && new URL(legacyViewerLocation, url).searchParams.get("variant") === "portrait-zh";
    const mediaResponse = await fetch(mediaUrl, {
      headers: { Range: "bytes=0-1023" },
      signal: controller.signal,
    });
    const mediaType = mediaResponse.headers.get("content-type") || "";
    const acceptRanges = mediaResponse.headers.get("accept-ranges") || "";
    const contentRange = mediaResponse.headers.get("content-range") || "";
    await mediaResponse.arrayBuffer();
    const mediaReady = mediaResponse.status === 206
      && /^video\/mp4\b/i.test(mediaType)
      && /^bytes$/i.test(acceptRanges)
      && /^bytes 0-1023\//i.test(contentRange);
    if (studioReady && versionsReady && cybercabReady && iphone18Ready && legacyViewerReady && mediaReady) {
      console.log(JSON.stringify({
        ok: true,
        url,
        status: response.status,
        versionsUrl,
        versionsStatus: versionsResponse.status,
        cybercabUrl,
        cybercabStatus: cybercabResponse.status,
        iphone18Url,
        iphone18Status: iphone18Response.status,
        iphone18EnUrl,
        iphone18EnStatus: iphone18EnResponse.status,
        iphone18PrototypeUrl,
        iphone18PrototypeStatus: iphone18PrototypeResponse.status,
        legacyViewerStatus: legacyViewerResponse.status,
        legacyViewerLocation,
        mediaUrl,
        mediaStatus: mediaResponse.status,
        mediaType,
        acceptRanges,
        contentRange,
      }));
      process.exit(0);
    }
    lastError = new Error(
      `unhealthy response: status=${response.status}, studio=${studioReady}, versions=${versionsReady}, versions_status=${versionsResponse.status}, cybercab=${cybercabReady}, cybercab_status=${cybercabResponse.status}, iphone18=${iphone18Ready}, iphone18_status=${iphone18Response.status}, legacy_viewer=${legacyViewerReady}, legacy_viewer_status=${legacyViewerResponse.status}, media_status=${mediaResponse.status}, media_type=${mediaType}, accept_ranges=${acceptRanges}, content_range=${contentRange}`,
    );
  } catch (error) {
    lastError = error;
  } finally {
    clearTimeout(timer);
  }
  await new Promise(resolve => setTimeout(resolve, 500));
}
throw lastError || new Error(`Asset Studio did not become healthy: ${url}`);
