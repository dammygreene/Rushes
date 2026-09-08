import { SourceStamp } from "./SourceStamp";
import { SOURCE_META, SOURCE_ORDER } from "@/lib/types";

/** First run: what the four lanes are, before anything has been searched. */
export function EmptyState() {
  return (
    <section>
      <p className="max-w-[64ch] text-[15px] leading-relaxed text-paper-dim">
        Name the subject, the light and the movement rather than the feeling. A
        Gemini planner turns that into one dense sentence for your own archive
        and a short keyword query for the public web.
      </p>
      <dl className="mt-6 divide-y divide-rule border-y border-rule">
        {SOURCE_ORDER.map((source) => (
          <div
            key={source}
            className="grid gap-x-6 gap-y-1 py-3 sm:grid-cols-[13rem_minmax(0,1fr)]"
          >
            <dt className="leading-6">
              <SourceStamp source={source} external={source !== "archive"} />
            </dt>
            <dd className="text-[14px] leading-6 text-paper-dim">
              {SOURCE_META[source].blurb}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Nothing came back. Say what to try instead of showing an empty sheet. */
export function NoResults({ query }: { query: string }) {
  return (
    <section className="border-y border-rule bg-slate px-4 py-5">
      <h2 className="text-[15px] font-medium">
        Nothing matched{" "}
        <span className="font-display text-[17px] italic">“{query}”</span>.
      </h2>
      <p className="mt-2 max-w-[64ch] text-[14px] leading-relaxed text-paper-dim">
        Every source answered, but none had a clip close enough to keep. Try
        naming the subject and the light rather than the feeling: “wet asphalt at
        dusk, headlights” finds more than “melancholy”.
      </p>
    </section>
  );
}

/** A failed request. Deliberately distinct from "nothing matched". */
export function ErrorState({ message }: { message: string }) {
  return (
    <section role="alert" className="border-y border-rule bg-slate px-4 py-5">
      <h2 className="text-[15px] font-medium">The search did not run.</h2>
      <p className="mt-2 font-mono text-[12px] leading-relaxed break-words text-paper-dim">
        {message}
      </p>
      <p className="mt-3 max-w-[64ch] text-[14px] leading-relaxed text-paper-dim">
        Check that the backend is up (
        <code className="font-mono text-paper">rushes-api</code>) and that{" "}
        <code className="font-mono text-paper">BACKEND_URL</code> points at it.
      </p>
    </section>
  );
}

/** An empty shelf: past searches or saved shots, before anything is on one. */
export function EmptyShelf({ children }: { children: React.ReactNode }) {
  return (
    <p className="border-y border-rule bg-slate px-4 py-5 text-[14px] leading-relaxed text-paper-dim">
      {children}
    </p>
  );
}

/**
 * The top of a shelf page: what it holds, and — once it holds something — the
 * one control that empties it. Deliberately quieter than the search headline,
 * which is the only place on the site that gets the full display size.
 */
export function ShelfHead({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-10 sm:mt-14">
      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2 border-b border-rule pb-4">
        <h1 className="font-display text-[clamp(2rem,5vw,3.5rem)] leading-none font-medium tracking-[-0.01em]">
          {title}
        </h1>
        {action}
      </div>
      <p className="mt-4 max-w-[64ch] text-[15px] leading-relaxed text-paper-dim">
        {children}
      </p>
    </div>
  );
}
