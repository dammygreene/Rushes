import type { Metadata } from "next";
import { SavedView } from "@/components/SavedView";

export const metadata: Metadata = { title: "Saved shots" };

export default function SavedPage() {
  return <SavedView />;
}
