#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="monorelay"
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
ExecStart=${PYTHON_PATH} -m backend.main --port 8787 --host 0.0.0.0
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
echo "Check status:  sudo systemctl status ${SERVICE_NAME}"
echo "View logs:     sudo journalctl -u ${SERVICE_NAME} -f"
echo "Stop:          sudo systemctl stop ${SERVICE_NAME}"
echo "Restart:       sudo systemctl restart ${SERVICE_NAME}"
echo "Uninstall:      sudo bash scripts/service_uninstall.sh"
echo ""
