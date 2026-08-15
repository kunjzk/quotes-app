#!/bin/bash
set -e

# Server setup script - Run this on the EC2 instance after Terraform provisioning
# This can be run manually or via SSH from your local machine

echo "================================================"
echo "Setting up Quotes App Server"
echo "================================================"

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker ubuntu
    rm get-docker.sh
else
    echo "Docker already installed"
fi

# Install Docker Compose
if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo apt-get install -y docker-compose-plugin
else
    echo "Docker Compose already installed"
fi

# Create application directory
echo "Creating application directory..."
sudo mkdir -p /opt/quotesapp
sudo chown ubuntu:ubuntu /opt/quotesapp

# Install git (optional, for cloning repo)
if ! command -v git &> /dev/null; then
    echo "Installing git..."
    sudo apt-get install -y git
fi

# Install other useful tools
echo "Installing additional tools..."
sudo apt-get install -y \
    curl \
    wget \
    vim \
    htop \
    net-tools

echo ""
echo "================================================"
echo "Server setup complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Copy your application code to /opt/quotesapp"
echo "2. Create .env file in /opt/quotesapp with your configuration"
echo "3. Copy systemd service file to /etc/systemd/system/quotesapp.service"
echo "4. Run: sudo systemctl daemon-reload"
echo "5. Run: sudo systemctl enable quotesapp"
echo "6. Run: sudo systemctl start quotesapp"
echo ""
echo "Note: You may need to log out and back in for Docker group changes to take effect"
echo ""
