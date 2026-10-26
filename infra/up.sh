#!/usr/bin/env bash
# One-command, idempotent AWS setup for the Prohori demo endpoint.
# Creates: budget alarm, private encrypted S3 bucket, DynamoDB trace table,
# least-privilege EC2 role, security group, key pair, t4g.small (Graviton2,
# Ubuntu 24.04 arm64) with an Elastic IP. TLS comes from Caddy + Let's Encrypt
# on <ip>.sslip.io, because phone cameras only open on HTTPS.
# Usage: bash infra/up.sh   (run from the repo root, AWS CLI logged in)
set -euo pipefail
export MSYS_NO_PATHCONV=1 AWS_PAGER=""
AWS="${AWS:-aws}"
command -v "$AWS" >/dev/null || AWS="/c/Program Files/Amazon/AWSCLIV2/aws.exe"
REGION="${REGION:-us-east-1}"
NAME=prohori
ALERT_EMAIL="${ALERT_EMAIL:-20hozaifa02@gmail.com}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.small}"
export AWS_REGION="$REGION"
cd "$(dirname "$0")/.."
ACCT=$("$AWS" sts get-caller-identity --query Account --output text)
BUCKET="$NAME-$ACCT-$REGION"
TABLE="$NAME-traces"
ROLE="$NAME-ec2"
STATE=infra/state.env
mkdir -p infra/.gen

