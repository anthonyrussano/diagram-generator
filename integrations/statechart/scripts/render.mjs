// Render chart.mmd files to SVG with Pele, using the theme CSS from the vendored render.md.
import fs from "node:fs";
import path from "node:path";
import { render } from "pele";

const repoRoot = path.resolve(import.meta.dirname, "..");
const guide = fs.readFileSync(path.join(repoRoot, "vendor/statechart/references/render.md"), "utf8");
const css = guide.match(/```css\n([\s\S]*?)```/)?.[1];
if (!css) throw new Error("No css block in vendor/statechart/references/render.md");

let failed = false;
for (const mmd of process.argv.slice(2)) {
  const out = mmd.replace(/\.mmd$/, "") + ".svg";
  try {
    const { svg } = render(fs.readFileSync(mmd, "utf8"), {
      limit: 1_000_000,
      outputLimit: 8_000_000,
      maxEdges: 10_000,
    });
    fs.writeFileSync(out, svg.replace(/(<svg[^>]*>)/, `$1<style>${css}</style>`));
    console.log(out);
  } catch (error) {
    failed = true;
    console.error(`${mmd}: ${error.name}: ${error.message}`);
  }
}
process.exit(failed ? 1 : 0);
