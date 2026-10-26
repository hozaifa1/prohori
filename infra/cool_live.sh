#!/usr/bin/env bash
# Serve the live judge endpoint from COOL (Cloud Optimized OpenCV, AWS Marketplace) on Graviton4, same URL, one-command
# rollback (infra/rollback_t4g.sh).  Idempotent: every step checks what already exists.
#
#   bash infra/cool_live.sh up        launch a c8g.large from the COOL AMI (role prohori-ec2, SG, key, gp3 encrypted,
#                                     tag Name=prohori-cool-live), bootstrap it (infra/bootstrap_cool.sh), copy the
#                                     service env from the running t4g, deploy HEAD (infra/push.sh TARGET=...), print
#                                     the cv2 build summary.  The new box answers on its own temporary public IP
#                                     (https://<ip-with-dashes>.sslip.io); the Elastic IP is NOT touched.
#   bash infra/cool_live.sh verify    POST every service/static/samples image to the live endpoint and to the new box,
#                                     compare gate tier and widths (tolerance 0.005 mm), infra/cool_compare.py.
#   bash infra/cool_live.sh cutover   move the Elastic IP to the COOL box, point Caddy at the live sslip.io name (it gets
#                                     its Let's Encrypt certificate), verify /health + one measure end to end, then STOP
#                                     (never terminate) the t4g.  Rolls back by itself if the verification fails.
#
# Env: COOL_AMI (default: Graviton4 COOL v3), COOL_TYPE (c8g.large; only c8g.large/xlarge/2xlarge are allowed),
#      COOL_THREADS (PROHORI_THREADS for the service; default 2 = the vCPUs of a c8g.large).
# Needs: AWS CLI logged in (aws login), infra/up.sh already run (role, SG, key, EIP), SSH allowed from your /24.
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
AWS="${AWS:-aws}"
command -v "$AWS" >/dev/null || AWS="/c/Program Files/Amazon/AWSCLIV2/aws.exe"
cd "$(dirname "$0")/.."
source infra/state.env
export AWS_REGION="$REGION"
AMI="${COOL_AMI:-ami-033e481a24f94c8cb}"
ITYPE="${COOL_TYPE:-c8g.large}"
THREADS="${COOL_THREADS:-2}"
ROLE=prohori-ec2
T4G_IID="${IID_T4G:-$IID}"      # the original t4g.small: the rollback target, never terminated
SSHO=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o ServerAliveInterval=30 -o LogLevel=ERROR)
case "$ITYPE" in c8g.large|c8g.xlarge|c8g.2xlarge) ;; *) echo "refusing instance type $ITYPE (cost cap)"; exit 2;; esac
mkdir -p infra/.gen

setstate() {   # setstate KEY VALUE : upsert a line in infra/state.env
  { grep -v "^$1=" infra/state.env || true; echo "$1=$2"; } > infra/.gen/state.tmp; cp infra/.gen/state.tmp infra/state.env
}
ssh_to() { local h="$1"; shift; ssh "${SSHO[@]}" "ubuntu@$h" "$@"; }
public_ip() { "$AWS" ec2 describe-instances --instance-ids "$1" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text; }
dashed() { echo "$1" | tr . -; }
find_cool() {
  "$AWS" ec2 describe-instances --filters Name=tag:Name,Values=prohori-cool-live \
    Name=instance-state-name,Values=pending,running,stopped,stopping \
    --query 'Reservations[0].Instances[0].InstanceId' --output text
}

