#!/bin/bash
# LocalStack initialization script
# This runs when LocalStack is ready

echo "Initializing LocalStack for Quotes App..."

# Verify SES email address
awslocal ses verify-email-identity --email-address test@localstack.local

# Create a verified domain (optional)
awslocal ses verify-domain-identity --domain localstack.local

echo "LocalStack initialization complete!"
echo "Verified email: test@localstack.local"
