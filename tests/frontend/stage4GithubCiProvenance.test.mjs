import assert from 'node:assert/strict';
import test from 'node:test';
import {
  inspectMainCiEvidence, verifyCurrentMainCiRun, REQUIRED_JOBS,
} from '../../scripts/verify-stage4-ci-provenance.mjs';

const SHA = 'a'.repeat(40);
const ID = 43414007965;
const REPO = 'bright4862-design/seo-autopilot';
function fixture() {
  return {
    run: {
      id: ID,
      html_url: 'https://github.com/' + REPO + '/actions/runs/' + ID,
      repository: { full_name: REPO }, head_repository: { full_name: REPO },
      path: '.github/workflows/ci.yml', event: 'push', head_branch: 'main',
      head_sha: SHA, status: 'completed', conclusion: 'success',
    },
    jobs: { total_count: 2, jobs: REQUIRED_JOBS.map(name => ({
      name, run_id: ID, status: 'completed', conclusion: 'success',
    })) },
    mainRef: { ref: 'refs/heads/main', object: { type: 'commit', sha: SHA } },
  };
}
const evaluate = f => inspectMainCiEvidence(f, { runId: ID, sourceSha: SHA });

test('baseline: exact current-main push plus both successful jobs', () => {
  assert.equal(evaluate(fixture()).pass, true);
});

test('a real-shaped green PR run does not attest a release-source main push', () => {
  const f = fixture();
  f.run.event = 'pull_request';
  f.run.head_branch = 'research/standard150-stage4-ci-run-receipt-20261113';
  f.run.head_sha = '934770a2d15ae6843fef5d639c7e4e1bd7725a80';
  f.mainRef.object.sha = '029639a0b4e8cb229baecb8b7f6f8195f5280e83';
  const result = evaluate(f);
  assert.equal(result.pass, false);
  assert.ok(result.failures.includes('not_main_push_ci'));
  assert.ok(result.failures.includes('source_not_current_main'));
});

test('success from a wrong repository, workflow, source or run reference refuses', () => {
  for (const edit of [
    f => { f.run.repository.full_name = 'example/other'; },
    f => { f.run.head_repository.full_name = 'example/other'; },
    f => { f.run.path = '.github/workflows/other.yml'; },
    f => { f.run.head_sha = 'b'.repeat(40); },
    f => { f.run.id = ID + 1; },
    f => { f.run.html_url += '?attempt=2'; },
  ]) {
    const f = fixture(); edit(f);
    assert.equal(evaluate(f).pass, false);
  }
});

test('source superseded on main refuses even if old CI succeeded', () => {
  const f = fixture();
  f.mainRef.object.sha = 'c'.repeat(40);
  assert.ok(evaluate(f).failures.includes('source_not_current_main'));
});

test('missing, duplicate, truncated, foreign, skipped and failed jobs refuse', () => {
  for (const edit of [
    f => { f.jobs.jobs.pop(); f.jobs.total_count = 1; },
    f => { f.jobs.jobs[1] = { ...f.jobs.jobs[0] }; },
    f => { f.jobs.total_count = 3; },
    f => { f.jobs.jobs[0].run_id += 1; },
    f => { f.jobs.jobs[0].conclusion = 'skipped'; },
    f => { f.jobs.jobs[1].status = 'in_progress'; },
    f => { f.jobs.jobs.push({ name: 'Extra', run_id: ID, status: 'completed', conclusion: 'failure' }); f.jobs.total_count = 3; },
  ]) {
    const f = fixture(); edit(f);
    assert.equal(evaluate(f).pass, false);
  }
});

test('unfinished and failed runs refuse despite green jobs', () => {
  for (const [status, conclusion] of [['in_progress', null], ['completed', 'failure']]) {
    const f = fixture(); f.run.status = status; f.run.conclusion = conclusion;
    assert.ok(evaluate(f).failures.includes('ci_run_not_successful'));
  }
});

test('invalid caller-controlled run ID and source SHA refuse', () => {
  for (const [runId, sourceSha] of [
    [NaN, SHA], [0, SHA], ['43414007965', SHA], [ID, 'badsha'], [ID, 'A'.repeat(40)],
  ]) {
    assert.equal(inspectMainCiEvidence(fixture(), { runId, sourceSha }).pass, false);
  }
});

test('API verifier fetches only three pinned read-only GitHub resources', async () => {
  const f = fixture();
  const oldFetch = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (url, options) => {
    assert.equal(options.method, 'GET');
    assert.equal(options.redirect, 'error');
    assert.equal(options.cache, 'no-store');
    seen.push(url);
    const base = 'https://api.github.com/repos/' + REPO + '/';
    const payload = url === base + 'actions/runs/' + ID ? f.run
      : url === base + 'actions/runs/' + ID + '/jobs?per_page=100&filter=latest' ? f.jobs
      : url === base + 'git/ref/heads/main' ? f.mainRef : null;
    assert.ok(payload, 'unexpected URL: ' + url);
    return { ok: true, json: async () => payload };
  };
  try {
    assert.equal((await verifyCurrentMainCiRun(ID, SHA)).pass, true);
    assert.equal(seen.length, 3);
  } finally { globalThis.fetch = oldFetch; }
});

test('unavailable GitHub API fails closed without inventing CI results', async () => {
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 503 });
  try {
    assert.deepEqual((await verifyCurrentMainCiRun(ID, SHA)).failures,
      ['github_readback_unavailable_or_invalid']);
    assert.equal((await verifyCurrentMainCiRun(ID, 'badsha')).pass, false);
  } finally { globalThis.fetch = oldFetch; }
});
