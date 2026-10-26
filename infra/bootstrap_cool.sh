#!/bin/bash
# EC2 user-data for the COOL-on-Graviton4 Prohori endpoint (COOL AMI = Ubuntu 24.04 arm64 + OpenCV 5.1-dev in /opt/cool).
# Same layout as infra/bootstrap.sh (user prohori, /opt/prohori/{venv,releases,current,data}, /etc/prohori.env,
# systemd unit prohori, Caddy), with ONE difference: OpenCV is COOL's, not the pip wheel.  COOL's cv2 is not installed
# in any venv; the AMI's own activate script exports PYTHONPATH + LD_LIBRARY_PATH, and the unit exports the same two
# variables, so `import cv2` in the service resolves to /opt/cool/python_3.12/site-packages/cv2/python-3.12.
# infra/push.sh sees /opt/cool in the unit and installs service/requirements.txt WITHOUT the opencv line.
# Placeholders are filled by infra/cool_live.sh.  Caddy starts on this box's own temporary <public-ip>.sslip.io name so
# the box can be tested over HTTPS before the Elastic IP moves; cool_live.sh switches it to the live name at cutover.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab || true
apt-get update
apt-get install -y python3-venv python3-pip caddy unzip curl
if ! command -v aws >/dev/null; then snap install aws-cli --classic || {
  curl -s https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip -o /tmp/awscli.zip && unzip -q /tmp/awscli.zip -d /tmp && /tmp/aws/install; }; fi

useradd --system --create-home --home-dir /opt/prohori --shell /usr/sbin/nologin prohori || true
mkdir -p /opt/prohori/releases /opt/prohori/data
python3 -m venv /opt/prohori/venv
/opt/prohori/venv/bin/pip install --upgrade pip

cat > /etc/prohori.env <<'ENVEOF'
PROHORI_AWS_REGION=__REGION__
AWS_REGION=__REGION__
PROHORI_DDB_TABLE=__TABLE__
PROHORI_S3_BUCKET=__BUCKET__
PROHORI_DATA_DIR=/opt/prohori/data
PROHORI_DEFAULT_POLICY=rules
PROHORI_LLM_DAILY_CAP=200
PROHORI_BEDROCK_MODEL=us.amazon.nova-lite-v1:0
PROHORI_BEDROCK_FALLBACK_MODELS=us.amazon.nova-micro-v1:0
PROHORI_THREADS=__THREADS__
ENVEOF

cat > /etc/systemd/system/prohori.service <<'UNITEOF'
[Unit]
Description=Prohori measurement service (COOL OpenCV, Graviton4)
After=network-online.target
[Service]
User=prohori
EnvironmentFile=/etc/prohori.env
# COOL's cv2 (what /opt/cool/venvs/python_3.12/bin/activate exports):
Environment=PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12
Environment=LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib
WorkingDirectory=/opt/prohori/current
ExecStart=/opt/prohori/venv/bin/uvicorn service.app:app --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers
Restart=always
RestartSec=2
[Install]
WantedBy=multi-user.target
UNITEOF

TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')
PUBIP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
cat > /etc/caddy/Caddyfile <<CADDYEOF
$(echo "$PUBIP" | tr . -).sslip.io {
	encode gzip
	request_body {
		max_size 20MB
	}
	reverse_proxy 127.0.0.1:8000
}
CADDYEOF
chown -R prohori:prohori /opt/prohori
systemctl daemon-reload
systemctl enable prohori caddy
systemctl restart caddy
touch /var/lib/cloud/prohori-bootstrap-done
