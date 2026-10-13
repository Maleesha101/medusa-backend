# MEDUSA Backend Architecture

## Decision: modular monolith first

MEDUSA starts as one deployable FastAPI application with explicit domain modules. This keeps local development and deployment manageable while preserving boundaries that can be extracted later if measured needs justify it.

## Proposed domain boundaries

| Module | Responsibilities |
| --- | --- |
| Platform | Platform-level settings, branding assets, feature configuration |
| Identity & access | Users, sessions/tokens, roles, permissions, organization membership |
| Organizations & teams | Universities, organizations, teams, team memberships |
| Competitions | Events, rounds, schedules, lifecycle and eligibility |
| Challenges | Challenge metadata, categories, publication state, flag validation interfaces |
| Submissions & scoring | Submission records, scoring rules, scoreboard snapshots |
| Sandbox | Challenge instance lifecycle and integration with the separate sandbox controller |
| Realtime | Authenticated WebSocket connections and event distribution |
| Audit & security operations | Administrative audit events, security alerts and operational events |
| Notifications & integrations | Email, webhooks, and background work |

Each module should expose public service interfaces. A module should not import another module's internal database models or repository implementation.

## Infrastructure

- PostgreSQL is the durable source of truth.
- Redis is for caching, coordination, and queue infrastructure where appropriate; it is not the source of truth for submissions or scores.
- S3-compatible object storage holds uploaded branding assets and challenge artifacts.
- Background workers handle jobs that should not block HTTP requests.
- WebSockets deliver authorized realtime updates; clients must not be trusted to determine scores or permissions.

## Initial layout

```text
app/
  api/                 # API routers and versioned route registration
  core/                # configuration and shared infrastructure
  modules/
    platform/
    identity/
    organizations/
    competitions/
    challenges/
    submissions/
    sandbox/
    realtime/
    audit/
  main.py
tests/
docs/
```

The module directories are introduced as their implementation begins, rather than creating empty placeholder packages for every future feature.

## Header icon / branding integration

The frontend currently has browser-local storage behavior suitable for a mock UI. It is not shared across users or browsers. The backend implementation must replace that with authenticated, permission-checked platform settings.

Proposed contract (to be finalized in the platform-settings issue):

- `GET /api/v1/platform/branding`: return the active public branding metadata and icon URL.
- `PUT /api/v1/admin/platform/branding/header-icon`: administrator-only upload/update.
- `DELETE /api/v1/admin/platform/branding/header-icon`: administrator-only reset to the default icon.

The upload path must validate allowed image formats and actual file signatures, enforce a size limit, generate a server-side object key, and store the asset in S3-compatible storage. Do not trust a client-provided filename or content type. Cache invalidation and audit events are required. The frontend should use the server's canonical icon URL once this API is implemented.

## Scaling

Do not target 50,000 concurrent participants by assumption alone. Establish load-test scenarios and performance budgets, measure database/Redis/API bottlenecks, and scale horizontally based on evidence. Challenge execution must be isolated from the API process and handled by a separate sandbox controller.
