#!/usr/bin/env bash
# bash infra/cool_loop_ssh.sh <label> <command...>   run a command on the loop instance
set -uo pipefail
cd "$(dirname "$0")/.."; source infra/state.env; source "infra/.gen/loop_${1:?label}.env"; shift
exec ssh -i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o ServerAliveInterval=30 -o LogLevel=ERROR "$USERNAME@$IP" "$@"
