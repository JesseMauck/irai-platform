"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { onChatsChanged, openIrai } from "@/lib/assistant";
import { useAuth } from "@/components/AuthProvider";

type Item = { href: string; label: string; icon: string; pro?: boolean; badge?: string };
const GROUPS: { title: string; items: Item[] }[] = [
  { title: "Workspace", items: [
    { href: "/terminal", label: "Terminal", icon: "M3 5h18v14H3zM7 9l3 3-3 3M12 15h5" },
    { href: "/library", label: "Library", icon: "M4 4h4v16H4zM10 4h4v16h-4zM16 5l4 1-3 14-4-1z" },
    { href: "/history", label: "History", icon: "M12 7v5l3 2M3 12a9 9 0 1 0 3-6.7M3 4v4h4" },
  ] },
  { title: "Trade", items: [
    { href: "/trade", label: "Trade", icon: "M4 17l5-5 4 4 7-8M14 8h6v6" },
    { href: "/bots", label: "Automation", icon: "M9 3h6v3H9zM5 8h14v10H5zM9 12h.01M15 12h.01M9 15h6", pro: true },
    { href: "/strategies", label: "Strategy marketplace", icon: "M3 9l2-5h14l2 5M4 9v11h16V9M3 9h18M9 20v-6h6v6" },
    { href: "/signals", label: "Premium Signals", icon: "M13 2L4 14h7l-1 8 9-12h-7z", badge: "IRAI" },
    { href: "/trades", label: "Community Trades", icon: "M17 3l4 4-4 4M21 7H9M7 21l-4-4 4-4M3 17h12" },
  ] },
  { title: "Research", items: [
    { href: "/earnings", label: "Earnings Hub", icon: "M4 5h16v15H4zM4 9h16M8 3v4M16 3v4M8 13h3v3H8z" },
    { href: "/screeners", label: "Screener", icon: "M3 5h18l-7 8v6l-4 2v-8z" },
    { href: "/patterns", label: "Pattern Lab", icon: "M3 17l4-6 4 3 4-8 6 9M3 21h18", badge: "New" },
    { href: "/macro", label: "Macro map", icon: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" },
    { href: "/heatmap", label: "Heatmaps", icon: "M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z" },
    { href: "/options", label: "Options Discover", icon: "M4 19V9M10 19V5M16 19v-7M22 19H2" },
    { href: "/research", label: "Research & themes", icon: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5" },
    { href: "/portfolio", label: "Portfolio", icon: "M12 3v9l7 4M12 3a9 9 0 1 0 9 9", pro: true },
  ] },
  { title: "Community", items: [
    { href: "/community", label: "Community", icon: "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM16 11a3 3 0 1 0 0-6M2 20c0-3 3-5 6-5s6 2 6 5M16 15c3 0 6 2 6 5" },
  ] },
  { title: "Systems", items: [
    { href: "/systems", label: "My systems", icon: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 9 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 4.6 15H4a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 5.6 9" },
  ] },
];

function Icon({ d, className = "h-[18px] w-[18px]" }: { d: string; className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden><path d={d} /></svg>;
}

export function Sidebar() {
  const { user } = useAuth();
  const path = usePathname() || "/";
  const [collapsed, setCollapsed] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [chats, setChats] = useState<{ id: number; title: string }[]>([]);
  const [chatOpen, setChatOpen] = useState(true);
  useEffect(() => { try { setCollapsed(localStorage.getItem("irai-sidebar") === "collapsed"); } catch { /* ignore */ } }, []);
  useEffect(() => { const f = () => setMobile(m => !m); window.addEventListener("irai:toggle-sidebar", f); return () => window.removeEventListener("irai:toggle-sidebar", f); }, []);
  useEffect(() => { setMobile(false); }, [path]);
  const loadChats = useCallback(() => { if (user) api<{ id: number; title: string }[]>("/api/assistant/chats").then(c => setChats(c.slice(0, 6))).catch(() => {}); }, [user]);
  useEffect(() => { loadChats(); return onChatsChanged(loadChats); }, [loadChats]);
  if (!user) return null;
  const toggle = () => { const n = !collapsed; setCollapsed(n); try { localStorage.setItem("irai-sidebar", n ? "collapsed" : "open"); } catch { /* ignore */ } };
  const wide = !collapsed || mobile;
  const pro = user.plan === "pro";
  const active = (href: string) => path === href || (href !== "/" && path.startsWith(href + "/"));
  return (
    <>
      {mobile && <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={() => setMobile(false)} />}
      <aside className={`print:hidden ${mobile ? "fixed inset-y-0 left-0 z-50 flex" : "sticky top-0 hidden lg:flex"} h-screen shrink-0 flex-col border-r border-line bg-card/80 backdrop-blur transition-[width] duration-200 ${wide ? "w-64" : "w-[60px]"}`}>
        <div className="p-2">
          <div className={`rounded-xl border border-primary/30 bg-gradient-to-br from-primary/15 to-transparent ${wide ? "p-2.5" : "p-1"}`}>
            <button onClick={() => (wide ? setChatOpen(o => !o) : openIrai({ chatId: "new" }))} className="flex w-full items-center gap-2 text-left" title="IRAI chat">
              <span className="solar-bg grid h-8 w-8 shrink-0 place-items-center rounded-lg text-sm font-bold text-primary-fg">✦</span>
              {wide && <span className="flex-1"><span className="block text-sm font-semibold leading-tight">IRAI</span><span className="block text-[11px] text-muted">Your research copilot</span></span>}
              {wide && <span className="text-xs text-muted">{chatOpen ? "▾" : "▸"}</span>}
            </button>
            {wide && chatOpen && (
              <div className="mt-2 space-y-1">
                <button onClick={() => openIrai({ chatId: "new" })} className="solar-bg w-full rounded-lg px-3 py-1.5 text-sm font-semibold text-primary-fg hover:brightness-110">+ New chat</button>
                {chats.map(c => <button key={c.id} onClick={() => openIrai({ chatId: c.id })} className="block w-full truncate rounded px-2 py-1 text-left text-xs text-muted hover:bg-accent hover:text-fg" title={c.title}>{c.title}</button>)}
                {chats.length > 0 && <Link href="/history?kind=chat" className="block px-2 text-[11px] text-primary">All chats →</Link>}
              </div>)}
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 pb-2">
          {GROUPS.map(g => (
            <div key={g.title} className="mt-3">
              {wide ? <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{g.title}</div> : <div className="mx-3 my-2 border-t border-line" />}
              {g.items.map(it => (
                <Link key={it.href} href={it.href} title={it.label}
                  className={`group flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm ${active(it.href) ? "bg-primary/15 text-fg" : "text-muted hover:bg-accent hover:text-fg"}`}>
                  <Icon d={it.icon} className={`h-[18px] w-[18px] shrink-0 ${active(it.href) ? "text-primary" : ""}`} />
                  {wide && <span className="flex-1 truncate">{it.label}</span>}
                  {wide && it.badge && <span className="rounded bg-primary/20 px-1.5 text-[9px] font-semibold text-primary">{it.badge}</span>}
                  {wide && it.pro && !pro && <span className="rounded border border-line px-1 text-[9px] text-muted">PRO</span>}
                </Link>))}
            </div>))}
        </nav>
        <div className="border-t border-line p-2">
          <button onClick={toggle} className="hidden w-full items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-accent hover:text-fg lg:flex" title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <Icon d={collapsed ? "M9 6l6 6-6 6" : "M15 6l-6 6 6 6"} />{wide && <span>Collapse</span>}
          </button>
        </div>
      </aside>
    </>
  );
}
