# AWS Deployment Guide

This guide walks you through deploying the Quotes App to AWS using Terraform.

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│              VPC (10.0.0.0/16)              │
│                                             │
│  ┌───────────────────────────────────────┐ │
│  │  Public Subnet (10.0.1.0/24)          │ │
│  │                                        │ │
│  │  ┌──────────────────────────────────┐ │ │
│  │  │  EC2 Instance (t3.small)         │ │ │
│  │  │  - Docker + Docker Compose       │ │ │
│  │  │  - systemd service               │ │ │
│  │  │                                  │ │ │
│  │  │  Containers:                     │ │ │
│  │  │  ├─ Django App (Gunicorn)        │ │ │
│  │  │  ├─ PostgreSQL                   │ │ │
│  │  │  ├─ Redis                        │ │ │
│  │  │  ├─ Celery Worker                │ │ │
│  │  │  └─ Celery Beat                  │ │ │
│  │  │                                  │ │ │
│  │  │  Public IP: xxx.xxx.xxx.xxx      │ │ │
│  │  └──────────────────────────────────┘ │ │
│  └───────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
                     │
                     ├─ Port 22 (SSH)
                     └─ Port 8000 (HTTP)
                     
External Services:
  └─ AWS SES (Email)
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Terraform** installed (v1.0+)
3. **AWS CLI** configured with credentials
4. **SSH key pair** for EC2 access
5. **Verified email** in AWS SES

## Step 1: Set Up AWS SES

Before deploying, you need to set up AWS SES for email functionality.

### 1.1 Verify Your Email Address

1. Go to AWS Console → SES
2. Click "Verified identities" → "Create identity"
3. Choose "Email address"
4. Enter your email (e.g., noreply@yourdomain.com)
5. Click "Create identity"
6. Check your email and click the verification link

**Note**: In sandbox mode, you can only send emails to verified addresses. To send to any address, request production access.

### 1.2 Create SMTP Credentials

1. Go to AWS Console → SES → SMTP settings
2. Click "Create SMTP credentials"
3. Enter a name (e.g., "quotesapp-smtp")
4. Click "Create user"
5. **Save the SMTP username and password** - you'll need these for Terraform

### 1.3 Note Your SMTP Endpoint

