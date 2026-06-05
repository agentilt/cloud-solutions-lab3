# Lab 3 — Cloud Solutions Architectures

Scaffold for the group final project. The architecture skeleton is generic — the group picks the use case and fills in the domain logic. The agentic component (Strands Agent on Amazon Bedrock AgentCore) is wired end-to-end so the team can iterate on tools and prompts without rebuilding plumbing.

## What's provided

- Account-agnostic Python CDK project (3 stacks: storage, agent, api)
- API Gateway → Lambda → Bedrock AgentCore `InvokeAgentRuntime` path
- Strands Agent stub with two `@tool` functions (placeholders to replace)
- S3 bucket + DynamoDB table + custom EventBridge bus for app data/events
- Least-privilege IAM scaffolding (no `*` actions)
- ARM64 Dockerfile for the AgentCore runtime image
- Report template covering every rubric section
- CDK unit-test scaffold

## What the group still needs to decide

- The use case / problem domain
- The agent's system prompt and the actual `@tool` implementations
- The data model in DynamoDB (PK/SK + GSIs based on access patterns)
- Whether to add async fan-out (SQS/EventBridge → workers), Step Functions, etc.
- Frontend (Amplify, static S3 site, or none — API alone is a valid entry point)

## Repository layout

```
.
├── app.py                      # CDK entry point
├── cdk.json                    # CDK config (account-agnostic)
├── requirements.txt            # CDK deps
├── requirements-dev.txt        # test / lint deps
├── cdk_app/                    # CDK stacks
│   ├── storage_stack.py        # S3 + DynamoDB + EventBridge bus
│   ├── api_stack.py            # API Gateway + Lambda entry point
│   └── agent_stack.py          # ECR image + AgentCore runtime + IAM
├── lambdas/                    # Lambda function source
│   ├── upload_url/             # presigned S3 upload URL (optional pattern)
│   └── agent_invoker/          # calls AgentCore InvokeAgentRuntime
├── agent/                      # Strands Agent (deployed to AgentCore)
│   ├── agent.py                # entry point (BedrockAgentCoreApp)
│   ├── tools.py                # @tool-decorated functions (stubs)
│   ├── requirements.txt
│   └── Dockerfile              # ARM64 image
├── docs/
│   ├── architecture.md         # workflow + diagram description
│   └── report.md               # final report (export to PDF for submission)
└── tests/
    └── test_stacks.py          # CDK assertions
```

## Quickstart

```bash
# Make sure the CDK CLI is current (library tracks latest schema).
npm install -g aws-cdk@latest   # needs Node 22+ (24 LTS recommended)

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Bootstrap CDK once per account/region
cdk bootstrap

cdk synth
cdk deploy --all
```

> If `cdk synth` complains about a "Cloud assembly schema version mismatch", your CDK CLI is older than the library. Upgrade with `npm install -g aws-cdk@latest`.

The project is account-agnostic: it reads `CDK_DEFAULT_ACCOUNT` / `CDK_DEFAULT_REGION` from the caller env (set by `aws configure` / `AWS_PROFILE`).

## Rubric checklist

- [ ] Agentic component — Strands + AgentCore deployed, ≥2 tools doing meaningful AWS work
- [ ] Account-agnostic CDK, no manual steps
- [ ] Least-privilege IAM (no wildcards), encryption at rest + in transit
- [ ] Architecture diagram (`docs/architecture.md` + exported PNG)
- [ ] Cost estimation per meaningful unit, fixed vs variable (`docs/report.md`)
- [ ] Limitations / assumptions section (`docs/report.md`)
- [ ] Report exported to `docs/report.pdf` for submission
