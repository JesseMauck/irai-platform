/** Pages can tell the Ask IRAI assistant what the member is looking at beyond what the URL says
 *  (for example the portfolio selected on /portfolio). */
export type AssistantContext = { portfolio_id?: number | null; symbol?: string | null };
let ctx: AssistantContext = {};
const subs = new Set<(c: AssistantContext) => void>();

export function setAssistantContext(c: AssistantContext) { ctx = c; subs.forEach(f => f(ctx)); }
export function getAssistantContext() { return ctx; }
export function onAssistantContext(f: (c: AssistantContext) => void) { subs.add(f); return () => { subs.delete(f); }; }

/** Open the Ask IRAI panel from anywhere (the sidebar, a page button). chatId: an existing chat, "new", or undefined to resume. */
type OpenReq = { chatId?: number | "new"; prompt?: string };
const openers = new Set<(r: OpenReq) => void>();
export function openIrai(r: OpenReq = {}) { openers.forEach(f => f(r)); }
export function onOpenIrai(f: (r: OpenReq) => void) { openers.add(f); return () => { openers.delete(f); }; }

const chatSubs = new Set<() => void>();
/** Called after a chat is saved, so the sidebar's recent-chat list can refresh. */
export function chatsChanged() { chatSubs.forEach(f => f()); }
export function onChatsChanged(f: () => void) { chatSubs.add(f); return () => { chatSubs.delete(f); }; }
