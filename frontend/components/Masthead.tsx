"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { StatusLamp, StatusNotes, useBackendStatus } from "./Status";
import { usePastSearches, useSavedShots } from "@/lib/store";

/**
 * Above every page: the wordmark, the three places there are to be, and the
 * tally lamp. The two counts come from this browser's own store, so they are
 * blank for the first paint and then settle — nothing on the server knows what
 * you searched or kept.
 */
export function Masthead() {
  const pathname = usePathname();
  const backend = useBackendStatus();
  const { entries } = usePastSearches();
  const { saved } = useSavedShots();

  const tabs = [
    { href: "/", label: "Search", count: 0 },
    { href: "/history", label: "History", count: entries.length },
    { href: "/saved", label: "Saved", count: saved.length },
  ];

  return (
    <header>
      {/* One row that becomes two rather than a hamburger: three destinations
          are worth showing outright at any width. Below `sm` the wordmark and
          the lamp share the top line and the tabs take the whole next one;
          above it, `order` puts them back in a single baseline row. */}
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-rule pt-4 pb-2 sm:gap-y-2 sm:pb-4">
        <Link
          href="/"
          className="inline-flex items-baseline gap-2.5 text-paper sm:order-1"
        >
          {/* Our own mark, so unlike a source's thumbnail it is ours to
              optimise. Decorative: the wordmark beside it says the name. The
              nudge sits the disc optically on the word rather than on the
              baseline its own bottom edge would land on. */}
          <Image
            src="/rushes-logo.png"
            alt=""
            width={20}
            height={20}
            priority
            className="translate-y-[3px]"
          />
          <span className="font-display text-[20px] tracking-[-0.01em]">
            Rushes
          </span>
        </Link>
        {/* Ahead of the tabs in source order so the mobile wrap puts it on the
            first line beside the wordmark; `order` moves it back to the end of
            the single row above `sm`. */}
        <div className="ml-auto sm:order-3">
          <StatusLamp {...backend} />
        </div>
        <nav
          aria-label="Sections"
          className="flex w-full items-baseline gap-6 sm:order-2 sm:w-auto"
        >
          {tabs.map((tab) => {
            const here = pathname === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={here ? "page" : undefined}
                // The negative margin buys a 30px tall target without moving
                // the baseline the row is aligned on.
                className={`-my-1.5 py-1.5 text-[13px] transition-colors ${
                  here
                    ? "text-paper underline decoration-paper-faint decoration-1 underline-offset-[6px]"
                    : "text-paper-dim hover:text-paper"
                }`}
              >
                {tab.label}
                {tab.count > 0 ? (
                  <span className="ml-1.5 font-mono text-[11px] tabular-nums text-paper-faint">
                    {tab.count}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>
      </div>
      <StatusNotes {...backend} />
    </header>
  );
}
