# Git workflow (course requirements)

* `main` = defenses only · `develop` = integration (**one squashed commit per feature**) · `feature/*` = named by feature.
* No direct commits to `main`/`develop`; PRs into `develop` (CI runs); **squash merge**; delete the branch after merging.
* `develop → main` only before a defense (this triggers the CD release workflow).

```bash
# start a feature from develop
git switch develop && git pull
git switch -c feature/training-dag

# work, commit small and often
git add -A && git commit -m "feat: training DAG skeleton"

# keep up to date with develop (rebase, resolve conflicts, force-push your OWN feature branch)
git fetch origin && git rebase origin/develop
git push --force-with-lease -u origin feature/training-dag

# open a Pull Request into develop on GitHub -> review -> "Squash and merge" -> "Delete branch"
# squash commit message = the feature (conventional style helps the release script): "feat: training DAG with MLflow promotion (#12)"
```

Before the defense
```bash
git switch develop && git pull
# on GitHub: Pull Request  develop -> main   (use "Create a merge commit", not squash, so history stays readable)
git switch main && git pull
git branch -r | grep -v -E "origin/(main|develop|HEAD)"     # remaining finished feature branches ...
git push origin --delete feature/old-branch                  # ... delete them (WIP branches may stay)
```
Release versions are computed from the commit messages since the last tag: only `fix:`/`docs:`/`chore:`… → patch;
anything else → minor; `feat!:` or `BREAKING CHANGE` → major; the very first release is `v1.0.0`.

## Adding this project to your existing Defense 1 repository
1. On `develop`, create `feature/mlflow-model-registry` etc. and copy the files of each workstream (see `TEAM_TASKS.md`)
   into it, one feature branch at a time, so the history shows who did what.
2. `team5_service_web/.github` (old polyrepo CI) was removed; the single CI is `.github/workflows/ci.yml`.
3. `.env` is never committed (`team2_docker_env/.gitignore`); share `.env.example` only.
