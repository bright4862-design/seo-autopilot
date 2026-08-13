import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const code = readFileSync(new URL('./tmp_gateway_probe.ts', import.meta.url), 'utf8');
const env = { ...process.env, PATH: `/app/node_modules/.bin:${process.env.PATH || ''}` };
const result = spawnSync(
  '/usr/bin/base44',
  ['--app-id', '6a498732ec779dfaaeab0e53', '--json', 'exec'],
  { input: code, encoding: 'utf8', env, cwd: '/app/base44', maxBuffer: 1024 * 1024 },
);
if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) {
  const safe = result.stderr
    .split('\n')
    .filter((line) => !/authorization|bearer|app_user_auth_proof|app_user_jwt/i.test(line))
    .join('\n');
  if (safe.trim()) process.stderr.write(`${safe}\n`);
}
process.exit(result.status ?? 1);
