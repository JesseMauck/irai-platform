"use client";
import { useApi } from "@/lib/hooks";
import { Card, PageHeader, Skeleton } from "@/components/ui";

export default function Learn() {
  const { data } = useApi<{ term: string; definition: string }[]>("/api/glossary");
  return (
    <div className="mx-auto max-w-4xl px-4 py-12">
      <PageHeader title="Learn" intro="Plain-language definitions for every metric on the site." />
      {!data ? <Skeleton /> : <div className="grid gap-3 md:grid-cols-2">{data.map(g => (
        <Card key={g.term} className="p-5" ><h2 id={g.term} className="font-semibold">{g.term}</h2><p className="mt-2 text-sm leading-relaxed text-muted">{g.definition}</p></Card>
      ))}</div>}
    </div>
  );
}
