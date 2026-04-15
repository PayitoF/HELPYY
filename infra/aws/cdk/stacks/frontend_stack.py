"""Frontend stack (POC) — S3 + CloudFront for app and widget."""
import aws_cdk as cdk
from aws_cdk import (
    aws_cloudfront as cf,
    aws_cloudfront_origins as origins,
    aws_s3 as s3,
)
from constructs import Construct


class FrontendStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env_name: str,
                 api_url: str, web_acl_arn: str | None = None, **kwargs):
        super().__init__(scope, id, **kwargs)
        r = cdk.RemovalPolicy.DESTROY

        app_bucket = s3.Bucket(self, "AppBucket",
            bucket_name=f"helpyy-{env_name}-app-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=r, auto_delete_objects=True)
        app_oai = cf.OriginAccessIdentity(self, "AppOAI")
        app_bucket.grant_read(app_oai)
        self.app_dist = cf.Distribution(self, "AppDist",
            comment=f"Helpyy App ({env_name})",
            web_acl_id=web_acl_arn,
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3Origin(app_bucket, origin_access_identity=app_oai),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS),
            default_root_object="index.html",
            error_responses=[cf.ErrorResponse(http_status=404,
                response_http_status=200, response_page_path="/index.html",
                ttl=cdk.Duration.seconds(0))])

        widget_bucket = s3.Bucket(self, "WidgetBucket",
            bucket_name=f"helpyy-{env_name}-widget-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=r, auto_delete_objects=True)
        widget_oai = cf.OriginAccessIdentity(self, "WidgetOAI")
        widget_bucket.grant_read(widget_oai)
        self.widget_dist = cf.Distribution(self, "WidgetDist",
            comment=f"Helpyy Widget ({env_name})",
            web_acl_id=web_acl_arn,
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3Origin(widget_bucket, origin_access_identity=widget_oai),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS),
            default_root_object="index.html")

        cdk.CfnOutput(self, "AppUrl",
            value=f"https://{self.app_dist.distribution_domain_name}")
        cdk.CfnOutput(self, "WidgetUrl",
            value=f"https://{self.widget_dist.distribution_domain_name}")
        cdk.CfnOutput(self, "AppBucketName", value=app_bucket.bucket_name)
        cdk.CfnOutput(self, "WidgetBucketName", value=widget_bucket.bucket_name)
        cdk.CfnOutput(self, "AppDistId", value=self.app_dist.distribution_id)
        cdk.CfnOutput(self, "WidgetDistId",
            value=self.widget_dist.distribution_id)
