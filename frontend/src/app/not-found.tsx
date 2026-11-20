import { Button } from "@/components/ui";
export default function NotFound() {
  return <div className="mx-auto max-w-xl px-4 py-24 text-center"><h1 className="stat text-4xl">Not found</h1><p className="mt-3 text-muted">That page doesn&apos;t exist. Try searching a ticker with ⌘K.</p><div className="mt-6"><Button href="/">Home</Button></div></div>;
}
