"""Compute stack (POC) — App Runner + Lambda monitor. No VPC."""
import aws_cdk as cdk
from aws_cdk import (
    aws_apprunner as apprunner,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_dynamodb as ddb,
    aws_s3 as s3,
)
from constructs import Construct

MONITOR_CODE = """
import json, os, urllib.request
def handler(event, ctx):
    url = os.environ["API_URL"] + "/api/v1/monitor/run"
    req = urllib.request.Request(url, method="POST",
        headers={"Content-Type": "application/json"}, data=b"{}")
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())
"""


class ComputeStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env_name: str,
                 tables: dict[str, ddb.ITable], model_bucket: s3.IBucket,
                 ml_service_url: str = "", **kwargs):
        super().__init__(scope, id, **kwargs)

        image_asset = ecr_assets.DockerImageAsset(self, "ApiImage",
            directory="../../..",
            file="infra/docker/Dockerfile.api",
            platform=ecr_assets.Platform.LINUX_AMD64,
            exclude=["cdk.out", "node_modules", ".git", "MLRepo",
                      "frontend", "tests", "docs", "*.bak", "__pycache__",
                      ".pytest_cache", "infra/aws/cdk/cdk.out",
                      "helpyy_hand.egg-info", ".github"])

        access_role = iam.Role(self, "AccessRole",
            assumed_by=iam.ServicePrincipal("build.apprunner.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSAppRunnerServicePolicyForECRAccess")])

        instance_role = iam.Role(self, "InstanceRole",
            assumed_by=iam.ServicePrincipal("tasks.apprunner.amazonaws.com"))
        for table in tables.values():
            table.grant_read_write_data(instance_role)
        model_bucket.grant_read(instance_role)
        instance_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"]))

        self.service = apprunner.CfnService(self, "ApiService",
            service_name=f"helpyy-{env_name}-api",
            source_configuration=apprunner.CfnService.SourceConfigurationProperty(
                authentication_configuration=apprunner.CfnService.AuthenticationConfigurationProperty(
                    access_role_arn=access_role.role_arn),
                image_repository=apprunner.CfnService.ImageRepositoryProperty(
                    image_identifier=image_asset.image_uri,
                    image_repository_type="ECR",
                    image_configuration=apprunner.CfnService.ImageConfigurationProperty(
                        port="8000",
                        runtime_environment_variables=[
                            apprunner.CfnService.KeyValuePairProperty(name="LLM_PROVIDER", value="bedrock"),
                            apprunner.CfnService.KeyValuePairProperty(name="BEDROCK_MODEL_ID",
                                value="anthropic.claude-3-haiku-20240307-v1:0"),
                            apprunner.CfnService.KeyValuePairProperty(name="DATABASE_TYPE", value="dynamodb"),
                            apprunner.CfnService.KeyValuePairProperty(name="DYNAMODB_TABLE_PREFIX", value=f"helpyy-{env_name}-"),
                            apprunner.CfnService.KeyValuePairProperty(name="LOG_LEVEL", value="INFO"),
                            apprunner.CfnService.KeyValuePairProperty(name="AWS_DEFAULT_REGION", value=self.region),
                            apprunner.CfnService.KeyValuePairProperty(name="ML_SERVICE_URL", value=ml_service_url),
                        ]))),
            instance_configuration=apprunner.CfnService.InstanceConfigurationProperty(
                cpu="1024", memory="2048",
                instance_role_arn=instance_role.role_arn),
            health_check_configuration=apprunner.CfnService.HealthCheckConfigurationProperty(
                protocol="HTTP", path="/health"))

        self.api_url = cdk.Fn.join("", ["https://", self.service.attr_service_url])

        self.monitor_fn = _lambda.Function(self, "MonitorFn",
            function_name=f"helpyy-{env_name}-monitor",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_inline(MONITOR_CODE),
            timeout=cdk.Duration.minutes(2), memory_size=128,
            environment={"API_URL": self.api_url})

        events.Rule(self, "MonitorCron",
            schedule=events.Schedule.rate(cdk.Duration.hours(6)),
            targets=[targets.LambdaFunction(self.monitor_fn)])

        cdk.CfnOutput(self, "ApiUrl", value=self.api_url)
        cdk.CfnOutput(self, "MonitorFnName", value=self.monitor_fn.function_name)
