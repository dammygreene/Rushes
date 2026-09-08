"use client";

import { useState } from "react";

/**
 * A frame of the editor's own footage. It stays a still picture until asked to
 * play, so the contact sheet is not a row of browser control bars, and so the
 * clip is only fetched when someone actually wants to see it. Reached only for
 * clips we host ourselves; third-party results never get this far.
 */
export function ClipFrame({
  src,
  poster,
  title,
}: {
  src: string;
  poster: string | null;
  title: string;
}) {
  const [playing, setPlaying] = useState(false);

  if (playing) {
    return (
      <video
        className="absolute inset-0 h-full w-full object-cover"
        src={src}
        poster={poster ?? undefined}
        controls
        autoPlay
        // Without this iOS Safari takes the clip fullscreen the moment it
        // plays, which loses the sheet the editor was scanning.
        playsInline
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setPlaying(true)}
      className="group/play absolute inset-0 flex cursor-pointer items-center justify-center"
    >
      {poster ? (
        <img
          src={poster}
          alt=""
          loading="lazy"
          decoding="async"
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : null}
      <span
        aria-hidden
        className="relative flex size-11 items-center justify-center bg-tungsten text-ink transition-opacity duration-200 group-hover/play:opacity-90 group-active/play:opacity-75"
      >
        <svg viewBox="0 0 12 14" className="h-3.5 w-3 fill-current">
          <polygon points="0,0 12,7 0,14" />
        </svg>
      </span>
      <span className="sr-only">Play “{title}”</span>
    </button>
  );
}
