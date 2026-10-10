# Quotes App

A Django-based application for managing and organizing book quotes with scheduled email reminders.

## Table of Contents

- [Local Development](#local-development)
- [AWS Deployment](#aws-deployment)
- [Features](#features)
- [Services](#services)
- [Email Testing](#email-testing)

## Local Development

### How to run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env file with your values (or use the defaults provided)
make up
```

Go to `localhost:8000` on browser to view app.

## Accessing Services

- **App**: http://localhost:8000
- **MailHog (Email Testing)**: http://localhost:8025
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

## Email Testing

The app uses **MailHog** for local email testing. All emails sent by the application will be captured by MailHog and can be viewed in the web interface at http://localhost:8025.

### Testing Email Functionality

The daily letter is the Today screen, delivered: same passages, same criteria.

1. **Create test data:**
   - Go to http://localhost:8000
   - Create a user account
   - Add at least a few passages (books or songs)

2. **Send a preview from the app:**
   - Open the account menu (your initial in the top bar) → Account
   - Choose a timezone and send time, then **Send a preview**

3. **View the email:**
   - Open http://localhost:8025 in your browser
   - You should see today's passages, with a link back to ReadReadRead

4. **Scheduled emails:**
   - Celery beat checks every 15 minutes and sends once the user's local send time has passed
   - Check the `quotes-celery-beat` logs: `docker-compose logs -f quotes-celery-beat`

## What make up does

1. Run postgres image locally with the values saved in .env
2. Run Redis for Celery task queue
3. Run MailHog for email testing
4. Build app image locally & run it once all services are ready
5. Creates a volume for postgres to persist data independently of container lifecycle

## AWS Deployment

For deploying to AWS with Terraform, see the comprehensive guide:

📖 **[AWS Deployment Guide](deployment/AWS_DEPLOYMENT.md)**

The deployment includes:
- Complete infrastructure as code (Terraform)
- Automated deployment scripts
- AWS SES integration for email
- systemd service for automatic startup
- Production-ready Docker Compose configuration
- LocalStack support for local testing

### Quick Start

**Test locally first (recommended):**
```bash
cd deployment
./test-localstack.sh
```

**Then deploy to AWS:**
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
terraform apply

# Deploy the application
cd ../deployment
./deploy.sh <server-ip> ~/.ssh/your-key.pem
```

### Testing Infrastructure Locally

Use LocalStack to test Terraform configurations locally before deploying to AWS:

📖 **[LocalStack Testing Guide](deployment/LOCALSTACK_TESTING.md)**

Benefits:
- ✅ Test IaC without AWS costs
- ✅ Validate Terraform syntax and dependencies
- ✅ Iterate quickly on infrastructure changes
- ✅ Catch errors before production deployment
- ✅ **Automatic CI validation** on every PR

## Features

- User authentication and authorization
- Quote management (create, read, update, soft delete)
- Book management with automatic creation
- Duplicate quote detection
- Daily email of today's passages, at a time you choose
- Background task processing with Celery
- Admin panel for user and content management
- Structured logging for key operations
