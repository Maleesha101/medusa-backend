# API security smoke tests

The `tests/test_api_security_smoke.py` suite exercises security-sensitive API behavior using FastAPI's test client and the isolated database/Redis fixtures in `tests/conftest.py`. It runs with the existing `pytest` command in CI and does not call production services.

Coverage includes:

- Requests to the authenticated `/api/v1/auth/me` endpoint without a bearer token or with a malformed token are rejected.
- Expired tokens and tokens signed with an incorrect secret are rejected.
- A normal participant cannot create competitions, an organizer-only operation.
- Invalid login credentials do not result in an access token.

Run locally:

```bash
pytest tests/test_api_security_smoke.py
```

These are deterministic API regression checks, not a full dynamic application security test (DAST), fuzzing campaign, penetration test, or proof that every route and object-level authorization rule is correct. Keep expanding coverage as sensitive endpoints and roles are added, and test resource ownership/tenant boundaries with representative fixtures where the API exposes those rules.
