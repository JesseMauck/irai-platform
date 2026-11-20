"use client";
import Link from "next/link";
import type { AdrRow, EtfRow, RvRow } from "@/lib/api";
import { compact, num, ord, pct, signed, tone } from "@/lib/format";
import { SourceBadge, TickerLink } from "./ui";

const th = "px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted";
const td = "px-3 py-2.5 text-sm num";

export function AdrTable({ rows, compactView = false }: { rows: AdrRow[]; compactView?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px]">
        <thead className="border-b border-line"><tr>
          <th className={th}>Pair</th>{!compactView && <th className={th}>Market</th>}
          <th className={th}>Premium</th><th className={th}>Basis</th><th className={th}>Z</th>
          {!compactView && <th className={th}>Half-life</th>}<th className={th}>Source</th>
          {!compactView && <><th className={th}>Confidence</th><th className={th}>Tradable</th></>}
        </tr></thead>
        <tbody className="divide-y divide-line">
          {rows.map(r => (
            <tr key={r.adr_symbol} className="hover:bg-accent/40">
              <td className={td}>
                <Link href={`/monitor/adr/${r.adr_symbol}`} className="font-semibold hover:text-primary">{r.adr_symbol}</Link>
                <span className="text-muted"> vs {r.local_symbol}</span>
                <div className="text-xs text-muted">{r.name}</div>
              </td>
              {!compactView && <td className={td}><div>{r.country}</div><div className="text-xs text-muted">{r.local_market_open ? "Open" : "Closed"} · 1 ADR : {r.ratio} local</div></td>}
              <td className={`${td} ${tone(r.premium)}`}>{pct(r.premium)}</td>
              <td className={`${td} text-muted`}>{pct(r.basis)}</td>
              <td className={`${td} font-semibold ${Math.abs(r.z ?? 0) >= 2 ? tone(r.z) : ""}`}>{signed(r.z)}</td>
              {!compactView && <td className={td}>{r.half_life_days != null ? `${r.half_life_days.toFixed(1)}d` : "—"}</td>}
              <td className={td}><SourceBadge source={r.source} /></td>
              {!compactView && <>
                <td className={td}>{r.confidence != null ? `${Math.round(r.confidence)}%` : "—"}</td>
                <td className={td}>{r.tradable ? <span className="text-up">Yes</span> : <span className="text-muted" title={r.reasons.join("\n")}>No</span>}</td>
              </>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EtfTable({ rows }: { rows: EtfRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px]">
        <thead className="border-b border-line"><tr>
          {["Fund", "Price", "NAV", "Premium", "Tier", "Exp. ratio", "AUM", "YTD", "Source"].map(h => <th key={h} className={th}>{h}</th>)}
        </tr></thead>
        <tbody className="divide-y divide-line">
          {rows.map(r => (
            <tr key={r.symbol} className="hover:bg-accent/40">
              <td className={td}><TickerLink symbol={r.symbol} /><div className="text-xs text-muted">{r.name} · {r.category}</div></td>
              <td className={td}>{num(r.price)}<div className={`text-xs ${tone(r.change_pct)}`}>{pct(r.change_pct)}</div></td>
              <td className={td}>{num(r.nav)}</td>
              <td className={`${td} font-semibold ${Math.abs(r.premium ?? 0) >= 0.005 ? tone(r.premium) : ""}`}>{pct(r.premium)}</td>
              <td className={`${td} text-xs text-muted`}>{r.tier}</td>
              <td className={td}>{pct(r.expense_ratio, 2, false)}</td>
              <td className={td}>{compact(r.total_assets)}</td>
              <td className={`${td} ${tone(r.ytd_return)}`}>{pct(r.ytd_return, 1)}</td>
              <td className={td}><SourceBadge source={r.source} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GradeChip({ grade }: { grade: string }) {
  const c = grade.startsWith("A") ? "bg-up/15 text-up" : grade.startsWith("B") ? "bg-data-1/15 text-data-1" : grade.startsWith("C") ? "bg-primary/15 text-primary" : grade === "—" ? "bg-accent text-muted" : "bg-down/15 text-down";
  return <span className={`inline-flex min-w-8 justify-center rounded px-1.5 py-0.5 text-xs font-bold ${c}`}>{grade}</span>;
}

export function RvTable({ rows }: { rows: RvRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px]">
        <thead className="border-b border-line"><tr>
          {["Name", "Peer group", "RV grade", "Multiple", "Peer median", "Quality", "ROE", "Source"].map(h => <th key={h} className={th}>{h}</th>)}
        </tr></thead>
        <tbody className="divide-y divide-line">
          {rows.map(r => (
            <tr key={r.peer_group + r.symbol} className="hover:bg-accent/40">
              <td className={td}><TickerLink symbol={r.symbol} /><div className="text-xs text-muted">{r.name}</div></td>
              <td className={`${td} text-muted`}>{r.peer_group}</td>
              <td className={td}><GradeChip grade={r.grade} /> <span className="text-xs text-muted">{ord(r.rv_percentile)}</span></td>
              <td className={td}>{r.multiple ? `${r.multiple.toFixed(1)}x` : "—"} <span className="text-xs text-muted">{r.multiple_name}</span></td>
              <td className={`${td} text-muted`}>{r.peer_median_multiple ? `${r.peer_median_multiple.toFixed(1)}x` : "—"}</td>
              <td className={td}>{ord(r.quality_percentile)}</td>
              <td className={td}>{pct(r.roe, 1, false)}</td>
              <td className={td}><SourceBadge source={r.source} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
