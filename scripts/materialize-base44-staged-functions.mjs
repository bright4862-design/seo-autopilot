#!/usr/bin/env node

import { fileURLToPath } from "node:url";

import { materializeStagedV9Packages } from "./lib/staged-v9-function-packages.mjs";

if (process.argv.length !== 3) {
  process.stderr.write("Usage: node scripts/materialize-base44-staged-functions.mjs <absolute new directory>\n");
  process.exitCode = 2;
} else {
  const root = fileURLToPath(new URL("../", import.meta.url));
  try {
    materializeStagedV9Packages(root, process.argv[2]);
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
