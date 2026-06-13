# CloudCompass Builder - Lab 3 Handoff Document

## Purpose of this file

This document is a self-contained handoff for another ChatGPT conversation or teammate. It summarizes the original CloudCompass idea, the Lab 3 assignment constraints, the rubric priorities, the resolved design ambiguities, and the final MVP direction.

Use this as the source of truth for continuing the project report, CDK planning, architecture diagram, implementation tasks, or final submission packaging.

---

## 1. Project identity

**Project name:** CloudCompass Builder  
**One-line description:** A governed multi-agent AWS infrastructure generator that turns a natural-language prompt into a validated, cost-estimated, deployable Python CDK project and a CloudFormation change set.

**Refined objective:**  
Build an agentic application that can generate an entire AWS cloud infrastructure package from a user prompt. The system should generate a complete Python CDK project, run validation/security checks, estimate cost, and create a CloudFormation change set for review. It should not automatically execute the deployment in the MVP.

---

## 2. Assignment requirements

The Lab 3 assignment requires a group project where the team designs and implements a cloud-native AWS application. The hard requirement is a working agentic application built with **Strands Agents** and deployed on **Amazon Bedrock AgentCore**.

Minimum agentic requirements:

1. Define at least one Strands Agent with a clear purpose and system prompt.
2. Expose at least two custom `@tool`-decorated functions that interact with AWS services.
3. Deploy and run the agent on Bedrock AgentCore, not only locally.
4. Invoke the agent from a real entry point such as API, UI, event, or scheduled job.

Submission requirements:

1. Full account-agnostic CDK project.
2. AWS-native implementation. For example, if the solution has an API, use Amazon API Gateway, not a custom FastAPI service.
3. Compressed submission containing the full CDK code and the report as a PDF.
4. Report must include architecture diagram, workflow explanation, technical decisions, service configurations, cost estimate by meaningful unit, fixed vs variable cost breakdown, limitations, assumptions, and CDK code reference.

Rubric areas to optimize for:

- Agentic implementation.
- Architecture quality and AWS-native design.
- IaC deployability.
- Security and least privilege.
- Scalability and production readiness.
- Solution uniqueness and real-world applicability.
- Architecture diagram clarity.
- Written report quality.

---

## 3. Final locked decisions

The ambiguous project decisions have been resolved as follows:

| Area | Final choice |
|---|---|
| Core product scope | CDK generator + validation + optional deployment path |
| Demo domain | One vertical: online bakery/shop |
| Deployment behavior | Generate CDK + create CloudFormation change set |
| CDK output | Complete CDK project + tests/security checks |
| RAG backend | S3 Vectors |
| CDK language | Python |
| AgentCore Gateway | Include in MVP |
| Models | Sonnet-class model for orchestration + Haiku-class model for cheaper sub-tasks |
| UI scope | Minimal form + output page |
| Cost unit for report | Cost per infrastructure-generation run |

---

## 4. MVP deployment boundary

The MVP generates a complete CDK project, validates it, and creates a **CloudFormation change set**, but it does **not automatically execute the deployment**.

The demo ends at the `CHANGE_SET_READY` state, where the user can review:

- Proposed AWS resources.
- Generated Python CDK project.
- IAM permissions.
- Security validation results.
- Cost estimate.
- CloudFormation change set preview.

Actual stack execution is a stretch goal. It would require a separate explicit human approval step outside the MVP demo flow.

MVP workflow states:

```text
RECEIVED
DESIGNING
GENERATING_CDK
VALIDATING
CHANGE_SET_READY
```

Stretch-goal workflow states:

```text
DEPLOYING
DEPLOYED
FAILED_ROLLBACK
```

MVP tool boundary:

| Tool | Status |
|---|---|
| `create_cloudformation_change_set()` | MVP |
| `execute_approved_change_set()` | Stretch goal only |

---

## 5. Demo scenario

Use one focused demo vertical: **online bakery/shop**.

Recommended demo prompt:

```text
Create the AWS infrastructure for a small online bakery. I need a static website, customer login, an order API, a database for orders, email receipts, logs, and a monthly budget under $200.
```

Expected generated architecture:

- S3 + CloudFront for static website hosting.
- Cognito for customer authentication.
- API Gateway HTTP API for order API.
- Lambda for backend compute.
- DynamoDB for order storage.
- SES for email receipts.
- CloudWatch for logs and basic monitoring.
- IAM least-privilege roles.
- Optional S3 artifact bucket for generated files and reports.

