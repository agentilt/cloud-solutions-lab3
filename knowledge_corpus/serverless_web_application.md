# Serverless Web Application Reference (AWS)

A small serverless web application (e.g. an online shop) is composed of:

- **Static frontend**: host the SPA in a private S3 bucket fronted by CloudFront
  with Origin Access Control (OAC). Never expose the origin bucket publicly.
  Redirect viewers to HTTPS and use SPA error responses (403/404 -> index.html).
- **Authentication**: use Amazon Cognito User Pools for customer sign-in and a
  JWT authorizer on the API. Prefer the authorization-code flow with PKCE.
- **API**: use API Gateway HTTP API (v2) — lower cost and latency than REST API,
  with native JWT authorizer support — integrated with AWS Lambda.
- **Compute**: AWS Lambda on ARM64 (Graviton) for ~20% lower cost; enable X-Ray.
- **Database**: Amazon DynamoDB on-demand single-table, AWS-managed encryption,
  point-in-time recovery. Model access patterns with pk/sk and add GSIs later.
- **Email**: Amazon SES for transactional receipts.
- **Observability**: CloudWatch Logs with bounded retention, X-Ray tracing.

This pattern scales out via managed services and keeps a small fixed cost.
