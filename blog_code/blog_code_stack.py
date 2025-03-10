from aws_cdk import (
    RemovalPolicy,
    Stack,
    aws_sqs as sqs,
    aws_iam as iam,
    aws_lambda,
    aws_sns as sns,
    aws_pipes as pipes,
    aws_logs as logs,
    aws_dynamodb as dynamodb
)
from constructs import Construct

class BlogCodeStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ################ Pipe components #######################

        # Pipe source SQS queue
        source_sqs_queue = sqs.Queue(
            self, 'SourceQueue',
            queue_name='SourceQueue',
            removal_policy=RemovalPolicy.DESTROY,
            enforce_ssl=True
        )

        # Pipe target SNS topic
        target_sns_topic = sns.Topic(
            self, "TargetTopic",
            topic_name="TargetTopic",
            enforce_ssl=True
        )

        # Enforce SSL on publisher
        target_sns_topic.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["sns:Publish"],
                resources=[target_sns_topic.topic_arn],
                conditions={
                    "Bool": {"aws:SecureTransport": "false"}  # Deny non-SSL traffic
                }
            )
        )

        #Eligibility table
        eligibility_table = dynamodb.Table(
            self, "EligibilityTable",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            table_name="EligibilityTable",
            removal_policy=RemovalPolicy.DESTROY
        )

        access_to_ddb_policy = iam.PolicyStatement(
            actions=[
                'dynamodb:PutItem',
                'dynamodb:GetItem'
            ],
            resources=[eligibility_table.table_arn],
            effect=iam.Effect.ALLOW
        )

        # Lambda enrichment
        enrichment_func = aws_lambda.Function(
            self, 'EnrichmentFunction',
            function_name='EnrichmentFunction',
            runtime=aws_lambda.Runtime.PYTHON_3_13,
            code=aws_lambda.Code.from_asset('blog_code/lambda'),
            handler='index.lambda_handler',
            tracing=aws_lambda.Tracing.ACTIVE,
            environment={
                "TABLE_NAME": eligibility_table.table_name
            }
        )

        enrichment_func.add_to_role_policy(access_to_ddb_policy)

        ################### IAM roles for Pipe ##################

        pipe_source_policy = iam.PolicyStatement(
            actions=[
                'sqs:ReceiveMessage', 
                'sqs:DeleteMessage', 
                'sqs:GetQueueAttributes'
            ],
            resources=[source_sqs_queue.queue_arn],
            effect=iam.Effect.ALLOW
        )

        pipe_target_policy = iam.PolicyStatement(
            actions=['sns:Publish'],
            resources=[target_sns_topic.topic_arn],
            effect=iam.Effect.ALLOW
        )

        pipe_enrichment_policy = iam.PolicyStatement(
            actions=['lambda:InvokeFunction'],
            resources=[enrichment_func.function_arn],
            effect=iam.Effect.ALLOW
        )

        # create the pipe role
        pipe_role = iam.Role(self, 'PipeRole',
            assumed_by=iam.ServicePrincipal('pipes.amazonaws.com'),
        )

        # add the three policies to the role
        pipe_role.add_to_policy(pipe_source_policy)
        pipe_role.add_to_policy(pipe_target_policy)
        pipe_role.add_to_policy(pipe_enrichment_policy)

        ################### EventBridge Pipe  ###################

        log_group = logs.LogGroup(
            self, 'PipesLogGroup',
            log_group_name='PipesLogGroup',
            removal_policy=RemovalPolicy.DESTROY
        )

        pipe = pipes.CfnPipe(
            self, "EnrichmentPipe",
            role_arn=pipe_role.role_arn,
            source=source_sqs_queue.queue_arn,
            target=target_sns_topic.topic_arn,
            enrichment=enrichment_func.function_arn,
            log_configuration=pipes.CfnPipe.PipeLogConfigurationProperty(
            cloudwatch_logs_log_destination=pipes.CfnPipe.CloudwatchLogsLogDestinationProperty(
                    log_group_arn=log_group.log_group_arn
                ),
                level='INFO',
            ),
        )

        pipe.apply_removal_policy(RemovalPolicy.DESTROY)
