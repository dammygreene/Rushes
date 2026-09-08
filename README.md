# Rushes

**Describe the shot. Get the clip.**

Rushes is natural-language video search across two worlds at once: the footage
you already own, and the footage you are allowed to use. Type

> *a lone figure on a rain-slicked neon street*

and one planned query fans out to four sources in parallel — your private
archive (vector search in ClickHouse), YouTube, the Internet Archive and
Pexels — then comes back as a single ranked grid where every card says **where
it came from** and **why it matched**.

Built for the Google Agentic Cinema Hackathon, ClickHouse track. MIT licensed.

---

## How it works

```
      "a lone figure on a rain-slicked neon street"
                        │
        ┌───────────────▼────────────────┐
        │  shot_planner  (ADK LlmAgent)  │   Gemini 2.5 Flash, structured
        │  → SearchPlan (JSON schema)    │   output: archive_query, web_query,
        └───────────────┬────────────────┘   keywords, mood, shot_type, sources
                        │
        ┌───────────────▼────────────────┐
        │  source_fanout  (ADK BaseAgent)│   four FunctionTools, asyncio.gather,
        └──┬──────┬──────────┬───────┬───┘   30 s budget per tool
           │      │          │       │
      ┌────▼──┐ ┌─▼──────┐ ┌─▼─────┐ ┌▼──────┐
      │archive│ │youtube │ │archive│ │pexels │
      │       │ │        │ │  .org │ │       │
      │Gemini │ │ Data   │ │ adv.  │ │videos │
      │embed →│ │ API v3 │ │search │ │search │
      │MCP →  │ └────────┘ └───────┘ └───────┘
      │Click- │      link out only, never rehosted
      │House  │
      └───┬───┘
          │  cosineDistance(embedding, [...]) ORDER BY distance ASC
          │
   ┌──────▼───────────────────────────────────────────┐
   │ merge: dedupe → score → interleave → explain     │
   └──────┬───────────────────────────────────────────┘
          │
   one ranked list, per-source health, "why this matched" on every card
```

Four steps, and each one is visible in the UI:

1. **Plan.** An ADK `LlmAgent` with `output_schema=SearchPlan` rewrites the
   sentence twice — a dense visual sentence for embedding, a 2–6 word keyword
   query for web APIs — and decides which sources are worth asking.
2. **Fan out.** Four ADK `FunctionTool`s run concurrently. A dead API degrades
   its own lane of the grid instead of failing the search.
3. **Merge.** Dedupe by URL, score each stream, interleave so every source shows
   near the top, cap at `RESULT_LIMIT`.
4. **Explain.** One batched Gemini call writes the "why this matched" line;
   deterministic keyword overlap is the fallback and never lies.

### The fan-out is code, not a second LLM turn

Deliberate: four parallel calls cost as long as the slowest source, the ordering
is reproducible on stage, and a broken API degrades one section of the grid
rather than derailing the agent mid-conversation. The tools are still ADK
`FunctionTool`s, invoked with a real ADK `ToolContext` inside an ADK
`SequentialAgent` — the planning that benefits from a model is done by a model,
and the plumbing that benefits from determinism is not.

---

## ClickHouse is queried through the real MCP server

