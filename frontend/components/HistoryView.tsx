"use client";

import Link from "next/link";
import { ClearButton } from "./ClearButton";
import { searchHref } from "./SearchBar";
import { EmptyShelf, ShelfHead } from "./States";
import { HISTORY_LIMIT, usePastSearches } from "@/lib/store";
import { timeAgo } from "@/lib/time";
import { SOURCE_META } from "@/lib/types";

/**
 * The log book. Every search this browser has run, newest first, with what came
 * back still attached to it. Opening one is a lookup here rather than two more
 * Gemini calls, which is the same reason stepping back through them is free.
 */
export function HistoryView() {
  const { entries, forget, clear, ready } = usePastSearches();

  return (
    <section>
      <ShelfHead
        title="Past searches"
        action={
          entries.length > 0 ? (
            <ClearButton
              label="Clear history"
              confirm="Clear all?"
              onConfirm={clear}
            />
          ) : null
        }
      >
        The last {HISTORY_LIMIT} searches this browser ran, with their results.
        Opening one costs nothing: it comes back from here rather than from the
        agents.
      </ShelfHead>

      {entries.length > 0 ? (
        <ul className="mt-8 divide-y divide-rule border-y border-rule">
          {entries.map((entry) => (
            <li
              key={entry.query}
              className="grid gap-x-6 gap-y-1.5 py-3.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-baseline"
            >
              <div className="min-w-0">
                <Link
                  href={searchHref(entry.query)}
                  className="font-display text-[19px] italic underline decoration-rule decoration-1 underline-offset-4 transition-colors hover:decoration-paper"
                >
                  {entry.query}
                </Link>
                <p className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-[11px] font-medium tracking-[0.14em] uppercase">
                  {entry.response.sources
                    .filter((report) => report.count > 0)
                    .map((report) => (
                      <span
                        key={report.source}
                        className={SOURCE_META[report.source].stamp}
                      >
                        {SOURCE_META[report.source].label} {report.count}
                      </span>
                    ))}
                  <span className="text-paper-faint">
                    {entry.response.results.length} kept
                  </span>
                </p>
              </div>
              {/* Its own line below `sm`, where pushing the two ends apart is
                  what makes Remove findable; back on the row's baseline above
                  it. */}
              <p className="flex items-baseline justify-between gap-4 text-[13px] text-paper-faint sm:justify-self-end">
                <span className="tabular-nums">{timeAgo(entry.at)}</span>
                <button
                  type="button"
                  onClick={() => forget(entry.query)}
                  // Padded past 24px, then pulled back flush. The touch overlay
                  // reaches ~9px beyond the label, which stays clear of the
                  // query link two lines up and of the next row's.
                  className="tap -mx-2 -my-1.5 cursor-pointer px-2 py-1.5 font-mono text-[11px] font-medium tracking-[0.18em] uppercase transition-colors hover:text-paper"
                >
                  Remove
                  <span className="sr-only"> “{entry.query}” from history</span>
                </button>
              </p>
            </li>
          ))}
        </ul>
      ) : null}

      {ready && entries.length === 0 ? (
        <div className="mt-8">
          <EmptyShelf>
            Nothing here yet. Once you have run a search it is kept in this
            browser, so you can step back into it without paying for it twice.{" "}
            <Link
              href="/"
              className="text-paper underline decoration-rule decoration-1 underline-offset-4 transition-colors hover:decoration-paper"
            >
              Describe a shot
            </Link>
            .
          </EmptyShelf>
        </div>
      ) : null}
    </section>
  );
}
