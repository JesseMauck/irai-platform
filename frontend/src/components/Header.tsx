"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "./AuthProvider";
import { TickerSearch } from "./TickerSearch";

interface NavItem { href?: string; label: string; desc?: string; children?: NavItem[] }

const NAV: NavItem[] = [
  { href: "/research", label: "Research" },
  { label: "Monitors", children: [
    { href: "/monitor/adr", label: "ADR Monitor", desc: "Cross-listings vs local lines, net of basis" },
    { href: "/monitor/etf", label: "ETF Monitor", desc: "Fund price vs NAV" },
    { href: "/monitor/fundamental", label: "Fundamental RV", desc: "Cheap for its quality, within peers" },
  ] },
  { href: "/valuebot", label: "ValueBot" },
  { href: "/screeners", label: "Screeners" },
  { href: "/community", label: "Community" },
  { href: "/learn", label: "Learn" },
];

/** The Irradiance mark: a solar disc with three rays (matches irradiance.ai). */
export function LogoMark({ className = "size-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <defs><linearGradient id="irr-solar" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse"><stop stopColor="#F5A524" /><stop offset="1" stopColor="#F2545B" /></linearGradient></defs>
      <circle cx="12" cy="12" r="4.5" fill="url(#irr-solar)" />
      <g stroke="url(#irr-solar)" strokeWidth="2" strokeLinecap="round"><path d="M12 2.5v3.2" /><path d="M4.7 4.7l2.3 2.3" /><path d="M19.3 4.7L17 7" /></g>
    </svg>
  );
}

export function Logo() {
  return (
    <Link href="/" aria-label="Irradiance home" className="shrink-0">
      <span className="inline-flex items-center gap-2"><LogoMark /><span className="text-lg font-semibold tracking-tight text-fg">irradiance</span></span>
    </Link>
  );
}

export function Header() {
  const path = usePathname();
  const { user, logout } = useAuth();
  const [menu, setMenu] = useState(false);
  const active = (h?: string) => h && path.startsWith(h);
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
        <Logo />
        <nav className="hidden items-center gap-1 lg:flex">
          {NAV.map(n => n.children ? (
            <div key={n.label} className="group relative">
              <button className={`rounded-md px-3 py-1.5 text-sm ${path.startsWith("/monitor") ? "text-fg" : "text-muted hover:text-fg"}`}>{n.label}</button>
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
          {user ? (
            <>
              <Link href="/account" className="hidden rounded-md px-3 py-1.5 text-sm text-muted hover:text-fg sm:block">@{user.handle}</Link>
              {user.plan !== "pro" && <Link href="/pricing" className="solar-bg rounded-lg px-3 py-1.5 text-sm font-semibold text-primary-fg">Upgrade</Link>}
              <button onClick={logout} className="hidden text-sm text-muted hover:text-fg md:block">Sign out</button>
            </>
          ) : (
            <>
              <Link href="/login" className="hidden rounded-md px-3 py-1.5 text-sm text-muted hover:text-fg sm:block">Sign in</Link>
              <Link href="/pricing" className="solar-bg rounded-lg px-3 py-1.5 text-sm font-semibold text-primary-fg">Upgrade</Link>
            </>
          )}
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
