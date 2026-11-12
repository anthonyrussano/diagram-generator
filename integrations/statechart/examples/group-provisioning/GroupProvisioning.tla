---- MODULE GroupProvisioning ----
\* One identity-provider group assigned to an app, and the database role that SCIM provisions for it.
CONSTANT Policy   \* "none" | "checkBeforeUnassign" | "decoupleBeforeGrant" | "both"

CheckUnassign == Policy \in {"checkBeforeUnassign", "both"}
DecoupleGrant == Policy \in {"decoupleBeforeGrant", "both"}

VARIABLES assigned, role, privs, owner, cycle, lost
vars == <<assigned, role, privs, owner, cycle, lost>>

Init ==
  /\ cycle = "incremental" /\ lost = FALSE
  /\ \/ \* an existing group: assigned, role exists, holds grants, owned by the SCIM provisioner
        /\ assigned = TRUE /\ role = "present" /\ privs = TRUE /\ owner = "provisioner"
     \/ \* a brand new group: not assigned yet, no role
        /\ assigned = FALSE /\ role = "absent" /\ privs = FALSE /\ owner = "none"

SafeToUnassign == role = "absent" \/ owner = "admin" \/ ~privs

AdminUnassigns ==
  /\ assigned
  /\ CheckUnassign => SafeToUnassign
  /\ assigned' = FALSE
  /\ UNCHANGED <<role, privs, owner, cycle, lost>>

AdminAssigns ==
  /\ ~assigned /\ assigned' = TRUE
  /\ UNCHANGED <<role, privs, owner, cycle, lost>>

AdminRestartsProvisioning ==
  /\ cycle = "incremental" /\ cycle' = "initial"
  /\ UNCHANGED <<assigned, role, privs, owner, lost>>

\* The initial cycle after a restart creates roles for assigned groups but ignores earlier unassignments.
InitialCycle ==
  /\ cycle = "initial" /\ cycle' = "incremental"
  /\ IF assigned /\ role = "absent"
       THEN role' = "present" /\ owner' = "provisioner"
       ELSE UNCHANGED <<role, owner>>
  /\ UNCHANGED <<assigned, privs, lost>>

IncrementalCreates ==
  /\ cycle = "incremental" /\ assigned /\ role = "absent"
  /\ role' = "present" /\ owner' = "provisioner"
  /\ UNCHANGED <<assigned, privs, cycle, lost>>

\* DELETE /Groups drops the role. SCIM can drop only a role it owns.
IncrementalDrops ==
  /\ cycle = "incremental" /\ ~assigned /\ role = "present" /\ owner = "provisioner"
  /\ role' = "absent" /\ owner' = "none" /\ privs' = FALSE
  /\ lost' = (lost \/ privs)
  /\ UNCHANGED <<assigned, cycle>>

TerraformGrants ==
  /\ role = "present" /\ ~privs
  /\ DecoupleGrant => owner = "admin"
  /\ privs' = TRUE
  /\ UNCHANGED <<assigned, role, owner, cycle, lost>>

AdminMovesOwnershipOffScim ==
  /\ role = "present" /\ owner = "provisioner" /\ owner' = "admin"
  /\ UNCHANGED <<assigned, role, privs, cycle, lost>>

Next ==
  \/ AdminUnassigns \/ AdminAssigns \/ AdminRestartsProvisioning \/ InitialCycle
  \/ IncrementalCreates \/ IncrementalDrops \/ TerraformGrants \/ AdminMovesOwnershipOffScim

Spec == Init /\ [][Next]_vars

\* Rule the reader agrees to: SCIM never drops a role while it still holds privileges or owns objects.
NoGrantsLost == ~lost
====
