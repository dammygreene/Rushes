"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { PlanPanel, SourceStrip } from "./AgentPanel";
import { ResultsGrid, ResultsSkeleton } from "./ResultsGrid";
import { SearchBar, searchHref } from "./SearchBar";
import { FrameCounter, useBackendStatus } from "./Status";
import { EmptyState, ErrorState, NoResults } from "./States";
import { recallSearch, rememberSearch } from "@/lib/store";
import { timeAgo } from "@/lib/time";
import type { SearchResponse } from "@/lib/types";

/** The headline and the field, shared with the fallback below. */
function Hero({ children }: { children: React.ReactNode }) {
  const backend = useBackendStatus();

  return (
    // Tighter above the fold on a phone: at 375px the headline, the blurb and
    // the field have to fit before the field is worth having, so the vertical
    // rhythm opens up only once there is room for it.
    <div className="mt-8 grid gap-8 sm:mt-14 sm:gap-10 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start lg:gap-16">
      <div>
        <h1 className="font-display text-[clamp(2.5rem,8vw,6.5rem)] leading-[0.95] font-medium tracking-[-0.01em]">
          Describe the shot.
          <br />
          Get the clip.
        </h1>
        <p className="mt-4 max-w-[48ch] text-[16px] leading-relaxed text-paper-dim sm:mt-5">
          Your own archive is searched by meaning. YouTube, the Internet Archive
          and Pexels are searched in the same pass.
        </p>
        <div className="mt-6 max-w-[46rem] sm:mt-8">{children}</div>
      </div>
      <FrameCounter {...backend} />
    </div>
  );
}

/**
 * What a production build serves before hydration, while `useSearchParams` is
 * still suspended. The form inside it is a real GET form, so it works anyway.
 */
export function SearchViewFallback() {
  return (
    <Hero>
      <SearchBar query="" pending={false} onSearch={() => {}} />
    </Hero>
  );
}

/**
 * Everything below the field, tagged with the words it belongs to and a rising
 * id. One object rather than four separate pieces of state: a response that
 * arrives after the words have moved on can then ask whether it is still wanted,
 * and the whole screen turns over in a single render.
 */
interface Screen {
  id: number;
  query: string;
  pending: boolean;
  response: SearchResponse | null;
  /** When it was stored, if this response came off this browser's own shelf. */
  restoredAt: number | null;
  error: string | null;
}

/**
 * What a set of words shows before anything is asked of the backend: nothing for
 * an empty query, the stored response if this browser has run them before, and
 * otherwise a pending screen — which is the cue the effect below searches on.
 */
function openScreen(query: string, id: number): Screen {
  const blank: Screen = {
    id,
    query,
    pending: false,
    response: null,
    restoredAt: null,
    error: null,
  };
  if (!query) return blank;
  const remembered = recallSearch(query);
  return remembered
    ? { ...blank, response: remembered.response, restoredAt: remembered.at }
    : { ...blank, pending: true };
}

/**
 * The search screen. The query lives in the URL and nowhere else, which is what
 * makes the browser's own back button work: every search is a history entry, and
 * stepping back onto one this browser has already run restores that response
 * from the store rather than spending another round trip on it.
 */
export function SearchView() {
  const router = useRouter();
  const params = useSearchParams();
  const query = (params.get("q") ?? "").trim();

  const [screen, setScreen] = useState<Screen>(() => openScreen(query, 1));
  // The URL is this component's input, so the screen follows it here in render
  // rather than a beat later in an effect.
  if (screen.query !== query) setScreen(openScreen(query, screen.id + 1));

  // The last screen handed to the backend. A search is two Gemini calls against
  // a free tier of twenty a day, and React runs effects twice in development, so
  // each screen asks exactly once.
  const sent = useRef(0);

  const run = useCallback(async (id: number, asked: string) => {
    /** Only the screen that asked for this may be written to. */
    const write = (patch: Partial<Screen>) =>
      setScreen((now) => (now.id === id ? { ...now, ...patch } : now));

    try {
      const raw = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: asked }),
      });
      const body = await raw.json().catch(() => null);
      if (!raw.ok) {
        const detail =
          (body as { detail?: unknown } | null)?.detail ?? `HTTP ${raw.status}`;
        throw new Error(
          typeof detail === "string" ? detail : JSON.stringify(detail),
        );
      }
      const found = body as SearchResponse;
      // Worth keeping whether or not this screen is still the one on show.
      rememberSearch(asked, found);
      write({ pending: false, response: found });
    } catch (caught) {
      write({
        pending: false,
        error: caught instanceof Error ? caught.message : "unknown error",
      });
    }
  }, []);

  useEffect(() => {
    if (!screen.pending || sent.current === screen.id) return;
    sent.current = screen.id;
    void run(screen.id, screen.query);
  }, [screen, run]);

  /** Ask again for the words already on screen: same URL, new request. */
  const again = useCallback(() => {
    setScreen((now) => ({
      ...now,
      id: now.id + 1,
      pending: true,
      response: null,
      restoredAt: null,
      error: null,
    }));
  }, []);

  const submit = useCallback(
    (asked: string) => {
      // The same words again would not change the URL, so re-ask by hand.
      if (asked === query) again();
      else router.push(searchHref(asked));
    },
    [again, query, router],
  );

  return (
    <>
      <Hero>
        <SearchBar query={query} pending={screen.pending} onSearch={submit} />
      </Hero>

      <div className="mt-10 space-y-6 sm:mt-14">
        {query ? (
          // gap-y-3 rather than 1: below `sm` these two wrap onto separate
          // lines, and both are padded targets that need room between them.
          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
            <Link
              href="/"
              className="-my-1.5 py-1.5 text-[13px] text-paper-dim underline decoration-rule decoration-1 underline-offset-4 transition-colors hover:text-paper hover:decoration-paper"
            >
              <span aria-hidden>←</span> Back to search
            </Link>
            {screen.restoredAt !== null ? (
              <p className="text-[13px] text-paper-faint">
                Kept in this browser, {timeAgo(screen.restoredAt)}.{" "}
                <button
                  type="button"
                  onClick={again}
                  className="-my-1.5 cursor-pointer py-1.5 text-paper-dim underline decoration-rule decoration-1 underline-offset-4 transition-colors hover:text-paper hover:decoration-paper"
                >
                  Search again
                </button>
              </p>
            ) : null}
          </div>
        ) : null}

        {screen.error ? <ErrorState message={screen.error} /> : null}

        {screen.pending ? (
          <>
            {/* Two Gemini calls and four sources runs to about half a minute,
                so the wait says so rather than letting it read as a hang. */}
            <p role="status" className="text-[13px] text-paper-dim">
              Planning the shot, then searching four sources at once. This
              usually takes around half a minute.
            </p>
            <ResultsSkeleton />
          </>
        ) : null}

        {!screen.pending && screen.response ? (
          <>
            <SourceStrip
              sources={screen.response.sources}
              totalMs={screen.response.total_ms}
              warnings={screen.response.warnings}
            />
            <PlanPanel plan={screen.response.plan} query={query} />
            {screen.response.results.length > 0 ? (
              <ResultsGrid results={screen.response.results} query={query} />
            ) : (
              <NoResults query={query} />
            )}
          </>
        ) : null}

        {!screen.pending && !screen.response && !screen.error ? (
          <EmptyState />
        ) : null}
      </div>
    </>
  );
}
