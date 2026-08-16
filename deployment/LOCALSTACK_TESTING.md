# Testing AWS Infrastructure with LocalStack

This guide shows you how to test the Terraform infrastructure locally using LocalStack before deploying to real AWS.

## What is LocalStack?

LocalStack is a fully functional local AWS cloud stack that runs in Docker. It emulates AWS services, allowing you to:
- Test infrastructure as code without AWS costs
- Develop and test locally without internet connection
- Iterate quickly on IaC scripts
- Catch errors before deploying to production

## Prerequisites

- Docker and Docker Compose installed
- Terraform installed
- Basic understanding of AWS services

## Quick Start

### Option 1: Automated Testing Script (Recommended)

```bash
cd deployment
./test-localstack.sh
```

This script will:
1. Start LocalStack container
2. Configure Terraform for LocalStack
3. Run `terraform plan`
4. Optionally apply the configuration
5. Show outputs
6. Optionally clean up everything

### Option 2: Manual Testing

#### 1. Start LocalStack

```bash
docker-compose -f docker-compose.localstack.yml up -d
```

Wait for LocalStack to be ready:
```bash
# Check health
curl http://localhost:4566/_localstack/health
```

#### 2. Configure Terraform for LocalStack

```bash
cd terraform

# Create provider override for LocalStack
cp provider-localstack.tf.example override.tf
```

#### 3. Initialize and Test

```bash
# Initialize Terraform with LocalStack configuration
terraform init -reconfigure

# Validate configuration
terraform validate

# Plan (using LocalStack variables)
terraform plan -var-file="localstack.tfvars"

# Apply
terraform apply -var-file="localstack.tfvars"
```

#### 4. Inspect Resources

```bash
# View Terraform outputs
terraform output

# Query LocalStack directly
docker-compose -f ../docker-compose.localstack.yml exec localstack \
  awslocal ec2 describe-instances

# Or use the awscli container
docker exec -it quotesapp-awscli \
  aws --endpoint-url=http://localstack:4566 ec2 describe-vpcs
```

#### 5. Clean Up

```bash
# Destroy resources
terraform destroy -var-file="localstack.tfvars" -auto-approve

# Remove override file
rm override.tf

# Stop LocalStack
cd ..
docker-compose -f docker-compose.localstack.yml down
```

## LocalStack Configuration

### Services Emulated

The `docker-compose.localstack.yml` configures these AWS services:
- **EC2** - Virtual machines (mocked)
- **VPC** - Virtual private cloud
- **IAM** - Identity and access management
- **SES** - Simple email service (mocked)
- **Secrets Manager** - Secrets storage

### Endpoints

- **LocalStack Gateway**: http://localhost:4566
- **Health Check**: http://localhost:4566/_localstack/health

### Credentials

LocalStack doesn't require real AWS credentials:
```bash
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
```

## Testing SES Locally

LocalStack mocks SES:

```bash
# Verify email address
docker exec quotesapp-localstack \
  awslocal ses verify-email-identity \
  --email-address test@localstack.local

# List verified emails
docker exec quotesapp-localstack \
  awslocal ses list-verified-email-addresses

# Send test email
docker exec quotesapp-localstack \
  awslocal ses send-email \
  --from test@localstack.local \
  --to user@example.com \
  --subject "Test Email" \
  --text "This is a test"
```

## LocalStack Limitations

### What Works Well
✅ VPC, Subnet, Route Table, Internet Gateway creation
✅ Security Group configuration
✅ IAM Role and Policy creation
✅ SES email verification (mocked)
✅ Terraform state management
✅ Resource dependencies and ordering

### What Has Limitations
⚠️ **EC2 Instances**: Created but not actually running (mocked)
⚠️ **Elastic IPs**: Created but not actually routable
⚠️ **AMI Lookups**: May return mock data
⚠️ **User Data Scripts**: Won't actually execute
⚠️ **SSH Access**: Can't actually SSH to mocked instances
⚠️ **Network Connectivity**: No actual network communication

### Free vs Pro

**LocalStack Community (Free)**:
- Basic AWS services
- Good for IaC validation
- No persistence by default

**LocalStack Pro** (Paid):
- More services and features
- Better EC2 simulation
- State persistence
- CI/CD integrations

For our use case, the **free version is sufficient** for testing Terraform syntax and resource relationships.

## Common Use Cases

### 1. Validate Terraform Syntax

```bash
./test-localstack.sh
# Select 'N' when asked to apply
```

This validates your `.tf` files without creating any resources.

### 2. Test Resource Dependencies

```bash
./test-localstack.sh
# Select 'y' to apply
# Check the order of resource creation
```

Ensures resources are created in the correct order.

### 3. Test Variable Configurations

```bash
cd terraform

# Edit localstack.tfvars with different values
vim localstack.tfvars

# Test with new variables
terraform plan -var-file="localstack.tfvars"
```

### 4. Debug Terraform Issues

```bash
cd terraform
cp provider-localstack.tf override.tf

# Enable detailed logging
export TF_LOG=DEBUG
terraform apply -var-file="localstack.tfvars"
```

### 5. Test IAM Policies

```bash
docker exec quotesapp-awscli \
  aws --endpoint-url=http://localstack:4566 \
  iam get-role --role-name quotesapp-local-ec2-role
```

