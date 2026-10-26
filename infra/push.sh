#!/usr/bin/env bash
# Ship the committed HEAD (or REF) to a Prohori instance and restart the service.
# Usage: bash infra/push.sh                      deploys to the live Elastic IP (state.env: the COOL box since cutover)
#        TARGET=<ip> bash infra/push.sh          deploys to one specific instance (e.g. the t4g or a not-yet-live box);
#        PUBLIC_HOST=<name> sets its PROHORI_PUBLIC_URL / health check name (default: the live sslip.io name).
# On a COOL box (its systemd unit points at /opt/cool) requirements are installed WITHOUT the opencv line, so
# `import cv2` stays COOL's; on the t4g the pip opencv wheel is installed as before.
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
AWS="${AWS:-aws}"
command -v "$AWS" >/dev/null || AWS="/c/Program Files/Amazon/AWSCLIV2/aws.exe"
cd "$(dirname "$0")/.."
source infra/state.env
export AWS_REGION="$REGION"
REF="${REF:-HEAD}"   # e.g. REF=demo-2026-10-21 to redeploy the demo build
SHA=$(git rev-parse --short "$REF^{commit}")
REL=$(date -u +%Y%m%d%H%M%S)-$SHA
TAR="infra/.gen/$REL.tgz"

# Only committed code ships: uncommitted work in progress never reaches the live endpoint.
git archive --format=tar.gz -o "$TAR" "$REF" src service models pyproject.toml
"$AWS" s3 cp "$TAR" "s3://$BUCKET/deploy/$REL.tgz" --only-show-errors

TARGET="${TARGET:-$EIP}"
PUBLIC_HOST="${PUBLIC_HOST:-$HOST}"
# the Elastic IP moves between instances, so host keys are not pinned (login is by key pair only)
SSH="ssh -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=15 ubuntu@$TARGET"
$SSH "sudo bash -s" <<EOF
set -euo pipefail
while [ ! -f /var/lib/cloud/prohori-bootstrap-done ]; do echo waiting for bootstrap; sleep 10; done
D=/opt/prohori/releases/$REL
mkdir -p \$D
aws s3 cp s3://$BUCKET/deploy/$REL.tgz /tmp/$REL.tgz --only-show-errors
tar -xzf /tmp/$REL.tgz -C \$D && rm /tmp/$REL.tgz
if grep -q /opt/cool /etc/systemd/system/prohori.service; then
  grep -vi '^opencv' \$D/service/requirements.txt > /tmp/requirements.nocv.txt   # COOL provides cv2
  /opt/prohori/venv/bin/pip install -q -r /tmp/requirements.nocv.txt
  /opt/prohori/venv/bin/pip uninstall -y -q opencv-contrib-python-headless opencv-python-headless opencv-python 2>/dev/null || true
else
  /opt/prohori/venv/bin/pip install -q -r \$D/service/requirements.txt
fi
setenv() { sed -i "/^\$1=/d" /etc/prohori.env; echo "\$1=\$2" >> /etc/prohori.env; }
setenv PROHORI_VERSION $SHA
setenv PROHORI_SNS_TOPIC_ARN "${TOPIC:-}"
setenv PROHORI_PUBLIC_URL https://$PUBLIC_HOST
chown -R prohori:prohori /opt/prohori
ln -sfn \$D /opt/prohori/current
systemctl restart prohori
ls -1dt /opt/prohori/releases/* | tail -n +6 | xargs -r rm -rf
for i in \$(seq 1 30); do curl -sf http://127.0.0.1:8000/health && exit 0; sleep 1; done
journalctl -u prohori -n 40 --no-pager; exit 1
EOF
echo
curl -s --max-time 20 "https://$PUBLIC_HOST/health" && echo && echo "deployed $SHA to $TARGET: https://$PUBLIC_HOST"
