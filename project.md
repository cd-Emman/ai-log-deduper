# Project Journey: AI Log Deduper

This document covers the system architecture, codebase layout, troubleshooting logs, and milestones for the AI Log Deduper project.

---

## 1. How the Pipeline Works

```mermaid
flowchart TD
    A[Chaos Generator Script] -->|POST Raw Logs| B[FastAPI Gateway]
    B -->|Publish| C[Amazon SQS]
    C -->|Trigger| D[AWS Lambda]
    C -->|Failed 3x| H[SQS DLQ]
    D -->|Conditional Check| E[(Amazon DynamoDB)]
    D -->|Generate Analysis| F[Gemini Developer API]
    D -->|Post Alert| G[Discord / Slack Webhook]
```

### Architectural Decisions and Trade-offs

An asynchronous SQS-to-Lambda queue architecture was selected to act as a buffer. This design protects the Gemini API from being overloaded by sudden bursts of raw application logs. Offloading log ingestion to the FastAPI gateway and buffering messages in SQS ensures the client receives an immediate response while allowing Lambda to process messages sequentially within API rate limits.

---

## 2. Codebase Structure

Here is the file structure and the purpose of each component in the repository:

### Foundational Configurations
- [.gitignore](./.gitignore): Excludes Python caches, virtual environments, and local credentials from Git.
- [.env.example](./.env.example): Template for local environment variables (API keys, SQS URLs).
- [docker-compose.yml](./docker-compose.yml): Configures LocalStack to emulate AWS SQS, DynamoDB, and SSM offline.
- [localstack-init.sh](./localstack-init.sh): Startup script to initialize AWS resources in LocalStack.
- [lambda_local_runner.py](./lambda_local_runner.py): Local script that polls SQS and runs the Lambda handler offline.

### Chaos Generator
- [chaos_generator/](./chaos_generator/): Test scripts to simulate application errors.
- [chaos.py](./chaos_generator/chaos.py): Simulator script that posts random tracebacks to the gateway every 10 seconds.
- [requirements.txt](./chaos_generator/requirements.txt): Dependencies for the simulator.

### FastAPI Gateway
- [gateway/](./gateway/): Gateway service code.
- [main.py](./gateway/main.py): FastAPI application that ingests logs, validates payloads, and sends messages to SQS.
- [Dockerfile](./gateway/Dockerfile): Docker build instructions for the gateway service.
- [requirements.txt](./gateway/requirements.txt): Python dependencies for the gateway.

### Lambda Processor
- [lambda/](./lambda/): Deduplication logic.
- [lambda_function.py](./lambda/lambda_function.py): AWS Lambda handler. Computes log MD5 hashes, performs the DynamoDB duplicate check, retrieves Gemini summaries, and posts alerts.
- [requirements.txt](./lambda/requirements.txt): Packaging requirements for the Lambda zip.

### Terraform Infrastructure (IaC)
- [terraform/](./terraform/): Terraform configuration files.
- [main.tf](./terraform/main.tf): Resource definitions including SQS queues, DLQ, IAM roles, Lambda triggers, DynamoDB table, and the CloudWatch dashboard.
- [ec2.tf](./terraform/ec2.tf): Provisions the m7i-flex.large EC2 instance, security groups, and IAM instance profile to host the FastAPI gateway container.
- [backend.tf](./terraform/backend.tf): Configures the remote S3 and DynamoDB backend for Terraform state tracking.
- [providers.tf](./terraform/providers.tf): Declares required providers (AWS, archive) and version constraints.
- [variables.tf](./terraform/variables.tf): Configures inputs like AWS region and SSM parameters.
- [outputs.tf](./terraform/outputs.tf): Declares resource outputs like SQS URLs and Lambda ARNs.
- [vpc.tf](./terraform/vpc.tf): Declares VPC configuration for the network layout.
- [terraform.tfvars](./terraform/terraform.tfvars): Local variable values (API keys and webhooks).

