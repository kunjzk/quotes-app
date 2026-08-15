#!/bin/bash
set -e

# Script to test Terraform infrastructure with LocalStack
# This allows you to test AWS infrastructure locally without any costs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "================================================"
echo "Testing Quotes App Infrastructure with LocalStack"
echo "================================================"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

# Check if LocalStack is running
if docker ps | grep -q quotesapp-localstack; then
    echo -e "${GREEN}✓ LocalStack is already running${NC}"
else
    echo -e "${YELLOW}Starting LocalStack...${NC}"
    cd "$PROJECT_ROOT"
    docker-compose -f docker-compose.localstack.yml up -d
    
    echo "Waiting for LocalStack to be ready..."
    sleep 10
    
    # Wait for LocalStack to be healthy
    for i in {1..30}; do
        if curl -s http://localhost:4566/_localstack/health | grep -q "running"; then
            echo -e "${GREEN}✓ LocalStack is ready${NC}"
            break
        fi
        echo "Waiting... ($i/30)"
        sleep 2
    done
fi

# Navigate to Terraform directory
cd "$TERRAFORM_DIR"

# Check if override.tf exists (would conflict with LocalStack)
if [ -f "override.tf" ]; then
    echo -e "${RED}Warning: override.tf already exists${NC}"
    echo "Please remove it or move it before testing with LocalStack"
    exit 1
fi

# Create LocalStack provider override
echo -e "${YELLOW}Creating LocalStack provider override...${NC}"
cp provider-localstack.tf override.tf

# Initialize Terraform
echo -e "${YELLOW}Initializing Terraform...${NC}"
terraform init -reconfigure

# Validate configuration
echo -e "${YELLOW}Validating Terraform configuration...${NC}"
if terraform validate; then
    echo -e "${GREEN}✓ Terraform configuration is valid${NC}"
else
    echo -e "${RED}✗ Terraform configuration is invalid${NC}"
    rm override.tf
    exit 1
fi

# Plan
echo ""
echo -e "${YELLOW}Running Terraform plan...${NC}"
if terraform plan -var-file="localstack.tfvars" -out=localstack.tfplan; then
    echo -e "${GREEN}✓ Terraform plan succeeded${NC}"
else
    echo -e "${RED}✗ Terraform plan failed${NC}"
    rm override.tf
    exit 1
fi

# Ask if user wants to apply
echo ""
echo -e "${YELLOW}Do you want to apply this plan to LocalStack? (y/N)${NC}"
read -r response

if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo -e "${YELLOW}Applying Terraform configuration to LocalStack...${NC}"
    if terraform apply localstack.tfplan; then
        echo ""
        echo -e "${GREEN}✓ Terraform apply succeeded${NC}"
        echo ""
        echo "=== Terraform Outputs ==="
        terraform output
        echo ""
        echo -e "${GREEN}Infrastructure created in LocalStack!${NC}"
        echo ""
        echo "Note: LocalStack limitations:"
        echo "- EC2 instances are mocked (not actually created)"
        echo "- Some features may not work exactly like AWS"
        echo "- Great for testing IaC syntax and logic"
    else
        echo -e "${RED}✗ Terraform apply failed${NC}"
    fi
else
    echo "Skipping apply"
    rm localstack.tfplan
fi

# Cleanup prompt
echo ""
echo -e "${YELLOW}Clean up? (y/N)${NC}"
echo "This will:"
echo "  - Destroy Terraform resources in LocalStack"
echo "  - Remove override.tf"
echo "  - Stop LocalStack container"
read -r cleanup_response

if [[ "$cleanup_response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo -e "${YELLOW}Cleaning up...${NC}"
    
    # Destroy Terraform resources
    terraform destroy -var-file="localstack.tfvars" -auto-approve || true
    
    # Remove override file
    rm -f override.tf
    rm -f localstack.tfplan
    
    # Stop LocalStack
    cd "$PROJECT_ROOT"
    docker-compose -f docker-compose.localstack.yml down
    
    echo -e "${GREEN}✓ Cleanup complete${NC}"
else
    echo "Keeping LocalStack running"
    echo "To clean up later, run:"
    echo "  cd $TERRAFORM_DIR && rm override.tf"
    echo "  cd $PROJECT_ROOT && docker-compose -f docker-compose.localstack.yml down"
fi

echo ""
echo "================================================"
echo "Testing complete!"
echo "================================================"
