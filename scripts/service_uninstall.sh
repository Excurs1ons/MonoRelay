#!/bin/bash
set -e

SERVICE_NAME="prisma-api-relay"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Uninstalling ${SERVICE_NAME}..."

systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
rm -f "$SERVICE_FILE"
systemctl daemon-reload

echo "${SERVICE_NAME} uninstalled."
