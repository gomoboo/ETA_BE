#!/bin/bash
set -euo pipefail
exec docker compose -p eta \
  --env-file /opt/eta/env/api.env \
  --env-file /opt/eta/env/image.env \
  -f /opt/eta/repo/infra/docker/compose.yml "$@"
