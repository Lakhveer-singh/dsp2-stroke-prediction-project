#!/usr/bin/env bash
# Tests next_version.sh against throw-away git repositories.   bash .github/scripts/test_next_version.sh
set -euo pipefail
SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/next_version.sh"
fail=0

new_repo() { d="$(mktemp -d)"; git -C "$d" init -q -b main; git -C "$d" config user.email t@t; git -C "$d" config user.name t; echo "$d"; }
commit() { git -C "$1" commit -q --allow-empty -m "$2"; }
check() { # name expected actual
  if [[ "$2" == "$3" ]]; then echo "ok   - $1 ($3)"; else echo "FAIL - $1: expected '$2' got '$3'"; fail=1; fi
}
tag_of() { (cd "$1" && bash "$SCRIPT" | grep '^tag=' | cut -d= -f2); }

r=$(new_repo); commit "$r" "init"; check "first release is v1.0.0" "v1.0.0" "$(tag_of "$r")"

r=$(new_repo); commit "$r" "init"; git -C "$r" tag v1.0.0; commit "$r" "Add training DAG (#12)"
check "free-form squash title -> minor" "v1.1.0" "$(tag_of "$r")"

r=$(new_repo); commit "$r" "init"; git -C "$r" tag v1.4.2; commit "$r" "fix: reload route"; commit "$r" "docs: readme"
check "only fix/docs -> patch" "v1.4.3" "$(tag_of "$r")"

r=$(new_repo); commit "$r" "init"; git -C "$r" tag v1.4.2; commit "$r" "fix: reload route"; commit "$r" "feat(api): model info"
check "feat among fixes -> minor" "v1.5.0" "$(tag_of "$r")"

r=$(new_repo); commit "$r" "init"; git -C "$r" tag v1.4.2; commit "$r" "feat!: new predictions schema"
check "type! -> major" "v2.0.0" "$(tag_of "$r")"

r=$(new_repo); commit "$r" "init"; git -C "$r" tag v2.3.1; git -C "$r" commit -q --allow-empty -m "refactor db" -m "BREAKING CHANGE: tables renamed"
check "BREAKING CHANGE footer -> major" "v3.0.0" "$(tag_of "$r")"

r=$(new_repo); commit "$r" "init"; git -C "$r" tag v1.0.0
check "no new commits -> no tag" "" "$(tag_of "$r")"

r=$(new_repo); commit "$r" "init"; git -C "$r" tag v1.9.0; git -C "$r" tag nightly; commit "$r" "chore: bump"
check "non-semver tags ignored" "v1.9.1" "$(tag_of "$r")"

exit $fail
