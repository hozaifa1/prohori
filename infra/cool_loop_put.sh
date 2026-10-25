#!/usr/bin/env bash
# bash infra/cool_loop_put.sh <label> put <local> <remote>   |   get <remote> <local>   (scp -r)
set -uo pipefail
cd "$(dirname "$0")/.."; source infra/state.env; source "infra/.gen/loop_${1:?label}.env"; dir="$2"; a="$3"; b="$4"
O=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o LogLevel=ERROR)
if [ "$dir" = put ]; then scp -r "${O[@]}" "$a" "$USERNAME@$IP:$b"; else scp -r "${O[@]}" "$USERNAME@$IP:$a" "$b"; fi
