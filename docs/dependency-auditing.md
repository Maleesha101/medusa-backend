# Python dependency vulnerability auditing

MEDUSA uses `pip-audit` in the `dependency-audit` GitHub Actions job. The job runs on pull requests targeting `main` and pushes to `main`, separately from Bandit SAST and the regular test/lint job.

## Local use

Install the project and development tools, then audit the installed environment:

```bash
python -m pip install -e ".[dev]"
pip-audit
```

Generate a JSON report locally with:

```bash
pip-audit --format=json --output=pip-audit-report.json
```

The CI job installs the project and development dependencies and audits that installed environment. This includes the dependency set used by the test and CI tooling as well as application dependencies.

## CI policy and reports

- The scanner version is bounded in `pyproject.toml` (`pip-audit>=2.7,<3.0`).
- Known vulnerabilities reported by the scanner cause a non-zero exit code and fail the job. There is no blanket ignore list.
- CI uploads `pip-audit-vulnerability-report` as a JSON artifact when the report file is available, including after scan failure. Artifacts are retained for 14 days.
- The job has read-only repository permissions and uses no application or deployment secrets.
- The audit depends on the vulnerability data source available to `pip-audit` at run time. A clean result means no known vulnerabilities were reported for the audited environment at that time; it is not a guarantee that dependencies are vulnerability-free.

## Triage and exceptions

1. Review the package name, installed version, advisory identifier, and affected/fixed version ranges in the report.
2. Upgrade to a fixed compatible version, then run tests and the audit again.
3. If an upgrade is not immediately possible, document the specific advisory, impact assessment, mitigation, owner, and expiration date in a narrowly scoped exception approved through the project's review process. Avoid blanket ignores and remove exceptions when the dependency is fixed.
