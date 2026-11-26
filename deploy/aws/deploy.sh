#!/usr/bin/env bash
# Deploy Ledger Checkup to your AWS account.
#
# Prereqs: AWS CLI v2 configured (`aws configure`) with an account you own.
# Secrets are prompted for and stored as SSM SecureString parameters (free standard tier),
# so they never appear in Git, in the template, or in your shell history.
#
# Usage: ./deploy/aws/deploy.sh [stack-name] [region] [Key=Value template overrides...]
#   e.g. ./deploy/aws/deploy.sh ledger-checkup us-east-1 Domain=books.example.com AllowedCidr=203.0.113.7/32
set -euo pipefail

STACK="${1:-ledger-checkup}"
REGION="${2:-${AWS_REGION:-us-east-1}}"
PREFIX="/ledger-checkup"
shift $(( $# > 2 ? 2 : $# ))
DIR="$(cd "$(dirname "$0")" && pwd)"

put_secret() {
  local name="$1" prompt="$2" value
  read -r -s -p "$prompt (leave empty to keep current): " value; echo
  if [[ -n "$value" ]]; then
    aws ssm put-parameter --region "$REGION" --name "$PREFIX/$name" --type SecureString \
      --value "$value" --overwrite >/dev/null
    echo "  saved $PREFIX/$name"
  fi
}

echo "Secrets for the app (stored encrypted in SSM Parameter Store, region $REGION):"
put_secret APP_PASSWORD "Web app password"
put_secret LLM_API_KEY "LLM API key (e.g. from https://console.groq.com/keys)"

aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$STACK" \
  --template-file "$DIR/template.yaml" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides ParameterPrefix="$PREFIX" "$@"

URL=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text)
echo
echo "Deployed. The server takes about 3-5 minutes to finish building after first boot."
echo "Open: $URL"
