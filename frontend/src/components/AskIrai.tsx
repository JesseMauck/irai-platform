"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import { getAssistantContext, onAssistantContext } from "@/lib/assistant";
import { useAuth } from "@/components/AuthProvider";

interface M { role: "user" | "assistant"; content: string }

function fromPath(path: string) {
  const t = path.match(/^\/ticker\/([^/]+)/);
  const th = path.match(/^\/research\/themes\/([^/]+)/);
  const b = path.match(/^\/bots\/(\d+)/);
  return { symbol: t ? decodeURIComponent(t[1]).toUpperCase() : null, theme: th ? th[1] : null, bot_id: b ? parseInt(b[1]) : null };
}

const SUGGEST: Record<string, string[]> = {
  ticker: ["What are the main risks here?", "Explain the valuation in plain English", "What changed in the latest news?"],
  theme: ["What drives this theme?", "Which constituents lead and lag?", "What are the PESTEL risks?"],
  portfolio: ["What stands out in my portfolio?", "Explain my risk profile", "What should I research next?"],
  bot: ["Explain what this bot does", "How do my risk controls work?", "Why might live results differ from the backtest?"],
  other: ["What can Irradiance do?", "How does ValueBot value a company?", "What is the ADR monitor?"],
};

export function AskIrai() {
  const { user } = useAuth();
  const path = usePathname() || "/";
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<M[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [extra, setExtra] = useState(getAssistantContext());
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => onAssistantContext(setExtra), []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);
  if (path.startsWith("/ticker/") && path.endsWith("/report")) return null; // keep printed reports clean
  const pc = fromPath(path);
  const symbol = pc.symbol ?? extra.symbol ?? null;
  const portfolio_id = path.startsWith("/portfolio") ? extra.portfolio_id ?? null : null;
  const kind = pc.bot_id ? "bot" : portfolio_id ? "portfolio" : pc.theme ? "theme" : symbol ? "ticker" : "other";
  const label = pc.bot_id ? "this bot" : portfolio_id ? "your portfolio" : pc.theme ? "this theme" : symbol ? symbol : null;
  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    const next = [...msgs, { role: "user" as const, content: text.trim() }];
    setMsgs(next); setQ(""); setBusy(true); setErr(null);
    try {
      const r = await api<{ reply: string }>("/api/assistant", { method: "POST", json: { messages: next, path, symbol, theme: pc.theme, bot_id: pc.bot_id, portfolio_id } });
      setMsgs([...next, { role: "assistant", content: r.reply }]);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="print:hidden">
      {!open && <button onClick={() => setOpen(true)} className="solar-bg fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-primary-fg shadow-lg hover:brightness-110" aria-label="Ask IRAI">
        <span aria-hidden>✦</span> Ask IRAI{label && <span className="font-normal opacity-80">· {label}</span>}</button>}
      {open && (
        <div className="fixed bottom-5 right-5 z-50 flex h-[560px] max-h-[80vh] w-[380px] max-w-[calc(100vw-2.5rem)] flex-col overflow-hidden rounded-2xl border border-line bg-card shadow-2xl">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <div><div className="text-sm font-semibold">Ask IRAI</div><div className="text-[11px] text-muted">{label ? `Looking at ${label}` : "Research assistant"}</div></div>
            <div className="flex gap-2 text-muted">{msgs.length > 0 && <button onClick={() => setMsgs([])} className="text-[11px] hover:text-fg">Clear</button>}<button onClick={() => setOpen(false)} aria-label="Close" className="hover:text-fg">✕</button></div>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm">
            {!user ? <div className="text-muted"><p>Ask questions about any ticker, theme, portfolio or bot, in plain English.</p><Link href={`/login?next=${encodeURIComponent(path)}`} className="mt-2 inline-block text-primary">Sign in to ask</Link></div>
              : !msgs.length ? <div><p className="text-muted">Ask about what&apos;s on this page, or anything on Irradiance.</p>
                <div className="mt-3 flex flex-col gap-1.5">{SUGGEST[kind].map(s => <button key={s} onClick={() => send(s)} className="rounded-lg border border-line px-3 py-1.5 text-left text-xs hover:border-primary">{s}</button>)}</div></div>
              : msgs.map((m, i) => <div key={i} className={m.role === "user" ? "ml-8 rounded-lg bg-primary/10 px-3 py-2" : "prose-irai text-sm"}>{m.role === "user" ? m.content : <ReactMarkdown>{m.content}</ReactMarkdown>}</div>)}
            {busy && <div className="text-xs text-muted">Thinking…</div>}
            {err && <div className="text-xs text-down">{err}</div>}
            <div ref={end} />
          </div>
          {user && <form onSubmit={e => { e.preventDefault(); send(q); }} className="border-t border-line p-2">
            <div className="flex gap-2"><input value={q} onChange={e => setQ(e.target.value)} placeholder={label ? `Ask about ${label}…` : "Ask anything…"} maxLength={2000} className="flex-1 rounded-lg border border-line bg-bg px-3 py-2 text-sm" />
              <button type="submit" disabled={busy || !q.trim()} className="solar-bg rounded-lg px-3 text-sm font-semibold text-primary-fg disabled:opacity-50">Send</button></div>
            <p className="mt-1 px-1 text-[10px] text-muted">AI answers can be wrong. Research and education only, not investment advice.</p>
          </form>}
        </div>)}
    </div>
  );
}
