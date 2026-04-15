"""Security stack (POC) — WAF basic rules for CloudFront. ~$5/mes."""
import aws_cdk as cdk
from aws_cdk import aws_wafv2 as wafv2
from constructs import Construct


class SecurityStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # WAF Web ACL — CLOUDFRONT scope must be deployed in us-east-1
        self.web_acl = wafv2.CfnWebACL(self, "WebACL",
            name=f"helpyy-{env_name}-waf",
            scope="CLOUDFRONT",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=f"helpyy-{env_name}-waf",
                sampled_requests_enabled=True,
            ),
            rules=[
                # AWS Managed: common threats (SQLi, XSS, etc.)
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=1,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet",
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="CommonRuleSet",
                        sampled_requests_enabled=True,
                    ),
                ),
                # AWS Managed: known bad inputs
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesKnownBadInputsRuleSet",
                    priority=2,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesKnownBadInputsRuleSet",
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="KnownBadInputs",
                        sampled_requests_enabled=True,
                    ),
                ),
                # Rate limit: 100 req/5min per IP on /api/
                wafv2.CfnWebACL.RuleProperty(
                    name="RateLimitAPI",
                    priority=3,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            limit=100,
                            aggregate_key_type="IP",
                            scope_down_statement=wafv2.CfnWebACL.StatementProperty(
                                byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                                    search_string="/api/",
                                    field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(
                                        uri_path={}
                                    ),
                                    text_transformations=[
                                        wafv2.CfnWebACL.TextTransformationProperty(
                                            priority=0, type="NONE"
                                        )
                                    ],
                                    positional_constraint="STARTS_WITH",
                                )
                            ),
                        )
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="RateLimitAPI",
                        sampled_requests_enabled=True,
                    ),
                ),
            ],
        )

        cdk.CfnOutput(self, "WebACLArn", value=self.web_acl.attr_arn)
        cdk.CfnOutput(self, "WebACLId", value=self.web_acl.attr_id)
