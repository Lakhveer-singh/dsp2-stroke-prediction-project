#!/usr/bin/env bash
# Computes the next semantic version (vMAJOR.MINOR.PATCH) from the commits since the last tag.
#
#   major : a commit has "BREAKING CHANGE" in its message or a "type!:" subject  (feat!: ...)
#   patch : every commit is fix/chore/docs/ci/test/refactor/style/perf/build (conventional prefix)
#   minor : anything else (feat:, or free-form squash-merge titles) -> a develop->main merge is a feature release
#   first release (no tag yet): v1.0.0
#
# Prints GitHub-Actions style outputs:  tag=vX.Y.Z / previous_tag=vA.B.C (empty on first release)
set -euo pipefail

last_tag="$(git describe --tags --abbrev=0 --match 'v[0-9]*.[0-9]*.[0-9]*' 2>/dev/null || true)"

if [[ -z "$last_tag" ]]; then
  echo "tag=v1.0.0"
  echo "previous_tag="
  exit 0
fi

range="${last_tag}..HEAD"
subjects="$(git log "$range" --pretty=%s)"
messages="$(git log "$range" --pretty=%B)"

if [[ -z "$subjects" ]]; then
  echo "No commits since ${last_tag}; nothing to release." >&2
  echo "tag="
  echo "previous_tag=${last_tag}"
  exit 0
fi

version="${last_tag#v}"
IFS='.' read -r major minor patch <<<"$version"

bump="minor"
if grep -q "BREAKING CHANGE" <<<"$messages" || grep -Eq '^[a-z]+(\([^)]*\))?!:' <<<"$subjects"; then
  bump="major"
elif ! grep -Evq '^(fix|chore|docs|ci|test|refactor|style|perf|build)(\([^)]*\))?:' <<<"$subjects"; then
  bump="patch"
fi

case "$bump" in
  major) major=$((major + 1)); minor=0; patch=0 ;;
  minor) minor=$((minor + 1)); patch=0 ;;
  patch) patch=$((patch + 1)) ;;
esac

echo "tag=v${major}.${minor}.${patch}"
echo "previous_tag=${last_tag}"
