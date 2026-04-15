"""ML stack (POC) — Lambda Docker with real model + Function URL."""
import aws_cdk as cdk
from aws_cdk import (
    aws_lambda as _lambda,
    aws_ecr_assets as ecr_assets,
    aws_s3 as s3,
)
from constructs import Construct


class MLStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env_name: str,
                 model_bucket: s3.IBucket, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Docker image with model + sklearn + handler
        image = ecr_assets.DockerImageAsset(self, "MLImage",
            directory="../../..",
            file="infra/docker/Dockerfile.ml",
            platform=ecr_assets.Platform.LINUX_AMD64,
            exclude=["cdk.out", "node_modules", ".git", "frontend",
                      "tests", "docs", "*.bak", "__pycache__",
                      ".pytest_cache", "backend", "infra/aws"])

        self.scoring_fn = _lambda.DockerImageFunction(self, "ScoringFn",
            function_name=f"helpyy-{env_name}-ml-scoring",
            code=_lambda.DockerImageCode.from_ecr(
                repository=image.repository,
                tag_or_digest=image.asset_hash),
            timeout=cdk.Duration.seconds(30),
            memory_size=512)

        # Function URL — public HTTPS endpoint for the ML service
        fn_url = self.scoring_fn.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE)

        self.ml_url = fn_url.url

        model_bucket.grant_read(self.scoring_fn)
        cdk.CfnOutput(self, "ScoringFnArn", value=self.scoring_fn.function_arn)
        cdk.CfnOutput(self, "MLServiceUrl", value=fn_url.url)
