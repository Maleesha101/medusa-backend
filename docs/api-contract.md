# API Contract Conventions

## Versioning
All public HTTP endpoints live under `/api/v1`. Breaking changes require a versioning decision and corresponding documentation.

## Response conventions
- Use appropriate HTTP status codes.
- Use JSON for API responses unless the endpoint intentionally serves a file or stream.
- Keep error responses consistent; a structured error schema will be introduced before domain endpoints are added.
- Never expose stack traces or internal implementation details to public clients.

## Initial endpoints

| Method | Path | Purpose | Current status |
| --- | --- | --- | --- |
| GET | `/api/v1/live` | Process liveness | Implemented |
| GET | `/api/v1/ready` | Service readiness | Placeholder only; dependency checks are not implemented yet |
| GET | `/api/v1/platform/branding` | Public branding metadata | Planned |
| PUT | `/api/v1/admin/platform/branding/header-icon` | Upload/replace shared header icon | Planned |
| DELETE | `/api/v1/admin/platform/branding/header-icon` | Reset shared header icon | Planned |

## Authentication and permissions
Administrative endpoints must require authenticated identity and explicit permission checks. Do not implement the planned admin endpoints until the authentication/authorization contract is in place or a deliberately scoped interim policy is documented and tested.

## Health endpoint semantics
- `/live` indicates the process can answer requests. It should not fail merely because a downstream dependency is temporarily unavailable.
- `/ready` must eventually check the dependencies required to serve traffic (at minimum the database, and Redis only if required for the deployment). Until these checks exist, the response is a scaffold placeholder and must not be treated as a production readiness signal.
