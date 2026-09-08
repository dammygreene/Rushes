import { SOURCE_META, type SearchPlan, type SourceReport } from "@/lib/types";

/**
 * The slate: what the planner agent understood, filled in like the fields on a
 * clapperboard so the search is not a black box. The archive query is set in
 * italic serif because it is a sentence written for a machine to feel, not a
 * keyword string; the web query is monospace because it is literally a query.
 */
export function PlanPanel({ plan, query }: { plan: SearchPlan; query: string }) {
  const rewritten = plan.archive_query && plan.archive_query !== query;

  // Objects rather than tuples: JSX inside an array literal trips react/jsx-key,
  // though the key lives on the row wrapper below.
  const rows: { label: string; value: React.ReactNode }[] = [];
  if (plan.archive_query) {
    rows.push({
      label: rewritten ? "Archive query, rewritten to embed" : "Archive query",
      value: (
        <span className="font-display text-[17px] leading-snug italic">
          {plan.archive_query}
        </span>
      ),
    });
  }
  if (plan.web_query) {
    rows.push({
      label: "Web query",
      value: <span className="font-mono text-[13px]">{plan.web_query}</span>,
    });
  }
  if (plan.keywords.length > 0) {
    rows.push({
      label: "Keywords",
      value: (
        <span className="font-mono text-[13px]">{plan.keywords.join(", ")}</span>
      ),
    });
  }
  for (const [label, value] of [
    ["Mood", plan.mood],
    ["Shot", plan.shot_type],
    ["Setting", plan.setting],
    ["Subjects", plan.subjects.join(", ")],
  ] as [string, string][]) {
    if (value) {
      rows.push({ label, value: <span className="text-[14px]">{value}</span> });
    }
  }

  return (
    <section>
      <h2 className="text-[12px] text-paper-dim">
        What the planner understood
      </h2>
      <dl className="mt-2 divide-y divide-rule border-y border-rule bg-slate">
        {rows.map(({ label, value }) => (
          <div
            key={label}
            className="grid gap-x-6 gap-y-1 px-4 py-3 sm:grid-cols-[13rem_minmax(0,1fr)]"
          >
            <dt className="text-[12px] leading-6 text-paper-faint">{label}</dt>
            {/* A rewritten archive query is a whole sentence and the keyword
                list can be one long token; neither may push the panel wider
                than a phone. */}
            <dd className="max-w-[78ch] break-words text-paper">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** Per-source outcome. A dead API is visible instead of silently missing. */
export function SourceStrip({
  sources,
  totalMs,
  warnings,
}: {
  sources: SourceReport[];
  totalMs: number;
  warnings: string[];
}) {
  return (
    <section>
      {/* The strip reads itself in print; a screen reader landing on the region
          needs it named. */}
      <h2 className="sr-only">What each source returned</h2>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-rule pb-2.5">
        {sources.map((report) => {
          const meta = SOURCE_META[report.source];
          return (
            <span
              key={report.source}
              title={report.note || undefined}
              className="text-[13px] text-paper-dim"
            >
              {meta.label}{" "}
              {report.ok ? (
                <span className={`font-mono tabular-nums ${meta.stamp}`}>
                  {report.count}
                </span>
              ) : (
                <span className="text-paper-faint">unavailable</span>
              )}
            </span>
          );
        })}
        <span className="ml-auto font-mono text-[12px] tabular-nums text-paper-faint">
          {sources.length} sources in {(totalMs / 1000).toFixed(1)}s
        </span>
      </div>

      {warnings.length > 0 ? (
        <ul className="mt-2.5 space-y-1">
          {warnings.map((warning) => (
            <li key={warning} className="text-[13px] text-paper-dim">
              {warning}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
