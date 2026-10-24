# Organization-scoped organizer authorization

Organizers may administer only organizations they created. Platform admins retain global administrative access. Public organization and published competition catalog endpoints remain public according to their existing route contracts.

## Enforcement

- New organizations record `created_by_user_id` from the authenticated caller; clients cannot choose this value.
- Competition creation checks access to the target organization.
- Competition status changes and round creation check access to the competition's organization.
- Challenge creation, editing, publishing, archiving, and private flag configuration resolve the parent round and competition, then check access to its organization.
- Authorization is checked server-side before any mutation.

## Existing organizations and migration

Migration `20261024_0012` adds a nullable creator reference to preserve existing records. Existing organizations without a creator fail closed for organizer actions; only admins can manage them until ownership is assigned through a controlled administrative process. Do not infer ownership from user-supplied IDs or automatically assign all legacy organizations to an arbitrary organizer.

## Validation

`tests/test_organization_authorization.py` checks allowed same-organization operations and denied cross-organization competition creation, status changes, round creation, challenge editing, and private flag replacement. The flag test verifies a denied request leaves the stored digest unchanged. These are regression tests, not a complete security audit. Future organization transfer/delegation should use an explicit audited ownership or membership model rather than weakening this check.