Expected MVP output:

1. Structured requirements JSON.
2. Architecture summary.
3. Generated Python CDK project.
4. Security and validation report.
5. Cost estimate per infrastructure-generation run.
6. CloudFormation synthesized template.
7. CloudFormation change set preview.
8. Final status: `CHANGE_SET_READY`.

---

## 6. Product scope

### In scope for MVP

CloudCompass Builder should:

1. Accept a natural-language infrastructure request through a minimal web UI.
2. Authenticate users with Cognito.
3. Invoke the Strands multi-agent app through API Gateway and Lambda.
4. Run the agent on Bedrock AgentCore Runtime.
5. Use AgentCore Gateway for AWS tool access.
6. Use S3 Vectors as the RAG backend for AWS guidance and templates.
7. Generate a complete Python CDK project.
8. Store generated artifacts in S3.
9. Store project status and metadata in DynamoDB.
10. Run validation with CodeBuild.
11. Validate generated IAM/security posture.
12. Create a CloudFormation change set.
13. Return a readable project summary to the UI.

### Out of scope for MVP

The MVP should not:

1. Execute the CloudFormation change set automatically.
2. Support arbitrary AWS services without restriction.
3. Build a fully polished production UI.
4. Create complex multi-account landing zones.
5. Handle regulated workloads requiring formal compliance review.
6. Claim exact production-grade security without human review.
7. Support every possible application pattern.

---

## 7. High-level architecture

```text
User
 |
 v
CloudFront + S3 Minimal Web UI
 |
 | Cognito JWT
 v
API Gateway HTTP API
 |
 v
Lambda Agent Invoker
 |
 | Invoke AgentCore Runtime
 v
Amazon Bedrock AgentCore Runtime
 |
 | Runs Strands multi-agent application
 |
 +--> Orchestrator Agent
      |
      +--> Requirements Analyst Agent
      +--> Architecture Designer Agent
      +--> CDK Generator Agent
      +--> Security Reviewer Agent
      +--> Cost Estimator Agent
      +--> Deployment Orchestrator Agent
             |
             +--> AgentCore Gateway
                    |
                    +--> Bedrock Knowledge Base / S3 Vectors
                    +--> AWS Price List API
                    +--> S3 Artifact Bucket
                    +--> DynamoDB Project Table
                    +--> CodeBuild Validation Project
                    +--> IAM Access Analyzer or validation checks
                    +--> CloudFormation Change Set

Observability:
AgentCore Observability + CloudWatch Logs/Metrics/Traces + X-Ray where useful
```

---

## 8. End-to-end flow

1. User signs in through Cognito.
2. User submits the bakery infrastructure prompt in the minimal web UI.
3. Frontend sends the request to API Gateway with the Cognito JWT.
4. API Gateway invokes a Lambda function.
5. Lambda validates the request and calls the AgentCore Runtime endpoint.
6. The Strands Orchestrator Agent receives the prompt and session context.
7. The Requirements Analyst Agent converts the prompt into a structured workload specification.
8. If required details are missing, the agent asks clarifying questions.
9. The Architecture Designer Agent retrieves approved AWS patterns and guidance from the Bedrock Knowledge Base backed by S3 Vectors.
10. The Architecture Designer selects AWS services for the bakery/shop use case.
11. The Cost Estimator Agent estimates the cost of the infrastructure-generation run.
12. The CDK Generator Agent creates a full Python CDK project.
13. The generated project is written to S3.
14. The project metadata and status are saved to DynamoDB.
15. The Deployment Orchestrator Agent starts a CodeBuild validation job.
16. CodeBuild runs tests, CDK synth, linting, and security checks.
17. The Security Reviewer Agent reviews validation output and generated permissions.
18. If validation passes, the Deployment Orchestrator creates a CloudFormation change set.
19. The UI displays the generated architecture summary, CDK artifact link, validation report, cost estimate, and change set summary.
20. The MVP stops at `CHANGE_SET_READY`.

---

## 9. Multi-agent design

Use a lead-orchestrator plus specialist agents topology.

### 9.1 Orchestrator Agent

Purpose: Own the conversation, call the other agents in the right order, and assemble the final answer.

Key responsibilities:

