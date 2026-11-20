"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, token as tokenStore, type User } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote } from "@/components/ui";

function ResetForm() {
  const t = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const { refresh } = useAuth();
  const [pw, setPw] = useState(""); const [pw2, setPw2] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    if (pw !== pw2) { setErr(new Error("Passwords don't match")); return; }
    try {
      const r = await api<{ token: string; user: User }>("/api/auth/reset", { method: "POST", json: { token: t, password: pw } });
      tokenStore.set(r.token); await refresh(); router.push("/account");
    } catch (x) { setErr(x as Error); }
  };
  return (
    <div className="mx-auto max-w-md px-4 py-20"><Card className="p-8">
      <h1 className="text-2xl font-semibold">Choose a new password</h1>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <input type="password" required minLength={8} placeholder="New password (8+ characters)" value={pw} onChange={e => setPw(e.target.value)} className="w-full rounded-lg border border-line bg-bg px-3 py-2" />
        <input type="password" required minLength={8} placeholder="Repeat it" value={pw2} onChange={e => setPw2(e.target.value)} className="w-full rounded-lg border border-line bg-bg px-3 py-2" />
        <ErrorNote error={err} /><Button type="submit" className="w-full" disabled={!t}>Save password</Button>
      </form>
      <p className="mt-3 text-xs text-muted">Saving signs out your other sessions.</p>
    </Card></div>
  );
}
export default function Page() { return <Suspense><ResetForm /></Suspense>; }
