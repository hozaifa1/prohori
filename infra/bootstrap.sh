#!/bin/bash
# EC2 user-data for the Prohori endpoint (Ubuntu 24.04 arm64). Placeholders are filled by infra/up.sh.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab || true
apt-get update
apt-get install -y python3-venv python3-pip caddy unzip curl
snap install aws-cli --classic || true

useradd --system --create-home --home-dir /opt/prohori --shell /usr/sbin/nologin prohori || true
mkdir -p /opt/prohori/releases /opt/prohori/data
python3 -m venv /opt/prohori/venv
/opt/prohori/venv/bin/pip install --upgrade pip

cat > /etc/prohori.env <<'EOF'
PROHORI_AWS_REGION=__REGION__
AWS_REGION=__REGION__
PROHORI_DDB_TABLE=__TABLE__
PROHORI_S3_BUCKET=__BUCKET__
PROHORI_DATA_DIR=/opt/prohori/data
PROHORI_DEFAULT_POLICY=rules
PROHORI_LLM_DAILY_CAP=200
PROHORI_BEDROCK_MODEL=us.amazon.nova-lite-v1:0
PROHORI_BEDROCK_FALLBACK_MODELS=us.amazon.nova-micro-v1:0
EOF

cat > /etc/systemd/system/prohori.service <<'EOF'
[Unit]
Description=Prohori measurement service
After=network-online.target
[Service]
User=prohori
EnvironmentFile=/etc/prohori.env
WorkingDirectory=/opt/prohori/current
ExecStart=/opt/prohori/venv/bin/uvicorn service.app:app --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers
Restart=always
RestartSec=2
[Install]
WantedBy=multi-user.target
EOF

cat > /etc/caddy/Caddyfile <<'EOF'
__HOST__ {
	encode gzip
	request_body {
		max_size 20MB
	}
	reverse_proxy 127.0.0.1:8000
}
EOF
chown -R prohori:prohori /opt/prohori
systemctl daemon-reload
systemctl enable prohori caddy
systemctl restart caddy
touch /var/lib/cloud/prohori-bootstrap-done
