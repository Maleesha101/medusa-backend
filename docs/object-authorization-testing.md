# Object-level authorization regression tests

`tests/test_object_authorization.py` verifies that team membership mutations are scoped to the authenticated user using the current API contract.

Coverage:

- A user who is not a member cannot call `DELETE /api/v1/teams/{team_id}/leave` to remove another user's membership; the API returns `404`, and the original captain membership remains intact.
- A team member can leave their own membership; the membership is removed while the captain's membership remains.

Run locally:

```bash
pytest tests/test_object_authorization.py
```

## Current coverage boundary

The competition and challenge authoring endpoints currently use role-based authorization (`organizer` or `admin`) rather than consistently enforcing organization ownership. These tests intentionally do not assert an organization-ownership rule that the route implementation does not currently provide. A follow-up should define whether organizers are globally trusted or scoped to specific organizations, then implement and test that policy consistently for competition status changes, round creation, and challenge authoring. Public organization/team/competition catalog endpoints should also remain explicitly documented as public where intended.

These tests run in the existing isolated test environment. They are regression checks for the stated membership behavior, not a complete tenant-isolation audit or a substitute for a security review.
