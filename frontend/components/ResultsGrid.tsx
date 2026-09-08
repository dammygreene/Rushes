import type { CSSProperties } from "react";
import { ResultCard } from "./ResultCard";
import type { SearchHit } from "@/lib/types";

/**
 * The contact sheet. Frames butt up in a fixed grid, each one ruled off from
 * its own margin text, and the sheet is fenced top and bottom by sprocket
 * bands. No card borders, no radii, no shadows: a contact print has none.
 */
export function ResultsGrid({
  results,
  query,
}: {
  results: SearchHit[];
  /** Filed with any frame saved off this sheet. */
  query?: string;
}) {
  return (
    <ContactSheet>
      <ul className={SHEET}>
        {results.map((hit, index) => (
          <li
            key={`${hit.source}:${hit.id}`}
            className="frame-in"
            style={{ "--frame": index } as CSSProperties}
          >
            <ResultCard hit={hit} query={query} />
          </li>
        ))}
      </ul>
    </ContactSheet>
  );
}

/** Empty frames while the four sources answer. Same grid, same reveal. */
export function ResultsSkeleton({ count = 8 }: { count?: number }) {
  return (
    <ContactSheet>
      <div className={SHEET} aria-hidden>
        {Array.from({ length: count }, (_, index) => (
          <div
            key={index}
            className="frame-in"
            style={{ "--frame": index } as CSSProperties}
          >
            {/* The wait is a shot planner plus four sources, upwards of thirty
                seconds. Only the grey blocks breathe, and they breathe in
                unison rather than in a chase: it says "still working", not
                "look here". */}
            <div className="breathing aspect-video bg-slate" />
            <div className="space-y-2 border-t border-rule pt-2.5">
              <div className="breathing h-3 w-4/5 bg-slate" />
              <div className="breathing h-3 w-1/3 bg-slate" />
            </div>
          </div>
        ))}
      </div>
    </ContactSheet>
  );
}

export const SHEET =
  "grid grid-cols-1 gap-x-4 gap-y-7 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";

export function ContactSheet({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <div className="perforation" aria-hidden />
      <div className="py-6">{children}</div>
      <div className="perforation" aria-hidden />
    </div>
  );
}
