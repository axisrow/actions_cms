#!/usr/bin/env bash
# Create or verify the release tag of the checked-out commit and move the major tag (`v0`, `v1`, ...) to it.
# Called by .github/workflows/release.yml.
#
#   release.sh pushed      a tag vX.Y.Z was pushed: it must equal the package version ($GITHUB_REF_NAME)
#   release.sh dispatch    run by hand: create the tag v<package version> on this commit; refuse if it exists
#
#   CMS_REMOTE             remote to push to (default origin)
#
# Writes `tag=vX.Y.Z` to $GITHUB_OUTPUT. The package version is read from src/actions_cms/__init__.py.
set -euo pipefail

mode="${1:?usage: release.sh pushed|dispatch}"
remote="${CMS_REMOTE:-origin}"

version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/actions_cms/__init__.py)"
if [ -z "$version" ]; then
  echo "::error::could not read __version__ from src/actions_cms/__init__.py"
  exit 1
fi
tag="v$version"

case "$mode" in
  pushed)
    if [ "$tag" != "${GITHUB_REF_NAME:-}" ]; then
      echo "::error::tag ${GITHUB_REF_NAME:-<none>} does not match the package version $version"
      exit 1
    fi
    ;;
  dispatch)
    if git ls-remote --exit-code --tags "$remote" "refs/tags/$tag" > /dev/null 2>&1; then
      echo "::error::tag $tag already exists — raise __version__ in src/actions_cms/__init__.py first"
      exit 1
    fi
    git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
      tag -a "$tag" -m "actions_cms $version"
    git push "$remote" "refs/tags/$tag"
    ;;
  *)
    echo "usage: release.sh pushed|dispatch" >&2
    exit 2
    ;;
esac

# Sites pin the action by major version, so that tag follows every release.
major="${tag%%.*}"
git tag --force "$major" "$tag^{commit}"
git push --force "$remote" "refs/tags/$major"

echo "tag=$tag"
if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "tag=$tag" >> "$GITHUB_OUTPUT"; fi
