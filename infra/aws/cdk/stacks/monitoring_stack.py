"""Monitoring stack (POC) — basic CloudWatch + SNS. Free tier."""
import aws_cdk as cdk
from aws_cdk import (
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
)
from constructs import Construct


class MonitoringStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env_name: str,
                 monitor_fn_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        self.alerts = sns.Topic(self, "Alerts",
            topic_name=f"helpyy-{env_name}-alerts")
        monitor_errors = cw.Alarm(self, "MonitorErrors",
            alarm_name=f"helpyy-{env_name}-monitor-errors",
            metric=cw.Metric(
                namespace="AWS/Lambda",
                metric_name="Errors",
                dimensions_map={"FunctionName": monitor_fn_name},
                statistic="Sum",
                period=cdk.Duration.minutes(15)),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD)
        monitor_errors.add_alarm_action(cw_actions.SnsAction(self.alerts))
        cdk.CfnOutput(self, "AlertsTopicArn",
            value=self.alerts.topic_arn)