### Remote Backend Setup
- [terraform/bootstrap/](./terraform/bootstrap/): Setup files for the remote backend.
- [bootstrap/main.tf](./terraform/bootstrap/main.tf): Creates the S3 bucket and DynamoDB locking table used for Terraform remote state.
- [bootstrap/providers.tf](./terraform/bootstrap/providers.tf): Provider details for the bootstrap stage.
- [bootstrap/variables.tf](./terraform/bootstrap/variables.tf): Input variables for the bootstrap workspace.

### CI/CD Workflow
- [.github/workflows/deploy.yml](./.github/workflows/deploy.yml): GitHub Actions workflow. Runs Ruff linting, unit tests, security scans (TFLint, Checkov, Trivy), builds/pushes the Docker image, and runs `terraform apply`.

---

## 3. Comprehensive Troubleshooting Log

Issues encountered during development and how they were resolved:

### Terraform & State Infrastructure

#### Sensitive plan secrets committed
- **Symptom**: Terraform plan files (`tfplan`) showing up in git diffs.
- **Cause**: Plaintext plan files were not defined in `.gitignore`.
- **Fix**: Added `*.plan` and `*plan*` patterns to `.gitignore`.

#### Stale terraform plans
- **Symptom**: Deployments ignored recent code changes.
- **Cause**: Running `terraform apply tfplan` using a plan file generated before the code files were changed.
- **Fix**: Regenerate plans (`terraform plan -out=tfplan`) after modifying code files.

#### SQS trigger mapping missing
- **Symptom**: Deployments returned no executions in CloudWatch.
- **Cause**: Destroying a single table cascaded and deleted the triggering handler.
- **Fix**: Switched to full, untargeted `terraform apply` runs to restore dependencies.

#### Lambda reserved concurrency errors
- **Symptom**: Concurrency assignment errors during deployments.
- **Cause**: Sandboxed AWS accounts require 10 unreserved concurrent executions, making reservations impossible.
- **Fix**: Reverted concurrency configuration to `-1`.

#### Local state files lost during CI/CD execution
- **Symptom**: Local state files (`terraform.tfstate`) lost on ephemeral runner runs.
- **Cause**: Local backend store is non-persistent across environments.
- **Fix**: Deployed S3 state bucket and DynamoDB locking table, migrated state using `terraform init -migrate-state`, and deleted local state files.

#### Backend resources destroyed during standard application teardown
- **Symptom**: Running `terraform destroy` in the main workspace attempted to delete the S3 state bucket and DynamoDB locking table, breaking remote backend access.
- **Cause**: Backend infrastructure was defined in the same workspace and state file as the application resources.
- **Fix**: Refactored backend resources into a separate directory (`terraform/bootstrap/`). Ran `terraform state rm` to decouple them from the main workspace database, ensuring they remain untouched during future application teardowns.

#### TFLint failure due to missing archive provider version constraint
- **Symptom**: TFLint failed in the CI/CD pipeline with `Warning: Missing version constraint for provider "archive"`.
- **Cause**: The `archive` provider was used in `terraform/main.tf` but was not declared in the `required_providers` block inside `terraform/providers.tf`.
- **Fix**: Added the `hashicorp/archive` provider with its version constraint to the `required_providers` block in `providers.tf`.

### Docker & CI/CD Pipeline Issues

#### GitHub Actions linting failure due to import ordering
- **Symptom**: Linting job failed with exit code 1.
- **Cause**: Ruff flagged E402 errors in `lambda_function.py` because `boto3` and `ClientError` were imported after the logging configurations.
- **Fix**: Moved all imports to the very top of `lambda_function.py`.

#### Docker image build/push fails due to uppercase username
- **Symptom**: The build-and-push job failed with error `repository name must be lowercase`.
- **Cause**: The repository owner identifier `cd-Emman` contains a capital letter 'E'. Docker tag specifications enforce lowercase letters.
- **Fix**: Added a bash step in `deploy.yml` using `tr '[:upper:]' '[:lower:]'` to dynamically convert the username to lowercase and referenced it in the image tags.