The archive lane does not use a ClickHouse client library. It speaks
[MCP](https://modelcontextprotocol.io) over stdio to the real
[`mcp-clickhouse`](https://github.com/ClickHouse/mcp-clickhouse) server, which
runs as a subprocess and only accepts `SELECT`:

```
rushes.tools.archive
  └─ embed_query()                      Gemini gemini-embedding-001, 768-d,
  │                                     task_type=RETRIEVAL_DOCUMENT
  └─ ClickHouseMcpClient.vector_search()
       └─ MCP stdio session → mcp-clickhouse → ClickHouse Cloud
            SELECT clip_id, title, …,
                   cosineDistance(embedding, [0.013,-0.041,…]) AS distance
            FROM default.archive_clips
            WHERE length(embedding) = 768
            ORDER BY distance ASC LIMIT 8
            SETTINGS max_execution_time = 20
```

Similarity is `1 - distance`; anything past `MAX_DISTANCE = 0.75` is dropped
rather than padded into the grid. `GET /api/status` proves the path end to end by
returning the MCP handshake info plus a live `count()` of your clips — the number
in the header strip travelled over MCP.

The one thing MCP does *not* do here is write. Table creation and the seeding
`INSERT` use `clickhouse-connect` directly, in
[`clickhouse/direct.py`](backend/src/rushes/clickhouse/direct.py), because the
MCP server is read-only by design. Every read on the search path goes through
MCP.

### Schema

```sql
CREATE TABLE IF NOT EXISTS default.archive_clips (
    clip_id UUID DEFAULT generateUUIDv4(),
    title String,
    description String,
    tags Array(String),
    embedding Array(Float32),
    duration_seconds UInt16,
    thumbnail_url String,
    clip_url String,
    source String DEFAULT 'archive',
    license String DEFAULT 'owned',
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY clip_id
```

---

## We never rehost anyone else's video

This is enforced in code, not just promised in a README:

| Source | What we store | What the UI does |
| --- | --- | --- |
| **Your archive** | The clip file in `data/clips/`, its caption and its embedding | Plays inline (`hosted_by_us: true`) |
| **YouTube** | Nothing | Thumbnail + title + link to `youtube.com/watch?v=…` |
| **Internet Archive** | Nothing | Thumbnail + title + link to the details page |
| **Pexels** | Nothing | Thumbnail + title + link to the Pexels page |

Only archive hits ever carry a `clip_url`, and only `hosted_by_us` hits get a
`<video>` element. Third-party thumbnails are hotlinked with a plain `<img>` —
routing them through `next/image` would cache other people's media on our
servers, so that ESLint rule is switched off on purpose. Licence strings are
carried through from each source, and the Internet Archive tool says out loud
when it had to widen past Creative-Commons-only collections
("*widened past CC-only collections; check rights on the source page*").

Saving a shot keeps only what its card already showed — id, title, thumbnail
URL, page URL, licence. The same rule is re-applied on the way back out of the
browser's store (`reviveHit` in `frontend/lib/store.ts`), so a hand-edited
`localStorage` still cannot turn someone else's clip into a playable one.

---

## What the browser remembers

Rushes has no accounts and no session table. The query lives in the URL
(`/?q=…`), so every search is a real history entry and the back button does what
it says. Past searches and saved shots are kept in `localStorage` under
`rushes.history.v1` and `rushes.saved.v1`:

- **`/history`** — the last 12 searches, each with its whole response. Reopening
  one is a lookup in the browser rather than two more Gemini calls, which is also
  what makes stepping back through them free. A restored screen says where it
  came from and offers *Search again*.
- **`/saved`** — a contact sheet of the frames you marked with **Save**, each one
  still linked to the search it came out of.

Nothing on the server knows about either list, and each page has one control
that empties it.

---

## Quick start

**Prerequisites:** Python 3.12, Node 20.9+, a
[ClickHouse Cloud](https://clickhouse.com/cloud) service, and a Gemini API key
from [AI Studio](https://aistudio.google.com/apikey). YouTube and Pexels keys are
optional for *searching* — those lanes report themselves as offline without them
— but a Pexels key is what builds the sample archive during seeding.

```bash
git clone <your fork> rushes && cd rushes

bash scripts/setup.sh          # macOS / Linux
pwsh -File scripts/setup.ps1   # Windows
```

The setup script creates **two** virtualenvs, which is not an accident:

- `backend/.venv` — the app. `google-adk[mcp]` pins `mcp<2`.
- `mcp-server/.venv` — the `mcp-clickhouse` server, which needs `fastmcp>=4` and
  therefore `mcp>=2`.

They cannot share a `site-packages`. Since the server is a subprocess spoken to
over stdio, an isolated interpreter costs nothing at runtime. `Settings.mcp_command()`
finds it automatically, or falls back to `uvx mcp-clickhouse`.

Then fill in `.env` (copied from [`.env.example`](.env.example), which documents
every variable) and build the archive:

```bash
cd backend
.venv/bin/python -m rushes.pipeline.create_schema   # CREATE TABLE
.venv/bin/python -m rushes.pipeline.seed            # fetch → caption → embed → INSERT
.venv/bin/rushes-doctor                             # verify every dependency for real
```

On Windows the interpreter is `.venv\Scripts\python.exe` and the console scripts
are `.venv\Scripts\rushes-doctor.exe` / `rushes-api.exe`.

> **The clips are already here.** This repository ships the 20 seeded clips in
> `data/clips/` and their Gemini captions in `data/captions/`, so you can build
> and deploy without spending Pexels or Gemini quota. `create_schema` and `seed`
> are still required once — they are what put the embeddings into *your*
> ClickHouse service — but the caption cache means seeding re-embeds rather than
> re-watching, which is the expensive half. Five of the clips predate the caption
> cache and will be captioned on first seed.

### What seeding actually does

`PEXELS_API_KEY` is required here even though the Pexels *search* lane is
optional: seeding is what builds the sample archive.

1. **Fetch** — ten stock queries × 2 clips, downloaded at ≤1280px into
   `data/clips/`. These files stand in for an editor's own rushes; they are the
   one source Rushes hosts, so the demo has something to play. Point
   `data/clips` at real footage and re-run the seed — nothing else changes.
2. **Caption** — Gemini *watches each video* (inline bytes under 18 MB, Files API
   above that) and returns a `ClipCaption` via `response_schema`: title,
   description, 5–10 editor-style tags, mood, setting, objects. Cached in
   `data/captions/`, so re-seeding is free. A failed caption falls back to the
   clip's own metadata instead of dropping the clip.
3. **Embed** — the caption is flattened to one string and embedded with
   `gemini-embedding-001` at `output_dimensionality=768`.
4. **Insert** — one batch `INSERT` through `clickhouse-connect`. `clip_id` is a
   UUIDv5 of the source key, and rows whose `clip_url` already exists are
   skipped, so the seed is idempotent.

```bash
python -m rushes.pipeline.seed --dry-run              # caption + embed, no writes
python -m rushes.pipeline.seed -q "night rain" --per-query 3
python -m rushes.pipeline.seed --recaption            # ignore the caption cache
```

### Run it

```bash
backend/.venv/bin/rushes-api          # :8080  FastAPI + the ADK agent
cd frontend && npm run dev            # :3000  Next.js
```

Open <http://localhost:3000>. The browser never talks to FastAPI directly — two
Next route handlers ([`app/api/search`](frontend/app/api/search/route.ts),
[`app/api/status`](frontend/app/api/status/route.ts)) proxy it, which keeps
`BACKEND_URL` and `API_TOKEN` server-side and removes CORS from the demo path.

### `rushes-doctor` checks the real thing

It does not inspect config; it embeds a sentence, starts the MCP server, counts
your clips over MCP, calls all four sources and runs one full search. Abridged:

```
configuration
  gemini            : api key AIza…7t (39 chars), model=gemini-3.6-flash
  embeddings        : gemini-embedding-001 @ 768d
  clickhouse        : xyz.us-east-1.aws.clickhouse.cloud:8443 table=default.archive_clips
  mcp server        : …/mcp-server/.venv/bin/mcp-clickhouse

[ ok ] gemini embeddings: 768d, unit norm
[ ok ] mcp-clickhouse 0.6.0 (protocol 2025-11-25), query tool: run_query
[ ok ] 20 clips indexed in default.archive_clips (counted over MCP)

sources (query: 'moody rain-soaked city street at night')
[ ok ] archive        3 results
[ ok ] youtube        3 results
[ ok ] public_domain  3 results
[ ok ] stock          3 results

[ ok ] end-to-end search: 22 results in 4180ms
```

Keys are masked in that output on purpose. Exit code is non-zero if Gemini or
ClickHouse is broken; a dead public source is a `[warn]`, because the app is
designed to survive it.

---

## Where Google Cloud actually runs

| Step | Google API | Where |
| --- | --- | --- |
| Plan the search | ADK `LlmAgent`, Gemini 2.5 Flash, `output_schema=SearchPlan` | [`agent.py`](backend/src/rushes/agent.py) |
| Orchestrate | ADK `SequentialAgent`, `BaseAgent`, `FunctionTool`, `Runner`, `InMemorySessionService` | [`agent.py`](backend/src/rushes/agent.py), [`tools/`](backend/src/rushes/tools/) |
| Watch each clip | `generate_content` + `response_schema`, Files API for big files | [`pipeline/captioner.py`](backend/src/rushes/pipeline/captioner.py) |
| Embed | `embed_content`, `gemini-embedding-001`, 768-d | [`gemini.py`](backend/src/rushes/gemini.py) |
| Explain matches | one batched `generate_content` for all cards | [`ranking.py`](backend/src/rushes/ranking.py) |
| Public video search | YouTube Data API v3 | [`tools/youtube.py`](backend/src/rushes/tools/youtube.py) |

`GOOGLE_GENAI_USE_VERTEXAI=true` switches every Gemini call to Vertex AI with ADC
instead of an AI Studio key; nothing else changes.

---

## Ranking: honest about mixing units

Only the archive lane produces a real semantic score. The public APIs return
their own ordering and nothing else, so their scores are constructed — and the
UI never pretends otherwise, which is why every card carries its source and its
score.

```python
archive   score = (0.75 · cosine_similarity + 0.25 · keyword_overlap) · 1.00
external  score = (0.55 · 1/(1 + 0.3·position) + 0.45 · keyword_overlap) · prior
                                                     # stock 0.93, yt/PD 0.90
```

The source priors are a deliberate thumb on the scale: when relevance is close,
the editor's own footage should win. Keyword overlap is computed against the
planner's keywords after stopword removal and light plural folding, so "reflections"
matches "reflection".

Then, per source: dedupe (by id and by URL), sort, and either

- `RANKING_STRATEGY=diverse` (default) — round-robin across sources, streams
  ordered by their best hit. Every source appears near the top, which is what
  makes the merge legible in a demo, or
- `RANKING_STRATEGY=score` — strict global score order.

**"Why this matched"** is a batched Gemini call over the top results
(`ENABLE_LLM_REASONS=true`). It can be turned off, and if it fails or returns
junk, `deterministic_reason()` takes over: the planner keywords that literally
appear in the hit ("matches: rain, neon, night"), or the similarity for archive
hits ("semantic match (81% similarity)"). The fallback is incapable of lying —
it only reports overlap it can point at.

---

## Project layout

```
backend/src/rushes/
  agent.py            ADK SequentialAgent: shot_planner -> source_fanout
  api.py              FastAPI: /api/search, /api/status, /healthz, /clips
  models.py           pydantic contract shared with the frontend
  ranking.py          merge, score, interleave, explain
  runtime.py          shared httpx client + the single MCP client
  config.py           Settings, mcp_command(), mcp_env()
  gemini.py           embeddings + structured generation
  clickhouse/
    mcp_client.py     stdio MCP session -> mcp-clickhouse (all reads)
    queries.py        SQL builders + payload parsing
    direct.py         clickhouse-connect, DDL + INSERT only
  tools/              archive, youtube, archive_org, pexels (ADK FunctionTools)
  pipeline/           fetch_clips -> captioner -> seed, create_schema, doctor
frontend/
  app/
    page.tsx          the search screen (a Suspense shell around SearchView)
    history/, saved/  what this browser remembers
    api/              route handlers proxying the backend
    icon.png          tab icon (Next.js file-based metadata)
  components/         SearchView, ResultsGrid, ResultCard, HistoryView, SavedView, …
  lib/store.ts        localStorage: past searches and saved shots
  lib/types.ts        mirror of models.py
  public/             rushes-logo.png, served at /rushes-logo.png
```

---

## API

`POST /api/search` — `{"query": "...", "limit": 24}`

```jsonc
{
  "query": "a lone figure on a rain-slicked neon street",
  "plan": {
    "archive_query": "lone silhouetted figure walking a wet neon-lit street at night",
    "web_query": "rainy neon street night",
    "keywords": ["rain", "neon", "night", "silhouette", "city street"],
    "mood": "lonely, cinematic",
    "shot_type": "wide",
    "sources": ["archive", "youtube", "public_domain", "stock"]
  },
  "results": [{
    "id": "…", "source": "archive", "title": "Rain On A Neon Crosswalk",
    "thumbnail_url": "…", "page_url": null,
    "clip_url": "http://localhost:8080/clips/pexels-12345.mp4",  // owned clips only
    "duration_seconds": 12, "license": "owned",
    "score": 0.83, "raw_score": 0.77,           // raw_score = cosine similarity
    "match_reason": "matches: rain, neon, night",
    "hosted_by_us": true                        // the only flag that lets <video> render
  }],
  "sources": [{"source": "youtube", "count": 6, "duration_ms": 412.0, "ok": true, "note": ""}],
  "total_ms": 3980.4,
  "warnings": []
}
```

A failed lane appears in `sources` with `ok: false` and a note, and the request
still returns 200 — the grid degrades one section instead of erroring.

`GET /api/status` proves the wiring (MCP handshake + live `count()`).
`GET /healthz` is the container probe. `GET /clips/<file>` serves your own
footage and nothing else. Set `API_TOKEN` to require
`Authorization: Bearer <token>` on `/api/search`; unset, it is open.

---

## Tests

```bash
cd backend && .venv/bin/pytest -q       # 58 passed
cd frontend && npm run lint && npm run build
```

The backend suite is hermetic: every HTTP source is an `httpx.MockTransport`, the
archive lane runs against a stub MCP client with a fake embedder, and the API
tests mount the app through `ASGITransport` so no lifespan, no subprocess and no
network are involved. That includes the failure paths that matter on stage — a
raising tool, a timing-out tool, a malformed plan from the LLM, and
`/api/status` when `uvx` is missing.

---

## Deploy

The backend is one container. Railway is the reference target — it builds the
Dockerfile directly and does not require a billing account to start — and
`railway.json` at the repository root is what aims it at `backend/Dockerfile`:

```json
{
  "build": { "builder": "DOCKERFILE", "dockerfilePath": "backend/Dockerfile" },
  "deploy": { "healthcheckPath": "/healthz", "healthcheckTimeout": 300 }
}
```

That file has to sit at the root of whatever gets uploaded, not next to the
Dockerfile: Railway's config file deliberately does not follow a service's Root
Directory setting. The path inside it is relative to the repository root, which
is also the build context. The image mirrors the repo layout because
`rushes.config` derives `REPO_ROOT` from the package location —
`/app/backend/src/rushes` makes `/app` the root that `data/clips` hangs off — so
the Dockerfile's `COPY` lines are root-relative and a context of `backend/`
cannot satisfy them.

**Deploy from GitHub rather than `railway up`.** Both work, but `railway up` tars
the build context and pushes it from your machine, and this repository ships the
20-clip archive: about 50 MB. The CLI allows that upload roughly 90 seconds
before failing with `operation timed out`, so anything under ~5 Mbps up will
never finish it — measured here at 189 KB/s, the same 50 MB needs 273 seconds.
Point Railway at the repository instead and it clones server-side:

```bash
railway init --name rushes-api
railway add --service rushes-api --repo <you>/<repo>
```

Linking the repo authorises Railway's GitHub app in the browser once. After
that every deploy is a `git push`, which has no client-side deadline to trip
over.

**Non-secret variables** in one call, with `--skip-deploys` so you are not
building 25 times:

```bash
railway variables \
  --set "PORT=8080" \
  --set "GOOGLE_GENAI_USE_VERTEXAI=false" \
  --set "GEMINI_MODEL=gemini-3.5-flash" \
  --set "GEMINI_EMBED_MODEL=gemini-embedding-001" \
  --set "EMBEDDING_DIM=768" \
  --set "CLICKHOUSE_HOST=<your-service>.clickhouse.cloud" \
  --set "CLICKHOUSE_PORT=8443" \
  --set "CLICKHOUSE_USER=default" \
  --set "CLICKHOUSE_SECURE=true" \
  --set "CLICKHOUSE_DATABASE=default" \
  --set "CLICKHOUSE_TABLE=archive_clips" \
  --set "MCP_STARTUP_TIMEOUT=90" \
  --set "MCP_CALL_TIMEOUT=60" \
  --set "PUBLIC_BASE_URL=https://placeholder.up.railway.app" \
  --set "ALLOWED_ORIGINS=https://placeholder.vercel.app" \
  --skip-deploys
```

`.env.example` is the full list; anything omitted falls back to the default in
`backend/src/rushes/config.py`.

**Secrets one at a time, over stdin,** so no key reaches your shell history:

```bash
railway variable set GOOGLE_API_KEY      --stdin --skip-deploys
railway variable set CLICKHOUSE_PASSWORD --stdin --skip-deploys
railway variable set YOUTUBE_API_KEY     --stdin --skip-deploys
railway variable set PEXELS_API_KEY      --stdin --skip-deploys
```

Each waits for the value on stdin: paste, then Ctrl+D (Ctrl+Z then Enter on
Windows). Railway's dashboard variables tab does the same job if you would
rather the values never touch a terminal.

**A public URL is opt-in** — Railway does not expose the service until asked:

```bash
railway domain
```

`PUBLIC_BASE_URL` is circular: it has to be the service's own URL, which does not
exist until that command runs. Set it afterwards.

```bash
railway variables --set "PUBLIC_BASE_URL=https://<what railway domain printed>"
```

Archive rows store clip paths like `/clips/pexels-855432.mp4`, and this is the
value that makes them absolute. A variable change redeploys but does not rebuild,
so it costs a restart rather than another build.

`healthcheckTimeout: 300` is not padding. Startup spawns the `mcp-clickhouse`
stdio subprocess and blocks on its handshake before uvicorn accepts a
connection — about 13 seconds observed, bounded by `MCP_STARTUP_TIMEOUT`. A
30-second health check would fail a cold start on a slow day and restart the
container into the same wait.

Then verify against the real thing, not the container's own health check:

```bash
curl -s https://<your-railway-domain>/api/status | python -m json.tool
```

`mcp_running: true`, a `clips` count matching your seeded archive, and no
`clickhouse` error. If it fails, read `railway logs` before assuming it worked:
the MCP startup failure is caught and logged as a warning, so the service will
serve search quite happily with the archive lane silently offline.

**Frontend → Vercel.** Import `frontend/` as the project root, set `BACKEND_URL`
to the Railway domain and `API_TOKEN` to the same value the backend has. Both are
server-side only; the browser only ever sees `/api/*` on the Vercel domain. Once
Vercel gives you the real hostname, set it back on Railway so CORS matches:

```bash
railway variables --set "ALLOWED_ORIGINS=https://your-app.vercel.app"
```

### Cloud Run, if you would rather use Google's runtime

`cloudbuild.yaml` targets the same image with the same root build context. It
needs a project with **billing enabled** — Cloud Run, Cloud Build, Artifact
Registry and Secret Manager all refuse to enable without it, even though the
demo itself fits inside the free tier.

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
                       artifactregistry.googleapis.com secretmanager.googleapis.com

# One per key; paste the value, then Ctrl+D. Nothing sensitive on a command line.
gcloud secrets create gemini-api-key       --data-file=-
gcloud secrets create clickhouse-password  --data-file=-
gcloud secrets create youtube-api-key      --data-file=-
gcloud secrets create pexels-api-key       --data-file=-

gcloud builds submit . --config cloudbuild.yaml --substitutions _PROJECT="$PROJECT"

gcloud run deploy rushes-api \
  --image "gcr.io/$PROJECT/rushes-api" --region us-central1 \
  --platform managed --allow-unauthenticated --port 8080 \
  --cpu 2 --memory 1Gi --min-instances 1 --cpu-boost \
  --set-env-vars "CLICKHOUSE_HOST=…,CLICKHOUSE_USER=default,CLICKHOUSE_SECURE=true,PUBLIC_BASE_URL=https://…,ALLOWED_ORIGINS=https://….vercel.app" \
  --set-secrets "GOOGLE_API_KEY=gemini-api-key:latest,CLICKHOUSE_PASSWORD=clickhouse-password:latest,YOUTUBE_API_KEY=youtube-api-key:latest,PEXELS_API_KEY=pexels-api-key:latest"
```

`--min-instances 1` because scaling to zero puts that 13-second MCP handshake in
front of a live demo, and `--cpu-boost` shortens it. `PUBLIC_BASE_URL` is
circular here too: deploy with the placeholder, then
`gcloud run services update rushes-api --region us-central1 --update-env-vars
PUBLIC_BASE_URL=<the URL Cloud Run printed>`.

---

## Known limits

- `/api/search` is unauthenticated unless `API_TOKEN` is set, and `main()` binds
  `0.0.0.0`. Set the token (or put Cloud Run IAM / a load balancer in front)
  before exposing it publicly.
- Vector search is a brute-force `cosineDistance` scan with no ANN index. At the
  scale of a hackathon archive this is the right trade; past ~10⁶ clips it is not.
- `MAX_DISTANCE = 0.75` means a query with nothing close in your archive returns
  *no* archive results rather than weak ones. That is intentional, and it is why
  the source strip shows counts per lane.
- Captions are only as good as one Gemini pass over a 1280px clip; the caption
  cache in `data/captions/` is the thing to edit if a clip is described wrongly.
- YouTube result counts are capped by the Data API quota (`YOUTUBE_VIDEO_LICENSE=creativeCommon`
  narrows results but is licence-safer).

---

## Credits

The sample archive is not our own footage. It is built during seeding from
[Pexels](https://www.pexels.com) videos, which is why every seeded row carries
`license: "Pexels License — Pixabay (sample archive)"` and why those clips are
the only ones the app will ever play inline. The Pexels License asks for no
attribution, but the people who shot those clips are the reason this demo has
anything to search, so they get a credit anyway. Point `data/clips/` at your own
rushes and this section stops applying to you.

Live results come from the [YouTube Data API](https://developers.google.com/youtube/v3),
the [Internet Archive](https://archive.org) advanced-search API and the
[Pexels Video API](https://www.pexels.com/api/). None of that footage is stored —
see [We never rehost anyone else's video](#we-never-rehost-anyone-elses-video).

---

## License

MIT — see [LICENSE](LICENSE). The code is ours to give away; the footage behind
the public sources is not, which is the whole reason this project links out
instead of downloading.

