#!/bin/bash

# TRMNL-ZH Automated Deployment Script for Ubuntu 24.04 LTS
# This script handles Stages 2 & 3 of the deployment process.

set -e # Exit on error

# --- Configuration ---
PROJECT_DIR="/home/ubuntu/TRMNL-ZH"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_NAME="trmnl.service"
NGINX_CONF="/etc/nginx/sites-available/trmnl"
PUBLIC_IP=$(curl -s http://checkip.amazonaws.com)

echo "🚀 Starting deployment for TRMNL-ZH on $PUBLIC_IP..."

# 1. System Dependencies
echo "📦 Installing system dependencies..."
sudo apt update
sudo apt install -y python3-pip python3-venv nginx git fonts-dejavu-core

# 2. Project Directory Setup
if [ ! -d "$PROJECT_DIR" ]; then
    echo "📂 Cloning repository..."
    git clone https://github.com/StefanoSimao/TRMNL-ZH.git "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# 3. Virtual Environment
echo "🐍 Setting up Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create .env Template if not exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "📝 Creating .env template. PLEASE UPDATE THIS FILE LATER!"
    cat <<EOF > "$PROJECT_DIR/.env"
TRMNL_DEVICE_ID="AA:BB:CC:DD:EE:FF"
TRMNL_REFRESH_RATE=45
SWITCHBOT_TOKEN=""
SWITCHBOT_SECRET=""
SWITCHBOT_DEVICE_ID_INDOOR=""
SWITCHBOT_DEVICE_ID_BALCONY=""
GEMINI_API_KEY=""
BASE_URL="http://$PUBLIC_IP"
EOF
fi

# 5. Systemd Service Creation
echo "⚙️ Creating systemd service..."
sudo bash -c "cat <<EOF > /etc/systemd/system/$SERVICE_NAME
[Unit]
Description=TRMNL-ZH FastAPI Server
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$VENV_DIR/bin/python run.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF"

# 6. Nginx Configuration
echo "🌐 Configuring Nginx..."
sudo bash -c "cat <<EOF > $NGINX_CONF
server {
    listen 80;
    server_name $PUBLIC_IP;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /generated/ {
        alias $PROJECT_DIR/generated/;
        expires 30s;
        add_header Cache-Control \"public, no-transform\";
    }
}
EOF"

# Enable Nginx site
sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 7. Restart and Enable Services
echo "🔄 Restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart nginx
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "✅ Deployment Complete!"
echo "-------------------------------------------------------"
echo "IMPORTANT: Update your credentials in: $PROJECT_DIR/.env"
echo "Then restart the app: sudo systemctl restart $SERVICE_NAME"
echo "Your TRMNL endpoint: http://$PUBLIC_IP/api/display"
echo "-------------------------------------------------------"
