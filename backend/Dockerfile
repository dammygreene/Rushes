# Rushes backend. Railway builds this via railway.json; it also runs on Cloud Run.
#
# Two virtualenvs on purpose. The app needs mcp<2 (pinned by google-adk[mcp]),
# while the mcp-clickhouse server needs fastmcp>=4 and therefore mcp>=2. They
# cannot share a site-packages, and the server is a subprocess anyway — it is
# spawned over stdio, so an isolated interpreter costs nothing at runtime.
#
# The directory layout mirrors the repository because rushes.config derives
# REPO_ROOT from the package location; PYTHONPATH further down is what makes
# that derivation land on /app rather than inside the venv.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---------------------------------------------------------------- app venv
COPY backend/pyproject.toml backend/README.md /app/backend/
RUN python -m venv /app/backend/.venv \
 && /app/backend/.venv/bin/pip install --upgrade pip setuptools wheel

COPY backend/src /app/backend/src
RUN /app/backend/.venv/bin/pip install /app/backend

# ------------------------------------------------------- mcp-clickhouse venv
# The hard hackathon requirement: ClickHouse is queried through the real
# mcp-clickhouse MCP server, not a client library pretending to be one.
RUN python -m venv /app/mcp-server/.venv \
 && /app/mcp-server/.venv/bin/pip install --upgrade pip \
 && /app/mcp-server/.venv/bin/pip install mcp-clickhouse==0.6.0

# The only footage we are entitled to serve: our own seeded archive, baked in and
# served from /clips. It has to be in the image, not a mounted volume — an archive
# row carries a repo-relative clip_url that tools/archive.py absolutises against
# PUBLIC_BASE_URL and api.py serves with StaticFiles, so a missing file does not
# degrade to "no preview", it renders a play button that 404s. Third-party hits
# never reach this path; they stay thumbnail + title + outbound link.
RUN mkdir -p /app/data/clips
COPY data/clips /app/data/clips

# The platform injects PORT; rushes.api.main reads it via Settings.port.
#
# PYTHONPATH pins `import rushes` to the source tree rather than the copy pip
# placed in site-packages. Both are importable and identical, but only the
# source path makes rushes.config's `Path(__file__).parents[3]` land on /app —
# from site-packages it lands on /app/backend/.venv/lib, and two runtime paths
# hang off that root, both of which fail silently. The MCP command falls back
# to `uvx mcp-clickhouse`, absent from this image, so the ClickHouse lane goes
# offline with nothing but a warning; and clips_dir points somewhere api.py
# then creates empty, so every baked clip 404s behind a working play button.
# The pip install above still earns its keep: dependency resolution and the
# rushes-api entry point.
ENV PORT=8080 \
    PYTHONPATH=/app/backend/src \
    PATH="/app/backend/.venv/bin:${PATH}"
EXPOSE 8080

# Least privilege: nothing here needs root.
RUN useradd --create-home --uid 10001 rushes && chown -R rushes:rushes /app
USER rushes

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8080\")}/healthz').read()"

CMD ["rushes-api"]
