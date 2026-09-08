# Rushes — Project Blueprint
### Agentic Cinema Hackathon (ClickHouse Track) — Deadline: Sep 9, 2026 @ 2:00pm PDT

**Tagline:** *"Describe the shot. Find it — whether it's in your archive or out on the web."*

---

## 1. The Problem (your pitch, one paragraph)

Editors and archivists waste hours hunting for the right clip — scrubbing folders of unlabeled footage, or searching YouTube with clunky keyword guesses. Rushes lets them describe a shot in plain English ("rain-soaked street at night, neon signs, wide shot") and instantly surfaces matches — first from their own private archive, then from legitimate public sources — ranked and unified in one search.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                       │
│         Search bar → results grid (archive + web)            │
└───────────────────────────┬───────────────────────────────────┘
                             │ query
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              Rushes Agent (Google ADK + Gemini)               │
│  - Parses natural-language query                              │
│  - Calls tools in parallel, merges + ranks results             │
└──────┬───────────────┬───────────────────┬─────────────────────┘
       │               │                   │
       ▼               ▼                   ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐
│ ClickHouse   │  │ YouTube Data │  │ Internet Archive API  │
│ MCP Server   │  │ API v3       │  │ (public domain films)  │
│ (your        │  │ (metadata +  │  │ + Pexels/Pixabay       │
│ private      │  │ links only,  │  │ (free stock footage)   │
│ archive,     │  │ no hosting)  │  │                        │
│ vector search│  │              │  │                        │
│ on captions) │  │              │  │                        │
└─────────────┘  └──────────────┘  └──────────────────────┘
```

**Key design decision:** you only *store and serve* clips you own (your seeded archive). Anything from YouTube/Internet Archive/Pexels is returned as metadata + thumbnail + outbound link — never downloaded/rehosted. This keeps you copyright-clean and is a talking point for the "Design" judging criterion.

---

## 3. Tech Stack

| Layer | Tool |
|---|---|
| Frontend | Next.js + Tailwind (your existing comfort zone) |
| Agent orchestration | Google Agent Development Kit (ADK), Python |
| LLM | Gemini (multimodal — video/image captioning + query understanding) |
| Vector/analytics DB | ClickHouse Cloud + `mcp-clickhouse` MCP server |
| Public search tools | YouTube Data API v3, Internet Archive API, Pexels Video API |
| Hosting | Cloud Run (backend agent) + Vercel or Cloud Run (frontend) |
| Auth/secrets | Google Secret Manager |

---

## 4. ClickHouse Schema

```sql
CREATE TABLE archive_clips (
    clip_id UUID DEFAULT generateUUIDv4(),
    title String,
    description String,          -- Gemini-generated rich caption
    tags Array(String),          -- Gemini-generated tags: setting, mood, objects, action
    embedding Array(Float32),    -- vector embedding of description, for semantic search
    duration_seconds UInt16,
    thumbnail_url String,
    clip_url String,             -- your hosted file (e.g. Cloud Storage signed URL)
    source String DEFAULT 'archive',
    license String DEFAULT 'owned',
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY clip_id;
```

Use ClickHouse's vector similarity functions (`cosineDistance` / `L2Distance` on the `embedding` array) to do semantic nearest-neighbor search against the query embedding.

---

## 5. Data Pipeline (seeding your archive)

1. **Source demo footage** — pull 60–100 short clips from Pexels/Pixabay (free-to-use, no licensing worry) to simulate a "private archive." Vary settings/moods/objects so search results look meaningfully different.
2. **Caption each clip with Gemini** — feed each clip (or extracted keyframes) to Gemini multimodal, prompt it to output a structured JSON: `{title, description, tags[], mood, setting, objects[]}`.
3. **Generate embeddings** — embed the `description` field (Gemini embedding model or a standard sentence-embedding model) into a float vector.
4. **Insert into ClickHouse** via the `mcp-clickhouse` MCP server (or direct client for the seed job).

---

## 6. Agent Query Flow

1. User types a query, e.g. *"abandoned warehouse, moody lighting"*.
2. Agent (ADK) embeds the query and:
   - Runs a **ClickHouse vector search** against `archive_clips` → top-k internal matches.
   - Calls **YouTube Data API** `search.list` with the same query → top-k external matches (title, thumbnail, video link, channel).
   - Calls **Internet Archive** advancedsearch API filtered to video/moving-image, public-domain license → top-k matches.
   - (Optional) Calls **Pexels API** for stock-footage fallback.
3. Agent merges all results into one ranked list, tagging each with its source (`Archive` / `YouTube` / `Public Domain` / `Stock`).
4. Frontend renders a grid: thumbnail, title, source badge, short Gemini-generated reason ("matches: rain, neon, wide shot"), and a link/play action.

---

## 7. Build Plan (Sep 5 → Sep 9)

**Day 1 (today):**
- Set up ClickHouse Cloud service ($400 credit), create schema.
- Set up Google Cloud project, enable Vertex AI/Gemini API, request $100 credit.
- Get YouTube Data API key, Internet Archive access (no key needed), Pexels API key.
- Source and organize 60–100 demo clips.

**Day 2:**
- Build the captioning/embedding pipeline script (Python) — run all clips through Gemini, generate embeddings, insert into ClickHouse.
- Verify vector search works with a few manual test queries.

**Day 3:**
- Build the ADK agent: tool definitions for ClickHouse MCP, YouTube, Internet Archive, Pexels.
- Wire up merge/ranking logic.
- Build the Next.js frontend search UI.

**Day 4:**
- Polish UI (loading states, source badges, empty states).
- Deploy backend (Cloud Run) and frontend (Vercel).
- Record the 3-minute demo video: (1) show the problem in 15 sec, (2) live search showing archive + YouTube + public domain results merging, (3) a second query showing range/versatility, (4) quick architecture callout mentioning Gemini + ADK + ClickHouse MCP explicitly.
- Write README, add OSS license (MIT), push public repo, submit Devpost form.

---

## 8. Submission Checklist

- [ ] Hosted project URL (Cloud Run/Vercel)
- [ ] 3-minute demo video (functioning app, not a trailer), YouTube/Vimeo, public
- [ ] Public repo (GitHub) with MIT/Apache license visible in the About section
- [ ] Code demonstrates real runtime calls to Google Cloud (Gemini/ADK) AND ClickHouse MCP — imported and called, not just named
- [ ] Partner track selected: ClickHouse
- [ ] Devpost submission form completed

---

## 9. The Build Prompt (give this to your coding agent)

```
I'm building "Rushes" — a hackathon project for Google's Agentic Cinema
hackathon (ClickHouse track). Deadline is tight (Sep 9), so prioritize a
working end-to-end demo over polish.

WHAT IT DOES:
A natural-language video search tool for film editors/archivists. A user
types a description of a shot (e.g. "rain-soaked street at night, neon
signs, wide shot") and the app returns matching clips from two sources,
merged into one ranked list:
  1. A private archive of clips I own, semantically indexed.
  2. Public sources: YouTube (metadata + link only, never hosted),
     Internet Archive (public domain film/video), and Pexels (free
     stock footage) — also metadata + link only.

We NEVER download, store, or rehost copyrighted third-party video. Public
results are always thumbnail + title + outbound link.

TECH STACK:
- Backend agent: Python, Google Agent Development Kit (ADK), Gemini API
  for query understanding, captioning, and embeddings.
- Database: ClickHouse Cloud, accessed via the official mcp-clickhouse
  MCP server. Table schema:
    archive_clips(clip_id UUID, title String, description String,
    tags Array(String), embedding Array(Float32), duration_seconds
    UInt16, thumbnail_url String, clip_url String, source String,
    license String, created_at DateTime)
  Use cosineDistance on `embedding` for vector similarity search.
- External tool integrations: YouTube Data API v3 (search.list),
  Internet Archive advancedsearch API (filtered to moving image +
  public domain), Pexels Video API.
- Frontend: Next.js + Tailwind. Single search bar, results grid with
  source badges (Archive / YouTube / Public Domain / Stock), thumbnail,
  title, and a short "why this matched" line.
- Deployment: backend on Cloud Run, frontend on Vercel (or Cloud Run).
  Secrets via Google Secret Manager.

BUILD IN THIS ORDER:
1. Set up ClickHouse Cloud service and create the archive_clips table.
2. Write a seeding script: take ~60-100 short video clips (I'll supply
   from Pexels/Pixabay), run each through Gemini to generate a
   structured caption (title, description, tags, mood, setting,
   objects), generate an embedding of the description, and insert
   into ClickHouse via the MCP server or direct client.
3. Build the ADK agent with four tools: 
   - clickhouse_search(query_embedding) → top-k from archive_clips
   - youtube_search(query) → top-k from YouTube Data API
   - archive_org_search(query) → top-k from Internet Archive API
   - pexels_search(query) → top-k from Pexels API
   The agent should call these in parallel, then merge/rank results
   by relevance score, and return a unified structured JSON response.
4. Build the Next.js frontend: search input, loading state, results
   grid rendering the unified JSON, with clear source labeling.
5. Deploy both, wire up env vars/secrets, and verify a real end-to-end
   query returns real results from all sources.

IMPORTANT CONSTRAINTS:
- ClickHouse must be called at runtime via the real mcp-clickhouse MCP
  server, not simulated — this is a hard hackathon requirement.
- Google Cloud (Gemini/ADK) must be genuinely imported and called in
  code, not just referenced.
- Keep the codebase clean enough to open-source with an MIT license
  and a clear README with setup instructions (this is a submission
  requirement).

Start by scaffolding the project structure and the ClickHouse schema
setup script, then walk me through the seeding pipeline before moving
to the agent.
```

---

## 10. Demo Video Script (3 minutes)

1. **0:00–0:20** — Cold open: show the pain. "Editors spend hours searching unlabeled archives for the right shot." Show a folder of cryptically-named files.
2. **0:20–1:30** — Live demo: type a query into Rushes, show results populating from Archive + YouTube + Public Domain, clearly labeled. Click through to one result.
3. **1:30–2:15** — Second, different query to show range (e.g. a mood-based query vs an object-based query).
4. **2:15–2:45** — Quick architecture callout: "Rushes is powered by Gemini for understanding and captioning, orchestrated with Google's Agent Development Kit, and backed by ClickHouse for fast semantic search over the archive."
5. **2:45–3:00** — Close: restate the problem/solution in one line, show the repo/project URL on screen.
