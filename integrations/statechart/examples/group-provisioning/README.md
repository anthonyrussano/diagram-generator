# SCIM group provisioning: group assignment vs. database role

Models one identity-provider group assigned to an app, and the database role that
SCIM provisions for it. Many SCIM connectors send `DELETE /Groups` when a group is
unassigned, and the target system drops the role together with every grant on it.

The model starts from either of two states: an existing group (assigned, role exists,
holds grants, owned by the SCIM provisioner) or a new group (not assigned, no role).

Rule: **NoGrantsLost**, meaning SCIM never drops a role while it still holds
privileges or owns objects.

| Config | Policy | Expected | Shortest bug path |
|---|---|---|---|
| `none.cfg` | No safeguards | breaks (exit 1) | admin unassigns → incremental cycle drops role |
| `checkBeforeUnassign.cfg` | Unassign only when SCIM cannot drop grants | breaks (exit 1) | assign → cycle creates role → unassign (no grants yet) → Terraform grants → cycle drops role |
| `decoupleBeforeGrant.cfg` | Terraform grants only after ownership moves off SCIM | breaks (exit 1) | Same as `none`: existing roles already hold grants |
| `both.cfg` | Both policies | holds (exit 0) | n/a |

The second row is the interesting one: a check done when the group is unassigned
does not cover a grant that arrives before the next provisioning cycle.

Assumptions:

- SCIM can drop only a role it owns.
- The initial cycle after a restart ignores earlier unassignments; the next
  incremental cycle processes them.
- User provisioning, partial grants, and Terraform recreating a dropped role are left out.

Run:

```bash
../../scripts/statechart GroupProvisioning.tla --config none.cfg --view view.mjs --out ../../output/group-provisioning/out-none
```
