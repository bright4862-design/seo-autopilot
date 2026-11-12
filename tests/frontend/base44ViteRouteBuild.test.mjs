import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

// This is deliberately a real, offline Vite build of the browser application.
// Source-level string checks cannot prove that Rollup's emitted executable
// entry retains exactly the route selected by the Base44 invocation adapter.
// Neither build publishes a site, invokes a Base44 function, or runs a scan.
const ROOT = process.cwd();
const SOURCE_SHA = '5e0dc8d083b1284ec36d6a75e0ddc21f1d11c093';
const MARKERS = {
  V8: 'FIXLIST_SELECTED_SCAN_ROUTES_V8_V1',
  V9: 'FIXLIST_SELECTED_SCAN_ROUTES_V9_V1',
};

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 240_000,
    maxBuffer: 16 * 1024 * 1024,
    ...options,
  });
  assert.equal(result.error, undefined, `${command} failed to start: ${result.error}`);
  assert.equal(result.status, 0,
    `${command} ${args.join(' ')} failed (${result.signal || result.status})\n` +
    `stdout:\n${(result.stdout || '').slice(-5000)}\nstderr:\n${(result.stderr || '').slice(-5000)}`);
  return result.stdout.trim();
}

test('actual Vite V8 and V9 entries contain only the selected route marker', { timeout: 520_000 }, (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'fixlist-site-route-build-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  for (const generation of ['V8', 'V9']) {
    const output = path.join(root, generation.toLowerCase());
    run('npm', ['run', 'build', '--', '--outDir', output, '--emptyOutDir'], {
      env: {
        ...process.env,
        VITE_SCAN_FUNCTION_GENERATION: generation,
        VITE_FIXLIST_SOURCE_SHA: SOURCE_SHA,
      },
    });

    // Exercise the SAME HTML entry selector used for public-site acceptance.
    const asset = run('python3', [
      'scripts/lib/find-vite-entry-script.py', path.join(output, 'index.html'),
    ]);
    assert.match(asset, /^\/assets\/index-[A-Za-z0-9_-]+\.js$/);
    const bundle = fs.readFileSync(path.join(output, asset.slice(1)), 'utf8');
    assert.ok(bundle.includes(SOURCE_SHA), `${generation}: selected entry lacks source SHA`);
    assert.ok(bundle.includes(MARKERS[generation]), `${generation}: selected marker was removed or split into another chunk`);
    const other = generation === 'V8' ? 'V9' : 'V8';
    assert.ok(!bundle.includes(MARKERS[other]), `${generation}: unselected marker survived bundling`);
  }
});