## Troubleshooting

### LocalStack Won't Start

```bash
# Check Docker is running
docker info

# Check logs
docker-compose -f docker-compose.localstack.yml logs -f

# Remove old containers
docker-compose -f docker-compose.localstack.yml down -v
docker-compose -f docker-compose.localstack.yml up -d
```

### Terraform Can't Connect

```bash
# Verify LocalStack is healthy
curl http://localhost:4566/_localstack/health

# Check if override.tf was created
ls -la terraform/override.tf

# If missing, create it
cd terraform
cp provider-localstack.tf.example override.tf

# Verify provider configuration
cat override.tf
```

### "Resource Already Exists" Error

```bash
# Clean up LocalStack state
docker-compose -f docker-compose.localstack.yml down -v
docker-compose -f docker-compose.localstack.yml up -d

# Clean Terraform state
cd terraform
rm -f terraform.tfstate*
terraform init -reconfigure
```

### Port 4566 Already in Use

```bash
# Find what's using the port
lsof -i :4566
# or
netstat -anp | grep 4566

# Kill the process or change LocalStack port in docker-compose.localstack.yml
```

## Best Practices

### 1. Always Clean Up

```bash
# Always destroy resources when done
terraform destroy -var-file="localstack.tfvars" -auto-approve

# Remove override.tf to avoid confusion
rm terraform/override.tf
```

### 2. Use Separate State

LocalStack uses separate Terraform state from real AWS. Don't mix them!

### 3. Test Before AWS Deployment

```bash
# 1. Test with LocalStack
./deployment/test-localstack.sh

# 2. If successful, deploy to AWS
cd terraform
terraform init  # Uses real AWS provider
terraform apply -var-file="terraform.tfvars"
```

### 4. Version Control

Never commit:
- `terraform/override.tf` (LocalStack override)
- `terraform/localstack.tfplan` (Plan file)
- `volume/` (LocalStack data)

These are already in `.gitignore`.

## Integration with CI/CD

LocalStack is **already integrated** into the CI pipeline! See `.github/workflows/terraform-localstack.yml`.

### What the CI Does

Every time you modify Terraform files, the CI automatically:
1. ✅ Starts LocalStack
2. ✅ Validates Terraform syntax
3. ✅ Runs `terraform plan`
4. ✅ Applies configuration to LocalStack
5. ✅ Verifies resources were created
6. ✅ Runs security scan (tfsec)
7. ✅ Estimates costs (Infracost)
8. ✅ Comments on PR with results

### Viewing CI Results

```bash
# List recent workflow runs
gh run list --workflow=terraform-localstack.yml

# View specific run
gh run view <run-id> --log
```

### CI Workflow Structure

```yaml
name: Terraform LocalStack Tests

on:
  pull_request:
    paths:
      - 'terraform/**'

jobs:
  terraform-validate:
    runs-on: ubuntu-latest
    services:
      localstack:
        image: localstack/localstack:latest
        ports:
          - 4566:4566
    steps:
      - name: Validate Terraform
      - name: Plan with LocalStack
      - name: Apply to LocalStack
      - name: Verify Resources
      - name: Comment on PR
```

See [`.github/workflows/README.md`](../.github/workflows/README.md) for full documentation.

### Benefits of CI Integration

- 🚀 **Automatic validation** - Every PR is tested
- 💬 **PR comments** - Results posted directly to PR
- 🔒 **Prevents bad merges** - Catch errors before merge
- 📊 **Cost visibility** - See infrastructure costs
- 🔐 **Security checks** - Automated security scanning

## Useful Commands

### LocalStack Management
```bash
# Start LocalStack
docker-compose -f docker-compose.localstack.yml up -d

# View logs
docker-compose -f docker-compose.localstack.yml logs -f

# Stop LocalStack
docker-compose -f docker-compose.localstack.yml down

# Completely remove (including volumes)
docker-compose -f docker-compose.localstack.yml down -v
```

### AWS CLI with LocalStack
```bash
# Using docker exec
docker exec quotesapp-awscli \
  aws --endpoint-url=http://localstack:4566 \
  <service> <command>

# Or install awslocal wrapper
pip install awscli-local
awslocal s3 ls
```

### Inspect Resources
```bash
# List VPCs
docker exec quotesapp-awscli \
  aws --endpoint-url=http://localstack:4566 vpc describe-vpcs

# List EC2 instances
docker exec quotesapp-awscli \
  aws --endpoint-url=http://localstack:4566 ec2 describe-instances

# List IAM roles
docker exec quotesapp-awscli \
  aws --endpoint-url=http://localstack:4566 iam list-roles
```

## Resources

- [LocalStack Documentation](https://docs.localstack.cloud/)
- [LocalStack GitHub](https://github.com/localstack/localstack)
- [Terraform with LocalStack](https://docs.localstack.cloud/user-guide/integrations/terraform/)
- [LocalStack Pro Features](https://localstack.cloud/pricing/)

## Summary

LocalStack is a powerful tool for testing AWS infrastructure locally:
- ✅ **Free** for basic services
- ✅ **Fast** - no waiting for AWS
- ✅ **Safe** - no costs or accidental deletions
- ✅ **Offline** - works without internet

Use it to validate your Terraform before deploying to real AWS!
