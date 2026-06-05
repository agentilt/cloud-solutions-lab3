# Architecture

> Replace this overview with one tied to the chosen use case. Keep the building blocks identified below — they are what the scaffold deploys.

## Components

| Layer | Service | Purpose |
|---|---|---|
| Entry | Amazon API Gateway (HTTP API) | Public REST entry: `POST /upload-url`, `POST /invoke` |
| Compute (entry) | AWS Lambda (Python 3.13, ARM64) | `upload_url` mints presigned S3 URLs; `agent_invoker` calls AgentCore |
| Agent | Amazon Bedrock AgentCore Runtime | Hosts the Strands Agent container (ARM64), `InvokeAgentRuntime` API |
| Agent logic | Strands Agents | Orchestrates LLM + `@tool` calls; system prompt in `agent/agent.py` |
| Foundation model | Amazon Bedrock (Anthropic Claude family) | Reasoning engine behind the agent |
| Data | Amazon DynamoDB (on-demand) | Single-table `pk`/`sk` store for app records |
| Object store | Amazon S3 (SSE-S3, versioned, TLS-only) | Uploads / artifacts; EventBridge notifications enabled |
| Events | Amazon EventBridge custom bus | Domain events emitted by the agent for async downstream work |
| Observability | CloudWatch Logs + X-Ray | Lambda + AgentCore runtime traces |

## Execution flow (default scaffold)

```
Client
  │
  │ 1. POST /invoke { "prompt": "..." }
  ▼
API Gateway (HTTP API)
  │
  ▼
agent_invoker Lambda
  │  bedrock-agentcore:InvokeAgentRuntime
  ▼
Bedrock AgentCore Runtime  ── invokes ──▶  Bedrock Foundation Model
  │  (Strands Agent inside)
  │
  ├──▶ @tool lookup_record   ──▶ DynamoDB GetItem
  └──▶ @tool record_event    ──▶ EventBridge PutEvents ──▶ (downstream consumers)
  │
  ▼
Response streamed back to Lambda → API Gateway → Client
```

A parallel ingestion flow is also wired:

```
Client → POST /upload-url → Lambda → presigned S3 URL → Client uploads to S3
S3 ObjectCreated → EventBridge (S3 source) → (team-defined consumer)
```

## Diagram

Export the architecture diagram to `docs/architecture.png` and reference it here. Recommended tools: AWS Application Composer, draw.io with the AWS 2024 icon set, or Lucidchart.

```markdown
![Architecture](./architecture.png)
```

## Why these choices

- **HTTP API (v2) over REST API (v1)** — lower cost, lower latency, sufficient features for the use case.
- **Lambda ARM64** — ~20% cheaper than x86 at equal performance for Python workloads.
- **AgentCore over self-hosting Strands** — managed runtime, autoscaling, no container ops; aligns with the lab's "use managed AWS services" requirement.
- **DynamoDB single-table on-demand** — fits unknown access patterns during development; switch to provisioned + GSIs once patterns stabilize.
- **EventBridge custom bus** — decouples the agent from downstream consumers; allows fan-out without coupling stacks.

## Boundaries

- **Region**: single-region deployment (default `us-east-1`); multi-region is out of scope.
- **Account**: single account. CDK is account-agnostic — re-deploy in a different account by changing `CDK_DEFAULT_ACCOUNT`.
- **Network**: AgentCore runtime uses `PUBLIC` network mode (no VPC). Switch to `VPC` mode if private VPC resources need to be reached.
