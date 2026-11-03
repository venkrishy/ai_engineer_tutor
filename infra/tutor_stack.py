import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_sqs as sqs
from constructs import Construct

MAIL_BUCKET = "tutor-mail-theaiguru-908196778839"
OWNER_EMAIL = "venkrishy@gmail.com"


class TutorStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.table = dynamodb.Table(
            self,
            "Table",
            table_name="tutor-main",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        cdk.CfnOutput(self, "TableName", value=self.table.table_name)

        mail_bucket = s3.Bucket.from_bucket_name(self, "MailBucket", MAIL_BUCKET)

        alerts = sns.Topic(self, "Alerts")
        alerts.add_subscription(subscriptions.EmailSubscription(OWNER_EMAIL))

        dead_letters = sqs.Queue(self, "DeadLetters", retention_period=cdk.Duration.days(14))

        self.clerk = lambda_.Function(
            self,
            "Clerk",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="tutor.handler.lambda_handler",
            code=lambda_.Code.from_asset(
                "..",
                ignore_mode=cdk.IgnoreMode.GIT,
                exclude=["/*", "!/tutor", "__pycache__", "*.pyc"],
            ),
            timeout=cdk.Duration.minutes(5),
            memory_size=512,
            environment={"TABLE_NAME": self.table.table_name},
            dead_letter_queue=dead_letters,
            retry_attempts=2,
        )
        self.table.grant_read_write_data(self.clerk)
        mail_bucket.grant_read(self.clerk)
        self.clerk.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:GetAccount", "ses:ListEmailIdentities"],
                resources=["*"],
            )
        )

        mail_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.clerk),
            s3.NotificationKeyFilter(prefix="raw/"),
        )

        alarm = cloudwatch.Alarm(
            self,
            "DeadLettersNotEmpty",
            metric=dead_letters.metric_approximate_number_of_messages_visible(
                period=cdk.Duration.minutes(1)
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="A letter could not be answered.",
        )
        alarm.add_alarm_action(cw_actions.SnsAction(alerts))
