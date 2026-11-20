"use client";
import { useState } from "react";

export interface Driver { key: string; label: string; unit: string }
export interface Refinements {
  market: { tam?: number; tam_growth?: number; target_share?: number };
  overrides: Record<string, number>;
  adjustments: { capitalize_rnd: "auto" | "yes" | "no"; rnd_life?: number; lease_adjust: boolean; one_time_addback?: number; normalize_margins: boolean };
  risk: { regions: { region: string; weight: number; crp?: number }[]; segments: { name: string; weight: number; unlevered_beta?: number }[]; riskfree_override?: number };
  extras: { options_count?: number; options_strike?: number; options_maturity?: number; volatility?: number; nol?: number; non_operating_assets?: number };
}
export const EMPTY_REFINE: Refinements = {
  market: {}, overrides: {}, adjustments: { capitalize_rnd: "auto", lease_adjust: true, normalize_margins: false },
  risk: { regions: [], segments: [] }, extras: {},
};

const pctIn = (v: string) => (v === "" ? undefined : parseFloat(v) / 100);
const numIn = (v: string, scale = 1) => (v === "" ? undefined : parseFloat(v) * scale);
const inp = "w-full rounded border border-line bg-bg px-2 py-1.5 text-sm num";

// Defined at module level (not inside the parent's render) so inputs keep focus and their values as the
// parent re-renders on every keystroke.
function Section({ id, title, hint, open, setOpen, children }: {
  id: string; title: string; hint: string; open: string | null; setOpen: (v: string | null) => void; children: React.ReactNode;
}) {
  return (
    <div className="border-t border-line">
      <button type="button" onClick={() => setOpen(open === id ? null : id)} className="flex w-full items-center justify-between py-3 text-left">
        <span><span className="text-sm font-medium">{title}</span><span className="ml-2 text-xs text-muted">{hint}</span></span><span className="text-muted">{open === id ? "−" : "+"}</span>
      </button>
      <div className={open === id ? "pb-4" : "hidden"}>{children}</div>
    </div>
  );
}

