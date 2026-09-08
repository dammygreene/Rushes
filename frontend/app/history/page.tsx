import type { Metadata } from "next";
import { HistoryView } from "@/components/HistoryView";

export const metadata: Metadata = { title: "Past searches" };

export default function HistoryPage() {
  return <HistoryView />;
}
