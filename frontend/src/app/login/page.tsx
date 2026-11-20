"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote } from "@/components/ui";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next") ?? "/account";
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await login(email, password); router.push(next.startsWith("/") ? next : "/account"); } catch (x) { setErr(x as Error); }
  };
  return (
    <div className="mx-auto max-w-md px-4 py-20">
      <Card className="p-8">
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <input type="email" required placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} className="w-full rounded-lg border border-line bg-bg px-3 py-2" autoComplete="email" />
          <input type="password" required placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} className="w-full rounded-lg border border-line bg-bg px-3 py-2" autoComplete="current-password" />
          <ErrorNote error={err} />
          <Button type="submit" className="w-full">Sign in</Button>
        </form>
        <p className="mt-4 text-sm text-muted">New here? <Link href="/signup" className="text-primary">Create an account</Link></p>
      </Card>
    </div>
  );
}
export default function Page() { return <Suspense><LoginForm /></Suspense>; }
