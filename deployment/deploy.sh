#!/bin/bash
set -e

# Deployment script for Quotes App
# Usage: ./deploy.sh <server-ip> <path-to-private-key>

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <server-ip> <path-to-private-key>"
    echo "Example: $0 54.123.45.67 ~/.ssh/quotesapp-key.pem"
    exit 1
fi

SERVER_IP=$1
SSH_KEY=$2
REMOTE_USER=ubuntu
DEPLOY_DIR=/opt/quotesapp

echo "================================================"
echo "Deploying Quotes App to $SERVER_IP"
echo "================================================"

# Test SSH connection
echo "Testing SSH connection..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$REMOTE_USER@$SERVER_IP" "echo 'SSH connection successful'"

# Create remote directory
echo "Creating deployment directory..."
ssh -i "$SSH_KEY" "$REMOTE_USER@$SERVER_IP" "sudo mkdir -p $DEPLOY_DIR && sudo chown ubuntu:ubuntu $DEPLOY_DIR"

# Copy application files (exclude unnecessary files)
echo "Copying application files..."
rsync -avz -e "ssh -i $SSH_KEY" \
    --exclude='.git' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='terraform' \
    --exclude='deployment' \
    --exclude='htmlcov' \
    --exclude='.coverage' \
    ../ "$REMOTE_USER@$SERVER_IP:$DEPLOY_DIR/"

# Copy systemd service file
echo "Setting up systemd service..."
scp -i "$SSH_KEY" quotesapp.service "$REMOTE_USER@$SERVER_IP:/tmp/"
ssh -i "$SSH_KEY" "$REMOTE_USER@$SERVER_IP" "sudo mv /tmp/quotesapp.service /etc/systemd/system/"

# Check if .env exists on remote
echo "Checking for .env file..."
if ssh -i "$SSH_KEY" "$REMOTE_USER@$SERVER_IP" "test -f $DEPLOY_DIR/.env"; then
    echo ".env file exists on remote server"
else
    echo "WARNING: .env file not found on remote server!"
    echo "Please create $DEPLOY_DIR/.env with the required configuration"
    echo "You can use .env.example as a template"
fi

# Run initial setup commands
echo "Running initial setup..."
ssh -i "$SSH_KEY" "$REMOTE_USER@$SERVER_IP" << 'ENDSSH'
cd /opt/quotesapp

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable quotesapp

# Stop existing services if running
sudo systemctl stop quotesapp || true

# Pull latest images
docker-compose pull

# Run migrations
echo "Running database migrations..."
docker-compose run --rm quotes-app python manage.py migrate

# Create superuser (interactive - comment out if not needed)
# docker-compose run --rm quotes-app python manage.py createsuperuser

# Start services
sudo systemctl start quotesapp

# Check status
sleep 5
sudo systemctl status quotesapp --no-pager

# Show logs
echo ""
echo "Recent logs:"
docker-compose logs --tail=50

ENDSSH

echo ""
echo "================================================"
echo "Deployment complete!"
echo "================================================"
echo "Application URL: http://$SERVER_IP:8000"
echo ""
echo "Useful commands:"
echo "  View logs: ssh -i $SSH_KEY $REMOTE_USER@$SERVER_IP 'cd $DEPLOY_DIR && docker-compose logs -f'"
echo "  Restart app: ssh -i $SSH_KEY $REMOTE_USER@$SERVER_IP 'sudo systemctl restart quotesapp'"
echo "  Stop app: ssh -i $SSH_KEY $REMOTE_USER@$SERVER_IP 'sudo systemctl stop quotesapp'"
echo "  SSH into server: ssh -i $SSH_KEY $REMOTE_USER@$SERVER_IP"
echo ""
