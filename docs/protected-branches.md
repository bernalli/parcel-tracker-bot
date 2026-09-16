# Branch protection (post-F8 setup notes)

Configured manually in GitHub repo settings → **Branches → main**.

| Setting                                                  | Value                                                       |
|----------------------------------------------------------|-------------------------------------------------------------|
| Require a pull request before merging                    | ✅                                                           |
| Required approving reviews                               | 1                                                           |
| Dismiss stale reviews when new commits pushed            | ✅                                                           |
| Require status checks to pass                            | ✅ — `test (3.11)`, `test (3.12)`, `gitleaks`, `pip-audit`   |
| Require branches to be up to date before merging         | ✅                                                           |
| Require conversation resolution before merging           | ✅                                                           |
| Require signed commits                                   | recommended (not enforced — small project)                  |
| Require linear history                                   | ✅                                                           |
| Allow force pushes                                       | ❌                                                           |
| Allow deletions                                          | ❌                                                           |
| Restrict who can push                                    | maintainer only                                             |

Re-apply via the `gh` CLI if the rules are ever wiped:

```bash
gh api -X PUT /repos/bernalli/parcel-tracker-bot/branches/main/protection \
  -f required_status_checks.strict=true \
  -F required_status_checks.contexts='["test (3.11)","test (3.12)","gitleaks","pip-audit"]' \
  -f enforce_admins=false \
  -f required_pull_request_reviews.required_approving_review_count=1 \
  -f required_pull_request_reviews.dismiss_stale_reviews=true \
  -f required_linear_history=true \
  -f allow_force_pushes=false \
  -f allow_deletions=false
```
