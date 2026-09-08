"use client";

import type { CSSProperties } from "react";
import Link from "next/link";
import { ClearButton } from "./ClearButton";
import { ContactSheet, SHEET } from "./ResultsGrid";
import { ResultCard } from "./ResultCard";
import { searchHref } from "./SearchBar";
import { EmptyShelf, ShelfHead } from "./States";
import { useSavedShots } from "@/lib/store";
import { timeAgo } from "@/lib/time";

/**
 * The selects reel: a contact sheet of frames you marked, newest first, each one
 * still carrying the search it came out of. A saved shot is metadata and nothing
 * more — your own archive clips still play here, and everything else is still a
 * thumbnail, a title and a link back to the source that holds it.
 */
export function SavedView() {
  const { saved, clear, ready } = useSavedShots();

  return (
    <section>
      <ShelfHead
        title="Saved shots"
        action={
          saved.length > 0 ? (
            <ClearButton
              label="Clear shelf"
              confirm="Clear all?"
              onConfirm={clear}
            />
          ) : null
        }
      >
        Frames you marked on a contact sheet, kept in this browser. Nothing is
        downloaded: your own clips play from your archive, and the rest link back
        to where they live. Use Saved on any frame to take it off the shelf.
      </ShelfHead>

      {saved.length > 0 ? (
        <ContactSheet>
          <ul className={SHEET}>
            {saved.map((shot, index) => (
              <li
                key={shot.key}
                className="frame-in flex flex-col"
                style={{ "--frame": index } as CSSProperties}
              >
                <div className="flex-1">
                  <ResultCard hit={shot.hit} query={shot.query} />
                </div>
                <p className="mt-2.5 flex flex-wrap items-baseline gap-x-2 border-t border-rule pt-2 text-[12px] text-paper-faint">
                  {shot.query ? (
                    <>
                      <span>from</span>
                      <Link
                        href={searchHref(shot.query)}
                        className="-my-1 py-1 font-display text-[15px] italic text-paper-dim underline decoration-rule decoration-1 underline-offset-4 transition-colors hover:text-paper hover:decoration-paper"
                      >
                        {shot.query}
                      </Link>
                      <span aria-hidden>·</span>
                    </>
                  ) : null}
                  <span className="tabular-nums">{timeAgo(shot.at)}</span>
                </p>
              </li>
            ))}
          </ul>
        </ContactSheet>
      ) : null}

      {ready && saved.length === 0 ? (
        <div className="mt-8">
          <EmptyShelf>
            No frames on the shelf yet. Every result carries a Save in its
            margin; press it and the shot waits here for you.{" "}
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
