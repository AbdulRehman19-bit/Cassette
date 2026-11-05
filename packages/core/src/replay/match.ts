import { canonicalArgs, normalize } from "../cassette/normalize.js";
import type { Cassette, ToolStep } from "../cassette/schema.js";

export interface MatchOptions {
  /** Argument names dropped before comparing (e.g. `per_page`). */
  ignoreArgs?: string[];
  /** `exact`: normalized args must be identical. `normalized`: also ignore `ignoreArgs` and whitespace differences in strings. */
  tolerance?: "exact" | "normalized";
}

function loose(args: Record<string, unknown>, ignore: string[]): string {
  const kept: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(args)) if (!ignore.includes(k)) kept[k] = v;
  return JSON.stringify(
    normalize(kept),
    (_k, v: unknown) => (typeof v === "string" ? v.trim().replace(/\s+/g, " ") : v),
  );
}

/**
 * Finds the recorded result for a live call. Each recorded step answers one
 * call (so repeated identical calls replay in order). Exact match wins; then
 * the tolerant match; otherwise `undefined`, which the caller reports as a divergence.
 */
export class Matcher {
  private readonly steps: ToolStep[];
  private readonly used = new Set<number>();
  constructor(cassette: Cassette, private readonly opts: MatchOptions = {}) {
    this.steps = cassette.steps.filter((s): s is ToolStep => s.type === "tool");
  }

  find(server: string, name: string, args: Record<string, unknown>): ToolStep | undefined {
    const want = canonicalArgs(args);
    const exact = this.take((s) => s.server === server && s.name === name && canonicalArgs(s.args) === want);
    if (exact) return exact;
    if ((this.opts.tolerance ?? "normalized") === "exact") return undefined;
    const ignore = this.opts.ignoreArgs ?? [];
    const wantLoose = loose(args, ignore);
    return this.take((s) => s.server === server && s.name === name && loose(s.args, ignore) === wantLoose);
  }

  /** Recorded tool steps that were never asked for. */
  unused(): ToolStep[] {
    return this.steps.filter((_, i) => !this.used.has(i));
  }

  private take(pred: (s: ToolStep) => boolean): ToolStep | undefined {
    const idx = this.steps.findIndex((s, i) => !this.used.has(i) && pred(s));
    if (idx < 0) return undefined;
    this.used.add(idx);
    return this.steps[idx];
  }
}
