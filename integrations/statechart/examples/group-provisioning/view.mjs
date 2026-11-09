export const title = "SCIM provisioning: group assignment vs. database role";

export const state = (v) => {
  if (v.lost) return "Role dropped, grants lost";
  const entra = v.assigned ? "Assigned" : "Unassigned";
  if (v.role === "absent") return `${entra}, no role`;
  if (v.owner === "admin") return `${entra}, admin owns role`;
  return `${entra}, SCIM owns role, ${v.privs ? "has grants" : "no grants"}`;
};

export const group = (v) =>
  v.lost ? "Grants lost"
  : v.role === "absent" ? "No role"
  : v.owner === "provisioner" && v.privs ? "SCIM can drop a role with grants"
  : "SCIM cannot drop grants";

export const colors = {
  "Grants lost": "pink",
  "No role": "tan",
  "SCIM can drop a role with grants": "orange",
  "SCIM cannot drop grants": "teal",
};

const words = {
  AdminUnassigns: "an admin unassigns the group",
  AdminAssigns: "an admin assigns the group",
  AdminRestartsProvisioning: "an admin restarts provisioning",
  InitialCycle: "a provisioning cycle creates the role",
  IncrementalCreates: "a provisioning cycle creates the role",
  IncrementalDrops: "an incremental cycle drops the role",
  TerraformGrants: "Terraform grants privileges",
  AdminMovesOwnershipOffScim: "an admin moves role ownership off SCIM",
};
export const step = (action, from) => (from.lost ? null : words[action] ?? action);
