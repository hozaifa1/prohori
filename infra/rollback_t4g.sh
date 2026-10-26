#!/usr/bin/env bash
# One-command rollback: serve the live endpoint from the original t4g.small again (stock pip OpenCV 5.0.0).
#   bash infra/rollback_t4g.sh
# Starts the stopped t4g (IID_T4G in infra/state.env), moves the Elastic IP back to it (same URL, no DNS change; the
# t4g's Caddy still holds its Let's Encrypt certificate for the sslip.io name), checks /health and one measure, deploys
# the current HEAD to it (SYNC=0 to skip; the t4g only misses pushes made after the cutover), then STOPS the COOL box
# (KEEP_COOL=1 leaves it running).  Nothing is ever terminated.
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
AWS="${AWS:-aws}"
command -v "$AWS" >/dev/null || AWS="/c/Program Files/Amazon/AWSCLIV2/aws.exe"
cd "$(dirname "$0")/.."
source infra/state.env
export AWS_REGION="$REGION"
T4G="${IID_T4G:?IID_T4G missing in infra/state.env}"
setstate() { { grep -v "^$1=" infra/state.env || true; echo "$1=$2"; } > infra/.gen/state.tmp; cp infra/.gen/state.tmp infra/state.env; }
mkdir -p infra/.gen

echo "== start t4g $T4G"
"$AWS" ec2 start-instances --instance-ids "$T4G" >/dev/null
"$AWS" ec2 wait instance-running --instance-ids "$T4G"
echo "== Elastic IP $EIP -> $T4G"
ALLOC=$("$AWS" ec2 describe-addresses --public-ips "$EIP" --query 'Addresses[0].AllocationId' --output text)
"$AWS" ec2 associate-address --allocation-id "$ALLOC" --instance-id "$T4G" --allow-reassociation >/dev/null
setstate IID "$T4G"
echo "== wait for https://$HOST/health from the t4g"
ok=0
for i in $(seq 1 60); do
  if curl -sf --max-time 15 "https://$HOST/health" > infra/.gen/health_rollback.json 2>/dev/null; then ok=1; break; fi; sleep 5
done
[ $ok = 1 ] || { echo "t4g did not answer on https://$HOST (check: ssh ubuntu@$EIP, systemctl status prohori caddy)"; exit 1; }
cat infra/.gen/health_rollback.json; echo
curl -s --max-time 120 -F "image=@service/static/samples/good-straight.jpg" "https://$HOST/api/measure" \
  | python -c "import json,sys; d=json.load(sys.stdin); m=d['measurement']; print('measure ok: cracks', len(m['cracks']), 'gate', m['gate']['tier'])"
if [ "${SYNC:-1}" = 1 ]; then echo "== deploy HEAD to the t4g"; bash infra/push.sh; fi
if [ "${KEEP_COOL:-0}" != 1 ] && [ -n "${COOL_IID:-}" ]; then
  echo "== stopping COOL box $COOL_IID (not terminated)"
  "$AWS" ec2 stop-instances --instance-ids "$COOL_IID" --query 'StoppingInstances[0].CurrentState.Name' --output text
fi
echo "rolled back: https://$HOST is served by the t4g $T4G"
