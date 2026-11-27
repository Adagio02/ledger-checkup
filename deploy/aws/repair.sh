#!/usr/bin/env bash
# Show the server's setup log and (re)start the app, without SSH, using SSM Run Command.
# Run from AWS CloudShell or any machine with the AWS CLI:
#   ./deploy/aws/repair.sh [region] [stack-name]
#   ./deploy/aws/repair.sh logs [region] [stack-name]    # only show logs, change nothing
set -euo pipefail

MODE=repair
if [[ "${1:-}" == "logs" ]]; then MODE=logs; shift; fi
REGION="${1:-${AWS_REGION:-us-east-1}}"
STACK="${2:-ledger-checkup}"

INSTANCE=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
echo "Instance: $INSTANCE ($REGION)"

LOGS='echo "===== setup log (last 60 lines) ====="; tail -n 60 /var/log/ledger-checkup-bootstrap.log 2>/dev/null || tail -n 60 /var/log/cloud-init-output.log; echo "===== containers ====="; docker ps -a 2>&1 || true'
FIX='set -e; export HOME=/root; dnf install -y -q git; if [ -d /opt/ledger-checkup/.git ]; then git -C /opt/ledger-checkup pull --ff-only; else git clone https://github.com/Adagio02/ledger-checkup.git /opt/ledger-checkup; fi; bash /opt/ledger-checkup/deploy/aws/bootstrap.sh > /tmp/bootstrap-run.log 2>&1 && echo "SUCCESS: app is running" || { echo "FAILED, last lines:"; tail -n 40 /tmp/bootstrap-run.log; }'

if [[ "$MODE" == logs ]]; then COMMANDS="$LOGS"; else COMMANDS="$LOGS; echo; echo '===== repairing (takes 3-6 minutes) ====='; $FIX"; fi

PARAMS=$(python3 -c 'import json,sys; print(json.dumps({"commands": [sys.argv[1]], "executionTimeout": ["1800"]}))' "$COMMANDS")
CMD_ID=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript --parameters "$PARAMS" --query Command.CommandId --output text)

echo "Waiting for the server to finish (this can take several minutes)..."
while true; do
  STATUS=$(aws ssm get-command-invocation --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" \
    --query Status --output text 2>/dev/null || echo Pending)
  case "$STATUS" in Pending|InProgress|Delayed) sleep 10 ;; *) break ;; esac
done
aws ssm get-command-invocation --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" \
  --query StandardOutputContent --output text
echo "Command status: $STATUS"