- Maintain session context.
- Decide whether clarification is needed.
- Delegate tasks.
- Enforce the MVP boundary.
- Prevent automatic deployment.

System prompt idea:

```text
You are CloudCompass Builder's orchestration agent. Convert a user's infrastructure request into a safe, validated, deployable AWS Python CDK project. Ask clarifying questions when necessary. Only use approved architecture patterns. Never execute deployment automatically. The MVP stops after creating a CloudFormation change set.
```

### 9.2 Requirements Analyst Agent

Purpose: Convert the user's plain-English request into a structured workload specification.

Example output:

```json
{
  "business_type": "online bakery",
  "workload_type": "serverless web application",
  "frontend_required": true,
  "authentication_required": true,
  "api_required": true,
  "database_required": true,
  "email_required": true,
  "monthly_budget_usd": 200,
  "expected_orders_per_month": null,
  "missing_requirements": ["expected monthly traffic or orders"]
}
```

### 9.3 Architecture Designer Agent

Purpose: Select AWS services using approved patterns retrieved from the S3 Vectors RAG corpus.

For the bakery scenario, recommended services are:

- S3.
- CloudFront.
- Cognito.
- API Gateway.
- Lambda.
- DynamoDB.
- SES.
- CloudWatch.
- IAM.

### 9.4 CDK Generator Agent

Purpose: Generate a full Python CDK project.

Generated project should include:

- `app.py`.
- Stack files under `cloudcompass_generated/` or `stacks/`.
- Tests.
- README.
- `requirements.txt`.
- `cdk.json`.
- Synthable infrastructure code.
- Outputs for API endpoint, frontend distribution, table name, and Cognito identifiers.

### 9.5 Security Reviewer Agent

Purpose: Review generated infrastructure before change-set creation.

Checks:

- No hardcoded credentials.
- No broad admin policies.
- No unnecessary `Action: "*"` or `Resource: "*"`.
- S3 Block Public Access enabled by default.
- Encryption where appropriate.
- Lambda logs enabled.
- DynamoDB point-in-time recovery considered.
- Secrets stored in Secrets Manager or SSM Parameter Store if needed.
- Generated template passes validation rules.

### 9.6 Cost Estimator Agent

Purpose: Estimate the cost per infrastructure-generation run.

Include:

- Bedrock model usage.
- AgentCore Runtime usage.
- AgentCore Gateway tool calls.
- S3 artifact storage.
- DynamoDB reads/writes.
- CodeBuild validation minutes.
- API Gateway and Lambda request handling.

### 9.7 Deployment Orchestrator Agent

Purpose: Coordinate S3 artifact writing, CodeBuild validation, and CloudFormation change-set creation.

MVP boundary:

- Can create a change set.
- Cannot execute it.

---

## 10. Custom tools

The lab requires at least two AWS-interacting custom tools. The project should implement more than two.

| Tool | AWS service | MVP? | Purpose |
|---|---|---:|---|
| `query_reference_guidance(query, workload_type)` | Bedrock Knowledge Base + S3 Vectors | Yes | Retrieve approved AWS architecture patterns and guidance |
| `get_service_pricing(service_code, region, usage_profile)` | AWS Price List API | Yes | Retrieve pricing data for cost estimates |
| `write_cdk_project(project_id, files)` | S3 | Yes | Store generated Python CDK project artifacts |
| `save_project_state(project_id, status, metadata)` | DynamoDB | Yes | Persist workflow status and metadata |
| `start_validation_build(project_id, artifact_s3_uri)` | CodeBuild | Yes | Run tests, synth, and security checks |
| `validate_generated_template(project_id, template_s3_uri)` | IAM/CloudFormation validation tools | Yes | Return security and deployability findings |
| `create_cloudformation_change_set(project_id, template_s3_uri)` | CloudFormation | Yes | Create deployment preview |
| `execute_approved_change_set(project_id, approval_token)` | CloudFormation | No | Stretch goal only |

---

## 11. CDK implementation plan

Use **Python CDK** for the main project.

Suggested repository structure:

