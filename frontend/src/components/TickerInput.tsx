"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

interface Hit { symbol: string; name: string; exchange: string; type: string }

/** Ticker field with live suggestions (symbol or company name), keyboard navigable. */
export function TickerInput({ value, onChange, onPick, placeholder = "Ticker or company", className = "", autoFocus = false }: {
  value: string; onChange: (v: string) => void; onPick?: (symbol: string) => void; placeholder?: string; className?: string; autoFocus?: boolean;
}) {
  const [q, setQ] = useState(value);
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const typed = useRef(false);
  useEffect(() => { setQ(value); }, [value]);
  useEffect(() => {
    if (!typed.current || q.trim().length < 1) { setHits([]); return; }
    const t = setTimeout(async () => {
      try { setHits((await api<Hit[]>(`/api/market/search?q=${encodeURIComponent(q.trim())}`)).slice(0, 8)); setOpen(true); setI(0); } catch { setHits([]); }
    }, 200);
    return () => clearTimeout(t);
  }, [q]);
  const pick = (h: Hit) => { typed.current = false; setQ(h.symbol); onChange(h.symbol); setOpen(false); onPick?.(h.symbol); };
  return (
    <div className="relative w-full">
      <input value={q} autoFocus={autoFocus} placeholder={placeholder} aria-label="Ticker" autoComplete="off"
        onChange={e => { typed.current = true; setQ(e.target.value); onChange(e.target.value.toUpperCase()); }}
        onFocus={() => hits.length && setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={e => {
          if ((!open || !hits.length) && e.key === "Enter" && onPick && q.trim()) { e.preventDefault(); onPick(q.trim().toUpperCase()); return; }
          if (!open || !hits.length) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setI(x => Math.min(hits.length - 1, x + 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setI(x => Math.max(0, x - 1)); }
          else if (e.key === "Enter") { e.preventDefault(); pick(hits[i]); }
          else if (e.key === "Escape") setOpen(false);
        }}
        className={`w-full rounded border border-line bg-bg px-2 py-1.5 text-sm uppercase ${className}`} />
      {open && hits.length > 0 && (
        <ul role="listbox" className="absolute z-40 mt-1 max-h-72 w-full min-w-64 overflow-auto rounded-lg border border-line bg-card py-1 shadow-xl">
          {hits.map((h, k) => (
            <li key={h.symbol} role="option" aria-selected={k === i} onMouseDown={e => { e.preventDefault(); pick(h); }}
              className={`cursor-pointer px-3 py-1.5 text-sm ${k === i ? "bg-accent" : ""}`}>
              <span className="font-semibold">{h.symbol}</span> <span className="text-muted">{h.name}</span>
              <span className="float-right text-[11px] text-muted">{h.type} · {h.exchange}</span>
            </li>))}
        </ul>
      )}
    </div>
  );
}
