# Terraform variables for LocalStack testing
# Use with: terraform apply -var-file="localstack.tfvars"

aws_region    = "us-east-1"
project_name  = "quotesapp-local"
instance_type = "t3.small"

# For LocalStack, these don't need to be real
ssh_allowed_ips = ["0.0.0.0/0"]

# Generate a dummy SSH key for testing
# ssh-keygen -t rsa -b 2048 -f ~/.ssh/quotesapp-localstack -N ""
# Then paste the public key here
ssh_public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLocalStackTestKey localstack@test"

# Test credentials (not real, just for LocalStack)
postgres_password = "localstack-postgres-password"
django_secret_key = "localstack-django-secret-key-for-testing-only"

# SES configuration (LocalStack mocks SES)
ses_smtp_username  = "localstack-ses-user"
ses_smtp_password  = "localstack-ses-pass"
ses_smtp_host      = "localhost"
ses_smtp_port      = 4566
default_from_email = "test@localstack.local"
