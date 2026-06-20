# Security and Least Privilege Guidance

- **No wildcard IAM actions.** Never grant `*` actions. Scope actions to the
  specific operations needed, and scope resources to specific ARNs. Resource
  wildcards are only acceptable for actions that have no resource-level
  permissions (e.g. `pricing:GetProducts`).
- **S3 buckets**: enable Block Public Access (all four settings), enforce TLS
  (`aws:SecureTransport`), and use SSE-S3 or KMS encryption at rest.
- **DynamoDB**: enable encryption at rest and point-in-time recovery.
- **Separate roles** per component (Lambda, agent runtime, CodeBuild,
  CloudFormation) so a compromise is contained.
- **Governed deployment**: generate a CloudFormation change set for human review
  before executing. Do not auto-deploy generated infrastructure.
- **Encryption in transit** everywhere: HTTPS at API Gateway and CloudFront,
  TLS-only S3 bucket policies.
- Add Bedrock Guardrails for prompt-injection protection on agent inputs.