echo "== budget alarm (\$25/month, alerts at 50/80/100%)"
if ! "$AWS" budgets describe-budget --account-id "$ACCT" --budget-name "$NAME-monthly" >/dev/null 2>&1; then
  cat > infra/.gen/budget.json <<EOF
{"BudgetName":"$NAME-monthly","BudgetLimit":{"Amount":"25","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}
EOF
  notif() { echo "{\"Notification\":{\"NotificationType\":\"$1\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":$2,\"ThresholdType\":\"PERCENTAGE\"},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$ALERT_EMAIL\"}]}"; }
  echo "[$(notif ACTUAL 50),$(notif ACTUAL 80),$(notif FORECASTED 100)]" > infra/.gen/notifs.json
  "$AWS" budgets create-budget --account-id "$ACCT" --budget file://infra/.gen/budget.json \
    --notifications-with-subscribers file://infra/.gen/notifs.json
fi

echo "== S3 bucket $BUCKET (private, encrypted)"
if ! "$AWS" s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  if [ "$REGION" = us-east-1 ]; then "$AWS" s3api create-bucket --bucket "$BUCKET" >/dev/null
  else "$AWS" s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint="$REGION" >/dev/null; fi
fi
"$AWS" s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
"$AWS" s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

echo "== DynamoDB $TABLE"
if ! "$AWS" dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  "$AWS" dynamodb create-table --table-name "$TABLE" --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=session_id,AttributeType=S AttributeName=step,AttributeType=S \
    --key-schema AttributeName=session_id,KeyType=HASH AttributeName=step,KeyType=RANGE \
    --sse-specification Enabled=true >/dev/null
  "$AWS" dynamodb wait table-exists --table-name "$TABLE"
  "$AWS" dynamodb update-time-to-live --table-name "$TABLE" \
    --time-to-live-specification Enabled=true,AttributeName=ttl >/dev/null
fi

echo "== SNS escalation topic"
TOPIC=$("$AWS" sns create-topic --name "$NAME-escalations" --attributes KmsMasterKeyId=alias/aws/sns \
  --query TopicArn --output text)
if [ "$("$AWS" sns list-subscriptions-by-topic --topic-arn "$TOPIC" --query 'length(Subscriptions)' --output text)" = 0 ]; then
  # The engineer must click the confirmation link AWS emails once.
  "$AWS" sns subscribe --topic-arn "$TOPIC" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
fi

echo "== IAM role $ROLE (least privilege)"
cat > infra/.gen/trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
cat > infra/.gen/policy.json <<EOF
{"Version":"2012-10-17","Statement":[
 {"Sid":"Bedrock","Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":[
   "arn:aws:bedrock:*:$ACCT:inference-profile/us.anthropic.claude-*",
   "arn:aws:bedrock:*:$ACCT:inference-profile/us.amazon.nova-*",
   "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
   "arn:aws:bedrock:*::foundation-model/amazon.nova-*"]},
 {"Sid":"Traces","Effect":"Allow","Action":["dynamodb:PutItem","dynamodb:Query","dynamodb:GetItem"],
  "Resource":"arn:aws:dynamodb:$REGION:$ACCT:table/$TABLE"},
 {"Sid":"Escalate","Effect":"Allow","Action":["sns:Publish"],"Resource":"$TOPIC"},
 {"Sid":"Evidence","Effect":"Allow","Action":["s3:PutObject"],"Resource":"arn:aws:s3:::$BUCKET/evidence/*"},
 {"Sid":"Deploy","Effect":"Allow","Action":["s3:GetObject"],"Resource":"arn:aws:s3:::$BUCKET/deploy/*"}
]}
EOF
if ! "$AWS" iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  "$AWS" iam create-role --role-name "$ROLE" --assume-role-policy-document file://infra/.gen/trust.json >/dev/null
  "$AWS" iam attach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
fi
"$AWS" iam put-role-policy --role-name "$ROLE" --policy-name "$NAME-app" --policy-document file://infra/.gen/policy.json
if ! "$AWS" iam get-instance-profile --instance-profile-name "$ROLE" >/dev/null 2>&1; then
  "$AWS" iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
  "$AWS" iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
  sleep 10  # instance profile propagation
fi

echo "== security group"
VPC=$("$AWS" ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$("$AWS" ec2 describe-security-groups --filters Name=group-name,Values="$NAME-web" Name=vpc-id,Values="$VPC" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = None ]; then
  SG=$("$AWS" ec2 create-security-group --group-name "$NAME-web" --description "Prohori HTTPS endpoint" \
    --vpc-id "$VPC" --query GroupId --output text)
  "$AWS" ec2 authorize-security-group-ingress --group-id "$SG" --ip-permissions \
    'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0}]' \
    'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}]' >/dev/null
fi
MYIP=$(curl -s https://checkip.amazonaws.com | tr -d '[:space:]')
"$AWS" ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 22 --cidr "${MYIP%.*}.0/24" >/dev/null 2>&1 || true

echo "== key pair"
KEY="$HOME/.ssh/$NAME-key.pem"
if ! "$AWS" ec2 describe-key-pairs --key-names "$NAME-key" >/dev/null 2>&1; then
  mkdir -p "$HOME/.ssh"
  "$AWS" ec2 create-key-pair --key-name "$NAME-key" --key-type ed25519 --query KeyMaterial --output text | tr -d '\r' > "$KEY"
  chmod 600 "$KEY"
fi

echo "== Elastic IP"
ALLOC=$("$AWS" ec2 describe-addresses --filters Name=tag:Name,Values="$NAME" --query 'Addresses[0].AllocationId' --output text)
if [ "$ALLOC" = None ]; then
  ALLOC=$("$AWS" ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" --query AllocationId --output text)
fi
EIP=$("$AWS" ec2 describe-addresses --allocation-ids "$ALLOC" --query 'Addresses[0].PublicIp' --output text)
HOST="$(echo "$EIP" | tr . -).sslip.io"

echo "== instance ($INSTANCE_TYPE)"
IID=$("$AWS" ec2 describe-instances --filters Name=tag:Name,Values="$NAME" \
  Name=instance-state-name,Values=pending,running,stopped,stopping --query 'Reservations[0].Instances[0].InstanceId' --output text)
if [ "$IID" = None ]; then
  AMI=$("$AWS" ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id \
    --query Parameter.Value --output text)
  sed -e "s/__HOST__/$HOST/g" -e "s/__BUCKET__/$BUCKET/g" -e "s/__TABLE__/$TABLE/g" -e "s/__REGION__/$REGION/g" \
    infra/bootstrap.sh > infra/.gen/userdata.sh
  IID=$("$AWS" ec2 run-instances --image-id "$AMI" --instance-type "$INSTANCE_TYPE" --key-name "$NAME-key" \
    --security-group-ids "$SG" --iam-instance-profile Name="$ROLE" \
    --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
    --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
    --credit-specification CpuCredits=standard \
    --user-data file://infra/.gen/userdata.sh \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=project,Value=prohori}]" \
    --query 'Instances[0].InstanceId' --output text)
fi
"$AWS" ec2 wait instance-running --instance-ids "$IID"
# Do not steal the Elastic IP back if it already serves another instance (the COOL box after infra/cool_live.sh cutover).
HOLDER=$("$AWS" ec2 describe-addresses --allocation-ids "$ALLOC" --query 'Addresses[0].InstanceId' --output text)
if [ "$HOLDER" = None ] || [ "$HOLDER" = "$IID" ] || [ "${FORCE_EIP:-0}" = 1 ]; then
  "$AWS" ec2 associate-address --instance-id "$IID" --allocation-id "$ALLOC" --allow-reassociation >/dev/null
else
  echo "   Elastic IP stays on $HOLDER (FORCE_EIP=1 to move it to $IID)"
fi

# keep the COOL / live-pointer keys infra/cool_live.sh wrote (IID_T4G, COOL_IID, COOL_IP); IID keeps pointing at whoever holds the EIP
EXTRA=$(grep -E '^(IID_T4G|COOL_IID|COOL_IP)=' "$STATE" 2>/dev/null || true)
[ "$HOLDER" = None ] || [ "$HOLDER" = "$IID" ] || [ "${FORCE_EIP:-0}" = 1 ] || IID_LIVE=$HOLDER
cat > "$STATE" <<EOF
REGION=$REGION
ACCT=$ACCT
BUCKET=$BUCKET
TABLE=$TABLE
SG=$SG
IID=${IID_LIVE:-$IID}
EIP=$EIP
HOST=$HOST
KEY=$KEY
TOPIC=$TOPIC
EOF
[ -z "$EXTRA" ] || echo "$EXTRA" >> "$STATE"
echo "== done: https://$HOST  (instance $IID)"
