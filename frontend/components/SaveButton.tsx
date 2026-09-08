"use client";

import { hitKey, useSavedShots } from "@/lib/store";
import type { SearchHit } from "@/lib/types";

/**
 * Keeping a shot for later. An editor pulling selects marks the frames they want
 * on the contact sheet itself, so the mark lives in the frame's margin next to
 * the other stencilled labels, and it says what it is in words.
 *
 * Only the metadata is kept, which is the whole point: a saved YouTube shot is
 * still a thumbnail, a title and a link out.
 */
export function SaveButton({
  hit,
  query = "",
}: {
  hit: SearchHit;
  query?: string;
}) {
  const { keys, toggle } = useSavedShots();
  const saved = keys.has(hitKey(hit));

  return (
    <button
      type="button"
      onClick={() => toggle(hit, query)}
      aria-pressed={saved}
      // The smallest control on the page and the one most likely to be hit with
      // a thumb. The padding takes the printed 11px label past the 24px WCAG
      // minimum on its own; `.tap` lays a 44px target over it on touch. The
      // horizontal pull keeps the label flush with the frame's right edge, and
      // the row it sits in carries enough gap-y to clear the overlay.
      className={`tap -mx-2 cursor-pointer px-2 py-1.5 font-mono text-[11px] font-medium tracking-[0.18em] uppercase transition-colors ${
        saved ? "text-paper" : "text-paper-faint hover:text-paper"
      }`}
    >
      {saved ? "Saved" : "Save"}
      <span className="sr-only">
        {saved ? ` “${hit.title}”, remove` : ` “${hit.title}” for later`}
      </span>
    </button>
  );
}
