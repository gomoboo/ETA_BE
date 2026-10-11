#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
region=$(python3 /opt/eta/repo/infra/scripts/config.py region)
# Install Docker Engine and Compose from Docker's signed Ubuntu repository.
install -m 0755 -d /etc/apt/keyrings
curl --fail --retry 5 https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<'SOURCES'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
SOURCES
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
if ! command -v aws > /dev/null; then
  temp_dir=$(mktemp -d)
  curl --fail --retry 5 https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o "$temp_dir/aws.zip"
  unzip -q "$temp_dir/aws.zip" -d "$temp_dir"
  "$temp_dir/aws/install"
  rm -rf "$temp_dir"
fi
if systemctl cat snap.amazon-ssm-agent.amazon-ssm-agent.service > /dev/null 2>&1; then
  systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service
else
  temp_deb=$(mktemp --suffix=.deb)
  curl --fail --retry 5 "https://s3.$region.amazonaws.com/amazon-ssm-$region/latest/debian_amd64/amazon-ssm-agent.deb" -o "$temp_deb"
  dpkg -i "$temp_deb"
  rm -f "$temp_deb"
  systemctl enable --now amazon-ssm-agent
fi
chmod 755 /opt/eta/repo/infra/scripts/*.sh
cat > /etc/systemd/system/eta-backend.service <<'UNIT'
[Unit]
Description=ETA Docker Compose backend
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target
StartLimitIntervalSec=0
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/eta/repo/infra/scripts/start.sh
ExecStop=/opt/eta/repo/infra/scripts/compose.sh stop --timeout 60
TimeoutStartSec=900
TimeoutStopSec=90
Restart=on-failure
RestartSec=30
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now eta-backend.service
