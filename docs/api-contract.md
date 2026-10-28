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
| POST | /api/v1/auth/register | Create a participant account | Public; role is assigned by the server; Redis rate limit per client IP |
| POST | /api/v1/auth/token | Exchange email/password for a short-lived access token | Public; Redis rate limits per client IP and normalized account |
| GET | /api/v1/auth/me | Return the authenticated user's safe profile | Bearer token |
| POST | /api/v1/auth/logout | Revoke the presented access token | Bearer token; returns 204 on success |
| POST | /api/v1/auth/password-reset/request | Request password-reset instructions | Public; generic 202 response; Redis limits per IP and normalized email |
| POST | /api/v1/auth/password-reset/confirm | Consume reset token and set a new password | Public; rate-limited; returns 204 on success |
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
| GET | /api/v1/teams/{team_id} | Get team details and public membership roster | Public; roster omits member email addresses |
| POST | /api/v1/teams/{team_id}/join | Join a team as the current user | Authenticated |
| PUT | /api/v1/teams/{team_id}/captain | Transfer captaincy to an existing team member | Current team captain |
| DELETE | /api/v1/teams/{team_id}/leave | Leave a team | Authenticated; current captain cannot leave |

Organization slugs must use lowercase letters, digits, and single hyphens. Duplicate slugs return HTTP 409. Team names are unique within an organization; duplicate names return HTTP 409. Joining an inactive or missing organization is not allowed. Duplicate membership returns HTTP 409. A team captain may transfer captaincy only to an existing member. The transfer atomically updates the team captain ID and both membership roles; after transfer, the former captain may leave as a regular member. The current captain cannot leave.

Public team rosters expose member user IDs, roles, and join timestamps only; they do not expose email addresses.\n\n## Competition and round endpoints

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
| PUT | /api/v1/challenges/{challenge_id}/flag | Set or replace the flag for a draft challenge | Owning-organization organizer or admin |
| POST | /api/v1/challenges/{challenge_id}/submissions | Submit a flag for a team | Authenticated team member |
| GET | /api/v1/competitions/{competition_id}/scoreboard | Get public competition standings | Public; competition must be public and published, active, or completed |
| GET | /api/v1/audit-events | Query recent security-sensitive audit events | Admin only; supports action, resource_type, actor_user_id, limit (1–100), and offset filters |

Challenge slugs are unique within a round. Points must be between 1 and 10,000. Difficulty is one of easy, medium, hard, or expert. New challenges always start as drafts; clients cannot set status during creation or metadata updates. Allowed status transitions are draft to published and published to archived. A challenge must have a configured flag before it can be published. Archived challenges cannot be edited. Finished competitions cannot receive new challenges. Public responses contain challenge metadata only.

## Challenge flags and submissions

- Flags must be configured before publishing and may be changed only while the challenge remains a draft.
- The API stores a keyed HMAC-SHA-256 digest of each flag, not plaintext. The configured AUTH_SECRET_KEY is used as the HMAC key; rotating it requires setting flags again for all challenges.
- Flag comparison uses constant-time digest comparison.
- A submission requires an active competition, a published challenge, an existing team from the same organization as the competition, membership of the authenticated user in that team, and a registration record for that exact team and competition. Teams without a matching registration receive HTTP 409.
- Each attempt records challenge ID, team ID, user ID, correctness, and timestamp. Submitted flag values are never persisted or returned.
- Incorrect attempts return HTTP 200 with correct=false; correct attempts return HTTP 200 with correct=true.
- A repeated solve by the same team returns HTTP 409. A partial unique database index protects the one-correct-solve invariant under concurrent submissions.
- A correct solve snapshots the challenge point value into `points_awarded`; incorrect attempts award zero. Later edits to challenge metadata do not change points already awarded.\n- The public scoreboard sums immutable awarded points and counts correct solves. Teams are ranked by points (competition ranking for ties); ties are ordered for display by earliest last solve, team name, then team ID. The endpoint currently includes teams with at least one submission, including zero-point teams with only incorrect attempts.\n- This increment does not implement a distributed submission rate limiter or persistent administrative audit events.

## Registration and authorization

Registration requires a valid email and a password of 12–128 characters. Duplicate email addresses return HTTP 409. Token requests use OAuth2 form fields: the field named username must contain the email address and password contains the password. Invalid credentials return a generic HTTP 401 response.

Access tokens identify the user; current role and active status are loaded from the database on each authenticated request. Role claims supplied by clients are not trusted. Public registration cannot set role or active status. Use require_roles(...) for protected routes and test both allowed and denied access.

## Token policy

Tokens are signed using HS256, include issuer, subject, issued-at, and expiration claims, and expire after 15 minutes by default (configurable from 1–60 minutes). Set a unique AUTH_SECRET_KEY of at least 32 characters in each deployment. The development placeholder must never be used in production. Explicit logout revocation and password-reset invalidation are implemented. Reset tokens are random, single-use, expire after 30 minutes by default, and are stored only as SHA-256 hashes. Reset requests return the same 202 response whether or not the account exists. SMTP must be configured to deliver reset links. Refresh-token rotation, MFA, and email verification are not implemented.

## Readiness semantics
- /live indicates the process can answer requests and does not check downstream dependencies.
- /ready executes a lightweight database query and returns HTTP 503 if the database is unavailable. Redis is not currently required by the request path and is not part of this probe.


