"use client";

import { useSyncExternalStore } from "react";
import type { StatusResponse } from "@/lib/types";

export interface BackendStatus {
  status: StatusResponse | null;
  failed: boolean;
}

const CONNECTING: BackendStatus = { status: null, failed: false };

/**
 * The answer lives in the module, not in a component, because several places on
 * every page want it: the lamp and the notes in the masthead, the frame counter
 * in the hero. One request serves them all, and it outlives navigation.
 */
let current: BackendStatus = CONNECTING;
/** True once a real answer is in. A failure is not one: the backend may come up. */
let settled = false;
let asking = false;

const listeners = new Set<() => void>();

function ask(): void {
  if (asking || settled) return;
  asking = true;
  void fetch("/api/status")
    .then((response) =>
      response.ok ? response.json() : Promise.reject(new Error("status")),
    )
    .then((status: StatusResponse): BackendStatus => ({ status, failed: false }))
    .catch((): BackendStatus => ({ status: null, failed: true }))
    .then((result) => {
      current = result;
      settled = !result.failed;
      asking = false;
      listeners.forEach((listener) => listener());
    });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Mounting a reader is what starts the request, and asking is idempotent.
  ask();
  return () => {
    listeners.delete(listener);
  };
}

/**
 * `/api/status` is the endpoint that proves the wiring: the clip count in it
 * travelled over MCP from ClickHouse. Read as an external store, so the server
 * render and the first paint agree on "connecting" and nothing flashes.
 */
export function useBackendStatus(): BackendStatus {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => CONNECTING,
  );
}

/**
 * A tally lamp, not a row of badges: lit when the backend answered, hollow when
 * it did not, and captioned only when something is wrong. Anything degraded is
 * said in a sentence underneath rather than encoded in a colour, so it survives
 * being read aloud or printed.
 */
export function StatusLamp({ status, failed }: BackendStatus) {
  const live = Boolean(status) && !failed;
  return (
    <span className="inline-flex items-center gap-2">
      <span
        aria-hidden
        className={`size-2 rounded-full ${
          live ? "bg-paper" : "border border-rule"
        }`}
      />
      <span className="sr-only">
        {failed
          ? "Backend unreachable."
          : live
            ? "Backend connected."
            : "Connecting to the backend."}
      </span>
      {live ? null : (
        <span className="font-mono text-[11px] text-paper-faint">
          {failed ? "offline" : "…"}
        </span>
      )}
    </span>
  );
}

/** Whatever is degraded, said plainly. Renders nothing when all is well. */
export function StatusNotes({ status, failed }: BackendStatus) {
  const notes: React.ReactNode[] = [];

  if (failed) {
    notes.push(
      <>
        Rushes can’t reach its search backend yet. Run{" "}
        <code className="bg-slate px-1 font-mono text-paper">rushes-api</code> to
        start it.
      </>,
    );
  } else if (status) {
    if (typeof status.clickhouse.clips !== "number") {
      notes.push(
        <>
          The archive isn’t answering, so only the public sources will return
          clips.
        </>,
      );
    }
    if (!status.gemini.configured) {
      notes.push(
        <>No Gemini key is set, so matching falls back to keyword overlap.</>,
      );
    }
  }

  if (notes.length === 0) return null;

  return (
    <div className="mt-3 space-y-1 text-[13px] leading-relaxed text-paper">
      {notes.map((note, index) => (
        <p key={index} className="max-w-[62ch]">
          {note}
        </p>
      ))}
    </div>
  );
}

/**
 * The frame counter: how many of the editor's own clips are indexed. Tungsten
 * because they are theirs. Padded to four digits so the number sits still.
 */
export function FrameCounter({ status, failed }: BackendStatus) {
  const clips =
    typeof status?.clickhouse.clips === "number" ? status.clickhouse.clips : null;
  const known = clips !== null;

  return (
    <div className="sm:text-right">
      <p
        className={`font-mono text-4xl leading-none tabular-nums sm:text-5xl ${
          known ? "text-tungsten" : "text-rule"
        }`}
        aria-hidden={!known}
      >
        {String(known ? clips : 0).padStart(4, "0")}
      </p>
      <p className="mt-2 text-[12px] leading-snug text-paper-dim">
        {known ? "clips in your own archive" : "archive count unavailable"}
      </p>
      <p className="text-[12px] leading-snug text-paper-faint">
        {known
          ? "counted over MCP, indexed by meaning"
          : failed
            ? "the backend has not answered"
            : "counting over MCP"}
      </p>
    </div>
  );
}
