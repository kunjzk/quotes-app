#!/bin/bash
set -e

# Log all output
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "Starting user-data script at $(date)"

# Update system
apt-get update
apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker ubuntu

# Install Docker Compose
apt-get install -y docker-compose-plugin

# Create application directory
mkdir -p /opt/quotesapp
cd /opt/quotesapp

# Clone the repository (you'll need to update this URL)
# For now, we'll create a placeholder that you can update
cat > /opt/quotesapp/README.txt << 'EOF'
Deploy your application here:
1. Clone your repo: git clone https://github.com/your-username/quotes-app.git
2. Or upload files via SCP
3. Update the systemd service to point to the correct directory
EOF

# Create .env file
cat > /opt/quotesapp/.env << 'EOF'
DJANGO_SECRET_KEY=${django_secret_key}
DJANGO_DEBUG_MODE=False
POSTGRES_NAME=quotesapp
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${postgres_password}
POSTGRES_HOST=quotes-postgres
POSTGRES_PORT=5432

# Email Configuration (AWS SES)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=${ses_smtp_host}
EMAIL_PORT=${ses_smtp_port}
EMAIL_USE_TLS=True
EMAIL_HOST_USER=${ses_smtp_username}
EMAIL_HOST_PASSWORD=${ses_smtp_password}
DEFAULT_FROM_EMAIL=${default_from_email}

# Celery Configuration
CELERY_BROKER_URL=redis://quotes-redis:6379
EOF

# Create systemd service
cat > /etc/systemd/system/quotesapp.service << 'EOF'
[Unit]
Description=Quotes App Docker Compose
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/quotesapp
ExecStartPre=/usr/bin/docker-compose pull
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=300
User=root

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

echo "User-data script completed at $(date)"
echo "Manual steps required:"
echo "1. Clone/upload your application to /opt/quotesapp"
echo "2. Run: systemctl enable quotesapp"
echo "3. Run: systemctl start quotesapp"
