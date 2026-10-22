# Static application security testing (SAST)

MEDUSA runs [Bandit](https://bandit.readthedocs.io/) against Python application code in the `sast` GitHub Actions job. The job runs on pull requests targeting `main` and pushes to `main`, separately from linting and tests.

## Local use

Install the development dependencies and run the same policy as CI:

```bash
python -m pip install -e ".[dev]"
bandit -r app -ll -ii
```

To create a machine-readable report locally:

```bash
bandit -r app -ll -ii -f json -o bandit-report.json
```

## CI policy

- The scan targets `app/`; tests and documentation are not part of the application-code scan.
- `-ll -ii` selects findings with at least medium severity and medium confidence. Any matching finding makes the scanner exit non-zero and fails the SAST job. Lower-severity or lower-confidence results are not gating under this initial policy.
- CI writes a JSON report and uploads it as the `bandit-sast-report` artifact even if the scan step fails. Reports are retained for 14 days.
- The SAST job uses read-only repository permissions and does not receive application or deployment secrets.
- Findings should be reviewed in context. Fix genuine issues; add narrow, explained suppressions only when a finding is demonstrably a false positive or accepted risk. Do not blanket-suppress a test ID or disable the scanner to make CI green.

This scanner complements, but does not replace, dependency vulnerability scanning, secret scanning, code review, dynamic testing, or a security assessment. Passing SAST does not certify the application as secure.
