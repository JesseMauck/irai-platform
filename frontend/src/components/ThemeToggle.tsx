"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";

type Theme = "light" | "dark";

/** Light/dark switch. The choice is saved in this browser; until then the system setting is used. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);
  const { user, prefs, savePrefs } = useAuth();
  useEffect(() => { setTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark"); }, []);
  const toggle = () => {
    const next: Theme = theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("irai-theme", next); } catch { /* storage unavailable */ }
    setTheme(next);
    if (user) savePrefs({ ...prefs, theme: next }).catch(() => {});
  };
  const label = theme === "light" ? "Switch to dark mode" : "Switch to light mode";
  return (
    <button onClick={toggle} aria-label={label} title={label}
      className="rounded-md p-2 text-muted hover:bg-accent hover:text-fg">
      {theme === "light" ? (
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      )}
    </button>
  );
}
