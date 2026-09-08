# rushes (frontend)

The UI half of [Rushes](../README.md): Next.js 16 (App Router, Turbopack) +
Tailwind 4. One search box, one grid, four sources, every card labelled with
where it came from and why it matched.

```bash
npm install
cp .env.example .env.local     # BACKEND_URL, optional API_TOKEN
npm run dev                    # :3000, expects the backend on :8080
```

The browser never calls FastAPI directly. [`app/api/search/route.ts`](app/api/search/route.ts)
and [`app/api/status/route.ts`](app/api/status/route.ts) proxy it server-side, so
`BACKEND_URL` and `API_TOKEN` stay out of the bundle and CORS never enters the
picture.

Worth knowing before editing:

- [`lib/types.ts`](lib/types.ts) mirrors the backend's pydantic models. If
  `backend/src/rushes/models.py` changes, change it here too.
- Only hits with `hosted_by_us` get a `<video>`. Everything else is thumbnail +
  title + outbound link — see [`components/ResultCard.tsx`](components/ResultCard.tsx).
- Third-party thumbnails use a plain `<img>` on purpose: `next/image` would cache
  other people's media on our servers. `@next/next/no-img-element` is disabled in
  [`eslint.config.mjs`](eslint.config.mjs) for exactly that reason.
- The design vocabulary lives in [`app/globals.css`](app/globals.css): two
  accents (tungsten for footage you own, print teal for links out), no radii, no
  shadows, and one reveal animation. Adding a third accent would turn a rights
  signal back into decoration.
- Every control is padded past the 24px WCAG 2.2 target minimum at its printed
  size. The `.tap` class in `globals.css` lays an invisible 44px hit area over
  the stencil-sized ones when the pointer is coarse; only use it where the
  control has that much clearance from its neighbours.

```bash
npm run lint && npm run build
```
