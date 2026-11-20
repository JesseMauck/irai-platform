"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type Plan } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "./AuthProvider";
import { Button, ErrorNote } from "./ui";

export function PricingCards() {
  const { data: plans } = useApi<Plan[]>("/api/plans");
  const [annual, setAnnual] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const { user, refresh } = useAuth();
  const router = useRouter();

  const { data: billing } = useApi<{ trial_available: boolean; plan: string }>(user ? "/api/billing/subscription" : null);
  const trialOpen = !user || billing?.trial_available !== false;

  const choose = async (p: Plan, mode: "trial" | "subscribe") => {
    if (!user) { router.push(`/signup?plan=${p.key}`); return; }
    if (p.key === "free") { router.push("/account"); return; }
    setBusy(p.key + mode); setErr(null);
    try {
      if (mode === "trial") {
        await api("/api/billing/trial", { method: "POST", json: { plan: p.key } });
        await refresh(); router.push("/account?trial=started"); return;
      }
      const r = await api<{ url: string | null }>("/api/billing/checkout", { method: "POST", json: { plan: p.key, interval: annual ? "annual" : "monthly" } });
      if (r.url) window.location.href = r.url; else { await refresh(); router.push("/account?checkout=success"); }
    } catch (e) { setErr(e as Error); } finally { setBusy(null); }
  };

  return (
    <div>
      <div className="mb-6 flex justify-center">
        <div className="inline-flex rounded-lg border border-line bg-card p-1 text-sm">
          <button onClick={() => setAnnual(false)} className={`rounded-md px-4 py-1.5 ${!annual ? "bg-accent text-fg" : "text-muted"}`}>Monthly</button>
          <button onClick={() => setAnnual(true)} className={`rounded-md px-4 py-1.5 ${annual ? "bg-accent text-fg" : "text-muted"}`}>Annual <span className="text-primary">2 mo free</span></button>
        </div>
      </div>
      <ErrorNote error={err} />
      <div className="grid gap-4 md:grid-cols-3">
        {(plans ?? []).map(p => {
          const current = user?.plan === p.key;
          const featured = p.key === "essential";
          return (
            <div key={p.key} className={`relative flex flex-col rounded-xl border p-6 ${featured ? "border-primary/60 bg-card shadow-[0_0_40px_#f5a52418]" : "border-line bg-card"}`}>
              {p.badge && <span className="solar-bg absolute -top-3 left-6 rounded-full px-3 py-0.5 text-xs font-semibold text-primary-fg">{p.badge}</span>}
              <h3 className="text-lg font-semibold">{p.name}</h3>
              <p className="text-sm text-muted">{p.tagline}</p>
              <div className="my-5 num">
                <span className="text-4xl font-semibold">${annual ? Math.round(p.annual / 12) : p.monthly}</span>
                <span className="text-muted">/mo</span>
                {annual && p.annual > 0 && <div className="text-xs text-muted">${p.annual} billed yearly</div>}
              </div>
              <ul className="mb-6 flex-1 space-y-2 text-sm">
                {p.features.map(f => <li key={f} className="flex gap-2"><span className="text-primary">✓</span><span className="text-slate-300">{f}</span></li>)}
              </ul>
              {p.key === "free" ? (
                <Button variant="outline" onClick={() => choose(p, "subscribe")} disabled={current}>{current ? "Current plan" : p.cta}</Button>
              ) : (
                <div className="space-y-2">
                  {trialOpen && !current && <Button variant={featured ? "primary" : "outline"} className="w-full" onClick={() => choose(p, "trial")} disabled={!!busy}>
                    {busy === p.key + "trial" ? "…" : "Start 7-day free trial"}</Button>}
                  <Button variant={trialOpen && !current ? "ghost" : featured ? "primary" : "outline"} className="w-full" onClick={() => choose(p, "subscribe")} disabled={!!busy}>
                    {busy === p.key + "subscribe" ? "…" : current ? `Keep ${p.name}: subscribe ${annual ? "yearly" : "monthly"}` : `Subscribe ${annual ? "yearly" : "monthly"}`}</Button>
                </div>
              )}
              <p className="mt-2 text-center text-xs text-muted">{p.note}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Faq() {
  const { data } = useApi<{ q: string; a: string }[]>("/api/faq");
  return (
    <div className="divide-y divide-line rounded-xl border border-line bg-card">
      {(data ?? []).map(f => (
        <details key={f.q} className="group p-5">
          <summary className="flex cursor-pointer list-none items-center justify-between font-medium">{f.q}<span className="text-muted transition group-open:rotate-45">+</span></summary>
          <p className="mt-3 text-sm leading-relaxed text-muted">{f.a}</p>
        </details>
      ))}
    </div>
  );
}
