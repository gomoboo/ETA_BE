#!/bin/bash
set -euo pipefail
umask 077
SCRIPTS=/opt/eta/repo/infra/scripts
image=${1:?Pass an immutable ECR image tagged with a commit SHA}
registry=$(python3 "$SCRIPTS/config.py" ecr_registry)
region=$(python3 "$SCRIPTS/config.py" region)
if [[ ! "$image" =~ ^[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9_./-]+:[a-f0-9]{40}$ ]] || [[ "$image" != "$registry/"* ]]; then
  echo 'Invalid image or unexpected registry' >&2
  exit 1
fi
aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry" > /dev/null
previous=$(sed -n 's/^API_IMAGE=//p' /opt/eta/env/image.env)
printf 'API_IMAGE=%s\n' "$image" > /opt/eta/env/.next-image.env
grep '^API_DOMAIN=' /opt/eta/env/image.env >> /opt/eta/env/.next-image.env
if ! docker pull "$image"; then
  rm -f /opt/eta/env/.next-image.env
  exit 1
fi
mv /opt/eta/env/.next-image.env /opt/eta/env/image.env
# During first boot PostgreSQL/Redis may not yet exist; start.sh starts the whole stack afterward.
if ! docker inspect eta-api-1 > /dev/null 2>&1; then
  exit 0
fi
if ! "$SCRIPTS/compose.sh" up -d --no-deps --no-build --wait --wait-timeout 180 api || \
   ! curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/health; then
  echo 'API replacement failed; restoring the previous image (database migrations are not rolled back)' >&2
  if [ -n "$previous" ]; then
    sed "s|^API_IMAGE=.*|API_IMAGE=$previous|" /opt/eta/env/image.env > /opt/eta/env/.rollback-image.env
    mv /opt/eta/env/.rollback-image.env /opt/eta/env/image.env
    "$SCRIPTS/compose.sh" up -d --no-deps --no-build --wait --wait-timeout 180 api
  fi
  exit 1
fi
