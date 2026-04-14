"""Data stack (POC) — DynamoDB + S3. No KMS, AWS-owned encryption."""
import aws_cdk as cdk
from aws_cdk import aws_dynamodb as ddb, aws_s3 as s3
from constructs import Construct


class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        r = cdk.RemovalPolicy.DESTROY
        self.tables = {}

        self.tables["users"] = ddb.Table(self, "Users",
            table_name=f"helpyy-{env_name}-users",
            partition_key=ddb.Attribute(name="user_id", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST, removal_policy=r)
        self.tables["users"].add_global_secondary_index(index_name="cedula-index",
            partition_key=ddb.Attribute(name="cedula", type=ddb.AttributeType.STRING))

        self.tables["sessions"] = ddb.Table(self, "Sessions",
            table_name=f"helpyy-{env_name}-sessions",
            partition_key=ddb.Attribute(name="session_id", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl", removal_policy=r)

        self.tables["notifications"] = ddb.Table(self, "Notifications",
            table_name=f"helpyy-{env_name}-notifications",
            partition_key=ddb.Attribute(name="user_id", type=ddb.AttributeType.STRING),
            sort_key=ddb.Attribute(name="created_at", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST, removal_policy=r)

        self.tables["pii_vault"] = ddb.Table(self, "PIIVault",
            table_name=f"helpyy-{env_name}-pii-vault",
            partition_key=ddb.Attribute(name="session_id", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at", removal_policy=r)

        self.tables["missions"] = ddb.Table(self, "Missions",
            table_name=f"helpyy-{env_name}-missions",
            partition_key=ddb.Attribute(name="user_id", type=ddb.AttributeType.STRING),
            sort_key=ddb.Attribute(name="mission_id", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST, removal_policy=r)

        self.model_bucket = s3.Bucket(self, "ModelBucket",
            bucket_name=f"helpyy-{env_name}-models-{self.account}",
            versioned=True, block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=r, auto_delete_objects=True)

        for name, table in self.tables.items():
            cdk.CfnOutput(self, f"{name}TableName", value=table.table_name)
        cdk.CfnOutput(self, "ModelBucketName", value=self.model_bucket.bucket_name)
