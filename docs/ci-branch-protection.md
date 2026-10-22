# CI security gate and branch protection

MEDUSA's GitHub Actions workflow exposes a stable aggregate security status check named **Required Security Gate**. It depends on all three security scans and runs even when a dependency has failed or been skipped. It succeeds only if Bandit SAST, the `pip-audit` dependency audit, and Gitleaks secret scanning each report `success`.

## Required status checks

In the repository's GitHub settings, configure a branch ruleset or branch protection rule targeting `main` and require pull requests before merging. Add these required status checks after they have appeared on a workflow run:

- `CI / Required Security Gate` (the aggregate security status check; exact displayed context may vary by GitHub Actions configuration)
- `CI / checks` (lint, formatting, migrations, and tests)

Use the exact status-check context shown in GitHub's branch protection selector rather than guessing its spelling. Do not require the three individual scan jobs as a substitute for the aggregate gate; the aggregate is designed to provide one stable security decision.

Recommended `main` protections:

- Require a pull request and at least one approving review, if the project has another reviewer available.
- Require the status checks listed above to pass before merging.
- Require branches to be up to date before merging if the team can tolerate the additional rebases/merges.
- Dismiss stale approvals after new commits and require approval of the latest reviewable push where appropriate.
- Block force pushes and branch deletion.
- Restrict bypass permissions to the smallest trusted administrator group; avoid routine bypasses.

## Important: enable repository settings separately

A workflow file can define checks but cannot make its own status check required. An authorized repository administrator must enable the ruleset/branch protection in GitHub repository settings. This change does **not** claim that protection is active until an administrator configures and verifies those settings. On repositories where the plan or permissions do not support the desired rules, use an available ruleset option or document the limitation explicitly.

## Operational guidance

If the aggregate gate fails, inspect its log to identify which scanner failed, then inspect the scanner's report artifact. Remediate real findings; any exception should be narrowly scoped, justified, approved, and time-bound. A failed or skipped security scan must not be treated as a pass.
