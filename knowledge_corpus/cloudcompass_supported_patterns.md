# CloudCompass Supported Service Catalog

The CloudCompass generator can emit these service types. The architecture
designer must only use these:

- `s3_bucket` — private, encrypted, versioned S3 bucket for assets.
- `cloudfront_site` — private S3 origin behind CloudFront (OAC) for a static site.
- `cognito_user_pool` — Cognito User Pool + app client for customer login.
- `lambda_api` — Lambda + API Gateway HTTP API; set `config.routes` like
  `["GET /orders", "POST /orders"]`.
- `dynamodb_table` — on-demand DynamoDB table; set `config.partition_key` and
  optional `config.sort_key`.
- `ses_email` — SES configuration set (and optional verified sender via
  `config.sender_email`) for transactional email.

Each service needs a unique alphanumeric `logical_id`. The `project_name` must be
lowercase-hyphenated. The deployment boundary is always `change-set-only`: the
MVP stops at a CloudFormation change set and never executes a deployment.

Example mapping for an online bakery: cloudfront_site (website) + cognito_user_pool
(login) + lambda_api (order API) + dynamodb_table (orders) + ses_email (receipts).
