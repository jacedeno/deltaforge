"use client";

import { useEffect, useState } from "react";

export default function ThemeToggle() {
  const [light, setLight] = useState(false);

  useEffect(() => {
    setLight(document.documentElement.getAttribute("data-theme") === "light");
  }, []);

  function toggle() {
    const next = !light;
    setLight(next);
    if (next) document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    try {
      localStorage.setItem("df-theme", next ? "light" : "dark");
    } catch {
      /* private mode — the choice just will not persist */
    }
  }

  return (
    <button
      onClick={toggle}
      className="font-mono2 text-[11px] px-3 py-1.5 rounded-md border"
      style={{ borderColor: "var(--border)", color: "var(--ink-secondary)" }}
      aria-label={light ? "Switch to dark theme" : "Switch to light theme"}
    >
      {light ? "◐ dark" : "◑ light"}
    </button>
  );
}
