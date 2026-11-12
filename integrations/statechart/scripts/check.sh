#!/usr/bin/env bash
# Smoke check: model-check the SCIM group-provisioning example under each policy, compare exit codes
# with the expected verdicts, and render each chart.
set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
example="${repo_root}/examples/group-provisioning"
work=$(mktemp -d)
trap 'rm -rf "${work}"' EXIT

declare -A expected=([none]=1 [checkBeforeUnassign]=1 [decoupleBeforeGrant]=1 [both]=0)
# Chart states drawn per policy; catches view.mjs labels drifting from the spec.
declare -A drawn=([none]=9 [checkBeforeUnassign]=9 [decoupleBeforeGrant]=9 [both]=7)
status=0
for policy in none checkBeforeUnassign decoupleBeforeGrant both; do
    set +e
    "${repo_root}/scripts/statechart" "${example}/GroupProvisioning.tla" \
        --config "${example}/${policy}.cfg" --view "${example}/view.mjs" \
        --out "${work}/${policy}" >/dev/null
    code=$?
    set -e
    if [[ "${code}" != "${expected[$policy]}" ]]; then
        echo "FAIL ${policy}: exit ${code}, expected ${expected[$policy]}"; status=1; continue
    fi
    [[ -s "${work}/${policy}/chart.mmd" ]] || { echo "FAIL ${policy}: no chart.mmd"; status=1; continue; }
    states=$(sed -n 's/.*The chart draws \([0-9]*\) states.*/\1/p' "${work}/${policy}/report.md")
    if [[ "${states}" != "${drawn[$policy]}" ]]; then
        echo "FAIL ${policy}: chart draws ${states} states, expected ${drawn[$policy]}"; status=1; continue
    fi
    node "${repo_root}/scripts/render.mjs" "${work}/${policy}/chart.mmd" >/dev/null
    grep -q "<svg" "${work}/${policy}/chart.svg" || { echo "FAIL ${policy}: bad SVG"; status=1; continue; }
    echo "ok   ${policy}: exit ${code}, $(sed -n 3p "${work}/${policy}/report.md")"
done
exit "${status}"
