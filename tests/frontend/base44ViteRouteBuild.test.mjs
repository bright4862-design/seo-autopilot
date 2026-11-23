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

  const entryParserFailures = [];
  for (const generation of ['V8', 'V9']) {
    const output = path.join(root, generation.toLowerCase());
    run('npm', ['run', 'build', '--', '--outDir', output, '--emptyOutDir'], {
      env: {
        ...process.env,
        VITE_SCAN_FUNCTION_GENERATION: generation,
        VITE_FIXLIST_SOURCE_SHA: SOURCE_SHA,
      },
    });

    // Check the production HTML parser, but if it fails, inspect the actual
    // emitted module entry as a *diagnostic only*. The test must remain RED
    // if the release checker rejects otherwise valid Vite output.
    const html = fs.readFileSync(path.join(output, 'index.html'), 'utf8');
    const scriptTags = [...html.matchAll(/<script\b[^>]*>/gi)].map((match) => match[0]);
    const entryTags = scriptTags.filter((tag) => /type=["']module["']/.test(tag) && /src=["']\/assets\/index-[A-Za-z0-9_-]+\.js["']/.test(tag));
    assert.equal(entryTags.length, 1, `${generation}: expected one Vite index module: ${scriptTags.join(' | ')}`);
    const asset = entryTags[0].match(/src=["'](\/assets\/index-[A-Za-z0-9_-]+\.js)["']/)[1];
    const entryParser = spawnSync('python3', [
      'scripts/lib/find-vite-entry-script.py', path.join(output, 'index.html'),
    ], { cwd: ROOT, encoding: 'utf8', timeout: 30_000 });
    if (entryParser.status !== 0 || entryParser.stdout.trim() !== asset) {
      const inlineBodies = [...html.matchAll(/<script\b[^>]*type=["']module["'][^>]*>([\s\S]*?)<\/script>/gi)]
        .map((match) => match[1].trim().slice(0, 350)).filter(Boolean);
      entryParserFailures.push({ generation, scriptTags, inlineBodies, stderr: entryParser.stderr.trim() });
    }
    const bundle = fs.readFileSync(path.join(output, asset.slice(1)), 'utf8');
    assert.ok(bundle.includes(SOURCE_SHA), `${generation}: selected entry lacks source SHA`);
    assert.ok(bundle.includes(MARKERS[generation]), `${generation}: selected marker was removed or split into another chunk`);
    const other = generation === 'V8' ? 'V9' : 'V8';
    assert.ok(!bundle.includes(MARKERS[other]), `${generation}: unselected marker survived bundling`);
  }
  assert.deepEqual(entryParserFailures, [], `Production entry selector rejected legitimate Vite output: ${JSON.stringify(entryParserFailures)}`);
});
