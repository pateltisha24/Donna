"use client";

import React, { useEffect, useState } from "react";

type Theme = "dark" | "light";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const saved = (localStorage.getItem("donna_theme") as Theme) || "dark";
    setTheme(saved);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("donna_theme", next);
  };

  return (
    <button
      onClick={toggle}
      aria-label="Toggle theme"
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="w-8 h-8 rounded-full flex items-center justify-center text-sm transition-colors"
      style={{
        backgroundColor: "var(--surface-2)",
        color: "var(--muted)",
        border: "1px solid var(--border)",
      }}
    >
      {theme === "dark" ? "☀" : "☾"}
    </button>
  );
}
