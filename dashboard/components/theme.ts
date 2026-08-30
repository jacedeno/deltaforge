"use client";

import { useEffect, useState } from "react";

/**
 * Charts read their colours from CSS custom properties, which do not notify
 * anyone when they change. This bumps a counter whenever the theme flips —
 * either by the toggle writing `data-theme`, or by the OS switching under a
 * viewer who never touched it — so chart options recompute against the new
 * palette instead of keeping the old one until the next data poll.
 */
export function useThemeTick(): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const bump = () => setTick((t) => t + 1);
    const observer = new MutationObserver(bump);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", bump);
    return () => {
      observer.disconnect();
      media.removeEventListener("change", bump);
    };
  }, []);

  return tick;
}

/** Resolve a CSS token to its current value. `tick` is the recompute trigger. */
export function token(name: string, _tick?: number): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
