/** The rights promise, restated on every page because it governs every page. */
export function Footer() {
  return (
    <footer className="mt-16 border-t border-rule pt-5 text-[13px] leading-relaxed text-paper-faint">
      <p className="max-w-[86ch]">
        Only clips in your own archive are hosted and playable here. YouTube,
        Internet Archive and Pexels results are a thumbnail, a title and a link
        back to the source. Nothing third party is downloaded or rehosted,
        including the shots you save.
      </p>
      <p className="mt-2">
        Searches and saved shots stay in this browser. Built on ClickHouse over
        MCP, Gemini and the Agent Development Kit. MIT licensed.
      </p>
    </footer>
  );
}
