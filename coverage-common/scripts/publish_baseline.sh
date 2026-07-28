#!/usr/bin/env bash
# Shared publish-to-baseline helper for all baseline-branch writers
# (coverage-update, codeql-publish, future int-coverage).
#
# Prepares a worktree for the baseline branch (creating an orphan branch on
# first publish), runs the caller-supplied mirror command with BASELINE_DIR
# exported, then commits and pushes.  On a non-fast-forward push (another
# writer landed first) it re-fetches and re-runs the mirror command --
# writers own disjoint subtrees and the catalog regenerates from whatever is
# on the branch, so a retry is always a clean overlay.
#
# Usage:
#   publish_baseline.sh <baseline-branch> <commit-sha> <commit-prefix> <mirror-command...>
#
# Environment:
#   BASELINE_DIR is exported to the mirror command (worktree root).
#   PUBLISH_RETRIES overrides the retry count (default 3).
set -euo pipefail

BASELINE_BRANCH="$1"; shift
COMMIT_SHA="$1"; shift
COMMIT_PREFIX="$1"; shift

RETRIES="${PUBLISH_RETRIES:-3}"
BASELINE_DIR="${RUNNER_TEMP:-/tmp}/fprime-baseline-publish"
export BASELINE_DIR

git config user.name  "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

cleanup_worktree() {
    git worktree remove --force "$BASELINE_DIR" 2>/dev/null || true
    rm -rf "$BASELINE_DIR"
    git worktree prune 2>/dev/null || true
}

for attempt in $(seq 1 "$RETRIES"); do
    cleanup_worktree
    # Drop any stale local branch left by a previous attempt so the orphan
    # path (and -B re-pointing) starts clean.
    git branch -D "$BASELINE_BRANCH" 2>/dev/null || true
    if git fetch origin "${BASELINE_BRANCH}:refs/remotes/origin/${BASELINE_BRANCH}" 2>/dev/null; then
        git worktree add -B "$BASELINE_BRANCH" "$BASELINE_DIR" "origin/${BASELINE_BRANCH}"
    else
        git worktree add --detach "$BASELINE_DIR" "$(git rev-parse HEAD)"
        git -C "$BASELINE_DIR" checkout --orphan "$BASELINE_BRANCH"
        git -C "$BASELINE_DIR" rm -rf --quiet . || true
    fi

    "$@"

    git -C "$BASELINE_DIR" add -A
    if git -C "$BASELINE_DIR" diff --cached --quiet; then
        echo "publish_baseline: no changes to commit; skipping push."
        exit 0
    fi

    SHORT_SHA=$(git rev-parse --short "$COMMIT_SHA")
    SUBJECT=$(git log -1 --format=%s "$COMMIT_SHA" 2>/dev/null || echo "update")
    git -C "$BASELINE_DIR" commit -m "${COMMIT_PREFIX}: ${SHORT_SHA} ${SUBJECT}"

    if git -C "$BASELINE_DIR" push origin "$BASELINE_BRANCH"; then
        exit 0
    fi
    echo "publish_baseline: push rejected (attempt ${attempt}/${RETRIES}); refetching and retrying." >&2
done

echo "publish_baseline: failed to push ${BASELINE_BRANCH} after ${RETRIES} attempts." >&2
exit 1
