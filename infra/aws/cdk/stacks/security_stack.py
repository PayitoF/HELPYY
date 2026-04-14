"""Security stack (POC) — minimal placeholder."""
import aws_cdk as cdk
from constructs import Construct


class SecurityStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        cdk.CfnOutput(self, "Note",
            value="POC: VPC/KMS/WAF disabled to save cost")
