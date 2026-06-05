#!/usr/bin/env python3
"""CDK entry point. Account-agnostic — picks up account/region from the caller env."""
import os

import aws_cdk as cdk

from cdk_app.agent_stack import AgentStack
from cdk_app.api_stack import ApiStack
from cdk_app.storage_stack import StorageStack

APP_NAME = os.environ.get("APP_NAME", "Lab3")

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

storage = StorageStack(app, f"{APP_NAME}-Storage", env=env)

agent = AgentStack(
    app,
    f"{APP_NAME}-Agent",
    env=env,
    data_table=storage.data_table,
    event_bus=storage.event_bus,
    data_bucket=storage.data_bucket,
)

ApiStack(
    app,
    f"{APP_NAME}-Api",
    env=env,
    data_bucket=storage.data_bucket,
    agent_runtime_arn=agent.runtime_arn,
)

app.synth()
