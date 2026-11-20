"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote } from "@/components/ui";

function SignupForm() {
  const { register, refresh } = useAuth();
  const router = useRouter();
  const plan = useSearchParams().get("plan");
  const [f, setF] = useState({ email: "", password: "", handle: "", display_name: "" });
  const [err, setErr] = useState<Error | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try {
      await register({ ...f, handle: f.handle.toLowerCase() });
      if (plan === "essential" || plan === "pro") {
        const r = await api<{ url: string | null }>("/api/billing/checkout", { method: "POST", json: { plan, interval: "monthly" } });
        if (r.url) { window.location.href = r.url; return; }
        await refresh();
      }
      router.push("/account?welcome=1");
    } catch (x) { setErr(x as Error); }
  };
  const field = (k: keyof typeof f, p: string, type = "text") =>
    <input type={type} required placeholder={p} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} className="w-full rounded-lg border border-line bg-bg px-3 py-2" />;
  return (
    <div className="mx-auto max-w-md px-4 py-20">
      <Card className="p-8">
        <h1 className="text-2xl font-semibold">Create your account</h1>
        {plan && plan !== "free" && <p className="mt-1 text-sm text-primary">Starting a 7-day {plan} trial.</p>}
        <form onSubmit={submit} className="mt-6 space-y-4">
          {field("display_name", "Name")}{field("handle", "Handle (e.g. quietquant)")}{field("email", "Email", "email")}{field("password", "Password (8+ characters)", "password")}
          <ErrorNote error={err} />
          <Button type="submit" className="w-full">Create account</Button>
        </form>
        <p className="mt-4 text-sm text-muted">Already have one? <Link href="/login" className="text-primary">Sign in</Link></p>
      </Card>
    </div>
  );
}
export default function Page() { return <Suspense><SignupForm /></Suspense>; }