#### GitHub Actions linting failure due to E402 imports in tests
- **Symptom**: Ruff checks in the CI/CD pipeline failed with `E402 Module level import not at top of file`.
- **Cause**: Python module imports (`os`/`sys`) were placed after helper logic, and the dynamic Lambda module import was flagged inside the mock patch context.
- **Fix**: Refactored `os`/`sys` imports to the top of `test_lambda.py` and added a `# noqa: E402` ignore flag to the dynamic `import lambda_function` statement.

#### LocalStack container exits with license activation failure
- **Symptom**: Container logs showed `Localstack returning with exit code 55. Reason: License activation failed!`
- **Cause**: Newer versions of LocalStack (2026.3.0+) require a valid auth token environment variable even for community features.
- **Fix**: Pinned the LocalStack image to version 3.8.0 in `docker-compose.yml` to run completely offline without an auth token.

#### Deployments ignored recent gateway code changes
- **Symptom**: Commits to the gateway service did not trigger updates on the live EC2 instance, causing the server to run outdated code.
- **Cause**: The Terraform EC2 user data referenced the static `latest` Docker tag. Because the image name string did not change, Terraform saw no differences and skipped redeploying the EC2 instance.
- **Fix**: Updated `.github/workflows/deploy.yml` to dynamically pass the unique Git commit SHA (`${{ github.sha }}`) as the `TF_VAR_gateway_image` variable to Terraform, forcing instance redeployments on every new push.

### API & Integration Errors

#### Gemini API HTTP 404 Error
- **Symptom**: Requesting summaries from Gemini failed with a 404.
- **Cause**: Endpoint was targeting the deprecated model name `gemini-1.5-flash`.
- **Fix**: Updated endpoint in `lambda_function.py` to target `gemini-2.5-flash`.

#### Webhook alert rejected with HTTP 403 Forbidden
- **Symptom**: Webhook payloads were rejected by Discord.
- **Cause**: Discord blocks default Python `urllib` user-agent strings.
- **Fix**: Added a standard browser-like `User-Agent` header to our request payload.

#### Gemini API rate limit HTTP 429
- **Symptom**: Bursts of unique events failed with 429 errors from Google.
- **Cause**: Default SQS configuration batched 10 messages, firing them all concurrently and triggering limits.
- **Fix**: Set `batch_size = 1` in Terraform and updated chaos sleep interval to 10 seconds.

#### Lambda Timeout during API Retries
- **Symptom**: Lambda execution timed out after 15 seconds.
- **Cause**: Exponential backoff sleeps (2, 4, 8 seconds) exceeded the execution limit.
- **Fix**: Implemented a fail-fast fallback: if the API returns rate limits, immediately send raw tracebacks to Discord.

#### Sliding window rate limits
- **Symptom**: Success rate degraded on back-to-back testing.
- **Cause**: Gemini Free Tier rate-limiting rules.
- **Fix**: Allowed the rate-limit window to reset before initiating next testing phase.

#### Peak capacity API drops (503 Service Unavailable)
- **Symptom**: Standard logs dropped during sequential processing.
- **Cause**: Peak burst loads on the Gemini Free Tier endpoint.
- **Fix**: Built an exponential backoff loop inside `lambda_function.py` to retry on 429 and 503 errors.

#### Unconfigured Gemini API key posted plain skip message instead of raw log
- **Symptom**: Leaving the Gemini API key blank or set to a mock string caused the Lambda to send `"Gemini API key not configured. Logging error analysis skipped."` as the Discord notification payload rather than falling back to the raw log layout.
- **Cause**: The fallback checks in `lambda_function.py` only caught errors containing `"Error analyzing log via Gemini"`, bypassing the unconfigured check.
- **Fix**: Refactored the code to return `None` on unconfigured or mock keys, and modified the fallback check to automatically trigger the raw log layout if the analysis is empty.

### Local Development & Testing

#### Chaos generator would not stop via Ctrl + C
- **Symptom**: Pressing Ctrl + C did not terminate `chaos.py`.
- **Cause**: Network calls blocked the signal handler in the Python console.
- **Fix**: Terminated the process group using `pkill -f chaos.py`.

#### FastAPI gateway fails with uvicorn: command not found
- **Symptom**: Starting the gateway inside the venv failed.
- **Cause**: Gateway requirements were not installed inside the active virtual environment session.
- **Fix**: Installed dependencies with `pip install -r gateway/requirements.txt`.

