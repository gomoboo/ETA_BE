#!/bin/bash
set -euo pipefail
umask 077
SCRIPTS=/opt/eta/repo/infra/scripts
region=$(python3 "$SCRIPTS/config.py" region)
parameter=$(python3 "$SCRIPTS/config.py" env_parameter)
image_parameter=$(python3 "$SCRIPTS/config.py" image_parameter)
domain=$(python3 "$SCRIPTS/config.py" domain)
install -d -m 700 /opt/eta/env
secret_file=$(mktemp /opt/eta/env/.api.XXXXXX)
trap 'rm -f "$secret_file"' EXIT
aws ssm get-parameter --region "$region" --name "$parameter" --with-decryption \
  --query Parameter.Value --output text > "$secret_file"
grep -Eq '^POSTGRES_PASSWORD=[a-fA-F0-9]{32,128}$' "$secret_file" || {
  echo 'Set POSTGRES_PASSWORD to 32-128 random hex characters in SSM' >&2
  exit 1
}
mv "$secret_file" /opt/eta/env/api.env
image=$(aws ssm get-parameter --region "$region" --name "$image_parameter" --query Parameter.Value --output text)
previous=$(sed -n 's/^API_IMAGE=//p' /opt/eta/env/image.env 2>/dev/null || true)
printf 'API_DOMAIN=%s\nAPI_IMAGE=%s\n' "${domain:-:80}" "${previous:-eta-backend:bootstrap}" > /opt/eta/env/image.env
"$SCRIPTS/compose.sh" up -d --wait --wait-timeout 180 db redis
if [ "$image" = bootstrap ]; then
  sed 's|^API_IMAGE=.*|API_IMAGE=eta-backend:bootstrap|' /opt/eta/env/image.env > /opt/eta/env/.bootstrap-image.env
  mv /opt/eta/env/.bootstrap-image.env /opt/eta/env/image.env
  if ! docker image inspect eta-backend:bootstrap > /dev/null 2>&1; then
    "$SCRIPTS/compose.sh" build api
  fi
else
  bash "$SCRIPTS/deploy.sh" "$image"
fi
"$SCRIPTS/compose.sh" up -d --no-build --wait --wait-timeout 180
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/health
# ECR authentication is managed by deploy.sh; no credentials are embedded in this script.
