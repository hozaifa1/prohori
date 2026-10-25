#!/usr/bin/env bash
# bash infra/cool_loop_down.sh <label>   terminate the loop instance, wait, append the ledger line, verify nothing is left
set -uo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
cd "$(dirname "$0")/.."; source infra/state.env; source "infra/.gen/loop_${1:?label}.env"; export AWS_REGION="$REGION"
LEDGER=eval/results/cool_agentloop/ledger.tsv
aws ec2 terminate-instances --instance-ids "$IID" >/dev/null 2>&1
aws ec2 wait instance-terminated --instance-ids "$IID" 2>/dev/null
t1=$(date -u +%FT%TZ)
hrs=$(T1="$t1" T0="$T_LAUNCH" python -c 'import os;from datetime import datetime as d;f="%Y-%m-%dT%H:%M:%SZ";print(round((d.strptime(os.environ["T1"],f)-d.strptime(os.environ["T0"],f)).total_seconds()/3600,3))' 2>/dev/null || echo "?")
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$LABEL" "$IID" "$ITYPE" "$AMI" "$T_LAUNCH" "$t1" "$hrs" >> "$LEDGER"
echo "terminated $IID ($hrs h)"
aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].State.Name' --output text
aws ec2 describe-instances --filters "Name=tag:Purpose,Values=cool-bench" "Name=instance-state-name,Values=pending,running,stopping,stopped" --query 'Reservations[].Instances[].[InstanceId,InstanceType,State.Name]' --output text