# ---------------------------------------------------------------------------------------------------------- up
cmd_up() {
  local cid; cid=$(find_cool)
  echo "== instance ($ITYPE from $AMI)"
  if [ "$cid" = None ]; then
    sed -e "s/__BUCKET__/$BUCKET/g" -e "s/__TABLE__/$TABLE/g" -e "s/__REGION__/$REGION/g" -e "s/__THREADS__/$THREADS/g" \
      infra/bootstrap_cool.sh > infra/.gen/userdata_cool.sh
    cid=$("$AWS" ec2 run-instances --image-id "$AMI" --instance-type "$ITYPE" --key-name prohori-key \
      --security-group-ids "$SG" --iam-instance-profile Name="$ROLE" --count 1 \
      --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
      --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=60,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
      --user-data file://infra/.gen/userdata_cool.sh \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=prohori-cool-live},{Key=Project,Value=prohori},{Key=Purpose,Value=live-cool}]" \
                           "ResourceType=volume,Tags=[{Key=Project,Value=prohori},{Key=Purpose,Value=live-cool}]" \
      --query 'Instances[0].InstanceId' --output text)
  fi
  echo "   $cid"; setstate COOL_IID "$cid"; setstate IID_T4G "$T4G_IID"
  "$AWS" ec2 start-instances --instance-ids "$cid" >/dev/null 2>&1 || true
  "$AWS" ec2 wait instance-running --instance-ids "$cid"
  local ip; ip=$(public_ip "$cid")
  [ "$ip" != None ] || ip=$EIP     # Elastic IP already moved (re-run after cutover)
  echo "   public IP $ip"; [ "$ip" = "$EIP" ] || setstate COOL_IP "$ip"
  for i in $(seq 1 60); do ssh_to "$ip" 'test -f /var/lib/cloud/prohori-bootstrap-done' 2>/dev/null && break; sleep 10; done
  ssh_to "$ip" 'test -f /var/lib/cloud/prohori-bootstrap-done' || { echo "bootstrap did not finish"; exit 4; }

  echo "== service env: copied from the running t4g (PROHORI_*, Bedrock model, table/bucket, SNS topic, LLM cap)"
  local src; src=$(public_ip "$T4G_IID")
  : > infra/.gen/prohori.env.t4g
  if [ "$src" != None ] && ssh_to "$src" 'test -r /etc/prohori.env' 2>/dev/null; then
    ssh_to "$src" 'cat /etc/prohori.env' > infra/.gen/prohori.env.t4g
  else
    echo "   t4g unreachable: keeping the defaults from bootstrap_cool.sh (+ SNS topic)"
  fi
  scp "${SSHO[@]}" infra/.gen/prohori.env.t4g "ubuntu@$ip:/tmp/prohori.env.t4g" >/dev/null
  ssh_to "$ip" "sudo bash -s" <<REMOTE
set -euo pipefail
setenv() { sed -i "/^\$1=/d" /etc/prohori.env; echo "\$1=\$2" >> /etc/prohori.env; }
while IFS='=' read -r k v; do [ -n "\$k" ] && setenv "\$k" "\$v"; done < /tmp/prohori.env.t4g
setenv PROHORI_THREADS $THREADS
setenv PROHORI_SNS_TOPIC_ARN "${TOPIC:-}"
rm -f /tmp/prohori.env.t4g
REMOTE

  echo "== deploy HEAD (push.sh; on a COOL box it installs requirements WITHOUT the opencv line)"
  TARGET="$ip" PUBLIC_HOST="$(dashed "$ip").sslip.io" bash infra/push.sh

  echo "== which cv2 does the service import?"
  ssh_to "$ip" "sudo -u prohori env PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12 LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib /opt/prohori/venv/bin/python -" <<'PY' | tee infra/.gen/cool_cv2_summary.txt
import cv2, numpy
b = cv2.getBuildInformation()
print('cv2', cv2.__version__, cv2.__file__)
print('numpy', numpy.__version__, 'threads', cv2.getNumThreads(), 'cpus', cv2.getNumberOfCPUs())
print(cv2.getCPUFeaturesLine())
for l in b.splitlines():
    if any(k in l for k in ('Version control', 'Build type', 'C++ flags (Release)', 'HAL', 'Parallel framework', 'JPEG', 'Platform:', 'timestamp')):
        print(l.strip())
PY
  echo "== up: https://$(dashed "$ip").sslip.io   (instance $cid, Elastic IP untouched)"
}

# ------------------------------------------------------------------------------------------------------- verify
cmd_verify() {
  local ip="${COOL_IP:?run 'up' first}"
  local new="https://$(dashed "$ip").sslip.io" old="https://$HOST"
  echo "== /health new: $new"; curl -s --max-time 30 "$new/health"; echo
  echo "== /health old: $old"; curl -s --max-time 30 "$old/health"; echo
  python infra/cool_compare.py "$old" "$new"
}

# ------------------------------------------------------------------------------------------------------ cutover
cmd_cutover() {
  local cid; cid=$(find_cool); [ "$cid" != None ] || { echo "no COOL instance: run 'up'"; exit 1; }
  local alloc cur
  alloc=$("$AWS" ec2 describe-addresses --public-ips "$EIP" --query 'Addresses[0].AllocationId' --output text)
  cur=$("$AWS" ec2 describe-addresses --public-ips "$EIP" --query 'Addresses[0].InstanceId' --output text)
  if [ "$cur" != "$cid" ]; then
    echo "== moving Elastic IP $EIP: $cur -> $cid"
    "$AWS" ec2 associate-address --allocation-id "$alloc" --instance-id "$cid" --allow-reassociation >/dev/null
  fi
  setstate IID "$cid"
  echo "== Caddy -> $HOST (the certificate is requested now that the name resolves to this box)"
  for i in $(seq 1 30); do ssh_to "$EIP" true 2>/dev/null && break; sleep 4; done
  ssh_to "$EIP" "sudo bash -s" <<REMOTE
set -euo pipefail
sed -i "s|^PROHORI_PUBLIC_URL=.*|PROHORI_PUBLIC_URL=https://$HOST|" /etc/prohori.env
cat > /etc/caddy/Caddyfile <<'CF'
$HOST {
	encode gzip
	request_body {
		max_size 20MB
	}
	reverse_proxy 127.0.0.1:8000
}
CF
systemctl restart prohori
systemctl reload caddy || systemctl restart caddy
REMOTE
  local ok=0
  for i in $(seq 1 30); do
    if curl -sf --max-time 15 "https://$HOST/health" > infra/.gen/health_live.json 2>/dev/null; then ok=1; break; fi; sleep 5
  done
  if [ $ok = 1 ] && grep -q '"cool": *true' infra/.gen/health_live.json; then
    echo "== live health:"; cat infra/.gen/health_live.json; echo
    if curl -s --max-time 120 -F "image=@service/static/samples/good-straight.jpg" "https://$HOST/api/measure" \
       | python -c "import json,sys; d=json.load(sys.stdin); m=d['measurement']; print('measure ok: cracks', len(m['cracks']), 'gate', m['gate']['tier'], 'session', d['session_id'])"; then
      echo "== stopping t4g $T4G_IID (rollback target; never terminated)"
      "$AWS" ec2 stop-instances --instance-ids "$T4G_IID" --query 'StoppingInstances[0].CurrentState.Name' --output text
      return 0
    fi
  fi
  echo "CUTOVER FAILED: rolling back"; bash infra/rollback_t4g.sh; exit 1
}

case "${1:-up}" in up) cmd_up;; verify) cmd_verify;; cutover) cmd_cutover;; *) echo "usage: $0 up|verify|cutover"; exit 2;; esac