## Audit events

The API records challenge submission outcomes, challenge creation/metadata/status changes, and competition status transitions in the same database transaction as the corresponding action. Audit records contain actor identity/role when available, action, outcome, resource type/id, timestamp, and allowlisted metadata. Submitted flag values, flag hashes, passwords, bearer tokens, and arbitrary request bodies must never be recorded. The GET /api/v1/audit-events endpoint is restricted to users whose current database role is admin; results are newest-first and paginated with a maximum page size of 100. This is an application-level audit log, not tamper-proof external storage; production deployments should restrict database access and export logs to a separately controlled sink.


## Real-time scoreboard updates

| Protocol | Path | Purpose | Access |
| --- | --- | --- | --- |
| WebSocket | /api/v1/competitions/{competition_id}/scoreboard/ws | Receive scoreboard invalidation events | Public competition only; private, missing, or non-publicly-visible competitions are rejected |

When a correct flag submission commits, the API publishes a `scoreboard.updated` event to a competition-scoped Redis Pub/Sub channel. The event contains the competition ID and submission ID only; it does not contain flags, team details, or the scoreboard itself. Clients should refetch `GET /api/v1/competitions/{competition_id}/scoreboard` after receiving an event. REST remains authoritative. Notifications are best-effort: if Redis is unavailable, a committed solve still succeeds, but connected clients may need to reconnect or refresh to recover current standings.


Authentication rate limits use shared Redis fixed windows. Defaults are 5 registration requests per IP per 600 seconds, 20 token requests per IP per 60 seconds, and 5 token requests per normalized account per 60 seconds. Over-limit responses return HTTP 429 with a Retry-After header. Redis failures fail closed with HTTP 503. The account identifier is hashed before inclusion in a Redis key. The API uses the direct peer IP; deployments behind a reverse proxy must configure trusted proxy handling rather than trusting arbitrary client-supplied forwarding headers.


## Access-token revocation

Access tokens include a unique token identifier (`jti`). `POST /api/v1/auth/logout` adds that identifier to a Redis denylist until the token's expiration. Authenticated requests check the denylist, so the logged-out token is rejected immediately. The denylist is shared across API replicas and entries expire automatically. Redis failures fail closed with HTTP 503 for authenticated requests and logout, rather than silently accepting a token whose revocation status cannot be checked. Logging out revokes only the presented access token; it does not revoke other tokens issued to the same account.


## Competition team registration

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| POST | /api/v1/competitions/{competition_id}/registrations | Register a team for a public competition | Authenticated member of the team |

The request body contains `team_id`. Registration is available only for public competitions in `published` or `active` status and only during the configured registration window. If `registration_opens_at` is unset, registration is open from publication; if `registration_closes_at` is unset, there is no closing-time limit. The team must belong to the competition's organization, and the authenticated caller must be a member of that team. A team can register only once per competition; a database unique constraint enforces this invariant. A hidden or unpublished competition returns HTTP 404, a closed/not-yet-open window returns HTTP 409, an ineligible team or non-member caller returns HTTP 403, and duplicate registration returns HTTP 409. Successful registration returns HTTP 201 with the registration ID, competition ID, team ID, registering user ID, and registration timestamp.


### Registration roster and withdrawal

| Method | Path | Purpose | Access |
| --- | --- | --- | --- |
| GET | /api/v1/competitions/{competition_id}/registrations?limit=50&offset=0 | List a competition's registrations in stable pages | Organizer/admin with access to the competition's organization |
| DELETE | /api/v1/competitions/{competition_id}/registrations/{team_id} | Withdraw a team's registration | Current team captain |

The roster is private and includes registration ID, competition ID, team ID/name, registering user ID, and timestamp; it does not include email addresses. The page size defaults to 50 and is limited to 100. Organizers are restricted to organizations they created; admins can manage registrations across organizations. Only the current captain can withdraw their team's registration, while the competition remains in `published` status and the registration close time has not passed. Withdrawal is rejected with HTTP 409 after the competition activates or the window closes, and with HTTP 403 for a non-captain. A withdrawn team loses its registration and therefore cannot submit challenge flags for that competition unless it registers again while registration remains open.


### Competition team capacity

Competition creation accepts optional `max_teams`, a positive integer that caps the number of registered teams. Omit it or set it to `null` for unlimited registration. When the configured capacity is reached, further registrations return HTTP 409 with a capacity error and do not create a registration. Capacity is checked while locking the competition row on databases that support row-level locks, so concurrent registrations are serialized on PostgreSQL. The database also retains the unique constraint preventing the same team from registering twice.


### Competition team-size eligibility

Competition creation may specify `min_team_size` and/or `max_team_size`, both positive integers. When both are set, the minimum must not exceed the maximum. The API checks the team's current membership count at registration time. Teams below the minimum or above the maximum receive HTTP 409 and are not registered. Leaving either bound unset disables that bound; leaving both unset preserves the existing behavior. These settings are independent of `max_teams`, which limits the total number of teams registered for a competition.


### Registered team roster locking

A team cannot add or remove members while it has a registration for a competition in `published` or `active` status. Join and leave requests return HTTP 409 and do not change membership. Captaincy transfer remains available because it does not change roster size. Membership changes become available again after the team withdraws its registration or the associated competition is completed or archived.
