# Terraform Infrastructure for Quotes App

This directory contains Terraform configuration to deploy the Quotes App infrastructure on AWS.

## What Gets Created

- **VPC** (10.0.0.0/16) with public subnet
- **Internet Gateway** for internet access
- **Security Group** with SSH and HTTP access
- **EC2 Instance** (t3.small) running Ubuntu 24.04
- **Elastic IP** for static public IP address
- **IAM Role** for SES email access

## Quick Start

1. **Copy and configure variables:**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your values
   ```

2. **Initialize Terraform:**
   ```bash
   terraform init
   ```

3. **Review the plan:**
   ```bash
   terraform plan
   ```

4. **Apply the configuration:**
   ```bash
   terraform apply
   ```

5. **Note the outputs:**
   ```bash
   terraform output
   ```

## Required Variables

See `terraform.tfvars.example` for all required variables:

- `ssh_public_key` - Your SSH public key for EC2 access
- `postgres_password` - PostgreSQL database password
- `django_secret_key` - Django secret key (generate with Python)
- `ses_smtp_username` - AWS SES SMTP username
- `ses_smtp_password` - AWS SES SMTP password
- `default_from_email` - Verified email address in SES

## Files

- `main.tf` - Main infrastructure configuration
- `variables.tf` - Variable definitions
- `outputs.tf` - Output values
- `user-data.sh` - Instance bootstrap script
- `terraform.tfvars.example` - Example variables file

## Outputs

After successful apply, you'll get:

- `public_ip` - Elastic IP address of the instance
- `app_url` - Direct URL to access the application
- `ssh_command` - Command to SSH into the instance
- `instance_id` - EC2 instance ID
- `vpc_id` - VPC ID
- `subnet_id` - Public subnet ID
- `security_group_id` - Security group ID

## Managing the Infrastructure

### View Current State
```bash
terraform show
```

### Update Infrastructure
```bash
# Make changes to .tf files
terraform plan
terraform apply
```

### Destroy Infrastructure
```bash
terraform destroy
```

**Warning:** This will permanently delete all resources!

## Cost Estimate

Approximate monthly costs (us-east-1):
- t3.small instance: ~$15-20/month
- 20GB EBS volume: ~$2/month
- Elastic IP: Free (when attached)
- Data transfer: ~$1-5/month
- **Total: ~$18-27/month**

## Security Considerations

### For Production

1. **Restrict SSH access:**
   ```hcl
   ssh_allowed_ips = ["YOUR.IP.ADDRESS/32"]
   ```

2. **Enable encryption:**
   - Root volume encryption is enabled by default
   - Consider using AWS Secrets Manager for sensitive data

3. **Network security:**
   - Consider using a bastion host for SSH access
   - Use a load balancer for HTTPS termination

4. **IAM permissions:**
   - Review and restrict IAM role permissions as needed
   - Follow principle of least privilege

## Troubleshooting

### SSH Connection Issues

- Verify security group allows your IP on port 22
- Check you're using the correct SSH key
- Ensure the instance is running

### Instance Not Starting

- Check user-data script logs: `/var/log/user-data.log`
- Verify all variables are set correctly
- Check CloudWatch logs

### Terraform State Issues

If state becomes corrupted:
```bash
terraform state list
terraform state show <resource>
terraform import <resource> <id>
```

## State Management

The Terraform state file contains sensitive information. For production:

1. **Use remote state:**
   ```hcl
   terraform {
     backend "s3" {
       bucket = "my-terraform-state"
       key    = "quotesapp/terraform.tfstate"
       region = "us-east-1"
     }
   }
   ```

2. **Enable state locking with DynamoDB**

3. **Never commit state files to git** (already in .gitignore)

## Next Steps

After infrastructure is created:

1. Follow the [AWS Deployment Guide](../deployment/AWS_DEPLOYMENT.md)
2. Deploy the application using deployment scripts
3. Configure monitoring and backups
4. Set up CI/CD pipeline
