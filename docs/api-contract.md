# API Contract Conventions

## Versioning
All public HTTP endpoints live under /api/v1. Breaking changes require a versioning decision and corresponding documentation.

## Response conventions
- Use appropriate HTTP status codes.
- Use JSON for responses unless the endpoint intentionally serves a file, stream, or empty response.
- Never expose stack traces or internal implementation details to public clients.
- User responses must never include password hashes or signing secrets.
- Challenge catalog responses must never include flags, flag hashes, or private grading data.
- Submission responses never echo the submitted flag.

## Identity endpoints

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| POST | /api/v1/auth/register | Create a participant account | Public; role is assigned by the server |
| POST | /api/v1/auth/token | Exchange email/password for a short-lived access token | Public |
| GET | /api/v1/auth/me | Return the authenticated user's safe profile | Bearer token |
| GET | /api/v1/live | Process liveness | Public |
| GET | /api/v1/ready | Database readiness | Public |

## Organization and team endpoints

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| GET | /api/v1/organizations | List active organizations | Public |
| POST | /api/v1/organizations | Create an organization | Organizer or admin |
| GET | /api/v1/organizations/{organization_id} | Get an active organization | Public |
| GET | /api/v1/organizations/{organization_id}/teams | List teams in an active organization | Public |
| POST | /api/v1/organizations/{organization_id}/teams | Create a team; creator becomes captain | Authenticated |
| GET | /api/v1/teams/{team_id} | Get team details and membership list | Public |
| POST | /api/v1/teams/{team_id}/join | Join a team as the current user | Authenticated |
| DELETE | /api/v1/teams/{team_id}/leave | Leave a team | Authenticated; captain cannot leave yet |

Organization slugs must use lowercase letters, digits, and single hyphens. Duplicate slugs return HTTP 409. Team names are unique within an organization; duplicate names return HTTP 409. Joining an inactive or missing organization is not allowed. Duplicate membership returns HTTP 409. A team captain must transfer captaincy before leaving; captaincy transfer is not implemented in this phase.

## Competition and round endpoints

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| GET | /api/v1/competitions | List public published, active, or completed competitions | Public |
| POST | /api/v1/competitions | Create a draft competition | Organizer or admin |
| GET | /api/v1/competitions/{competition_id} | Get a public competition | Public; private competitions return 404 |
| PATCH | /api/v1/competitions/{competition_id}/status | Advance competition lifecycle | Organizer or admin |
| GET | /api/v1/competitions/{competition_id}/rounds | List ordered rounds for a public competition | Public; private competitions return 404 |
| POST | /api/v1/competitions/{competition_id}/rounds | Create a round | Organizer or admin |

Competition slugs are globally unique. A competition starts in draft. Allowed transitions are draft to published, published to active, active to completed, and completed to archived. Invalid transitions return HTTP 409. Round positions and slugs must be unique within a competition, and positions start at 1. Finished competitions cannot receive new rounds. Schedule start values must be earlier than corresponding end values.

## Challenge authoring and catalog endpoints

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| POST | /api/v1/rounds/{round_id}/challenges | Create a draft challenge | Organizer or admin |
| GET | /api/v1/rounds/{round_id}/challenges | List published challenges | Public; parent competition must be public and published, active, or completed |
| GET | /api/v1/challenges/{challenge_id} | Get a published challenge | Public; drafts and archived challenges return 404 |
| PATCH | /api/v1/challenges/{challenge_id} | Update challenge metadata | Organizer or admin |
| PATCH | /api/v1/challenges/{challenge_id}/status | Publish or archive a challenge | Organizer or admin |
| PUT | /api/v1/challenges/{challenge_id}/flag | Set or replace the flag for a draft challenge | Organizer or admin |
| POST | /api/v1/challenges/{challenge_id}/submissions | Submit a flag for a team | Authenticated team member |
| GET | /api/v1/competitions/{competition_id}/scoreboard | Get public competition standings | Public; competition must be public and published, active, or completed |
| GET | /api/v1/audit-events | Query recent security-sensitive audit events | Admin only; supports action, resource_type, actor_user_id, limit (1–100), and offset filters |

Challenge slugs are unique within a round. Points must be between 1 and 10,000. Difficulty is one of easy, medium, hard, or expert. New challenges always start as drafts; clients cannot set status during creation or metadata updates. Allowed status transitions are draft to published and published to archived. A challenge must have a configured flag before it can be published. Archived challenges cannot be edited. Finished competitions cannot receive new challenges. Public responses contain challenge metadata only.

## Challenge flags and submissions

- Flags must be configured before publishing and may be changed only while the challenge remains a draft.
- The API stores a keyed HMAC-SHA-256 digest of each flag, not plaintext. The configured AUTH_SECRET_KEY is used as the HMAC key; rotating it requires setting flags again for all challenges.
- Flag comparison uses constant-time digest comparison.
- A submission requires an active competition, a published challenge, an existing team from the same organization as the competition, and membership of the authenticated user in that team.
- Each attempt records challenge ID, team ID, user ID, correctness, and timestamp. Submitted flag values are never persisted or returned.
- Incorrect attempts return HTTP 200 with correct=false; correct attempts return HTTP 200 with correct=true.
- A repeated solve by the same team returns HTTP 409. A partial unique database index protects the one-correct-solve invariant under concurrent submissions.
- A correct solve snapshots the challenge point value into `points_awarded`; incorrect attempts award zero. Later edits to challenge metadata do not change points already awarded.\n- The public scoreboard sums immutable awarded points and counts correct solves. Teams are ranked by points (competition ranking for ties); ties are ordered for display by earliest last solve, team name, then team ID. The endpoint currently includes teams with at least one submission, including zero-point teams with only incorrect attempts.\n- This increment does not implement a distributed submission rate limiter or persistent administrative audit events.

## Registration and authorization

Registration requires a valid email and a password of 12–128 characters. Duplicate email addresses return HTTP 409. Token requests use OAuth2 form fields: the field named username must contain the email address and password contains the password. Invalid credentials return a generic HTTP 401 response.

Access tokens identify the user; current role and active status are loaded from the database on each authenticated request. Role claims supplied by clients are not trusted. Public registration cannot set role or active status. Use require_roles(...) for protected routes and test both allowed and denied access.

## Token policy

Tokens are signed using HS256, include issuer, subject, issued-at, and expiration claims, and expire after 15 minutes by default (configurable from 1–60 minutes). Set a unique AUTH_SECRET_KEY of at least 32 characters in each deployment. The development placeholder must never be used in production. Refresh-token rotation, revocation, MFA, password reset, and email verification are not implemented in this phase.

## Readiness semantics
- /live indicates the process can answer requests and does not check downstream dependencies.
- /ready executes a lightweight database query and returns HTTP 503 if the database is unavailable. Redis is not currently required by the request path and is not part of this probe.


## Audit events

The API records challenge submission outcomes, challenge creation/metadata/status changes, and competition status transitions in the same database transaction as the corresponding action. Audit records contain actor identity/role when available, action, outcome, resource type/id, timestamp, and allowlisted metadata. Submitted flag values, flag hashes, passwords, bearer tokens, and arbitrary request bodies must never be recorded. The GET /api/v1/audit-events endpoint is restricted to users whose current database role is admin; results are newest-first and paginated with a maximum page size of 100. This is an application-level audit log, not tamper-proof external storage; production deployments should restrict database access and export logs to a separately controlled sink.