The SMTP endpoint depends on your region:
- `us-east-1`: `email-smtp.us-east-1.amazonaws.com`
- `us-west-2`: `email-smtp.us-west-2.amazonaws.com`
- See [AWS SES regions](https://docs.aws.amazon.com/ses/latest/dg/regions.html) for others

## Step 2: Prepare Terraform Configuration

### 2.1 Navigate to Terraform Directory

```bash
cd terraform
```

### 2.2 Create terraform.tfvars

```bash
cp terraform.tfvars.example terraform.tfvars
```

### 2.3 Edit terraform.tfvars

```hcl
aws_region    = "us-east-1"
project_name  = "quotesapp"
instance_type = "t3.small"

# Your public IP for SSH access (recommended)
# Get your IP: curl ifconfig.me
ssh_allowed_ips = ["YOUR.IP.ADDRESS/32"]

# Your SSH public key (cat ~/.ssh/id_rsa.pub)
ssh_public_key = "ssh-rsa AAAAB3Nza... your-email@example.com"

# Generate a secure password
postgres_password = "your-secure-postgres-password"

# Generate Django secret key:
# python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
django_secret_key = "your-django-secret-key"

# AWS SES credentials (from Step 1.2)
ses_smtp_username  = "your-ses-smtp-username"
ses_smtp_password  = "your-ses-smtp-password"
ses_smtp_host      = "email-smtp.us-east-1.amazonaws.com"
ses_smtp_port      = 587
default_from_email = "noreply@yourdomain.com" # Must match verified email
```

## Step 3: Deploy Infrastructure with Terraform

### 3.1 Initialize Terraform

```bash
terraform init
```

### 3.2 Review the Plan

```bash
terraform plan
```

Review the resources that will be created:
- VPC, Subnet, Internet Gateway, Route Table
- Security Group
- EC2 Instance (t3.small)
- Elastic IP
- IAM Role for SES access

### 3.3 Apply the Configuration

```bash
terraform apply
```

Type `yes` when prompted. This will take 2-3 minutes.

### 3.4 Note the Outputs

After completion, Terraform will output:
```
public_ip = "54.123.45.67"
app_url = "http://54.123.45.67:8000"
ssh_command = "ssh -i ~/.ssh/your-key.pem ubuntu@54.123.45.67"
```

**Save these values!**

## Step 4: Deploy the Application

### 4.1 Option A: Automated Deployment Script

From your local machine:

```bash
cd ../deployment
./deploy.sh <server-ip> <path-to-ssh-key>
```

Example:
```bash
./deploy.sh 54.123.45.67 ~/.ssh/quotesapp-key.pem
```

This script will:
- Copy application files to the server
- Set up the systemd service
- Run database migrations
- Start all services

### 4.2 Option B: Manual Deployment

If you prefer to deploy manually:

1. **SSH into the server:**
   ```bash
   ssh -i ~/.ssh/your-key.pem ubuntu@<server-ip>
   ```

2. **Clone the repository:**
   ```bash
   sudo mkdir -p /opt/quotesapp
   sudo chown ubuntu:ubuntu /opt/quotesapp
   cd /opt/quotesapp
   git clone https://github.com/your-username/quotes-app.git .
   ```

3. **Create .env file:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   
   Update with your SES credentials (they should already be set by Terraform in `/opt/quotesapp/.env`)

4. **Set up systemd service:**
   ```bash
   sudo cp deployment/quotesapp.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable quotesapp
   ```

5. **Build and start services:**
   ```bash
   docker-compose build
   docker-compose run --rm quotes-app python manage.py migrate
   sudo systemctl start quotesapp
   ```

6. **Check status:**
   ```bash
   sudo systemctl status quotesapp
   docker-compose logs -f
   ```

## Step 5: Create Admin User

SSH into the server and create a superuser:

```bash
ssh -i ~/.ssh/your-key.pem ubuntu@<server-ip>
cd /opt/quotesapp
docker-compose exec quotes-app python manage.py createsuperuser
```

## Step 6: Verify Deployment

1. **Check the app is running:**
   ```bash
   curl http://<server-ip>:8000
   ```

2. **Visit in browser:**
   ```
   http://<server-ip>:8000
   ```

3. **Login and test email:**
   - Create a user with quotes
   - Trigger email manually:
     ```bash
     docker-compose exec quotes-app python manage.py shell
     >>> from quotes.tasks import send_email_task
     >>> send_email_task.delay(1)  # Replace 1 with user ID
     >>> exit()
     ```
   - Check your email inbox

## Useful Commands

### On Your Local Machine

```bash
# SSH into server
ssh -i ~/.ssh/your-key.pem ubuntu@<server-ip>

# Deploy updates
cd deployment
./deploy.sh <server-ip> ~/.ssh/your-key.pem

# View Terraform outputs
cd terraform
terraform output
```

### On the Server

```bash
# View service status
sudo systemctl status quotesapp

# View logs
cd /opt/quotesapp
docker-compose logs -f

# Restart application
sudo systemctl restart quotesapp

# Stop application
sudo systemctl stop quotesapp

# Start application
sudo systemctl start quotesapp

# Rebuild containers
docker-compose build
docker-compose up -d

# Run migrations
docker-compose exec quotes-app python manage.py migrate

# Access Django shell
docker-compose exec quotes-app python manage.py shell

# View Celery worker logs
docker-compose logs -f quotes-celery-worker

# View Celery beat logs
docker-compose logs -f quotes-celery-beat
```

## Troubleshooting

### Issue: Can't SSH into the instance

- Check security group allows your IP on port 22
- Verify you're using the correct SSH key
- Check the instance is running: `aws ec2 describe-instances`

### Issue: App not loading on port 8000

- Check security group allows 0.0.0.0/0 on port 8000
- Verify containers are running: `docker-compose ps`
- Check logs: `docker-compose logs quotes-app`

### Issue: Emails not sending

- Verify email address is verified in SES
- Check SES sending limits (sandbox mode restricts recipients)
- Verify SMTP credentials are correct
- Check Celery worker logs: `docker-compose logs quotes-celery-worker`

### Issue: Database migrations fail

- Check postgres container is healthy: `docker-compose ps`
- View postgres logs: `docker-compose logs quotes-postgres`
- Manually run migrations: `docker-compose exec quotes-app python manage.py migrate`

## Cost Estimate

Approximate monthly costs (us-east-1):
- t3.small EC2 instance: ~$15-20
- 20GB EBS volume: ~$2
- Elastic IP: Free (when attached)
- Data transfer: ~$1-5 (depending on usage)
- **Total: ~$18-27/month**

SES costs:
- First 1,000 emails/month: Free (if sending from EC2)
- After that: $0.10 per 1,000 emails

## Cleaning Up

To destroy all resources:

```bash
cd terraform
terraform destroy
```

Type `yes` when prompted. This will delete:
- EC2 instance
- Elastic IP
- Security groups
- Subnets
- VPC
- All associated resources

**Warning**: This will permanently delete your instance and all data!

## Next Steps

- Set up a domain name and SSL certificate (Route 53 + ACM)
- Configure a load balancer (ALB)
- Set up monitoring (CloudWatch)
- Move to RDS for managed PostgreSQL
- Implement automated backups
- Set up CI/CD pipeline
- Request SES production access for unrestricted sending