/** The "Refine" step: market sizing, locked drivers, earnings adjustments, risk and loose ends. All optional. */
export function ValueBotRefine({ drivers, value, onChange }: { drivers: Driver[]; value: Refinements; onChange: (r: Refinements) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const set = (patch: Partial<Refinements>) => onChange({ ...value, ...patch });
  return (
    <div>
      <Section open={open} setOpen={setOpen} id="market" title="Market size" hint="Revenue growth is solved so year-10 revenue = market × share">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-xs text-muted">Total market today ($bn)<input className={inp} onChange={e => set({ market: { ...value.market, tam: numIn(e.target.value, 1e9) } })} /></label>
          <label className="text-xs text-muted">Market growth (% a year)<input className={inp} onChange={e => set({ market: { ...value.market, tam_growth: pctIn(e.target.value) } })} /></label>
          <label className="text-xs text-muted">Year-10 market share (%)<input className={inp} onChange={e => set({ market: { ...value.market, target_share: pctIn(e.target.value) } })} /></label>
        </div>
      </Section>
      <Section open={open} setOpen={setOpen} id="numbers" title="Your numbers" hint="Lock any driver; your numbers always win">
        <div className="grid gap-2 md:grid-cols-2">
          {drivers.map(d => (
            <label key={d.key} className="flex items-center justify-between gap-2 text-xs text-muted">{d.label}{d.unit === "pct" ? " (%)" : ""}
              <input className={`${inp} w-24`} placeholder="auto" onChange={e => {
                const o = { ...value.overrides }; const v = d.unit === "pct" ? pctIn(e.target.value) : numIn(e.target.value);
                if (v === undefined || !isFinite(v)) delete o[d.key]; else o[d.key] = v; set({ overrides: o });
              }} /></label>
          ))}
        </div>
      </Section>
      <Section open={open} setOpen={setOpen} id="earnings" title="Measure earnings right" hint="R&D, leases, one-time items, cycles">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-xs text-muted">Capitalize R&amp;D<select className={inp} value={value.adjustments.capitalize_rnd} onChange={e => set({ adjustments: { ...value.adjustments, capitalize_rnd: e.target.value as "auto" } })}><option value="auto">Auto</option><option value="yes">Yes</option><option value="no">No</option></select></label>
          <label className="text-xs text-muted">R&amp;D life (years)<input className={inp} onChange={e => set({ adjustments: { ...value.adjustments, rnd_life: numIn(e.target.value) } })} /></label>
          <label className="text-xs text-muted">One-time add-back ($m)<input className={inp} onChange={e => set({ adjustments: { ...value.adjustments, one_time_addback: numIn(e.target.value, 1e6) } })} /></label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.adjustments.lease_adjust} onChange={e => set({ adjustments: { ...value.adjustments, lease_adjust: e.target.checked } })} />Treat leases as debt</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.adjustments.normalize_margins} onChange={e => set({ adjustments: { ...value.adjustments, normalize_margins: e.target.checked } })} />Normalize margins over the cycle</label>
        </div>
      </Section>
      <Section open={open} setOpen={setOpen} id="risk" title="Risk" hint="Where revenue is earned, business mix, risk-free rate">
        <div className="space-y-3">
          <div><div className="text-xs text-muted">Revenue by region (weight %, optional country risk premium %)</div>
            {value.risk.regions.map((r, i) => (
              <div key={i} className="mt-1 grid grid-cols-[1fr_80px_80px_24px] gap-2">
                <input className={inp} value={r.region} placeholder="e.g. United States" onChange={e => { const a = [...value.risk.regions]; a[i] = { ...r, region: e.target.value }; set({ risk: { ...value.risk, regions: a } }); }} />
                <input className={inp} value={r.weight || ""} placeholder="%" onChange={e => { const a = [...value.risk.regions]; a[i] = { ...r, weight: parseFloat(e.target.value) || 0 }; set({ risk: { ...value.risk, regions: a } }); }} />
                <input className={inp} placeholder="CRP %" onChange={e => { const a = [...value.risk.regions]; a[i] = { ...r, crp: pctIn(e.target.value) }; set({ risk: { ...value.risk, regions: a } }); }} />
                <button type="button" onClick={() => set({ risk: { ...value.risk, regions: value.risk.regions.filter((_, j) => j !== i) } })} className="text-muted hover:text-down">×</button></div>))}
            <button type="button" onClick={() => set({ risk: { ...value.risk, regions: [...value.risk.regions, { region: "", weight: 0 }] } })} className="mt-1 text-xs text-primary">+ Add region</button></div>
          <div><div className="text-xs text-muted">Business segments (weight %, optional unlevered beta) for a bottom-up beta</div>
            {value.risk.segments.map((s, i) => (
              <div key={i} className="mt-1 grid grid-cols-[1fr_80px_80px_24px] gap-2">
                <input className={inp} value={s.name} placeholder="e.g. Software" onChange={e => { const a = [...value.risk.segments]; a[i] = { ...s, name: e.target.value }; set({ risk: { ...value.risk, segments: a } }); }} />
                <input className={inp} value={s.weight || ""} placeholder="%" onChange={e => { const a = [...value.risk.segments]; a[i] = { ...s, weight: parseFloat(e.target.value) || 0 }; set({ risk: { ...value.risk, segments: a } }); }} />
                <input className={inp} placeholder="β" onChange={e => { const a = [...value.risk.segments]; a[i] = { ...s, unlevered_beta: numIn(e.target.value) }; set({ risk: { ...value.risk, segments: a } }); }} />
                <button type="button" onClick={() => set({ risk: { ...value.risk, segments: value.risk.segments.filter((_, j) => j !== i) } })} className="text-muted hover:text-down">×</button></div>))}
            <button type="button" onClick={() => set({ risk: { ...value.risk, segments: [...value.risk.segments, { name: "", weight: 0 }] } })} className="mt-1 text-xs text-primary">+ Add segment</button></div>
          <label className="block w-48 text-xs text-muted">Risk-free rate override (%)<input className={inp} onChange={e => set({ risk: { ...value.risk, riskfree_override: pctIn(e.target.value) } })} /></label>
        </div>
      </Section>
      <Section open={open} setOpen={setOpen} id="extras" title="Loose ends" hint="Employee options, NOLs, cross-holdings">
        <div className="grid gap-3 md:grid-cols-3">
          {([["options_count", "Options outstanding (m)", 1e6], ["options_strike", "Average strike", 1], ["options_maturity", "Option life (years)", 1],
             ["nol", "Net operating loss ($m)", 1e6], ["non_operating_assets", "Cross-holdings ($m)", 1e6]] as const).map(([k, l, sc]) => (
            <label key={k} className="text-xs text-muted">{l}<input className={inp} onChange={e => set({ extras: { ...value.extras, [k]: numIn(e.target.value, sc) } })} /></label>))}
          <label className="text-xs text-muted">Volatility (%)<input className={inp} onChange={e => set({ extras: { ...value.extras, volatility: pctIn(e.target.value) } })} /></label>
        </div>
      </Section>
    </div>
  );
}

/** Strip empty values so the API receives only what the member actually set. */
export function cleanRefinements(r: Refinements) {
  const clean = <T extends object>(o: T) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== "" && !(typeof v === "number" && !isFinite(v))));
  return {
    market: clean(r.market), overrides: r.overrides, adjustments: clean(r.adjustments),
    risk: { ...clean({ riskfree_override: r.risk.riskfree_override }),
      regions: r.risk.regions.filter(x => x.region && x.weight > 0).map(clean),
      segments: r.risk.segments.filter(x => x.name && x.weight > 0).map(clean) },
    extras: clean(r.extras),
  };
}
