#!/usr/bin/env bash
# Stage the given paths, commit them and push, surviving a concurrent push from another workflow.
# Called by action.yml; runs in the site repository.
#
#   CMS_COMMIT_PATHS    whitespace-separated paths to stage (missing ones are skipped)
#   CMS_COMMIT_MESSAGE  commit message; {date} and {datetime} expand to the current UTC time
#   CMS_PUSH_ATTEMPTS   how many times to try pushing (default 5)
#   CMS_PUSH_BACKOFF    seconds to wait after the first failed attempt, doubled each time (default 2)
#   CMS_REMOTE          remote to push to (default origin)
#
# Writes `changed=true|false` to $GITHUB_OUTPUT. Exits non-zero if the push cannot be made;
# nothing partial ever reaches the remote.
set -euo pipefail

paths_line="${CMS_COMMIT_PATHS:-}"
read -ra paths <<< "${paths_line//$'\n'/ }"
message="${CMS_COMMIT_MESSAGE:-cms: {datetime}}"
attempts="${CMS_PUSH_ATTEMPTS:-5}"
backoff="${CMS_PUSH_BACKOFF:-2}"
remote="${CMS_REMOTE:-origin}"

finish() {
  echo "changed=$1"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "changed=$1" >> "$GITHUB_OUTPUT"; fi
  exit 0
}

if ! branch="$(git symbolic-ref --quiet --short HEAD)"; then
  echo "commit.sh: HEAD is detached — check out a branch before committing" >&2
  exit 1
fi

# A path that is neither on disk nor tracked is not an error: `inbox` before the first collection.
existing=()
for path in ${paths[@]+"${paths[@]}"}; do  # this form survives an empty list on bash 3.2
  if [ -e "$path" ] || [ -n "$(git ls-files -- "$path" | head -n 1)" ]; then existing+=("$path"); fi
done
if [ "${#existing[@]}" -eq 0 ]; then finish false; fi

git add -A -- "${existing[@]}"
if git diff --cached --quiet; then finish false; fi

export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-github-actions[bot]}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-$GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-$GIT_AUTHOR_EMAIL}"

message="${message//\{datetime\}/$(date -u '+%F %H:%M')}"
message="${message//\{date\}/$(date -u +%F)}"
git commit --quiet -m "$message"

for ((attempt = 1; attempt <= attempts; attempt++)); do
  if git push --quiet "$remote" "HEAD:refs/heads/$branch"; then finish true; fi
  if [ "$attempt" -eq "$attempts" ]; then break; fi
  echo "commit.sh: push failed (attempt $attempt of $attempts), rebasing onto $remote/$branch" >&2
  if ! git pull --quiet --rebase --autostash "$remote" "$branch"; then
    if [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; then
      git rebase --abort
      echo "commit.sh: the remote changed the same files — giving up, nothing was pushed" >&2
      exit 1
    fi
    echo "commit.sh: could not fetch $remote/$branch, will retry" >&2
  fi
  sleep "$backoff"
  backoff=$((backoff * 2))
done

echo "commit.sh: push failed after $attempts attempts" >&2
exit 1
