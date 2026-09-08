import { Suspense } from "react";
import { SearchView, SearchViewFallback } from "@/components/SearchView";

/**
 * A server shell around a client view. The query is read from the URL with
 * `useSearchParams`, which suspends, so the boundary is required rather than
 * decorative: without it a production build of this static page fails outright.
 */
export default function Home() {
  return (
    <Suspense fallback={<SearchViewFallback />}>
      <SearchView />
    </Suspense>
  );
}
