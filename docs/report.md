# Lab 3 — Project Report

**Course:** Cloud Solutions Architectures
**Group:** Group 2
**Members:** Agustin Gentil, Boumediene Rayane Mazari, Diego Alfaro Gómez, Renato González Huamán, Sebastián Otegui Gómez
**Submission date:** 2026-06-28

---

## 1. Use case

> One paragraph: the problem the solution addresses, who it is for, and why the agentic component adds value over a non-agentic implementation.

## 2. Architecture diagram and workflow

> Embed `architecture.png` here. Walk through the execution flow step by step (request enters → service hops → response). Cover both the synchronous agent-invocation flow and any async flows (S3 uploads, EventBridge consumers, scheduled jobs, etc.).

![Architecture](./architecture.png)

### Service interactions

| # | Source | Target | Mechanism | Purpose |
|---|---|---|---|---|
| 1 | Client | API Gateway | HTTPS | Entry point |
| 2 | API Gateway | Lambda (agent_invoker) | Proxy integration | Bridge to AgentCore |
| 3 | Lambda | Bedrock AgentCore Runtime | `InvokeAgentRuntime` | Agent invocation |
| 4 | AgentCore | Bedrock foundation model | `InvokeModel` | LLM reasoning |
| 5 | AgentCore | DynamoDB | `GetItem` via `lookup_record` tool | Read app data |
| 6 | AgentCore | EventBridge | `PutEvents` via `record_event` tool | Emit domain events |

## 3. Technical decisions

> For each major decision: the options considered, the choice made, and why.

- **API style:** HTTP API v2 over REST API v1 — lower latency and ~70% cheaper for our request volume.
- **Lambda architecture:** ARM64 (Graviton) — ~20% cheaper at equivalent performance for our Python workload.
- **Agent framework:** Strands Agents on Bedrock AgentCore — managed runtime, no container ops, native streaming.
- **Foundation model:** Anthropic Claude (family selection) — chosen for tool-use reliability and instruction-following.
- **Data layer:** DynamoDB on-demand single-table — fits evolving access patterns; we add GSIs as access patterns stabilize.
- **Eventing:** Custom EventBridge bus — decouples the agent from downstream consumers; allows future fan-out without coupling stacks.
- **IaC:** Python CDK with three stacks (Storage / Agent / Api) — separation by lifecycle: data outlives app code; the agent image rebuilds independently.

## 4. Service configurations

| Service | Configuration | Rationale |
|---|---|---|
| S3 data bucket | SSE-S3, BlockPublicAccess=ALL, TLS-only (`aws:SecureTransport`), versioned, EventBridge notifications | Defaults safe; required for least-privilege auditing |
| DynamoDB | On-demand, AWS-managed KMS, PITR enabled | No capacity tuning needed during development; PITR for recovery |
| AgentCore runtime | `PUBLIC` network mode, ARM64 container, ECR-backed | Simplest viable network posture; ARM64 image required by AgentCore |
| Lambda | Python 3.13, ARM64, 512 MB, 30 s timeout, X-Ray active | Cost-effective and observable defaults |
| API Gateway | HTTP API v2, CORS open (TODO tighten) | Lower cost; CORS to be tightened pre-prod |
| IAM | No `*` actions or resources; resource-scoped to specific tables, buckets, models | Rubric requirement; least-privilege |
| Encryption | At rest: SSE-S3 + DDB AWS-managed KMS. In transit: API Gateway HTTPS, S3 TLS-only policy, AgentCore HTTPS | Defense in depth |

## 5. Cost estimation

**Meaningful unit:** *cost per agent invocation* (one user prompt → one response, with up to N tool calls).

### Variable costs per invocation

| Component | Driver | Per-invocation cost (USD) |
|---|---|---|
| Bedrock model tokens | input + output tokens | _TODO_ |
| AgentCore runtime | active CPU seconds + memory-GB-seconds | _TODO_ |
| Lambda (agent_invoker) | invocation + GB-seconds | _TODO_ |
| API Gateway request | $1.00 per million | _TODO_ |
| DynamoDB reads/writes | 1 RCU per `lookup_record`, 1 WCU per `record_event` | _TODO_ |
| EventBridge custom-bus events | $1.00 per million | _TODO_ |
| CloudWatch logs ingestion | per GB ingested | _TODO_ |
| **Total variable** | | **_TODO_** |

### Fixed costs (monthly, regardless of traffic)

| Component | Cost |
|---|---|
| AgentCore runtime baseline | _TODO_ |
| ECR storage (agent image) | _TODO_ |
| S3 storage (uploads + versioning) | _TODO_ |
| DynamoDB storage | _TODO_ |
| CloudWatch log retention | _TODO_ |
| **Total fixed** | **_TODO_** |

### Worked example

> "At 10,000 invocations/month: fixed = $X, variable = $Y → total = $Z (about $W per invocation)."

## 6. Limitations and assumptions

### Limitations

- Single-region deployment. No DR/failover.
- AgentCore network mode is `PUBLIC` — cannot reach private VPC resources without re-deployment.
- API has no auth (open `/invoke`). Add Cognito / API key / Lambda authorizer before any real traffic.
- CORS is wide-open (`*`) for local development. Tighten before any external use.
- No prompt-injection guardrails configured at the Bedrock Guardrails layer.
- No semantic caching — every prompt hits the model.

### Assumptions

- Group AWS account has Bedrock model access enabled for the chosen Claude model in the deployment region.
- AgentCore is available in the deployment region.
- Container build host supports `docker buildx` for ARM64 cross-compilation.
- Traffic volume during evaluation is modest (≤ low thousands of invocations / month).
- All data is non-PII / non-sensitive — no additional compliance (HIPAA/PCI/GDPR-restricted) controls in scope.

## 7. Appendix: CDK code overview

Stacks deployed by `cdk deploy --all`:

1. **`Lab3-Storage`** — S3 data bucket, DynamoDB single-table, EventBridge custom bus.
2. **`Lab3-Agent`** — ECR image (ARM64 Strands agent), least-privilege execution role, AgentCore runtime created via custom resource.
3. **`Lab3-Api`** — HTTP API + 2 Lambdas (`upload_url`, `agent_invoker`).

Full source in the accompanying zip.
