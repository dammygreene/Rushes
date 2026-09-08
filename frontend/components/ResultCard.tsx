import { ClipFrame } from "./ClipFrame";
import { SaveButton } from "./SaveButton";
import { SourceStamp } from "./SourceStamp";
import { SOURCE_META, formatDuration, type SearchHit } from "@/lib/types";

/**
 * One frame on the contact sheet: the picture, a hairline, then the margin.
 * The licensing rule is enforced here, not just documented: only clips we host
 * ourselves are handed to a <video> element. Everything else is a thumbnail, a
 * title and an outbound link to the source's own page.
 */
export function ResultCard({
  hit,
  query,
}: {
  hit: SearchHit;
  /** The search this frame came out of, filed with it when it is saved. */
  query?: string;
}) {
  const duration = formatDuration(hit.duration_seconds);
  const clipUrl = hit.hosted_by_us ? hit.clip_url : null;
  const linked = Boolean(hit.page_url) && !clipUrl;

  return (
    <article className="group flex h-full flex-col">
      <div className="relative aspect-video bg-black">
        {clipUrl ? (
          <ClipFrame
            src={clipUrl}
            poster={hit.thumbnail_url}
            title={hit.title}
          />
        ) : (
          <Thumbnail hit={hit} />
        )}
      </div>

      <div className="flex flex-1 flex-col border-t border-rule pt-2.5">
        <h3 className="text-[15px] leading-snug font-medium text-pretty">
          {linked ? (
            <a
              href={hit.page_url ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              className="line-clamp-2 underline decoration-rule decoration-1 underline-offset-4 transition-colors hover:decoration-paper"
            >
              {hit.title}
            </a>
          ) : (
            <span className="line-clamp-2">{hit.title}</span>
          )}
        </h3>

        {hit.match_reason ? (
          <p className="mt-1.5 line-clamp-2 text-[13px] leading-snug text-paper-dim">
            <span className="sr-only">Why this matched: </span>
            {hit.match_reason}
          </p>
        ) : null}

        {/* The frame's margin. 11px rather than 10px: these are stencil labels,
            but they are also the licence and the source, and 10px mono is below
            the floor for anything a reader is expected to actually read. */}
        <div className="mt-auto flex flex-wrap items-baseline gap-x-3 gap-y-2 pt-3">
          <SourceStamp source={hit.source} external={linked} />
          {duration ? (
            <span className="font-mono text-[11px] tabular-nums text-paper-dim">
              {duration}
            </span>
          ) : null}
          <span className="max-w-full min-w-0 truncate font-mono text-[11px] text-paper-faint">
            {hit.license || "licence unknown"}
          </span>
          <span
            className="ml-auto font-mono text-[11px] tabular-nums text-paper-faint"
            title="Blended relevance. Archive hits start from cosine similarity in ClickHouse; web hits from rank position plus keyword overlap."
          >
            <span className="sr-only">Relevance </span>
            {hit.score.toFixed(2)}
          </span>
          <SaveButton hit={hit} query={query} />
        </div>
      </div>
    </article>
  );
}

function Thumbnail({ hit }: { hit: SearchHit }) {
  if (!hit.thumbnail_url) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate">
        <span className="font-mono text-[11px] tracking-[0.18em] text-paper-faint uppercase">
          no preview
        </span>
      </div>
    );
  }

  const image = (
    // Deliberately not next/image: optimising a third party's thumbnail would
    // mean caching their media on our servers. We hotlink and link back.
    <img
      src={hit.thumbnail_url}
      alt=""
      loading="lazy"
      decoding="async"
      // The wrapper is aspect-video, so the box is already reserved and a
      // sheet of twenty-four thumbnails arriving cannot shift the layout.
      className="h-full w-full object-cover"
    />
  );

  return hit.page_url ? (
    <a
      href={hit.page_url}
      target="_blank"
      rel="noopener noreferrer"
      className="block h-full w-full"
      aria-label={`Open “${hit.title}” on ${SOURCE_META[hit.source].site}`}
    >
      {image}
    </a>
  ) : (
    image
  );
}
