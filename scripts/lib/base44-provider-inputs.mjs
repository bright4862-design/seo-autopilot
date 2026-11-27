import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const buildInputs = [
  ".npmrc", "base44/agents", "base44/entities", "base44/config.jsonc", "components.json",
  "data/base44-function-routes.json", "data/generated-staged-v9-routes.json", "index.html",
  "jsconfig.json", "package.json", "package-lock.json", "postcss.config.js", "public", "src",
  "tailwind.config.js", "vite.config.js",
];

export function providerBuildDigest(root) {
  const hash = createHash("sha256");
  function visit(relative) {
    const file = path.join(root, relative);
    const stat = fs.lstatSync(file);
    if (stat.isDirectory()) {
      for (const name of fs.readdirSync(file).sort()) visit(relative + "/" + name);
    } else if (stat.isFile()) {
      const digest = createHash("sha256").update(fs.readFileSync(file)).digest();
      hash.update(relative).update("\0").update(digest);
    } else {
      throw new Error("Unexpected provider build input " + relative);
    }
  }
  for (const relative of [...buildInputs, "scripts", "vite.config.source.js"]) visit(relative);
  return hash.digest("hex");
}
