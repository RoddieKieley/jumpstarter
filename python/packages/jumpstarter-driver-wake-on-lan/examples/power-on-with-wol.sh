#!/usr/bin/env bash
# Option C helper: power on, wait, then Wake-on-LAN.
# Run inside a Jumpstarter shell where both `j power` and `j wol` are available.
set -euo pipefail

WAIT="${WAIT:-5}"

echo "Powering on..."
j power on
echo "Waiting ${WAIT}s before Wake-on-LAN..."
sleep "${WAIT}"
echo "Sending Wake-on-LAN..."
j wol wake
echo "Done."
