import { env } from "cloudflare:workers";

type IterationRow = {
  id: string;
  case_id: string;
  asset_id: string;
  playhead: number;
  instruction: string;
  status: string;
  paid_generation_allowed: number;
  created_at: string;
};

async function ensureSchema() {
  const db = env.DB;
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS iteration_requests (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      case_id TEXT NOT NULL,
      asset_id TEXT NOT NULL,
      playhead REAL NOT NULL DEFAULT 0,
      instruction TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued',
      paid_generation_allowed INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    )`),
    db.prepare("CREATE INDEX IF NOT EXISTS iteration_requests_owner_case_created_idx ON iteration_requests (user_id, case_id, created_at)"),
  ]);
}

function requestUserId(request: Request) {
  const supplied = request.headers.get("oai-authenticated-user-id");
  if (supplied) return supplied;
  const hostname = new URL(request.url).hostname;
  return hostname === "localhost" || hostname === "127.0.0.1" ? "local-owner" : null;
}

function serialize(row: IterationRow) {
  return {
    id: row.id,
    assetId: row.asset_id,
    playhead: row.playhead,
    text: row.instruction,
    status: row.status,
    paidGenerationAllowed: Boolean(row.paid_generation_allowed),
    createdAt: row.created_at,
  };
}

export async function GET(request: Request) {
  const userId = requestUserId(request);
  if (!userId) return Response.json({ error: "sign-in required" }, { status: 401 });
  const caseId = new URL(request.url).searchParams.get("caseId")?.trim();
  if (!caseId) return Response.json({ error: "caseId is required" }, { status: 400 });

  await ensureSchema();
  const result = await env.DB.prepare(`SELECT id, case_id, asset_id, playhead, instruction, status,
      paid_generation_allowed, created_at
    FROM iteration_requests
    WHERE user_id = ? AND case_id = ?
    ORDER BY created_at ASC
    LIMIT 100`).bind(userId, caseId).all<IterationRow>();
  return Response.json({ iterations: result.results.map(serialize) });
}

export async function POST(request: Request) {
  const userId = requestUserId(request);
  if (!userId) return Response.json({ error: "sign-in required" }, { status: 401 });
  const payload = await request.json() as { caseId?: string; assetId?: string; playhead?: number; text?: string };
  const caseId = payload.caseId?.trim() ?? "";
  const assetId = payload.assetId?.trim() ?? "";
  const instruction = payload.text?.trim() ?? "";
  const playhead = Number.isFinite(payload.playhead) ? Math.max(0, Number(payload.playhead)) : 0;
  if (!caseId || !assetId || !instruction) return Response.json({ error: "caseId, assetId and text are required" }, { status: 400 });
  if (instruction.length > 2000) return Response.json({ error: "instruction is too long" }, { status: 400 });

  await ensureSchema();
  const iteration = {
    id: crypto.randomUUID(), caseId, assetId, playhead, text: instruction,
    status: "queued", paidGenerationAllowed: false, createdAt: new Date().toISOString(),
  };
  await env.DB.prepare(`INSERT INTO iteration_requests
    (id, user_id, case_id, asset_id, playhead, instruction, status, paid_generation_allowed, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, ?)`)
    .bind(iteration.id, userId, caseId, assetId, playhead, instruction, iteration.createdAt).run();
  return Response.json({ iteration }, { status: 201 });
}

export async function DELETE(request: Request) {
  const userId = requestUserId(request);
  if (!userId) return Response.json({ error: "sign-in required" }, { status: 401 });
  const id = new URL(request.url).searchParams.get("id")?.trim();
  if (!id) return Response.json({ error: "id is required" }, { status: 400 });
  await ensureSchema();
  await env.DB.prepare("DELETE FROM iteration_requests WHERE id = ? AND user_id = ?").bind(id, userId).run();
  return Response.json({ deleted: true });
}
