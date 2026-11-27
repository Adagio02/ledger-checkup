#!/usr/bin/env bash
# Installs Docker and starts Ledger Checkup on an Amazon Linux 2023 instance.
# Runs automatically at first boot (from the CloudFormation user data) and is safe to re-run:
#   sudo bash /opt/ledger-checkup/deploy/aws/bootstrap.sh
#
# Settings (all optional, via environment variables):
#   AWS_REGION       region holding the SSM parameters (default: the instance's region)
#   PARAM_PREFIX     SSM path for APP_PASSWORD / LLM_API_KEY (default: /ledger-checkup)
#   DOMAIN           domain for automatic HTTPS (default: none, plain HTTP on port 80)
set -euxo pipefail
exec > >(tee -a /var/log/ledger-checkup-bootstrap.log) 2>&1
export HOME="${HOME:-/root}"

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PARAM_PREFIX="${PARAM_PREFIX:-/ledger-checkup}"
COMPOSE_VERSION="v2.32.1"
BUILDX_VERSION="v0.19.3"

if [[ -z "${AWS_REGION:-}" ]]; then
  TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  AWS_REGION=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
fi

# 1 GB swap so the image build fits in a micro instance's memory
if ! swapon --show | grep -q /swapfile; then
  [[ -f /swapfile ]] || { fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile; }
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Docker plus the compose and buildx plugins (Amazon Linux's docker package ships neither;
# compose cannot build images without buildx). Versions are pinned so boots are repeatable.
dnf install -y docker git
systemctl enable --now docker
case "$(uname -m)" in
  x86_64) ARCH_COMPOSE=x86_64; ARCH_BUILDX=amd64 ;;
  aarch64) ARCH_COMPOSE=aarch64; ARCH_BUILDX=arm64 ;;
  *) echo "Unsupported CPU $(uname -m)"; exit 1 ;;
esac
PLUGINS=/usr/local/lib/docker/cli-plugins
mkdir -p "$PLUGINS"
curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${ARCH_COMPOSE}" \
  -o "$PLUGINS/docker-compose"
curl -fsSL "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-${ARCH_BUILDX}" \
  -o "$PLUGINS/docker-buildx"
chmod +x "$PLUGINS/docker-compose" "$PLUGINS/docker-buildx"
docker compose version
docker buildx version

# App settings from SSM Parameter Store (secrets never live in Git or the template)
get() {
  aws ssm get-parameter --region "$AWS_REGION" --with-decryption --name "$PARAM_PREFIX/$1" \
    --query Parameter.Value --output text 2>/dev/null || true
}
cd "$APP_DIR"
LLM_BASE_URL_VALUE=$(get LLM_BASE_URL)
LLM_MODEL_VALUE=$(get LLM_MODEL)
umask 077
cat > .env <<EOF
APP_PASSWORD=$(get APP_PASSWORD)
LLM_API_KEY=$(get LLM_API_KEY)
LLM_BASE_URL=${LLM_BASE_URL_VALUE:-https://api.groq.com/openai/v1}
LLM_MODEL=${LLM_MODEL_VALUE:-llama-3.3-70b-versatile}
DB_PATH=/app/data/ledger_checkup.db
EOF
umask 022
grep -q '^APP_PASSWORD=.\+' .env || echo "WARNING: no APP_PASSWORD found in SSM at $PARAM_PREFIX/APP_PASSWORD; the site is not password-protected"
mkdir -p data && chown 1000:1000 data

export DOMAIN="${DOMAIN:-:80}"
[[ -n "$DOMAIN" ]] || DOMAIN=":80"
docker compose up -d --build --remove-orphans
docker compose ps
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null http://localhost/health; then echo "Local health check passed"; break; fi
  sleep 2
done
curl -fsS -o /dev/null http://localhost/health || \
  { echo "App did not answer on port 80"; docker compose logs --tail 50; exit 1; }
echo "Ledger Checkup is running."
