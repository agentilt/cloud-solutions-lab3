# CloudCompass Builder - Lab 3 Report

**Course:** Cloud Solutions Architectures  
**Group:** Group 2  
**Members:** Agustin Gentil, Boumediene Rayane Mazari, Diego Alfaro Gomez, Renato Gonzalez Huaman, Sebastian Otegui Gomez  
**Submission date:** 2026-06-28

## 1. Use Case

CloudCompass Builder helps a small team turn a natural-language AWS
infrastructure request into a governed, reviewable deployment package. The demo
vertical is an online bakery/shop that needs a static website, customer login,
an order API, order storage, email receipts, logs, and a budget target under
$200/month. The agentic layer adds value because it decomposes the request into
requirements, architecture selection, deterministic CDK generation, validation,
cost estimation, and deployment preview while enforcing a no-auto-deploy
boundary.

## 2. Architecture And Workflow

The deployed CloudCompass platform uses AWS-native services:

| Layer | Services |
|---|---|
| Frontend and auth | S3 private bucket, CloudFront with Origin Access Control, Cognito Hosted UI |
| API entry | API Gateway HTTP API with Cognito JWT authorizer |
| Compute | Lambda project handler and AgentCore invoker |
| Agentic runtime | Strands Agents on Amazon Bedrock AgentCore Runtime |
| State and artifacts | DynamoDB project table and S3 artifact bucket |
| Validation and preview | CodeBuild and CloudFormation change sets |
| Observability | CloudWatch logs and X-Ray tracing |

Workflow:

1. User signs in through Cognito.
2. Browser submits `POST /projects` with a prompt and region.
3. API Gateway validates the JWT; Lambda derives `user_id` from the JWT `sub`.
4. Lambda stores `RECEIVED` in DynamoDB and invokes AgentCore.
5. The Strands orchestration app runs specialist steps for requirements,
   architecture, CDK generation, security review, cost, and deployment preview.
6. The deterministic generator renders a Python CDK project for the MVP service
   catalog: S3, Lambda/API Gateway, and DynamoDB.
7. The agent stores the generated CDK zip and manifest in S3.
8. The agent starts a CodeBuild validation run.
9. The agent creates a CloudFormation change set and stops at
   `CHANGE_SET_READY`.
10. The UI polls `GET /projects/{project_id}` and displays artifact, validation,
    cost, and change-set details.

## 3. Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| Agent topology | Lead orchestrator plus specialist Strands agents | Clear decomposition and rubric alignment |
| Runtime | Bedrock AgentCore Runtime | Managed agent hosting and required by the lab |
| Generator | Deterministic Jinja2 renderer | Repeatable output, unit tests, no LLM-generated syntax drift |
| API | HTTP API v2 | Lower cost and sufficient JWT support |
| Auth | Cognito Hosted UI and JWT authorizer | AWS-native identity without custom auth code |
| Frontend hosting | Private S3 behind CloudFront OAC | No public origin bucket and CDN delivery |
| Validation | CodeBuild | Isolated synth/compile checks for generated artifacts |
| Deployment boundary | CloudFormation change set only | Human review before any real deployment |
| RAG/guidance | S3 guidance corpus with S3 Vectors hook | Keeps MVP deployable while preserving the chosen extension point |

## 4. Service Configuration

| Service | Configuration |
|---|---|
| S3 artifact bucket | SSE-S3, Block Public Access, TLS-only, versioned, EventBridge enabled |
| DynamoDB | `pk`/`sk`, on-demand billing, AWS-managed encryption, PITR, TTL |
| CloudFront | Private S3 origin through OAC, HTTPS redirect, SPA error responses |
| Cognito | Email sign-in, hosted domain, authorization-code flow with PKCE |
| API Gateway | Cognito JWT authorizer on `/projects`, `/invoke`, and `/upload-url` |
| Lambda | Python 3.13, ARM64, X-Ray active, one-month log retention |
| AgentCore | ARM64 container image, scoped model invocation, S3/DynamoDB/CodeBuild/CloudFormation tool permissions |
| CodeBuild | No-source project, artifact URI supplied at runtime, Python compile plus `cdk synth` |
| CloudFormation | Change-set creation only from the agent role; execution is out of MVP scope |

## 5. Agentic Implementation

