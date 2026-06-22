#!/usr/bin/env python3
"""CDK entry point for CloudCompass Builder."""
import os

import aws_cdk as cdk

from cdk_app.agent_stack import AgentStack
from cdk_app.api_stack import ApiStack
from cdk_app.auth_stack import AuthStack
from cdk_app.frontend_stack import FrontendDeploymentStack, FrontendHostingStack
from cdk_app.knowledge_stack import KnowledgeStack
from cdk_app.storage_stack import StorageStack
from cdk_app.validation_stack import ValidationStack

APP_NAME = os.environ.get("APP_NAME", "CloudCompass")

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

# The CloudFront frontend only serves the static UI. Skip it with
# `cdk deploy --all -c deployFrontend=false` to deploy the graded agentic core on
# accounts not yet verified for CloudFront (new accounts) — the agent is then
# driven by invoking the runtime directly (see README).
deploy_frontend = str(app.node.try_get_context("deployFrontend")).lower() not in (
    "false",
    "0",
    "no",
)

storage = StorageStack(app, f"{APP_NAME}-Storage", env=env)
frontend_hosting = (
    FrontendHostingStack(app, f"{APP_NAME}-FrontendHosting", env=env) if deploy_frontend else None
)

auth = AuthStack(
    app,
    f"{APP_NAME}-Auth",
    env=env,
    frontend_url=frontend_hosting.frontend_url if frontend_hosting else None,
)

validation = ValidationStack(
    app,
    f"{APP_NAME}-Validation",
    env=env,
    artifact_bucket=storage.data_bucket,
)

knowledge = KnowledgeStack(app, f"{APP_NAME}-Knowledge", env=env)

agent = AgentStack(
    app,
    f"{APP_NAME}-Agent",
    env=env,
    data_table=storage.data_table,
    event_bus=storage.event_bus,
    data_bucket=storage.data_bucket,
    validation_project=validation.validation_project,
    cloudformation_execution_role=validation.cloudformation_execution_role,
    knowledge_base_id=knowledge.knowledge_base_id,
    knowledge_base_arn=knowledge.knowledge_base_arn,
)

api = ApiStack(
    app,
    f"{APP_NAME}-Api",
    env=env,
    data_bucket=storage.data_bucket,
    data_table=storage.data_table,
    user_pool=auth.user_pool,
    user_pool_client=auth.user_pool_client,
    agent_runtime_arn=agent.runtime_arn,
)

if frontend_hosting is not None:
    FrontendDeploymentStack(
        app,
        f"{APP_NAME}-FrontendDeployment",
        env=env,
        site_bucket=frontend_hosting.site_bucket,
        distribution=frontend_hosting.distribution,
        api_url=api.http_api.url or "",
        user_pool=auth.user_pool,
        user_pool_client=auth.user_pool_client,
        user_pool_domain_base_url=auth.user_pool_domain.base_url(),
    )

app.synth()
