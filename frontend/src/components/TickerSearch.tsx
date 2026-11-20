"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";

interface Hit { symbol: string; name: string; exchange?: string; type?: string }

/** Type any ticker or company name → jump to its live ticker page. ⌘K / Ctrl+K opens it. */
export function TickerSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [active, setActive] = useState(0);
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(o => !o); }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 10); else { setQ(""); setHits([]); } }, [open]);
  useEffect(() => {
    if (!q.trim()) { setHits([]); return; }
    const id = setTimeout(async () => {
      try { setHits(await api<Hit[]>(`/api/market/search?q=${encodeURIComponent(q.trim())}`)); setActive(0); } catch { setHits([]); }
    }, 180);
    return () => clearTimeout(id);
  }, [q]);

  const go = (sym: string) => { setOpen(false); router.push(`/ticker/${encodeURIComponent(sym.toUpperCase())}`); };
  const list: Hit[] = q.trim() && !hits.some(h => h.symbol.toUpperCase() === q.trim().toUpperCase())
    ? [{ symbol: q.trim().toUpperCase(), name: "Open this ticker" }, ...hits] : hits;

  return (
    <>
      <button onClick={() => setOpen(true)} className="flex items-center gap-2 rounded-lg border border-line bg-card px-3 py-1.5 text-sm text-muted hover:text-fg" aria-label="Search tickers">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <span className="hidden sm:inline">Search ticker</span>
        <kbd className="hidden rounded bg-accent px-1.5 text-[10px] sm:inline">⌘K</kbd>
      </button>
      {open && createPortal(
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[12vh]" onClick={() => setOpen(false)}>
          <div className="w-full max-w-xl overflow-hidden rounded-xl border border-line bg-card shadow-2xl" onClick={e => e.stopPropagation()}>
            <input ref={input} autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Any ticker or company: AAPL, Toyota, SPY, EURUSD=X, BTC-USD…"
              className="w-full border-b border-line bg-transparent px-4 py-3 text-base outline-none placeholder:text-muted"
              onKeyDown={e => {
                if (e.key === "ArrowDown") { e.preventDefault(); setActive(a => Math.min(a + 1, list.length - 1)); }
                if (e.key === "ArrowUp") { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
                if (e.key === "Enter" && list[active]) go(list[active].symbol);
              }} />
            <ul className="max-h-80 overflow-y-auto py-1">
              {list.map((h, i) => (
                <li key={h.symbol + i}>
                  <button onClick={() => go(h.symbol)} onMouseEnter={() => setActive(i)}
                    className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm ${i === active ? "bg-accent" : ""}`}>
                    <span><span className="font-semibold">{h.symbol}</span> <span className="text-muted">{h.name}</span></span>
                    <span className="text-xs text-muted">{[h.exchange, h.type].filter(Boolean).join(" · ")}</span>
                  </button>
                </li>
              ))}
              {!list.length && <li className="px-4 py-3 text-sm text-muted">Type a symbol and press Enter.</li>}
            </ul>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
