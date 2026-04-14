#!/usr/bin/env python3
"""CDK app (POC) — orchestrates all stacks."""
import os
import aws_cdk as cdk
from stacks.data_stack import DataStack
from stacks.compute_stack import ComputeStack
from stacks.ml_stack import MLStack
from stacks.frontend_stack import FrontendStack
from stacks.monitoring_stack import MonitoringStack

app = cdk.App()
env_name = os.getenv("CDK_ENV", "dev")
aws_env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT", "622247620363"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"))
tags = {"project": "helpyy-hand", "environment": env_name}

data = DataStack(app, f"helpyy-data-{env_name}",
    env=aws_env, env_name=env_name)

compute = ComputeStack(app, f"helpyy-compute-{env_name}",
    env=aws_env, env_name=env_name,
    tables=data.tables, model_bucket=data.model_bucket)
compute.add_dependency(data)

ml = MLStack(app, f"helpyy-ml-{env_name}",
    env=aws_env, env_name=env_name,
    model_bucket=data.model_bucket)
ml.add_dependency(data)

frontend = FrontendStack(app, f"helpyy-frontend-{env_name}",
    env=aws_env, env_name=env_name,
    api_url=compute.api_url)
frontend.add_dependency(compute)

monitoring = MonitoringStack(app, f"helpyy-monitoring-{env_name}",
    env=aws_env, env_name=env_name,
    monitor_fn_name=compute.monitor_fn.function_name)
monitoring.add_dependency(compute)

for stack in [data, compute, ml, frontend, monitoring]:
    for k, v in tags.items():
        cdk.Tags.of(stack).add(k, v)

app.synth()
