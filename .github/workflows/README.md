# GitHub Actions Workflows

This directory contains CI/CD workflows for the Quotes App.

## Workflows

### 1. `docker.yml` - Application Build and Test

**Triggers:** Push/PR to `main` branch

**Jobs:**
- **build** - Builds Docker image and saves as artifact
- **test** - Runs Django tests with PostgreSQL
- **publish** - Pushes image to GHCR (main branch only)

**Purpose:** Ensures application code builds and tests pass

### 2. `terraform-localstack.yml` - Infrastructure Validation

**Triggers:** 
- Push/PR when `terraform/**` files change
- Manual workflow dispatch

**Jobs:**
- **terraform-validate** - Tests Terraform with LocalStack
  - Validates syntax
  - Runs `terraform plan`
  - Applies configuration to LocalStack
  - Verifies resources created
  - Cleans up
  - Comments on PR with results

- **terraform-security-scan** - Security analysis with tfsec
  - Scans for security issues
  - Checks best practices
  - Reports vulnerabilities

- **terraform-cost-estimate** - Cost estimation with Infracost
  - Estimates monthly AWS costs
  - Shows cost diff on PRs
  - Requires `INFRACOST_API_KEY` secret

**Purpose:** Validates infrastructure changes before AWS deployment

## Why LocalStack in CI?

### ✅ Benefits

1. **Early error detection** - Catch IaC issues before code review
2. **Zero AWS costs** - No test infrastructure charges
3. **Fast feedback** - ~2-5 minutes vs 10+ for real AWS
4. **Safe testing** - No risk to production resources
5. **Consistent environment** - Same test setup every time
6. **PR confidence** - Automated validation comments

### 📊 What Gets Tested

- ✅ Terraform syntax and formatting
- ✅ Resource plan generation
- ✅ Resource creation (in LocalStack)
- ✅ Resource dependencies
- ✅ Outputs validation
- ✅ Security best practices (tfsec)
- ✅ Cost estimates (Infracost)

### ⚠️ Limitations

LocalStack tests validate IaC logic but don't test:
- Actual EC2 instance startup
- Real network connectivity
- Actual application deployment
- Production-like performance

**These are tested in staging/production deployments.**

## Setup

### Required Secrets

None required for basic functionality!

### Optional Secrets

- `INFRACOST_API_KEY` - For cost estimation
  - Get free API key at https://www.infracost.io/
  - Add to repository secrets

## Workflow Status

View workflow runs:
```bash
gh run list --workflow=docker.yml
gh run list --workflow=terraform-localstack.yml
```

View specific run:
```bash
gh run view <run-id>
gh run view <run-id> --log
```

## Local Testing

Test what CI will do:

### Application Tests
```bash
# Run tests locally (same as CI)
make test
```

### Infrastructure Tests
```bash
# Run LocalStack tests (same as CI)
cd deployment
./test-localstack.sh
```

## Debugging Failed Workflows

### Application Build Failure
1. Check Docker build logs
2. Verify `requirements.txt` is valid
3. Test locally: `docker build -t quotes-app .`

### Application Test Failure
1. Check test output in logs
2. Verify database connection
3. Test locally: `make test`

### Terraform Validation Failure
1. Check Terraform error message
2. Validate syntax: `cd terraform && terraform validate`
3. Test locally: `./deployment/test-localstack.sh`
4. Check if `provider-localstack.tf` is properly formatted

### Security Scan Issues
1. Review tfsec findings
2. Check [tfsec documentation](https://aquasecurity.github.io/tfsec/)
3. Fix or suppress (if false positive)

## Adding New Workflows

### Best Practices

1. **Name descriptively** - Clear workflow and job names
2. **Trigger appropriately** - Use path filters
3. **Run parallel** - Independent jobs should run concurrently
4. **Comment on PRs** - Provide feedback to developers
5. **Cache dependencies** - Speed up workflow runs
6. **Use actions versions** - Pin to major versions (e.g., `@v4`)

### Example Workflow Structure

```yaml
name: Descriptive Name

on:
  pull_request:
    paths:
      - 'relevant/path/**'

jobs:
  job-name:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Do something
        run: echo "Hello"
```

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [LocalStack Documentation](https://docs.localstack.cloud/)
- [tfsec Documentation](https://aquasecurity.github.io/tfsec/)
- [Infracost Documentation](https://www.infracost.io/docs/)
