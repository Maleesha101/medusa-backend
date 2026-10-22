# Secret scanning with Gitleaks

MEDUSA runs Gitleaks in the `secret-scan` GitHub Actions job on pull requests targeting `main` and pushes to `main`. The scanner checks repository files for patterns associated with credentials and other secrets. The workflow fetches full Git history so the scan can cover committed history, not just the latest snapshot.

## Local use

Install Gitleaks version `8.24.2` using the official installation instructions, then run from the repository root:

```bash
gitleaks dir . --redact --exit-code 1
```

To create a local JSON report:

```bash
gitleaks dir . --report-format json --report-path gitleaks-report.json --redact --exit-code 1
```

## CI policy and reports

- CI installs the pinned Gitleaks version `8.24.2` and runs with redaction enabled.
- Any detected finding fails the job by default. There is no broad allowlist or blanket suppression configuration.
- A JSON report is uploaded as `gitleaks-secret-scan-report` when the scanner creates it, including when findings cause a non-zero exit. Artifacts are retained for 7 days.
- The job has read-only repository permissions and receives no application or deployment secrets. The scanner does not need credentials to inspect repository content.

## Triage and response

1. Treat a suspected live credential as exposed. Revoke or rotate it immediately and review relevant provider audit logs.
2. Remove the secret from the current code and replace it with an environment variable or secret manager reference. Removing it in a later commit does not remove it from Git history.
3. Assess whether history rewriting is appropriate for the repository and coordinate it with collaborators; history rewriting does not replace credential rotation.
4. For a confirmed false positive, use the narrowest possible rule or allowlist entry and document the exact finding and rationale. Do not exclude broad directories or disable a rule category to make CI pass.

Secret scanning is a detection layer, not a guarantee that every secret type will be identified. Continue to avoid committing credentials and use least-privilege, rotatable secrets.
