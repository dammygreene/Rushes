"use client";

import { useState } from "react";

/**
 * Emptying a shelf cannot be undone: the store is this browser, and there is no
 * copy of it on a server. So the button asks once, in place, rather than opening
 * a dialog over the page. Moving away from it puts the question back.
 */
export function ClearButton({
  label,
  confirm,
  onConfirm,
}: {
  label: string;
  confirm: string;
  onConfirm: () => void;
}) {
  const [asking, setAsking] = useState(false);

  return (
    <button
      type="button"
      onClick={() => {
        if (!asking) {
          setAsking(true);
          return;
        }
        setAsking(false);
        onConfirm();
      }}
      onBlur={() => setAsking(false)}
      // Padded past 24px in place, then pulled back out so the label stays
      // flush with the heading rule it sits on. The 44px touch overlay only
      // ever extends over the headline beside it, which is not a target.
      className={`tap -mx-2 -my-1.5 cursor-pointer px-2 py-1.5 font-mono text-[11px] font-medium tracking-[0.14em] uppercase transition-colors ${
        asking ? "text-tungsten" : "text-paper-faint hover:text-paper"
      }`}
    >
      {asking ? confirm : label}
    </button>
  );
}
