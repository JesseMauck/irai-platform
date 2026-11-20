"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button, Card, ErrorNote } from "@/components/ui";

export default function Forgot() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { setDone((await api<{ message: string }>("/api/auth/forgot", { method: "POST", json: { email } })).message); } catch (x) { setErr(x as Error); }
  };
  return (
    <div className="mx-auto max-w-md px-4 py-20"><Card className="p-8">
      <h1 className="text-2xl font-semibold">Reset your password</h1>
      {done ? <p className="mt-4 text-sm text-muted">{done}</p> : (
        <form onSubmit={submit} className="mt-6 space-y-4">
          <input type="email" required placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} className="w-full rounded-lg border border-line bg-bg px-3 py-2" />
          <ErrorNote error={err} /><Button type="submit" className="w-full">Email me a reset link</Button>
        </form>)}
      <p className="mt-4 text-sm text-muted"><Link href="/login" className="text-primary">Back to sign in</Link></p>
    </Card></div>
  );
}
