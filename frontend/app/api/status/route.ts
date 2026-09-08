/**
 * Proxy for the backend's wiring report, used by the header strip.
 *
 * It is the honest answer to "is ClickHouse really being queried?" — the count
 * it reports comes back over the mcp-clickhouse stdio server.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8080";
const API_TOKEN = process.env.API_TOKEN ?? "";

export async function GET() {
  const headers: Record<string, string> = {};
  if (API_TOKEN) headers.Authorization = `Bearer ${API_TOKEN}`;

  try {
    const upstream = await fetch(`${BACKEND_URL}/api/status`, {
      headers,
      signal: AbortSignal.timeout(30_000),
      cache: "no-store",
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return Response.json(
      { detail: `cannot reach the search backend at ${BACKEND_URL}` },
      { status: 502 },
    );
  }
}
