# LocalStack provider override
# This file is ignored by default (see .terraform.tfignore)
# Rename to override.tf when testing with LocalStack

# To use LocalStack:
# 1. Start LocalStack: docker-compose -f docker-compose.localstack.yml up -d
# 2. Copy this file: cp provider-localstack.tf override.tf
# 3. Run terraform: terraform init && terraform apply -var-file="localstack.tfvars"
# 4. Clean up: rm override.tf when done

provider "aws" {
  region                      = var.aws_region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    ec2            = "http://localhost:4566"
    vpc            = "http://localhost:4566"
    iam            = "http://localhost:4566"
    ses            = "http://localhost:4566"
    secretsmanager = "http://localhost:4566"
  }
}
