#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="mono-api-relay"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Installing ${SERVICE_NAME} as a systemd service..."

PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo "Error: python3 not found"
    exit 1
fi

USER=$(whoami)
GROUP=$(id -gn)

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=MonoRelay - LLM API Relay Server
After=network.target

[Service]
Type=simple
User=${USER}
Group=${GROUP}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PYTHON_PATH} -m backend.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl start "${SERVICE_NAME}"

echo ""
echo "=========================================="
echo "${SERVICE_NAME} installed and started!"
echo "=========================================="
echo ""
echo "Check status:  systemctl status ${SERVICE_NAME}"
echo "View logs:     journalctl -u ${SERVICE_NAME} -f"
echo "Stop:          systemctl stop ${SERVICE_NAME}"
echo "Restart:       systemctl restart ${SERVICE_NAME}"
echo ""
