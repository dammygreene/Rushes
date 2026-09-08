"use client";

import Link from "next/link";
import { useState } from "react";

const EXAMPLES = [
  "a lone figure on a rain-slicked neon street",
  "1950s traffic in a busy downtown",
  "waves breaking over black rock",
];

/** Every way of starting a search ends up here: the query lives in the URL. */
export function searchHref(query: string): string {
  return `/?q=${encodeURIComponent(query.trim())}`;
}

/**
 * A real GET form pointed at `/`, so a submit that beats hydration still lands
 * on `/?q=…`; the handler below only takes over to keep the navigation on the
 * client. The examples are links for the same reason.
 */
export function SearchBar({
  query,
  pending,
  onSearch,
}: {
  query: string;
  pending: boolean;
  onSearch: (query: string) => void;
}) {
  const [value, setValue] = useState(query);
  const [shown, setShown] = useState(query);

  // Stepping back to an earlier search puts its words back in the field.
  if (query !== shown) {
    setShown(query);
    setValue(query);
  }

  return (
    <div>
      <form
        action="/"
        method="get"
        onSubmit={(event) => {
          event.preventDefault();
          const trimmed = value.trim();
          if (!trimmed || pending) return;
          setValue(trimmed);
          onSearch(trimmed);
        }}
      >
        <label htmlFor="q" className="block text-[12px] text-paper-dim">
          Your shot, in one sentence
        </label>
        <div className="mt-2 flex flex-col gap-px sm:flex-row">
          <input
            id="q"
            name="q"
            type="text"
            value={value}
            maxLength={400}
            autoComplete="off"
            disabled={pending}
            // 16px keeps iOS from zooming the page on focus, and the search
            // hint puts "search" on the software keyboard's return key.
            enterKeyHint="search"
            onChange={(event) => setValue(event.target.value)}
            placeholder="a lone figure on a rain-slicked neon street"
            className="min-h-12 flex-1 border border-rule bg-slate px-4 py-3 text-[16px] text-paper transition-colors placeholder:font-display placeholder:text-[15px] placeholder:italic placeholder:text-paper-faint focus:border-tungsten disabled:opacity-60 sm:placeholder:text-[17px]"
          />
          <button
            type="submit"
            disabled={pending || value.trim().length === 0}
            className="min-h-12 cursor-pointer bg-tungsten px-6 text-[15px] font-medium text-ink transition-opacity duration-200 hover:opacity-90 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 sm:min-w-32"
          >
            {pending ? "Searching" : "Search"}
          </button>
        </div>
      </form>

      {/* Stacked rather than run into one sentence: at 375px the three phrases
          wrap into a paragraph whose links break mid-word, and each line here
          is a 36px target instead of a fragment of a shared one. */}
      <div className="mt-4">
        <p className="text-[12px] text-paper-dim">Or try one of these</p>
        <ul className="mt-1">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <Link
                href={searchHref(example)}
                prefetch={false}
                className="inline-block py-1.5 font-display text-[16px] leading-snug italic text-paper underline decoration-rule decoration-1 underline-offset-4 transition-colors hover:decoration-paper"
              >
                {example}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
