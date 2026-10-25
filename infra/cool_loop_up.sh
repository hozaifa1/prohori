#!/usr/bin/env bash
# COOL developer-agent loop: launch ONE c8g instance from the COOL AMI and leave it running for an interactive loop
# (infra/cool_loop_ssh.sh / cool_loop_put.sh), then infra/cool_loop_down.sh terminates it.  Same guards as cool_session.sh:
# tagged Project=prohori Purpose=cool-bench, instance-initiated shutdown = terminate, `shutdown -h +MAXMIN` timer
# (user data and ssh), only c8g.large/xlarge/2xlarge, launch/terminate appended to eval/results/cool_agentloop/ledger.tsv.
#
#   bash infra/cool_loop_up.sh <label> <c8g.xlarge> [max-minutes]
# Writes infra/.gen/loop_<label>.env (IID, IP, USERNAME, T_LAUNCH, ITYPE).
set -uo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
LABEL="${1:?label}"; ITYPE="${2:?type}"; MAXMIN="${3:-150}"
AMI="${COOL_AMI:-ami-033e481a24f94c8cb}"
cd "$(dirname "$0")/.."
source infra/state.env
export AWS_REGION="$REGION"
case "$ITYPE" in c8g.large|c8g.xlarge|c8g.2xlarge) ;; *) echo "refusing instance type $ITYPE (cost cap)"; exit 2;; esac
mkdir -p infra/.gen eval/results/cool_agentloop
LEDGER=eval/results/cool_agentloop/ledger.tsv
[ -f "$LEDGER" ] || printf 'label\tinstance_id\ttype\tami\tlaunch_utc\tterminate_utc\tapprox_hours\n' > "$LEDGER"
SSHO=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o ServerAliveInterval=30 -o LogLevel=ERROR)
UD=infra/.gen/loop_userdata.sh
printf '#!/bin/bash\nshutdown -h +%s\n' "$MAXMIN" > "$UD"
T_LAUNCH=$(date -u +%FT%TZ)
IID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$ITYPE" --key-name prohori-key \
  --security-group-ids "$SG" --count 1 --instance-initiated-shutdown-behavior terminate \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2 \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=60,VolumeType=gp3,DeleteOnTermination=true}' \
  --user-data "file://$UD" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=prohori-coolloop-$LABEL},{Key=Project,Value=prohori},{Key=Purpose,Value=cool-bench}]" "ResourceType=volume,Tags=[{Key=Project,Value=prohori},{Key=Purpose,Value=cool-bench}]" \
  --query 'Instances[0].InstanceId' --output text) || { echo "run-instances failed"; exit 3; }
echo "instance $IID launched $T_LAUNCH"
# record immediately so a crash of this script cannot lose the id
printf 'IID=%s\nIP=\nUSERNAME=\nT_LAUNCH=%s\nITYPE=%s\nLABEL=%s\nAMI=%s\n' "$IID" "$T_LAUNCH" "$ITYPE" "$LABEL" "$AMI" > "infra/.gen/loop_$LABEL.env"
aws ec2 wait instance-running --instance-ids "$IID"
IP=$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
USERNAME=""
for i in $(seq 1 40); do
  for u in ubuntu ec2-user; do
    if ssh "${SSHO[@]}" "$u@$IP" true 2>/dev/null; then USERNAME=$u; break 2; fi
  done
  sleep 8
done
[ -n "$USERNAME" ] || { echo "ssh never came up (instance $IID still running: run cool_loop_down.sh $LABEL)"; exit 4; }
ssh "${SSHO[@]}" "$USERNAME@$IP" "sudo shutdown -h +$MAXMIN >/dev/null 2>&1 || true"
printf 'IID=%s\nIP=%s\nUSERNAME=%s\nT_LAUNCH=%s\nITYPE=%s\nLABEL=%s\nAMI=%s\n' "$IID" "$IP" "$USERNAME" "$T_LAUNCH" "$ITYPE" "$LABEL" "$AMI" > "infra/.gen/loop_$LABEL.env"
echo "up: $IID $IP $USERNAME"
