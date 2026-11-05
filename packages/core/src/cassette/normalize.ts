/** Placeholder written in place of any volatile value. */
export const TS = "<timestamp>";
export const ID = "<id>";

const ISO_TS = /\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\b/g;
const UUID = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
// Provider-issued ids: Anthropic (msg_, toolu_, req_), OpenAI (chatcmpl-, call_, resp_).
const PROVIDER_ID = /\b(?:msg_|toolu_|req_|chatcmpl-|call_|resp_)[A-Za-z0-9]{6,}\b/g;

export function normalizeString(s: string): string {
  return s.replace(ISO_TS, TS).replace(UUID, ID).replace(PROVIDER_ID, ID);
}

/**
 * Deep-normalize a JSON value: volatile substrings become placeholders and
 * object keys are sorted, so two runs that differ only in timestamps, ids or
 * key order serialize identically.
 */
export function normalize<T>(value: T): T {
  return walk(value) as T;
}

function walk(v: unknown): unknown {
  if (typeof v === "string") return normalizeString(v);
  if (Array.isArray(v)) return v.map(walk);
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(v).sort()) {
      const nv = walk((v as Record<string, unknown>)[k]);
      if (nv !== undefined) out[k] = nv;
    }
    return out;
  }
  return v;
}

/** Stable string form of normalized args, used as the exact-match key. */
export function canonicalArgs(args: unknown): string {
  return JSON.stringify(normalize(args ?? {}));
}
