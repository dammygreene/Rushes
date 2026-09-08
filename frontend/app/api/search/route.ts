/**
 * Server-side proxy to the FastAPI backend.
 *
 * The browser never talks to the backend directly: BACKEND_URL and API_TOKEN
 * stay on the server, which also means no CORS dance and no token in devtools.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8080";
const API_TOKEN = process.env.API_TOKEN ?? "";

// Four sources in parallel plus a planning call: slow, but bounded.
const TIMEOUT_MS = 75_000;

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: "expected a JSON body" }, { status: 400 });
  }

  const { query, limit } = (body ?? {}) as { query?: unknown; limit?: unknown };
  if (typeof query !== "string" || query.trim().length === 0) {
    return Response.json({ detail: "query is required" }, { status: 400 });
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_TOKEN) headers.Authorization = `Bearer ${API_TOKEN}`;

  try {
    const upstream = await fetch(`${BACKEND_URL}/api/search`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        query: query.trim().slice(0, 400),
        limit: typeof limit === "number" ? limit : null,
      }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });

    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    // A dead backend is the most likely demo failure, so say so plainly.
    const detail =
      error instanceof Error && error.name === "TimeoutError"
        ? "the search backend timed out"
        : `cannot reach the search backend at ${BACKEND_URL}`;
    return Response.json({ detail }, { status: 502 });
  }
}
