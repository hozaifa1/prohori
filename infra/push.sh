#!/usr/bin/env bash
# Ship the current working tree to the Prohori instance and restart the service.
# Usage: bash infra/push.sh   (after infra/up.sh)
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
AWS="${AWS:-aws}"
command -v "$AWS" >/dev/null || AWS="/c/Program Files/Amazon/AWSCLIV2/aws.exe"
cd "$(dirname "$0")/.."
source infra/state.env
export AWS_REGION="$REGION"
SHA=$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- src service || echo -dirty)
REL=$(date -u +%Y%m%d%H%M%S)-$SHA
TAR="infra/.gen/$REL.tgz"

# Tracked + new (non-ignored) files under the runtime dirs only.
git ls-files -co --exclude-standard src service models pyproject.toml | tar -czf "$TAR" -T -
"$AWS" s3 cp "$TAR" "s3://$BUCKET/deploy/$REL.tgz" --only-show-errors

SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 ubuntu@$EIP"
$SSH "sudo bash -s" <<EOF
set -euo pipefail
while [ ! -f /var/lib/cloud/prohori-bootstrap-done ]; do echo waiting for bootstrap; sleep 10; done
D=/opt/prohori/releases/$REL
mkdir -p \$D
aws s3 cp s3://$BUCKET/deploy/$REL.tgz /tmp/$REL.tgz --only-show-errors
tar -xzf /tmp/$REL.tgz -C \$D && rm /tmp/$REL.tgz
/opt/prohori/venv/bin/pip install -q -r \$D/service/requirements.txt
setenv() { sed -i "/^\$1=/d" /etc/prohori.env; echo "\$1=\$2" >> /etc/prohori.env; }
setenv PROHORI_VERSION $SHA
setenv PROHORI_SNS_TOPIC_ARN "${TOPIC:-}"
setenv PROHORI_PUBLIC_URL https://$HOST
chown -R prohori:prohori /opt/prohori
ln -sfn \$D /opt/prohori/current
systemctl restart prohori
ls -1dt /opt/prohori/releases/* | tail -n +6 | xargs -r rm -rf
for i in \$(seq 1 30); do curl -sf http://127.0.0.1:8000/health && exit 0; sleep 1; done
journalctl -u prohori -n 40 --no-pager; exit 1
EOF
echo
curl -s --max-time 20 "https://$HOST/health" && echo && echo "live: https://$HOST"
