#!/usr/bin/env bash
# One COOL benchmark session: launch ONE c8g instance, ship the bundle + inputs, run infra/cool_remote.sh on it under
# nohup, poll, pull the results, terminate.  Cost guards: the instance is tagged Project=prohori Purpose=cool-bench,
# launched with --instance-initiated-shutdown-behavior terminate and a `shutdown -h +180` timer (user data and ssh),
# and a trap terminates it when this script exits for any reason.
#
# Usage (repo root, AWS CLI logged in):
#   bash infra/cool_session.sh <label> <ami-id> <instance-type> <main|sweep> <local-out-dir> [max-minutes]
# Needs: infra/state.env (SG, KEY), inputs staged in $COOL_INPUTS (default ~/prohori_data/cool_stage with raw/ samples/
# synth/ sub-dirs; see research/COOL_NOTES.md), the AWS key pair prohori-key, and a security-group rule allowing your
# IP on tcp/22.
set -uo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
AWS="${AWS:-aws}"
LABEL="${1:?label}"; AMI="${2:?ami}"; ITYPE="${3:?type}"; MODE="${4:?main|sweep}"; OUT="${5:?out dir}"; MAXMIN="${6:-150}"
cd "$(dirname "$0")/.."
source infra/state.env
export AWS_REGION="$REGION"
case "$ITYPE" in c8g.large|c8g.xlarge|c8g.2xlarge) ;; *) echo "refusing instance type $ITYPE (cost cap)"; exit 2;; esac
INPUTS="${COOL_INPUTS:-$HOME/prohori_data/cool_stage}"
mkdir -p "$OUT" infra/.gen
LEDGER=eval/results/cool/ledger.tsv
[ -f "$LEDGER" ] || printf 'label\tinstance_id\ttype\tami\tlaunch_utc\tterminate_utc\tapprox_hours\n' > "$LEDGER"
IID=""; T_LAUNCH=""
SSHO=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o ServerAliveInterval=30 -o LogLevel=ERROR)
terminate() {
  [ -n "$IID" ] || return 0
  echo "== terminating $IID"
  "$AWS" ec2 terminate-instances --instance-ids "$IID" >/dev/null 2>&1
  "$AWS" ec2 wait instance-terminated --instance-ids "$IID" 2>/dev/null
  t1=$(date -u +%FT%TZ)
  hrs=$(T1="$t1" T0="$T_LAUNCH" python -c 'import os;from datetime import datetime as d;f="%Y-%m-%dT%H:%M:%SZ";print(round((d.strptime(os.environ["T1"],f)-d.strptime(os.environ["T0"],f)).total_seconds()/3600,3))' 2>/dev/null || echo "?")
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$LABEL" "$IID" "$ITYPE" "$AMI" "$T_LAUNCH" "$t1" "$hrs" >> "$LEDGER"
  IID=""
}
trap terminate EXIT
trap 'exit 130' INT TERM

echo "== bundle"
BUNDLE=infra/.gen/cool_bundle.tgz
tar -czf "$BUNDLE" --exclude=__pycache__ src/prohori data/print/test_panel_ground_truth.json eval/cool_*.py infra/cool_*.sh infra/build_opencv_ref.sh
INTAR="infra/.gen/cool_inputs_$(basename "$INPUTS").tar"
if [ "$MODE" = inspect ]; then   # verification only: no benchmark inputs needed
  mkdir -p infra/.gen/empty/raw infra/.gen/empty/samples infra/.gen/empty/synth; INTAR=infra/.gen/cool_empty.tar
  tar -cf "$INTAR" -C infra/.gen/empty raw samples synth
else
  [ -f "$INTAR" ] && [ "$INTAR" -nt "$INPUTS/raw" ] || tar -cf "$INTAR" -C "$INPUTS" raw samples synth
fi
ls -la "$BUNDLE" "$INTAR"

echo "== launch $ITYPE from $AMI"
UD=infra/.gen/cool_userdata.sh
printf '#!/bin/bash\nshutdown -h +180\n' > "$UD"
T_LAUNCH=$(date -u +%FT%TZ)
IID=$("$AWS" ec2 run-instances --image-id "$AMI" --instance-type "$ITYPE" --key-name prohori-key \
  --security-group-ids "$SG" --count 1 \
  --instance-initiated-shutdown-behavior terminate \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2 \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=60,VolumeType=gp3,DeleteOnTermination=true}' \
  --user-data "file://$UD" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=prohori-cool-$LABEL},{Key=Project,Value=prohori},{Key=Purpose,Value=cool-bench}]" "ResourceType=volume,Tags=[{Key=Project,Value=prohori},{Key=Purpose,Value=cool-bench}]" \
  --query 'Instances[0].InstanceId' --output text) || { echo "run-instances failed"; IID=""; exit 3; }
echo "instance $IID"
"$AWS" ec2 wait instance-running --instance-ids "$IID"
IP=$("$AWS" ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "ip $IP"
USERNAME=""
for i in $(seq 1 40); do
  for u in ubuntu ec2-user; do
    if ssh "${SSHO[@]}" "$u@$IP" true 2>/dev/null; then USERNAME=$u; break 2; fi
  done
  sleep 8
done
[ -n "$USERNAME" ] || { echo "ssh never came up"; exit 4; }
echo "ssh user $USERNAME"
SSH=(ssh "${SSHO[@]}" "$USERNAME@$IP")
"${SSH[@]}" 'sudo shutdown -h +180 >/dev/null 2>&1 || true'   # belt and braces (also in user data)
scp "${SSHO[@]}" "$BUNDLE" "$INTAR" "$USERNAME@$IP:/tmp/" >/dev/null || { echo "scp failed"; exit 5; }
"${SSH[@]}" "mkdir -p ~/prohori ~/inputs && tar -xzf /tmp/cool_bundle.tgz -C ~/prohori && tar -xf /tmp/$(basename "$INTAR") -C ~/inputs && ls ~/inputs/*/ | wc -l"
"${SSH[@]}" "nohup bash ~/prohori/infra/cool_remote.sh $MODE > ~/remote.out 2>&1 &" 
echo "== remote started $(date -u +%T); polling (max $MAXMIN min)"
deadline=$(( $(date +%s) + MAXMIN * 60 ))
while true; do
  sleep 60
  st=$("${SSH[@]}" 'if [ -f ~/DONE ]; then echo DONE; elif [ -f ~/FAILED ]; then echo FAILED; else echo RUNNING; fi; tail -n 2 ~/results/remote.log 2>/dev/null | cut -c1-200' 2>/dev/null) || st="SSHFAIL"
  echo "[$(date -u +%T)] $(echo "$st" | tr '\n' '|')"
  case "$st" in DONE*|FAILED*) break;; esac
  [ "$(date +%s)" -gt "$deadline" ] && { echo "deadline reached"; break; }
done
echo "== pull results"
scp -r "${SSHO[@]}" "$USERNAME@$IP:~/results/." "$OUT/" >/dev/null 2>&1 || echo "scp pull had errors"
scp "${SSHO[@]}" "$USERNAME@$IP:~/remote.out" "$OUT/remote.out" >/dev/null 2>&1 || true
ls "$OUT"
echo "$IID $IP $ITYPE $AMI" > "$OUT/instance.txt"
terminate
echo "== session end"
