import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const SAFE_NAME = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/;

function inventory(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
}

function packageFiles(directory, prefix = "") {
  const entries = [];
  for (const item of inventory(directory)) {
    if (!SAFE_NAME.test(item.name)) throw new Error("Unsafe Base44 package path");
    const relative = prefix + item.name;
    const absolute = path.join(directory, item.name);
    if (item.isDirectory()) entries.push(...packageFiles(absolute, relative + "/"));
    else if (item.isFile()) entries.push([relative, absolute]);
    else throw new Error("Unsupported Base44 package entry");
  }
  return entries;
}

function readPackage(directory, name) {
  const entries = packageFiles(directory);
  const config = entries.find(([relative]) => relative === "function.jsonc");
  if (!config) throw new Error("Base44 function metadata is missing");
  const metadata = JSON.parse(fs.readFileSync(config[1], "utf8"));
  if (metadata.name !== name || typeof metadata.entry !== "string") throw new Error("Invalid Base44 function metadata");
  const nestedPrefix = `base44/functions/${name}/`;
  const nested = metadata.entry.startsWith(nestedPrefix);
  const entry = nested ? metadata.entry.slice(nestedPrefix.length) : metadata.entry;
  if (!SAFE_NAME.test(entry) || entry === "function.jsonc") throw new Error("Invalid Base44 function entrypoint");
  const files = entries
    .filter(([relative]) => relative !== "function.jsonc")
    .map(([relative, absolute]) => {
      if (nested && !relative.startsWith(nestedPrefix)) throw new Error("Unexpected bytes around nested Base44 package");
      return [nested ? relative.slice(nestedPrefix.length) : relative, absolute];
    });
  if (!files.some(([relative]) => relative === entry)) throw new Error("Base44 function entrypoint is missing");
  if (files.some(([relative]) => relative === "function.jsonc")) throw new Error("Duplicate Base44 function metadata");
  return { metadata: { ...metadata, entry }, files };
}

function digest(pkg) {
  const data = Object.entries(pkg.metadata).sort(([a], [b]) => a.localeCompare(b));
  const files = pkg.files.map(([name, absolute]) =>
    [name, createHash("sha256").update(fs.readFileSync(absolute)).digest("hex")]);
  return createHash("sha256").update(JSON.stringify([data, files])).digest("hex");
}

export function functionInventoryDigest(directory, name) {
  return digest(readPackage(directory, name));
}

export function captureFunctionInventory(project, listedFunctions, restoreProject) {
  const functions = path.join(project, "base44/functions");
  const present = inventory(functions);
  const expected = listedFunctions.split(/\r?\n/).map(line => /^ {2}([A-Za-z0-9_][A-Za-z0-9_.-]{0,127})$/.exec(line)?.[1])
    .filter(Boolean).sort();
  const actual = present.map(item => item.name).sort();
  if (!expected.length || new Set(expected).size !== expected.length
      || present.some(item => !item.isDirectory() || !SAFE_NAME.test(item.name))
      || JSON.stringify(expected) !== JSON.stringify(actual)) {
    throw new Error("Base44 function list and pulled package inventory disagree");
  }
  const digests = Object.create(null);
  for (const name of expected) {
    const pkg = readPackage(path.join(functions, name), name);
    digests[name] = digest(pkg);
    if (restoreProject) {
      const target = path.join(restoreProject, "base44/functions", name);
      fs.mkdirSync(target, { recursive: true });
      for (const [relative, absolute] of pkg.files) {
        const file = path.join(target, relative);
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.copyFileSync(absolute, file, fs.constants.COPYFILE_EXCL);
      }
      fs.writeFileSync(path.join(target, "function.jsonc"), JSON.stringify(pkg.metadata, null, 2), { flag: "wx" });
    }
  }
  return digests;
}

export function compareFunctionInventories(before, after) {
  const missingOrChanged = Object.keys(before).filter(name => !Object.hasOwn(after, name) || after[name] !== before[name]);
  const unexpected = Object.keys(after).filter(name => !Object.hasOwn(before, name));
  return { missingOrChanged, unexpected };
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const [action, ...args] = process.argv.slice(2);
  if (action === "capture" && [3, 4].includes(args.length)) {
    const [project, list, output, restoreProject] = args;
    const result = captureFunctionInventory(project, fs.readFileSync(list, "utf8"), restoreProject);
    fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  } else if (["compare", "restore-plan"].includes(action) && args.length === 2) {
    const [before, after] = args.map(file => JSON.parse(fs.readFileSync(file, "utf8")));
    const { missingOrChanged, unexpected } = compareFunctionInventories(before, after);
    if (unexpected.length) {
      const detail = "Unexpected registered Base44 functions: " + unexpected.join(", ");
      if (action === "compare") throw new Error(detail);
      process.stderr.write(detail + "\n");
    }
    if (missingOrChanged.length) process.stdout.write(missingOrChanged.join("\n") + "\n");
  } else {
    throw new Error("Use capture PROJECT LIST OUTPUT [RESTORE], compare BEFORE AFTER, or restore-plan BEFORE AFTER");
  }
}
