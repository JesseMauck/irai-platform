/** Pages can tell the Ask IRAI assistant what the member is looking at beyond what the URL says
 *  (for example the portfolio selected on /portfolio). */
export type AssistantContext = { portfolio_id?: number | null; symbol?: string | null };
let ctx: AssistantContext = {};
const subs = new Set<(c: AssistantContext) => void>();

export function setAssistantContext(c: AssistantContext) { ctx = c; subs.forEach(f => f(ctx)); }
export function getAssistantContext() { return ctx; }
export function onAssistantContext(f: (c: AssistantContext) => void) { subs.add(f); return () => { subs.delete(f); }; }