```text
cloudcompass-builder/
  README.md
  app.py
  cdk.json
  requirements.txt
  cloudcompass_builder/
    __init__.py
    frontend_stack.py
    api_stack.py
    auth_stack.py
    agent_runtime_stack.py
    knowledge_stack.py
    data_stack.py
    validation_stack.py
    observability_stack.py
  agent/
    Dockerfile
    requirements.txt
    app.py
    agents/
      orchestrator.py
      requirements_analyst.py
      architecture_designer.py
      cdk_generator.py
      security_reviewer.py
      cost_estimator.py
      deployment_orchestrator.py
    tools/
      kb_tool.py
      pricing_tool.py
      s3_artifact_tool.py
      dynamodb_state_tool.py
      codebuild_validation_tool.py
      template_validation_tool.py
      cloudformation_tool.py
    prompts/
      orchestrator.md
      cdk_generator.md
      security_reviewer.md
  frontend/
    index.html
    app.js
  validation/
    buildspec.yml
    allowed_resource_types.json
    tests/
      test_synth.py
      test_security_defaults.py
  report/
    lab3_report.md
```

Account-agnostic rules:

- No hardcoded account IDs.
- No hardcoded ARNs.
- No hardcoded regions unless explicitly handled through environment/config.
- Use CDK constructs and generated names.
- Pass environment-sensitive values through context, SSM parameters, or stack outputs.

---

## 12. Data and artifact design

### DynamoDB table

Table name: `CloudCompassProjects`

Suggested keys:

```text
PK = USER#{user_id}
SK = PROJECT#{project_id}
```

Important attributes:

```text
status
prompt
requirements_json
architecture_spec_json
cost_estimate_json
security_findings_json
artifact_s3_uri
synthesized_template_s3_uri
change_set_arn
created_at
updated_at
ttl
```

### S3 artifact layout

```text
s3://cloudcompass-artifacts-{account}-{region}/
  projects/
    {project_id}/
      source/
        cdk-project.zip
      synthesized/
        template.json
      reports/
        architecture-summary.json
        cost-estimate.json
        security-findings.json
        validation-output.json
      diagrams/
        architecture.mmd
```

---

## 13. Security model

Security principles:

1. Least privilege by role.
2. No automatic deployment execution in MVP.
3. No hardcoded credentials.
4. Encrypt data at rest where supported.
5. Store generated artifacts in a private S3 bucket.
6. Block public S3 access unless explicitly required for frontend hosting through CloudFront.
7. Use Cognito authentication for the UI/API.
8. Use separate IAM roles for Lambda, AgentCore runtime, CodeBuild validation, and CloudFormation change-set creation.
9. Validate generated IAM and CloudFormation before creating the change set.
10. Log key actions for auditability.

Important distinction:

- The agent can generate and validate infrastructure.
- The agent can create a change set.
- The agent cannot execute the change set in the MVP.

---

## 14. Cost model

The report's meaningful unit is:

```text
Cost per infrastructure-generation run
```

A single run means:

```text
User prompt -> requirements -> architecture -> CDK generation -> validation -> CloudFormation change set
```

Cost categories:

### Variable costs

- Bedrock model inference.
- AgentCore Runtime active usage.
- AgentCore Gateway tool calls.
- Knowledge base/vector retrieval.
- CodeBuild validation minutes.
- DynamoDB reads/writes.
- S3 artifact storage and requests.
- API Gateway requests.
- Lambda duration.
- CloudWatch logs.

### Fixed or low baseline costs

- S3 storage baseline.
- CloudWatch log retention baseline.
- Any KMS keys if customer-managed keys are used.
- Stored knowledge base corpus.
- Frontend static hosting artifacts.

Report should emphasize:

- Model calls and CodeBuild validation are likely the largest variable costs.
- S3 Vectors was selected to reduce fixed vector-store overhead.
- CloudFormation itself is not the meaningful cost driver; the resources created by CloudFormation are.
- The generated bakery infrastructure's runtime cost can be described separately as an example, but the official unit chosen for the report is the generation run.

---

## 15. Team collaboration plan

Suggested five-person split:

| Person | Stream | Owns build work | Owns report section |
|---|---|---|---|
| 1 | Agent orchestration | Strands orchestrator, prompts, agent contracts, AgentCore Runtime integration | Agentic implementation and workflow |
| 2 | CDK generation | Python CDK generator agent, generated project templates, tests | IaC generation and technical decisions |
| 3 | Validation and deployment preview | CodeBuild, validation checks, CloudFormation change-set creation | IaC deployability and MVP boundary |
| 4 | Knowledge, data, and pricing | S3 Vectors, knowledge corpus, pricing tool, DynamoDB schema | Cost model, RAG grounding, data model |
| 5 | Frontend, API, auth, security, observability | S3/CloudFront UI, API Gateway, Lambda, Cognito, IAM, logs/traces | Architecture diagram, security, final report assembly |

