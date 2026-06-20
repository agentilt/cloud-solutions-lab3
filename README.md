# CloudCompass Builder

CloudCompass Builder is a governed multi-agent AWS infrastructure generator.
It accepts a natural-language infrastructure prompt and produces a validated,
cost-estimated, deployable Python CDK project plus a CloudFormation change-set
preview. The MVP stops at `CHANGE_SET_READY`; it does not execute the change set.

The project follows the source-of-truth handoff in
`docs/cloudcompass_builder_handoff.md`.

## What Is Implemented

- Account-agnostic Python CDK app for the CloudCompass platform.
- Cognito Hosted UI authentication.
- CloudFront + private S3 static frontend.
- API Gateway HTTP API with Cognito JWT authorization.
- Lambda project API: `POST /projects`, `GET /projects/{project_id}`.
- Bedrock AgentCore runtime container for a Strands multi-agent app.
- CloudCompass-specific Strands tools for S3 artifacts, DynamoDB state,
  CodeBuild validation, pricing estimate, and CloudFormation change-set preview.
- Deterministic Python CDK generator for S3, Lambda/API Gateway, and DynamoDB.
- CodeBuild validation project for generated CDK archives.
- Tests for generator contracts, Lambda request handling, and CDK assertions.
- Architecture and report drafts under `docs/`.

## Repository Layout

```text
.
├── app.py
├── cdk_app/                  # CloudCompass platform CDK stacks
├── agent/                    # Strands app deployed to AgentCore
├── cdk_generator/            # Deterministic generated-project renderer
├── frontend/                 # Static authenticated UI
├── lambdas/                  # API Lambda handlers
├── docs/                     # Architecture, report, handoff
└── tests/                    # CDK, generator, Lambda tests
```

## Local Setup

```powershell
C:\Users\sebog\miniconda3\envs\carrefour\python.exe -m pip install -r requirements.txt -r requirements-dev.txt -r cdk_generator\requirements.txt
C:\Users\sebog\miniconda3\envs\carrefour\python.exe -m pytest
```

On this Windows environment, `cdk synth` may need the explicit Python executable:

```powershell
cdk synth --app "C:\Users\sebog\miniconda3\envs\carrefour\python.exe app.py"
```

If jsii cannot create its temporary runtime inside the sandbox, run synth outside
the sandbox or from a normal terminal.

## Demo Prompt

```text
Create the AWS infrastructure for a small online bakery. I need a static website, customer login, an order API, a database for orders, email receipts, logs, and a monthly budget under $200.
```

Expected MVP result:

- Structured requirements and architecture summary.
- Generated Python CDK project archive in S3.
- Validation/security summary.
- Cost estimate per infrastructure-generation run.
- CloudFormation change-set ARN or stored preview template.
- Final status: `CHANGE_SET_READY`.
