"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useId } from "react";
import { useAuth } from "./AuthProvider";
import { ThemeToggle } from "./ThemeToggle";
import { TickerSearch } from "./TickerSearch";

interface NavItem { href?: string; label: string; desc?: string; children?: NavItem[] }

const NAV: NavItem[] = [
  { href: "/research", label: "Research" },
  { label: "Monitors", children: [
    { href: "/monitor/adr", label: "ADR Monitor", desc: "Cross-listings vs local lines, net of basis" },
    { href: "/monitor/etf", label: "ETF Monitor", desc: "Fund price vs NAV" },
    { href: "/monitor/fundamental", label: "Fundamental RV", desc: "Cheap for its quality, within peers" },
    { href: "/monitor/pairs", label: "Pair ideas", desc: "Pro: score spreads within peer groups" },
  ] },
  { href: "/valuebot", label: "ValueBot" },
  { label: "Tools", children: [
    { href: "/compare", label: "Compare", desc: "Up to eight stocks side by side, with AI analysis" },
    { href: "/lab", label: "Strategy Lab", desc: "Backtest and optimise trading rules" },
    { href: "/lab/montecarlo", label: "Monte Carlo", desc: "Simulate outcomes for a stock or portfolio" },
    { href: "/screeners", label: "Screeners", desc: "Preset and custom screens" },
    { href: "/bots", label: "Trading bots", desc: "Pro: paper-trade strategies with risk controls" },
    { href: "/portfolio", label: "Portfolio analysis", desc: "Pro: import holdings for risk, income and an AI review" },
    { href: "/algotrader", label: "IRAI AlgoTrader", desc: "How bots, signals and broker connections work" },
  ] },
  { href: "/community", label: "Community" },
  { href: "/learn", label: "Learn" },
];

/** Irradiance mark: the "i" with a rising arrow, crimson → amber. Matches the brand artwork in both themes. */
export function LogoMark({ className = "h-7 w-auto" }: { className?: string }) {
  const gid = `irr-mark-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`; // unique per instance so a hidden copy can't break the gradient
  return (
    <svg viewBox="15 13 39 33" fill="none" aria-hidden="true" className={className}>
      <defs>
        <linearGradient id={gid} x1="17" y1="44" x2="51" y2="16" gradientUnits="userSpaceOnUse">
          <stop stopColor="#C8364F" /><stop offset="0.55" stopColor="#E0605A" /><stop offset="1" stopColor="#F2923A" />
        </linearGradient>
      </defs>
      <circle cx="27.8" cy="17.6" r="3" fill={`url(#${gid})`} />
      <path d="M24.6 24.4h6.2l-0.9 14.6h-6.1z" fill={`url(#${gid})`} />
      <path d="M17.6 44c2.6-1.4 5.2-2.4 7.6-2.2 2.6.2 4.7 2.2 7.2 1.6 2.6-.6 4-3 5.7-5.6l5.2-8.2"
        stroke={`url(#${gid})`} strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M51 16.4l-12 5.2 3.4 2.4-2.2 3.4 4.6 2.8 2.2-3.4 3.4 2.4z" fill={`url(#${gid})`} />
    </svg>
  );
}

/** Full logo: mark + IRRADIANCE.AI wordmark. Wordmark follows the theme (light text on dark, dark text on light). */
export function Logo() {
  return (
    <Link href="/" aria-label="Irradiance.AI home" className="shrink-0">
      <span className="inline-flex items-center gap-2">
        <LogoMark />
        <span className="text-[1.15rem] font-semibold italic leading-none tracking-tight text-fg">
          IRRADIANCE<span className="logo-ai">.AI</span>
        </span>
      </span>
    </Link>
  );
}

export function Header() {
  const path = usePathname();
  const { user, logout } = useAuth();
  const [menu, setMenu] = useState(false);
  const active = (h?: string) => h && path.startsWith(h);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur print:hidden">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
        <Logo />
        <nav className={`hidden items-center gap-1 ${user ? "2xl:flex" : "lg:flex"}`}>
          {NAV.map(n => n.children ? (
            <div key={n.label} className="group relative">
              <button className={`rounded-md px-3 py-1.5 text-sm ${(n.children?.some(c => path.startsWith(c.href!)) ? "text-fg" : "text-muted hover:text-fg")}`}>{n.label}</button>
              <div className="invisible absolute left-0 top-full w-72 pt-2 opacity-0 transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
                <div className="rounded-xl border border-line bg-card p-2 shadow-xl">
                  {n.children.map(c => (
                    <Link key={c.href} href={c.href!} className="block rounded-lg px-3 py-2 hover:bg-accent">
                      <div className="text-sm font-medium">{c.label}</div><div className="text-xs text-muted">{c.desc}</div>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <Link key={n.href} href={n.href!} className={`rounded-md px-3 py-1.5 text-sm ${active(n.href) ? "text-fg" : "text-muted hover:text-fg"}`}>{n.label}</Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <TickerSearch />
          <span className="hidden sm:contents"><ThemeToggle /></span>
          {user ? (
            <>
              <Link href="/terminal" className="hidden rounded-md px-3 py-1.5 text-sm font-medium text-primary sm:block">Terminal</Link>
              {user.is_admin && <Link href="/admin" className="hidden rounded-md px-3 py-1.5 text-sm text-muted hover:text-fg sm:block">Admin</Link>}
              <Link href="/account" className="hidden rounded-md px-3 py-1.5 text-sm text-muted hover:text-fg sm:block">@{user.handle}</Link>
              {user.plan !== "pro" && <Link href="/pricing" className="solar-bg rounded-lg px-3 py-1.5 text-sm font-semibold text-primary-fg">Upgrade</Link>}
              <button onClick={logout} className="hidden whitespace-nowrap text-sm text-muted hover:text-fg md:block">Sign out</button>
            </>
          ) : (
            <>
              <Link href="/login" className="hidden rounded-md px-3 py-1.5 text-sm text-muted hover:text-fg sm:block">Sign in</Link>
              <Link href="/signup" className="solar-bg whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-semibold text-primary-fg">Start free</Link>
            </>
          )}
          {user && <button className="rounded-md p-2 text-muted lg:hidden" onClick={() => window.dispatchEvent(new Event("irai:toggle-sidebar"))} aria-label="Open portal menu" title="Portal menu">▤</button>}
          <button className="rounded-md p-2 text-muted lg:hidden" onClick={() => setMenu(m => !m)} aria-label="Menu">☰</button>
        </div>
      </div>
      {menu && (
        <nav className="border-t border-line px-4 py-3 lg:hidden" onClick={() => setMenu(false)}>
          {NAV.flatMap((n): NavItem[] => n.children ?? [n]).map(n => <Link key={n.href} href={n.href!} className="block py-2 text-sm">{n.label}</Link>)}
          <Link href={user ? "/account" : "/login"} className="block py-2 text-sm">{user ? "Account" : "Sign in"}</Link>
        </nav>
      )}
    </header>
  );
}
