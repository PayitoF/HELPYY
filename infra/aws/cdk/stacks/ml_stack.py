"""ML stack (POC) — Lambda scoring. $0/month when idle."""
import aws_cdk as cdk
from aws_cdk import aws_lambda as _lambda, aws_s3 as s3
from constructs import Construct

ML_CODE = """
def handler(event, ctx):
    return {"statusCode": 200, "body": "ML scoring placeholder"}
"""


class MLStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env_name: str,
                 model_bucket: s3.IBucket, **kwargs):
        super().__init__(scope, id, **kwargs)
        self.scoring_fn = _lambda.Function(self, "ScoringFn",
            function_name=f"helpyy-{env_name}-ml-scoring",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_inline(ML_CODE),
            timeout=cdk.Duration.seconds(30), memory_size=512,
            environment={"MODEL_BUCKET": model_bucket.bucket_name,
                         "MODEL_KEY": "models/logistic_regression/model.tar.gz"})
        model_bucket.grant_read(self.scoring_fn)
        cdk.CfnOutput(self, "ScoringFnArn", value=self.scoring_fn.function_arn)
