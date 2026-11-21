"use client";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

/**
 * Product screenshot in a browser frame with a CSS 3D tilt: the card leans toward the cursor with perspective, a soft glare
 * follows the pointer, and floating chips sit on a raised plane for parallax. Pure CSS transforms driven by CSS variables
 * (no re-renders while moving). Rests at a gentle angle; flat and still for reduced-motion users and on touch screens.
 */
export function TiltShot({ src, alt, url, chips = [], rest = "right", priority = false, max = 10 }: {
  src: string; alt: string; url: string; chips?: { text: string; pos: "tl" | "tr" | "bl" | "br" }[];
  rest?: "left" | "right" | "flat"; priority?: boolean; max?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [live, setLive] = useState(false);
  useEffect(() => {
    const ok = matchMedia("(pointer: fine)").matches && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    setLive(ok);
  }, []);
  const restY = rest === "flat" ? 0 : rest === "right" ? -7 : 7;
  const set = (rx: number, ry: number, gx = 50, gy = 50) => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--rx", `${rx}deg`);
    el.style.setProperty("--ry", `${ry}deg`);
    el.style.setProperty("--gx", `${gx}%`);
    el.style.setProperty("--gy", `${gy}%`);
  };
  const move = (e: React.PointerEvent) => {
    if (!live || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    set((0.5 - y) * max, (x - 0.5) * max * 1.4, x * 100, y * 100);
  };
  const leave = () => set(rest === "flat" ? 0 : 4, restY);
  useEffect(() => { leave(); }, [live]); // eslint-disable-line react-hooks/exhaustive-deps
  const POS = { tl: "-left-4 top-10", tr: "-right-4 top-14", bl: "-left-6 bottom-12", br: "-right-5 bottom-8" };
  return (
    <div ref={ref} onPointerMove={move} onPointerLeave={leave} className={`tilt ${live ? "tilt-live" : ""}`}>
      <div className="tilt-card">
        <div className="flex items-center gap-1.5 border-b border-line bg-card px-3 py-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" /><span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" /><span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <span className="mx-auto truncate rounded-md bg-bg px-3 py-0.5 text-[11px] text-muted">{url}</span>
        </div>
        <Image src={src} alt={alt} width={1600} height={1027} priority={priority} sizes="(min-width: 1024px) 640px, 100vw" className="block h-auto w-full" />
        <div className="tilt-glare" aria-hidden />
      </div>
      {chips.map(c => <div key={c.text} className={`tilt-chip ${POS[c.pos]}`} aria-hidden>{c.text}</div>)}
    </div>
  );
}

export interface Showcase { src: string; alt: string; url: string; eyebrow: string; title: string; body: string; bullets: string[];
  href: string; cta: string; chips?: { text: string; pos: "tl" | "tr" | "bl" | "br" }[] }

export function FeatureShowcase({ items, note = true }: { items: Showcase[]; note?: boolean }) {
  return (
    <div className="space-y-20 md:space-y-28">
      {items.map((it, i) => (
        <div key={it.title} className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
          <div className={i % 2 ? "lg:order-2" : ""}>
            <TiltShot src={it.src} alt={it.alt} url={it.url} chips={it.chips} rest={i % 2 ? "left" : "right"} />
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-primary">{it.eyebrow}</div>
            <h3 className="mt-2 text-3xl font-semibold tracking-tight">{it.title}</h3>
            <p className="mt-3 text-muted">{it.body}</p>
            <ul className="mt-5 space-y-2 text-sm">{it.bullets.map(b => <li key={b} className="flex gap-2"><span className="text-primary">✓</span><span className="text-fg-2">{b}</span></li>)}</ul>
            <Link href={it.href} className="solar-bg mt-6 inline-block rounded-lg px-4 py-2 text-sm font-semibold text-primary-fg">{it.cta}</Link>
          </div>
        </div>
      ))}
      {note && <p className="text-center text-[11px] text-muted">Illustrative product screenshots. Live pages label every number with its source.</p>}
    </div>
  );
}
