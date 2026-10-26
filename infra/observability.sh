#!/usr/bin/env bash
# CloudWatch observability for the live Prohori service.  Idempotent; run from the repo root, AWS CLI logged in.
#   bash infra/observability.sh            (TARGET=<ip> to install the log forwarder on another box; default: live EIP)
# Creates: log group /prohori/service (14-day retention); logs permissions for role prohori-ec2 (one log group only);
# metric filters (namespace Prohori/Service) on the service's structured JSON access lines: Requests, Http5xx,
# MeasureServerMs (p50/p95), TierCertified / TierIndicative / TierRefused / NoBoard; dashboard Prohori-Service;
# alarm prohori-5xx (any 5xx in 5 min -> SNS topic prohori-alarms, email ALERT_EMAIL, confirm once); and installs
# infra/cwlogs_forwarder.py as systemd unit prohori-logs on the instance (journald -> CloudWatch Logs).
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
AWS="${AWS:-aws}"
command -v "$AWS" >/dev/null || AWS="/c/Program Files/Amazon/AWSCLIV2/aws.exe"
cd "$(dirname "$0")/.."
source infra/state.env
export AWS_REGION="$REGION"
GROUP=/prohori/service; NS=Prohori/Service; ROLE=prohori-ec2
ALERT_EMAIL="${ALERT_EMAIL:-20hozaifa02@gmail.com}"
TARGET="${TARGET:-$EIP}"
mkdir -p infra/.gen

echo "== log group $GROUP (14 days)"
"$AWS" logs create-log-group --log-group-name "$GROUP" 2>/dev/null || true
"$AWS" logs put-retention-policy --log-group-name "$GROUP" --retention-in-days 14

echo "== role $ROLE: logs permissions for this one log group (mirrored in up.sh)"
"$AWS" iam get-role-policy --role-name "$ROLE" --policy-name prohori-app --query PolicyDocument --output json > infra/.gen/policy_cur.json
python - "$ACCT" "$REGION" <<'PY'
import json, sys
acct, region = sys.argv[1:3]
d = json.load(open("infra/.gen/policy_cur.json"))
d["Statement"] = [s for s in d["Statement"] if s.get("Sid") != "Logs"] + [{
    "Sid": "Logs", "Effect": "Allow",
    "Action": ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
    "Resource": f"arn:aws:logs:{region}:{acct}:log-group:/prohori/service:*"}]
json.dump(d, open("infra/.gen/policy_new.json", "w"))
PY
"$AWS" iam put-role-policy --role-name "$ROLE" --policy-name prohori-app --policy-document file://infra/.gen/policy_new.json

echo "== metric filters ($NS)"
mf() {  # mf <name> <pattern> <metric> <value>
  "$AWS" logs put-metric-filter --log-group-name "$GROUP" --filter-name "$1" --filter-pattern "$2" \
    --metric-transformations "metricName=$3,metricNamespace=$NS,metricValue=$4,unit=${5:-Count}"
}
mf requests    '{ $.evt = "request" }'                                 Requests        1
mf http5xx     '{ $.evt = "request" && $.status >= 500 }'              Http5xx         1
mf server-ms   '{ $.evt = "request" && $.server_ms > 0 }'             MeasureServerMs '$.server_ms' Milliseconds
mf tier-cert   '{ $.evt = "request" && $.tier = "certified" }'         TierCertified   1
mf tier-indic  '{ $.evt = "request" && $.tier = "indicative" }'        TierIndicative  1
mf tier-refus  '{ $.evt = "request" && $.tier = "refused" }'           TierRefused     1
mf no-board    '{ $.evt = "request" && $.gate = "no_board" }'          NoBoard         1

echo "== alarm prohori-5xx"
TOPIC_AL=$("$AWS" sns create-topic --name prohori-alarms --query TopicArn --output text)
if [ "$("$AWS" sns list-subscriptions-by-topic --topic-arn "$TOPIC_AL" --query 'length(Subscriptions)' --output text)" = 0 ]; then
  "$AWS" sns subscribe --topic-arn "$TOPIC_AL" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
fi
"$AWS" cloudwatch put-metric-alarm --alarm-name prohori-5xx --namespace "$NS" --metric-name Http5xx --statistic Sum \
  --period 300 --evaluation-periods 1 --threshold 1 --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching --alarm-actions "$TOPIC_AL" \
  --alarm-description "Prohori service returned at least one HTTP 5xx in 5 minutes (log group $GROUP)"

echo "== dashboard Prohori-Service"
W() { echo "{\"type\":\"metric\",\"x\":$1,\"y\":$2,\"width\":12,\"height\":6,\"properties\":{\"region\":\"$REGION\",\"title\":\"$3\",$4}}"; }
M() { echo "[\"$NS\",\"$1\",{\"stat\":\"$2\",\"label\":\"$3\"}]"; }
cat > infra/.gen/dashboard.json <<DASH
{"widgets":[
 $(W 0 0 "Requests per minute" "\"view\":\"timeSeries\",\"period\":60,\"metrics\":[$(M Requests Sum requests)]"),
 $(W 12 0 "Measure server_ms p50 / p95" "\"view\":\"timeSeries\",\"period\":300,\"metrics\":[$(M MeasureServerMs p50 p50),$(M MeasureServerMs p95 p95)]"),
 $(W 0 6 "HTTP 5xx" "\"view\":\"timeSeries\",\"period\":60,\"metrics\":[$(M Http5xx Sum 5xx)]"),
 $(W 12 6 "Gate tier counts" "\"view\":\"timeSeries\",\"stacked\":true,\"period\":300,\"metrics\":[$(M TierCertified Sum certified),$(M TierIndicative Sum indicative),$(M TierRefused Sum refused),$(M NoBoard Sum no_board)]"),
 {"type":"alarm","x":0,"y":12,"width":12,"height":3,"properties":{"title":"Alarms","alarms":["arn:aws:cloudwatch:$REGION:$ACCT:alarm:prohori-5xx"]}},
 {"type":"log","x":12,"y":12,"width":12,"height":6,"properties":{"region":"$REGION","title":"Latest measure requests","query":"SOURCE '$GROUP' | fields @timestamp, status, tier, cracks, server_ms | filter route = '/api/measure' | sort @timestamp desc | limit 20","view":"table"}}
]}
DASH
"$AWS" cloudwatch put-dashboard --dashboard-name Prohori-Service --dashboard-body file://infra/.gen/dashboard.json >/dev/null

echo "== journald forwarder on $TARGET (systemd unit prohori-logs)"
SSHO=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=15)
scp "${SSHO[@]}" infra/cwlogs_forwarder.py "ubuntu@$TARGET:/tmp/cwlogs_forwarder.py" >/dev/null
ssh "${SSHO[@]}" "ubuntu@$TARGET" "sudo bash -s" <<'REMOTE'
set -euo pipefail
install -m 0644 /tmp/cwlogs_forwarder.py /opt/prohori/cwlogs_forwarder.py && rm /tmp/cwlogs_forwarder.py
cat > /etc/systemd/system/prohori-logs.service <<'UNIT'
[Unit]
Description=Prohori journald to CloudWatch Logs forwarder
After=prohori.service
[Service]
EnvironmentFile=/etc/prohori.env
ExecStart=/opt/prohori/venv/bin/python /opt/prohori/cwlogs_forwarder.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable prohori-logs >/dev/null 2>&1
systemctl restart prohori-logs
sleep 3
systemctl is-active prohori-logs
REMOTE
echo "== done: dashboard Prohori-Service, alarm prohori-5xx, log group $GROUP"
