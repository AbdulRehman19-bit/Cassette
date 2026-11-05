import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { Cassette, CASSETTE_VERSION } from "./schema.js";
import { normalize } from "./normalize.js";

export const CASSETTE_EXT = ".cassette.json";

export function cassettePath(dir: string, scenario: string): string {
  return join(dir, `${scenario}${CASSETTE_EXT}`);
}

/** Validate, normalize volatile fields, and write `<dir>/<scenario>.cassette.json`. */
export async function writeCassette(dir: string, cassette: Cassette): Promise<string> {
  const parsed = Cassette.parse({ ...cassette, version: CASSETTE_VERSION });
  const normalized = normalize({ ...parsed, recordedAt: "<normalized>" });
  await mkdir(dir, { recursive: true });
  const path = cassettePath(dir, parsed.scenario);
  await writeFile(path, JSON.stringify(normalized, null, 2) + "\n", "utf8");
  return path;
}

export async function readCassette(path: string): Promise<Cassette> {
  return Cassette.parse(JSON.parse(await readFile(path, "utf8")));
}

export async function readScenario(dir: string, scenario: string): Promise<Cassette> {
  return readCassette(cassettePath(dir, scenario));
}

export async function listCassettes(dir: string): Promise<string[]> {
  try {
    return (await readdir(dir)).filter((f) => f.endsWith(CASSETTE_EXT)).map((f) => f.slice(0, -CASSETTE_EXT.length)).sort();
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw e;
  }
}
