"""Offline tests: stale Actions checkouts must not become release authority."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/lib/release-source-guard.sh"


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "remote.git"
    author = tmp_path / "author"
    checkout = tmp_path / "checkout"
    git("init", "--bare", str(origin))
    git("init", "-b", "main", str(author))
    git("config", "user.name", "Fixture Author", cwd=author)
    git("config", "user.email", "fixture@example.test", cwd=author)
    (author / "README.txt").write_text("A\n")
    git("add", "README.txt", cwd=author)
    git("commit", "-m", "A", cwd=author)
    git("remote", "add", "origin", str(origin), cwd=author)
    git("push", "-u", "origin", "main", cwd=author)
    # Ensure a fresh checkout of this bare repository is on the main branch.
    git("symbolic-ref", "HEAD", "refs/heads/main", cwd=origin)
    git("clone", str(origin), str(checkout))
    first = git("rev-parse", "HEAD", cwd=checkout)
    assert len(first) == 40
    yield origin, author, checkout, first


def advance(author):
    (author / "README.txt").write_text("B\n")
    git("add", "README.txt", cwd=author)
    git("commit", "-m", "B", cwd=author)
    git("push", "origin", "main", cwd=author)
    return git("rev-parse", "HEAD", cwd=author)


def invoke(checkout, sha, *, actions=True, ref="refs/heads/main", event_sha=None, confirm=None):
    env = os.environ.copy()
    for key in ("GITHUB_ACTIONS", "GITHUB_REF", "GITHUB_SHA"):
        env.pop(key, None)
    if actions:
        env.update(GITHUB_ACTIONS="true", GITHUB_REF=ref, GITHUB_SHA=event_sha or sha)
    return subprocess.run(
        ["bash", "-c", 'source "$1"; fixlist_require_exact_main "$2" "$3" "$4"',
         "guard", str(GUARD), str(checkout), sha, confirm if confirm is not None else sha],
        text=True, capture_output=True, env=env, check=False,
    )


def test_current_exact_main_is_allowed(repos):
    _, _, checkout, sha = repos
    result = invoke(checkout, sha)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"source_sha={sha}"


def test_stale_origin_tracking_ref_does_not_authorize_actions(repos):
    _, author, checkout, sha = repos
    later = advance(author)
    assert later != sha
    assert git("rev-parse", "origin/main", cwd=checkout) == sha
    result = invoke(checkout, sha)
    assert result.returncode == 2
    assert "not current origin/main" in result.stderr
    assert "source_sha=" not in result.stdout


def test_missing_origin_tracking_ref_cannot_mask_advanced_main(repos):
    _, author, checkout, sha = repos
    advance(author)
    git("update-ref", "-d", "refs/remotes/origin/main", cwd=checkout)
    result = invoke(checkout, sha)
    assert result.returncode == 2
    assert "not current origin/main" in result.stderr


def test_missing_tracking_ref_still_permits_current_remote(repos):
    _, _, checkout, sha = repos
    git("update-ref", "-d", "refs/remotes/origin/main", cwd=checkout)
    assert invoke(checkout, sha).returncode == 0


def test_unavailable_remote_fails_closed(repos):
    _, _, checkout, sha = repos
    git("remote", "set-url", "origin", str(checkout / "nonexistent.git"), cwd=checkout)
    result = invoke(checkout, sha)
    assert result.returncode == 2
    assert "cannot verify" in result.stderr


def test_manual_mode_also_rejects_superseded_main(repos):
    _, author, checkout, sha = repos
    advance(author)
    assert invoke(checkout, sha, actions=False).returncode == 2


def test_incorrect_event_or_confirmation_refused(repos):
    _, _, checkout, sha = repos
    assert invoke(checkout, sha, ref="refs/heads/feature").returncode == 2
    assert invoke(checkout, sha, event_sha="0" * 40).returncode == 2
    assert invoke(checkout, sha, confirm="0" * 40).returncode == 2


def test_dirty_checkout_refused(repos):
    _, _, checkout, sha = repos
    (checkout / "README.txt").write_text("modified\n")
    result = invoke(checkout, sha)
    assert result.returncode == 2
    assert "dirty" in result.stderr


def test_cloud_operator_reuses_live_remote_guard():
    content = (ROOT / "scripts/fixlist-cloud-operator.sh").read_text()
    body = content.split("require_exact_main_owner_source() {", 1)[1].split("\n}\n", 1)[0]
    assert 'source "$REPO_ROOT/scripts/lib/release-source-guard.sh"' in body
    assert 'fixlist_require_exact_main "$REPO_ROOT" "$SOURCE_SHA" "$SOURCE_SHA"' in body

def test_zero_traffic_tag_is_a_mutation_with_live_source_check():
    operator = (ROOT / "scripts/fixlist-cloud-operator.sh").read_text()
    case = operator.split("  tag-worker-candidate)", 1)[1].split("    ;;", 1)[0]
    assert case.index("require_exact_main_owner_source") < case.index("tag_worker_candidate \"$TARGET_REVISION\"")

    workflow = (ROOT / ".github/workflows/fixlist-cloud-operator.yml").read_text()
    # Owner-comment promotion and direct operator dispatch are separate callers.
    promotion = workflow.split("      - name: Tag the exact zero-traffic candidate", 1)[1].split(
        "      - name: Resolve candidate token audience", 1)[0]
    assert "SOURCE_SHA: ${{ steps.command.outputs.source_sha }}" in promotion
    direct = workflow.split("      - name: Run allowlisted worker operation", 1)[1].split(
        "      - name: Build isolated Standard 150 worker candidate", 1)[0]
    assert "SOURCE_SHA: ${{ github.sha }}" in direct
