import { SOURCE_META, type SourceId } from "@/lib/types";

/**
 * The label stencilled under a frame on a contact sheet: where this clip came
 * from, in the only monospace on the page. Tungsten means the editor owns it
 * and it plays here; print teal plus the arrow means it lives somewhere else
 * and clicking leaves the site.
 */
export function SourceStamp({
  source,
  external,
}: {
  source: SourceId;
  external?: boolean;
}) {
  const meta = SOURCE_META[source];
  return (
    <span
      className={`font-mono text-[11px] font-medium tracking-[0.18em] uppercase ${meta.stamp}`}
    >
      {meta.label}
      {external ? (
        <>
          <span aria-hidden>&nbsp;↗</span>
          <span className="sr-only"> (opens on {meta.site})</span>
        </>
      ) : null}
    </span>
  );
}