#### Lambda context object crash
- **Symptom**: Logs reported `AttributeError: LambdaContext object has no attribute epoch_now_ms`.
- **Cause**: Standard AWS Context does not provide timestamp attributes.
- **Fix**: Replaced it with Python's built-in `int(time.time())` function.

#### VPC Lambda DNS Resolution Failure
- **Symptom**: Deploying inside a private VPC subnet blocked outbound network activity.
- **Cause**: Security Group egress rules blocked TCP/UDP port 53.
- **Fix**: Opened Security Group egress blocks to allow all outbound traffic.

#### NAT Gateway IP-Level rate limits
- **Symptom**: Running inside the VPC triggered persistent 429 errors from Google.
- **Cause**: Traffic routing through one NAT Gateway concentrated all requests on a single IP.
- **Fix**: Removed VPC configurations in `terraform/main.tf` to use rotating AWS public IPs.

#### Lambda swallowed exceptions blocking SQS DLQ redrive
- **Symptom**: Failed messages were consumed but never routed to the Dead Letter Queue (DLQ).
- **Cause**: The Lambda event handler caught all general exceptions and returned a 200 status, which caused SQS to delete the message instead of retrying it.
- **Fix**: Updated `lambda_function.py` to raise the exception on processing errors, forcing SQS to trigger retries and correctly move the message to the DLQ after 3 failures.

#### Pytest gateway import failure (ModuleNotFoundError)
- **Symptom**: Running `pytest` returned `ModuleNotFoundError: No module named 'gateway'`.
- **Cause**: The repository root directory was not included in Python's search path (`sys.path`) during collection.
- **Fix**: Executed Pytest using the `python -m pytest` command, which automatically prepends the current working directory to `sys.path`.

#### Pytest ValueError: unknown url type: 'mock-secret'
- **Symptom**: The Lambda unit test failed with `ValueError: unknown url type: 'mock-secret'`.
- **Cause**: The mock SSM parameters returned a plaintext mock key for the webhook URL, which `urllib` rejected as invalid.
- **Fix**: Updated the mocked parameter logic in `test_lambda.py` to return a valid HTTPS URL scheme for keys containing `webhook`.

#### AWS CLI fails to put SSM parameter containing HTTP URL
- **Symptom**: Parameter creation failed with `Error parsing parameter '--value': Unable to retrieve http://localhost:8000/mock-webhook: Could not connect to the endpoint URL`.
- **Cause**: AWS CLI automatically attempts to fetch the contents of arguments starting with `http://` or `https://` as external resources.
- **Fix**: Added `awslocal configure set cli_follow_urlparam false` to the top of `localstack-init.sh` to disable this automatic download behavior.

---

## 4. Completed Milestones & Roadmap

- ✔ **CI/CD Pipeline Automation**: Created a GitHub Actions workflow to run Ruff, build/push the FastAPI Docker container, and run `terraform apply` automatically on pushes to `master`.
- ✔ **Infrastructure Resilience**: Set up SQS DLQ with a `maxReceiveCount` of 3 to isolate failed logs, and implemented a redrive mechanism to re-process them.
- ✔ **Security Enhancements (SSM)**: Swapped plaintext variables for AWS Systems Manager (SSM) Parameter Store SecureString parameters to fetch keys at runtime.
- ✔ **CI/CD Security Scanners**: Integrated Checkov, TFLint, and Trivy scanning into the CI/CD pipeline.
- ✔ **Automated Testing**: Integrated Pytest into the pipeline to test FastAPI and Lambda logic.
- ✔ **Local Development Infrastructure**: Configured `docker-compose.yml` with LocalStack to run the queue, database, and parameter store offline.
- ✔ **Infrastructure Monitoring**: Created a custom CloudWatch dashboard tracking SQS queue metrics, Lambda errors, and DynamoDB capacity.
- ✔ **FastAPI Gateway Cloud Deployment**: Migrated the FastAPI ingestion gateway from local Docker environments to a live, self-hosted EC2 instance (m7i-flex.large) running Docker via User Data automation.