The AgentCore container defines a Strands orchestrator and six specialist
agents: Requirements Analyst, Architecture Designer, CDK Generator, Security
Reviewer, Cost Estimator, and Deployment Orchestrator. The MVP workflow is
deterministic for demo reliability, but all major actions are exposed through
Strands `@tool` functions:

- `query_reference_guidance()` reads approved guidance from S3 with a curated fallback.
- `render_cdk_project()` calls the deterministic generator.
- `write_cdk_project()` writes the generated archive to S3.
- `save_project_state()` persists workflow state in DynamoDB.
- `start_validation_build()` starts CodeBuild.
- `validate_generated_template()` performs lightweight security checks.
- `get_service_pricing()` returns cost per infrastructure-generation run.
- `create_cloudformation_change_set()` creates a preview and never executes it.

## 6. Security

Security controls:

- User identity comes from Cognito JWT claims, not from request body fields.
- Project records use `PK = USER#{user_id}` and `SK = PROJECT#{project_id}`.
- Frontend and artifact buckets block public access and enforce TLS.
- API routes require a Cognito JWT authorizer.
- Lambda, AgentCore, CodeBuild, and CloudFormation use separate roles.
- The agent role can create/describe change sets but cannot execute them.
- Generated CDK defaults include private S3, encryption, DynamoDB PITR, and X-Ray on Lambda.
- Logs are retained for one month for lab-cost control.

Limitations:

- The generated CDK catalog is intentionally narrow for the MVP.
- S3 Vectors and AgentCore Gateway are represented as pluggable hooks with a fallback corpus.
- CodeBuild validation is asynchronous; the UI displays the started build metadata.
- The change-set preview template is conservative for the MVP; the full CDK zip is the source artifact for review.

## 7. Cost Estimate

**Meaningful unit:** one infrastructure-generation run.

A run means:

```text
Prompt -> requirements -> architecture -> CDK generation -> validation -> change set
```

Estimated variable cost per run: **$0.35 to $1.25**.

| Component | Cost driver | Estimated per-run cost |
|---|---|---|
| Bedrock model inference | Prompt and generated output tokens | $0.15-$0.65 |
| AgentCore runtime and gateway calls | Runtime duration and tool calls | $0.05-$0.20 |
| CodeBuild validation | 2-5 small build minutes | $0.05-$0.25 |
| S3, DynamoDB, Lambda, API Gateway, logs | Requests and small stored artifacts | $0.10-$0.15 |

Fixed or low-baseline monthly costs:

| Component | Notes |
|---|---|
| S3 artifacts and frontend files | Low unless many generated archives are retained |
| CloudWatch logs | Controlled with one-month retention |
| DynamoDB storage | Small project metadata records |
| ECR image storage | Agent container image |
| CloudFront/Cognito | Mostly request-driven for this demo scale |

The generated bakery infrastructure runtime cost is separate from the
CloudCompass generation cost. CloudFormation itself is not the meaningful cost
driver; the resources created by a reviewed stack are.

## 8. Scalability And Production Readiness

The MVP uses managed services with natural scale-out boundaries: CloudFront for
the UI, API Gateway and Lambda for entry traffic, AgentCore for agent runtime,
DynamoDB on-demand for project state, S3 for artifacts, and CodeBuild for
isolated validation. Production hardening would add a job queue or Step
Functions for long-running validation, stricter CORS origins, Bedrock Guardrails,
full S3 Vectors provisioning, richer generated service templates, and explicit
human approval workflow for change-set execution.

## 9. CDK Code Reference

Main platform stacks:

1. `CloudCompass-Storage`: artifact bucket, project table, EventBridge bus.
2. `CloudCompass-FrontendHosting`: private S3 frontend bucket and CloudFront OAC.
3. `CloudCompass-Auth`: Cognito user pool, app client, hosted domain.
4. `CloudCompass-Validation`: CodeBuild project and CloudFormation execution role.
5. `CloudCompass-Agent`: AgentCore container image, execution role, runtime custom resource.
6. `CloudCompass-Api`: authenticated HTTP API and Lambda routes.
7. `CloudCompass-FrontendDeployment`: static UI and generated config.

The generated user-facing CDK package lives under `cdk_generator/` and is
separate from `cdk_app/`, which deploys CloudCompass itself.
