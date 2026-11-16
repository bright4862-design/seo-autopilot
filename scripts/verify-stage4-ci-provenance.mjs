// Read-only GitHub Actions attestation for current-main Standard 150 CI.
// This checks CI provenance only; it is never release, deployment or canary approval.
import { pathToFileURL } from 'node:url';

export const REPO = 'bright4862-design/seo-autopilot';
export const REQUIRED_JOBS = Object.freeze([
  'Lint, typecheck, contract tests, and build',
  'Scanner regression fixtures',
]);
const SHA = /^[0-9a-f]{40}$/;

export function inspectMainCiEvidence({ run, jobs, mainRef }, { runId, sourceSha }) {
  const failures = [];
  const check = (ok, message) => { if (!ok) failures.push(message); };
  const idValid = Number.isSafeInteger(runId) && runId > 0;
  const shaValid = typeof sourceSha === 'string' && SHA.test(sourceSha);
  check(idValid, 'invalid_expected_run_id');
  check(shaValid, 'invalid_expected_source_sha');
  if (!idValid || !shaValid) return { pass: false, failures };

  check(run?.id === runId, 'run_id_mismatch');
  check(run?.html_url === 'https://github.com/' + REPO + '/actions/runs/' + runId, 'run_url_mismatch');
  check(run?.repository?.full_name === REPO, 'wrong_run_repository');
  check(run?.head_repository?.full_name === REPO, 'wrong_head_repository');
  check(run?.path === '.github/workflows/ci.yml', 'wrong_workflow');
  check(run?.event === 'push', 'not_main_push_ci');
  check(run?.head_branch === 'main', 'wrong_run_branch');
  check(run?.head_sha === sourceSha, 'run_source_sha_mismatch');
  check(run?.status === 'completed' && run?.conclusion === 'success', 'ci_run_not_successful');

  // A fresh point-in-time main read-back is evidence, not a concurrency lock.
  check(mainRef?.ref === 'refs/heads/main' && mainRef?.object?.type === 'commit', 'invalid_main_ref');
  check(mainRef?.object?.sha === sourceSha, 'source_not_current_main');

  check(Array.isArray(jobs?.jobs), 'missing_ci_jobs');
  if (Array.isArray(jobs?.jobs)) {
    check(Number.isSafeInteger(jobs.total_count) && jobs.total_count === jobs.jobs.length,
      'incomplete_ci_job_inventory');
    for (const name of REQUIRED_JOBS) {
      const matching = jobs.jobs.filter(job => job?.name === name);
      check(matching.length === 1, 'missing_or_duplicate_required_job:' + name);
      if (matching.length === 1) {
        check(matching[0].run_id === runId, 'foreign_run_job:' + name);
        check(matching[0].status === 'completed' && matching[0].conclusion === 'success',
          'required_job_not_successful:' + name);
      }
    }
    check(jobs.jobs.every(job => job?.run_id === runId &&
      job?.status === 'completed' && job?.conclusion === 'success'), 'unverified_ci_job');
  }
  return { pass: failures.length === 0, failures, run_id: runId, source_sha: sourceSha };
}

async function getJson(path, token) {
  const headers = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
  if (token) headers.Authorization = 'Bearer ' + token;
  const response = await fetch('https://api.github.com/repos/' + REPO + '/' + path, {
    method: 'GET', headers, redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) throw new Error('github_readback_failed');
  return response.json();
}

export async function verifyCurrentMainCiRun(runId, sourceSha, token = '') {
  if (!Number.isSafeInteger(runId) || runId <= 0 ||
      typeof sourceSha !== 'string' || !SHA.test(sourceSha)) {
    return { pass: false, failures: ['invalid_expected_run_id_or_source_sha'] };
  }
  // Never fetch record-supplied URLs: repository and paths are fixed.
  try {
    const [run, jobs, mainRef] = await Promise.all([
      getJson('actions/runs/' + runId, token),
      getJson('actions/runs/' + runId + '/jobs?per_page=100&filter=latest', token),
      getJson('git/ref/heads/main', token),
    ]);
    return inspectMainCiEvidence({ run, jobs, mainRef }, { runId, sourceSha });
  } catch {
    return { pass: false, failures: ['github_readback_unavailable_or_invalid'] };
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [idText, sourceSha] = process.argv.slice(2);
  const runId = /^[1-9]\d*$/.test(idText ?? '') ? Number(idText) : NaN;
  const result = await verifyCurrentMainCiRun(runId, sourceSha, process.env.GITHUB_TOKEN ?? '');
  console.log(JSON.stringify({ ...result, scope: 'read_only_current_main_ci_only_not_release_acceptance' }, null, 2));
  process.exitCode = result.pass ? 0 : 2;
}
