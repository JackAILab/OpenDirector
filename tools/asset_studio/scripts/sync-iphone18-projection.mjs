import { cp, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = join(studioRoot, "..", "..");
const source = join(repositoryRoot, "productions", "iphone18_concept_live_60s_v1");
const destination = join(studioRoot, "public", "iphone18-live");

await mkdir(destination, { recursive: true });
for (const name of ["index.html", "live-room.css", "live-room.js", "DESIGN.md", "hyperframes.json"]) {
  await cp(join(source, name), join(destination, name), { force: true });
}
console.log(`Projected canonical iPhone 18 prototype to ${destination}`);