Recommended integration approach:

1. Define shared JSON contracts first.
2. Build agent tools with mock responses first.
3. Replace mocks with AWS calls incrementally.
4. Get a hello-world agent deployed to AgentCore early.
5. Integrate UI/API only after the agent invocation path works.
6. Keep a working end-to-end demo branch stable.
7. Freeze scope before final report writing.

---

## 16. Shared JSON contracts

### Input request

```json
{
  "user_id": "demo-user",
  "project_id": "generated-uuid",
  "prompt": "Create the AWS infrastructure for a small online bakery...",
  "region": "us-east-1"
}
```

### Architecture spec

```json
{
  "project_name": "bakery-shop",
  "pattern": "serverless-web-application",
  "services": [
    "S3",
    "CloudFront",
    "Cognito",
    "API Gateway",
    "Lambda",
    "DynamoDB",
    "SES",
    "CloudWatch",
    "IAM"
  ],
  "budget_monthly_usd": 200,
  "deployment_boundary": "change-set-only"
}
```

### Final MVP response

```json
{
  "project_id": "generated-uuid",
  "status": "CHANGE_SET_READY",
  "architecture_summary": "...",
  "cdk_artifact_s3_uri": "s3://.../cdk-project.zip",
  "validation_summary": "...",
  "cost_estimate": {
    "unit": "infrastructure-generation-run",
    "estimated_cost_usd": "..."
  },
  "change_set_arn": "arn:aws:cloudformation:...",
  "next_action": "Review the change set. Execution is outside MVP scope."
}
```

---

## 17. Report structure to write later

Recommended final PDF report outline:

1. Title page.
2. Executive summary.
3. Problem and target user.
4. MVP scope and deployment boundary.
5. Architecture diagram.
6. End-to-end workflow.
7. Agentic implementation.
8. AWS services and technical decisions.
9. CDK/IaC implementation.
10. Security and least privilege.
11. Scalability and production readiness.
12. Cost estimate per infrastructure-generation run.
13. Limitations and assumptions.
14. Team collaboration.
15. Appendix: sample prompt, generated architecture, sample change-set summary.

---

## 18. Immediate next tasks

1. Create the Python CDK skeleton.
2. Build a hello-world Strands agent and deploy it to AgentCore Runtime.
3. Create the minimal web UI and API Gateway/Lambda invoker path.
4. Define JSON contracts between agents and tools.
5. Build the S3 artifact writer and DynamoDB state writer tools.
6. Add RAG retrieval from Bedrock Knowledge Base backed by S3 Vectors.
7. Implement the Python CDK generator for the bakery architecture.
8. Add CodeBuild validation.
9. Create CloudFormation change set creation logic.
10. Write the final report and architecture diagram.

---

## 19. Suggested prompt for another ChatGPT conversation

Use this prompt to continue work in another chat:

```text
I am working on an AWS Lab 3 group project called CloudCompass Builder. It is a governed multi-agent AWS infrastructure generator. The user submits a natural-language prompt, and the system generates a complete Python CDK project, validates it, estimates cost, and creates a CloudFormation change set. The MVP does not execute the change set.

Fixed decisions:
- Scope: CDK generator + validation + optional deployment path.
- Demo domain: online bakery/shop.
- Deployment behavior: generate CDK + create CloudFormation change set only.
- CDK output: complete Python CDK project + tests/security checks.
- RAG backend: S3 Vectors.
- CDK language: Python.
- AgentCore Gateway: included in MVP.
- Models: Sonnet-class model for orchestration + Haiku-class model for cheaper sub-tasks.
- UI: minimal form + output page.
- Cost unit: cost per infrastructure-generation run.

The system uses Strands Agents on Amazon Bedrock AgentCore Runtime, API Gateway, Lambda, Cognito, S3/CloudFront UI, DynamoDB, S3 artifact bucket, Bedrock Knowledge Base with S3 Vectors, CodeBuild validation, CloudFormation change sets, CloudWatch, and IAM least privilege.

Help me continue from this point.
```
