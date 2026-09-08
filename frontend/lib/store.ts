"use client";

/**
 * What this browser remembers: the searches you have run, and the shots you kept.
 *
 * It lives in localStorage, which is a choice rather than a shortcut. The search
 * path on the server is read-only over MCP, Rushes has no accounts, and giving
 * "my saved shots" a table would put a second, quite different story into a
 * schema that exists to hold footage.
 *
 * A past search keeps its whole response, not just the query. Re-opening one is
 * then instant and free, which matters twice over: a plan-then-search round trip
 * is two Gemini calls against a free tier of twenty a day, and it is what lets
 * the browser's back button behave like a back button.
 */

import { useCallback, useMemo, useSyncExternalStore } from "react";
import type { SearchHit, SearchResponse } from "./types";

export interface PastSearch {
  /** Exactly the words that were searched, and the key we look up by. */
  query: string;
  /** Epoch ms, absolute, so a restored search can say how old it is. */
  at: number;
  response: SearchResponse;
}

export interface SavedShot {
  /** `${source}:${id}`, the same key the contact sheet keys its frames by. */
  key: string;
  /** The search that turned it up, kept as context on the shelf. */
  query: string;
  at: number;
  hit: SearchHit;
}

const HISTORY_KEY = "rushes.history.v1";
const SAVED_KEY = "rushes.saved.v1";

/** A past search carries a whole response, so the shelf is short on purpose. */
export const HISTORY_LIMIT = 12;
const SAVED_LIMIT = 240;

const NEVER = () => () => {};
const YES = () => true;
const NO = () => false;

/** False for the render the server produced, true once the browser is in charge. */
function useReady(): boolean {
  return useSyncExternalStore(NEVER, YES, NO);
}

export function hitKey(hit: SearchHit): string {
  return `${hit.source}:${hit.id}`;
}

/**
 * localStorage is user-writable, so the rule that matters is re-applied on the
 * way in rather than trusted: only an archive clip we host ourselves may carry a
 * playable URL. Anything else is a thumbnail, a title and a link out, however
 * the stored JSON came to look.
 */
function reviveHit(hit: SearchHit): SearchHit {
  if (hit.source === "archive" && hit.hosted_by_us) return hit;
  return { ...hit, hosted_by_us: false, clip_url: null };
}

/** One stable empty array, so a server render and a fresh browser agree. */
const BLANK: never[] = [];

interface Shelf<T> {
  read: () => readonly T[];
  blank: () => readonly T[];
  write: (rows: readonly T[]) => void;
  subscribe: (listener: () => void) => () => void;
}

/**
 * A newest-first list under one localStorage key, readable by
 * `useSyncExternalStore`: the parsed rows are held so repeated reads return the
 * same array, and every writer wakes both this tab's subscribers and any others.
 */
function shelf<T>(key: string, limit: number, revive: (row: T) => T): Shelf<T> {
  let rows: readonly T[] | null = null;
  const listeners = new Set<() => void>();
  const announce = () => listeners.forEach((listener) => listener());

  const onStorage = (event: StorageEvent) => {
    // A null key means the whole store was cleared, here or in another tab.
    if (event.key === null || event.key === key) {
      rows = null;
      announce();
    }
  };

  const load = (): readonly T[] => {
    if (typeof window === "undefined") return BLANK;
    try {
      const raw = window.localStorage.getItem(key);
      const parsed: unknown = JSON.parse(raw ?? "null");
      return Array.isArray(parsed) ? (parsed as T[]).map(revive) : BLANK;
    } catch {
      // Storage disabled, or a half-written value. Start empty, don't throw.
      return BLANK;
    }
  };

  /** Shed the oldest rows rather than lose the write when the quota is hit. */
  const persist = (wanted: readonly T[]): readonly T[] => {
    if (typeof window === "undefined") return wanted;
    for (let size = wanted.length; size >= 0; size--) {
      const kept = wanted.slice(0, size);
      try {
        window.localStorage.setItem(key, JSON.stringify(kept));
        return kept;
      } catch {
        continue;
      }
    }
    return wanted;
  };

  return {
    read: () => (rows ??= load()),
    blank: () => BLANK,
    write: (next) => {
      rows = persist(next.slice(0, limit));
      announce();
    },
    subscribe: (listener) => {
      if (listeners.size === 0) window.addEventListener("storage", onStorage);
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) {
          window.removeEventListener("storage", onStorage);
        }
      };
    },
  };
}

const searches = shelf<PastSearch>(HISTORY_KEY, HISTORY_LIMIT, (entry) => ({
  ...entry,
  response: {
    ...entry.response,
    results: entry.response.results.map(reviveHit),
  },
}));

const shots = shelf<SavedShot>(SAVED_KEY, SAVED_LIMIT, (shot) => ({
  ...shot,
  hit: reviveHit(shot.hit),
}));

/**
 * Filed under the words that were typed, not under the response's own echo of
 * them, so that recalling a search always finds what running it stored.
 */
export function rememberSearch(query: string, response: SearchResponse): void {
  const asked = query.trim();
  if (!asked) return;
  const rest = searches.read().filter((entry) => entry.query !== asked);
  searches.write([{ query: asked, at: Date.now(), response }, ...rest]);
}

/** The stored response for a query, if this browser has run it before. */
export function recallSearch(query: string): PastSearch | null {
  const asked = query.trim();
  return searches.read().find((entry) => entry.query === asked) ?? null;
}

export function usePastSearches() {
  const ready = useReady();
  const entries = useSyncExternalStore(
    searches.subscribe,
    searches.read,
    searches.blank,
  );

  const forget = useCallback((query: string) => {
    searches.write(searches.read().filter((entry) => entry.query !== query));
  }, []);
  const clear = useCallback(() => searches.write(BLANK), []);

  return { entries, forget, clear, ready };
}

export function useSavedShots() {
  const ready = useReady();
  const saved = useSyncExternalStore(shots.subscribe, shots.read, shots.blank);
  const keys = useMemo(
    () => new Set(saved.map((shot) => shot.key)),
    [saved],
  );

  const toggle = useCallback((hit: SearchHit, query: string) => {
    const key = hitKey(hit);
    const rows = shots.read();
    const without = rows.filter((shot) => shot.key !== key);
    const removing = without.length < rows.length;
    const kept: SavedShot = { key, query, at: Date.now(), hit: reviveHit(hit) };
    shots.write(removing ? without : [kept, ...rows]);
  }, []);

  const clear = useCallback(() => shots.write(BLANK), []);

  return { saved, keys, toggle, clear, ready };
}
