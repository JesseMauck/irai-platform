"use client";
import { useApi } from "@/lib/hooks";
import { pct } from "@/lib/format";
import { Card, PageHeader, Skeleton } from "@/components/ui";

interface Row { rank: number; handle: string; name: string; verification: string; closed_trades: number; win_rate: number; avg_return: number; risk_adjusted: number | null }

export default function Leaderboards() {
  const { data } = useApi<{ min_trades: number; rows: Row[] }>("/api/community/leaderboard");
  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <PageHeader title="Leaderboards" intro={`Ranked by risk-adjusted return on timestamp- or broker-verified closed trades. Minimum ${data?.min_trades ?? 20} closed trades. Self-reported trades don't count.`} />
      <Card>
        {!data ? <Skeleton /> : (
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-muted"><tr>{["Rank", "Trader", "Verification", "Closed", "Win rate", "Avg return", "Risk-adj."].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line num">
              {data.rows.map(r => <tr key={r.handle}><td className="p-3">{r.rank}</td><td className="p-3">{r.name} <span className="text-muted">@{r.handle}</span></td><td className="p-3 text-muted">{r.verification}</td>
                <td className="p-3">{r.closed_trades}</td><td className="p-3">{pct(r.win_rate, 0, false)}</td><td className="p-3">{pct(r.avg_return, 1)}</td><td className="p-3">{r.risk_adjusted?.toFixed(2) ?? "—"}</td></tr>)}
              {data.rows.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-muted">No one has enough verified closed trades yet.</td></tr>}
            </tbody>
          </table>
        )}
      </Card>
      <p className="mt-3 text-xs text-muted">Risk-adjusted score = average return ÷ volatility of returns. Past performance does not predict future results.</p>
    </div>
  );
}
