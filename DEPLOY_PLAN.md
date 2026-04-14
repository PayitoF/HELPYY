PLAN DE DEPLOY POC — Helpyy Hand AWS                                                                                                   
                                                                                                                                         
  Estado actual                                                                                                                          
                                                                                                                                         
  - Cuenta AWS: 622247620363 (us-east-1)                                                                                                 
  - Perfil: --profile helpyy (AWSAdministratorAccess via SSO)                                                                            
  - Bedrock habilitado: Claude 3 Haiku                                                                                                   
  - CDK instalado + requirements instalados                                                                                              
  - Bootstrap FALLÓ porque app.py referencia stacks viejos (VPC, KMS, ECS)                                                               
  - Necesita: reescribir stacks para POC, crear .dockerignore, luego bootstrap + deploy                                                  
                                                                                                                                         
  Arquitectura POC (~$35-50/mes)                                                                                                         
                                                                                                                                         
  - App Runner (no ECS+ALB) — escala a 0, HTTPS gratis                                                                                   
  - Sin VPC/NAT — $0                                                                                                                     
  - Bedrock Haiku (no Sonnet) — 12x más barato                                                                                           
  - Lambda para ML scoring (no SageMaker) — $0 idle                                                                                      
  - DynamoDB PAYPERREQUEST — free tier                                                                                                   
  - S3 + CloudFront para frontends — ~$1/mes                                                                                             
  - Sin WAF, sin KMS custom — POC                                                                                                        
                                                                                                                                         
  Archivo 1: .dockerignore (raíz del proyecto)                                                                                           
                                                                                                                                         
  cdk.out                                                                                                                                
  node_modules                                                                                                                           
  .git                                                                                                                                   
  MLRepo/data                                                                                                                            
  MLRepo/models                                                                                                                          
  frontend/app-mockup/node_modules                                                                                                       
  *.bak                                                                                                                                  
  __pycache__                                                                                                                            
  .pytest_cache                                                                                                                          
  data/                                                                                                                                  
                                                                                                                                         
  Archivo 2: infra/aws/cdk/stacks/data_stack.py                                                                                          
                                                                                                                                         
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
                                                                                                                                         
  Archivo 3: infra/aws/cdk/stacks/compute_stack.py                                                                                       
                                                                                                                                         
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
                   tables: dict[str, ddb.ITable], model_bucket: s3.IBucket, **kwargs):                                                   
          super().__init__(scope, id, **kwargs)                                                                                          
                                                                                                                                         
          image_asset = ecr_assets.DockerImageAsset(self, "ApiImage",                                                                    
              directory="../../..",                                                                                                      
              file="infra/docker/Dockerfile.api",                                                                                        
              exclude=["cdk.out", "node_modules", ".git", "MLRepo/data",                                                                 
                        "MLRepo/models", "*.bak", "__pycache__", ".pytest_cache"])                                                       
                                                                                                                                         
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
                                                                                                                                         
  Archivo 4: infra/aws/cdk/stacks/ml_stack.py                                                                                            
                                                                                                                                         
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
                                                                                                                                         
  Archivo 5: infra/aws/cdk/stacks/frontend_stack.py                                                                                      
                                                                                                                                         
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
                   api_url: str, **kwargs):                                                                                              
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
              default_behavior=cf.BehaviorOptions(                                                                                       
                  origin=origins.S3Origin(widget_bucket, origin_access_identity=widget_oai),                                             
                  viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS),                                                     
              default_root_object="index.html")                                                                                          
                                                                                                                                         
          cdk.CfnOutput(self, "AppUrl",                                                                                                  
              value=f"https://{self.app_dist.distribution_domain_name}")                                                                 
          cdk.CfnOutput(self, "WidgetUrl",                                                                                               
              value=f"https://{self.widget_dist.distribution_domain_name}")                                                              
          cdk.CfnOutput(self, "AppBucket", value=app_bucket.bucket_name)                                                                 
          cdk.CfnOutput(self, "WidgetBucket", value=widget_bucket.bucket_name)                                                           
          cdk.CfnOutput(self, "AppDistId", value=self.app_dist.distribution_id)                                                          
          cdk.CfnOutput(self, "WidgetDistId",                                                                                            
              value=self.widget_dist.distribution_id)                                                                                    
                                                                                                                                         
  Archivo 6: infra/aws/cdk/stacks/monitoring_stack.py                                                                                    
                                                                                                                                         
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
                                                                                                                                         
  Archivo 7: infra/aws/cdk/stacks/security_stack.py                                                                                      
                                                                                                                                         
  """Security stack (POC) — minimal placeholder."""                                                                                      
  import aws_cdk as cdk                                                                                                                  
  from constructs import Construct                                                                                                       
                                                                                                                                         
  class SecurityStack(cdk.Stack):                                                                                                        
      def __init__(self, scope: Construct, id: str, *, env_name: str, **kwargs):                                                         
          super().__init__(scope, id, **kwargs)                                                                                          
          cdk.CfnOutput(self, "Note",                                                                                                    
              value="POC: VPC/KMS/WAF disabled to save cost")                                                                            
                                                                                                                                         
  Archivo 8: infra/aws/cdk/app.py                                                                                                        
                                                                                                                                         
  #!/usr/bin/env python3                                                                                                                 
  """CDK app (POC) — orchestrates all stacks."""                                                                                         
  import os                                                                                                                              
  import aws_cdk as cdk                                                                                                                  
  from stacks.data_stack import DataStack                                                                                                
  from stacks.compute_stack import ComputeStack                                                                                          
  from stacks.ml_stack import MLStack                                                                                                    
  from stacks.frontend_stack import FrontendStack                                                                                        
  from stacks.monitoring_stack import MonitoringStack                                                                                    
                                                                                                                                         
  app = cdk.App()                                                                                                                        
  env_name = os.getenv("CDK_ENV", "dev")                                                                                                 
  aws_env = cdk.Environment(                                                                                                             
      account=os.getenv("CDK_DEFAULT_ACCOUNT", "622247620363"),                                                                          
      region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"))                                                                               
  tags = {"project": "helpyy-hand", "environment": env_name}                                                                             
                                                                                                                                         
  data = DataStack(app, f"helpyy-data-{env_name}",                                                                                       
      env=aws_env, env_name=env_name)                                                                                                    
                                                                                                                                         
  compute = ComputeStack(app, f"helpyy-compute-{env_name}",                                                                              
      env=aws_env, env_name=env_name,                                                                                                    
      tables=data.tables, model_bucket=data.model_bucket)                                                                                
  compute.add_dependency(data)                                                                                                           
                                                                                                                                         
  ml = MLStack(app, f"helpyy-ml-{env_name}",                                                                                             
      env=aws_env, env_name=env_name,                                                                                                    
      model_bucket=data.model_bucket)                                                                                                    
  ml.add_dependency(data)                                                                                                                
                                                                                                                                         
  frontend = FrontendStack(app, f"helpyy-frontend-{env_name}",                                                                           
      env=aws_env, env_name=env_name,                                                                                                    
      api_url=compute.api_url)                                                                                                           
  frontend.add_dependency(compute)                                                                                                       
                                                                                                                                         
  monitoring = MonitoringStack(app, f"helpyy-monitoring-{env_name}",                                                                     
      env=aws_env, env_name=env_name,                                                                                                    
      monitor_fn_name=compute.monitor_fn.function_name)                                                                                  
  monitoring.add_dependency(compute)                                                                                                     
                                                                                                                                         
  for stack in [data, compute, ml, frontend, monitoring]:                                                                                
      for k, v in tags.items():                                                                                                          
          cdk.Tags.of(stack).add(k, v)                                                                                                   
                                                                                                                                         
  app.synth()                                                                                                                            
                                                                                                                                         
  Pasos de deploy                                                                                                                        
                                                                                                                                         
  # 1. Limpiar cdk.out viejo                                                                                                             
  cd /Users/payo/Desktop/BBVA/helpyy-hand/infra/aws/cdk                                                                                  
  rm -rf cdk.out                                                                                                                         
                                                                                                                                         
  # 2. Crear .dockerignore en raíz del proyecto (Archivo 1)                                                                              
                                                                                                                                         
  # 3. Reemplazar los archivos 2-8 con el contenido de arriba                                                                            
                                                                                                                                         
  # 4. Bootstrap CDK                                                                                                                     
  cd infra/aws/cdk                                                                                                                       
  cdk bootstrap aws://622247620363/us-east-1 --profile helpyy                                                                            
                                                                                                                                         
  # 5. Synth (verificar que compila)                                                                                                     
  cdk synth --profile helpyy 2>&1 | head -20                                                                                             
                                                                                                                                         
  # 6. Deploy stack por stack                                                                                                            
  cdk deploy helpyy-data-dev --profile helpyy --require-approval never                                                                   
  cdk deploy helpyy-compute-dev --profile helpyy --require-approval never                                                                
  cdk deploy helpyy-ml-dev --profile helpyy --require-approval never                                                                     
  cdk deploy helpyy-frontend-dev --profile helpyy --require-approval never                                                               
  cdk deploy helpyy-monitoring-dev --profile helpyy --require-approval never                                                             
                                                                                                                                         
  # 7. Subir frontends a S3                                                                                                              
  cd /Users/payo/Desktop/BBVA/helpyy-hand                                                                                                
  cd frontend/app-mockup && npm run build && cd ../..                                                                                    
  aws s3 sync frontend/app-mockup/dist/ s3://helpyy-dev-app-622247620363/ --profile helpyy                                               
  aws s3 sync frontend/web-widget/ s3://helpyy-dev-widget-622247620363/ --profile helpyy                                                 
                                                                                                                                         
  # 8. Invalidar CloudFront (usar dist IDs del output del paso 6)                                                                        
  aws cloudfront create-invalidation --distribution-id XXXXX --paths "/*" --profile helpyy                                               
                                                                                                                                         
  GitHub Actions secrets a configurar                                                                                                    
                                                                                                                                         
  - AWSROLEARN_QA: (crear OIDC role)                                                                                                     
  - AWSACCOUNTID: 622247620363                                                                                                           
  - CFAPPDIST_ID: (del output de frontend stack)                                                                                         
  - CFWIDGETDIST_ID: (del output de frontend stack)                                                                                      
                                                                                                                                         
  Nota sobre compute_stack                                                                                                               
                                                                                                                                         
  Si App Runner da problemas con DockerImageAsset, alternativa: push manual a ECR y referenciar la URI directamente en image_identifier.


  NOtas adicionales : 
                                                                                                                                        
  Voy a planificar esto con cuidado porque el presupuesto es limitado. Primero déjame hacer el análisis de costos y luego te digo la     
  arquitectura optimizada.                                                                                                               
                                                                                                                                         
  Credenciales AWS                                                                                                                       
                                                                                                                                         
  NO me pases credenciales por el chat. En su lugar:                                                                                     
                                                                                                                                         
  1. Instala AWS CLI si no lo tienes: brew install awscli                                                                                
  2. Configura un perfil: aws configure --profile helpyy                                                                                 
  3. Te va a pedir: Access Key ID, Secret Access Key, Region (us-east-1), Output (json)                                                  
  4. Verifica que funcione: aws sts get-caller-identity --profile helpyy                                                                 
                                                                                                                                         
  Pégame el output de ese último comando (solo muestra account ID y user ARN, nada sensible).                                            
                                                                                                                                         
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
                                                                                                                                         
  Análisis de costos — $800 / 3 meses (~$267/mes)                                                                                        
                                                                                                                                         
  La arquitectura CDK que creamos es para producción. Para una POC con $267/mes necesitamos recortar agresivamente. Aquí el desglose:    
                                                                                                                                         
  ┌─────────────────────┬──────────────────────────────────┬───────────────────────────────────────────┬─────────────────┐               
  │ Servicio            │ Arquitectura CDK (prod)          │ POC optimizada                            │ Costo POC/mes   │               
  ├─────────────────────┼──────────────────────────────────┼───────────────────────────────────────────┼─────────────────┤               
  │ **Compute**         │ ECS Fargate (24/7) ~$35/mes      │ **ECS Fargate Spot** o **App Runner**     │ ~$15            │               
  │ **VPC + NAT**       │ NAT Gateway $32/mes              │ **Sin NAT, subnets públicas**             │ $0              │               
  │ **LLM**             │ Bedrock Claude Sonnet            │ **Bedrock Claude Haiku** (20x más barato) │ ~$5-15          │               
  │ **ML Scoring**      │ SageMaker endpoint 24/7 ~$50/mes │ **Lambda + modelo en container**          │ ~$1             │               
  │ **DynamoDB**        │ PAY_PER_REQUEST                  │ Igual (gratis con poco tráfico)           │ ~$0.50          │               
  │ **Frontend**        │ S3 + CloudFront                  │ Igual (prácticamente gratis)              │ ~$1             │               
  │ **Monitoring**      │ CloudWatch full                  │ Básico (free tier)                        │ $0              │               
  │ **CI/CD**           │ GitHub Actions                   │ Igual (gratis para repos públicos)        │ $0              │               
  │ **WAF**             │ $5/mes + $0.60/M requests        │ **Quitar WAF** (POC)                      │ $0              │               
  │ **KMS**             │ $1/key/mes                       │ 1 key                                     │ $1              │               
  │ **Secrets Manager** │ $0.40/secret/mes                 │ 2 secrets                                 │ $0.80           │               
  │                     │                                  │ **Total estimado**                        │ **~$35-50/mes** │               
  └─────────────────────┴──────────────────────────────────┴───────────────────────────────────────────┴─────────────────┘               
                                                                                                                                         
  Eso te deja ~$200/mes de margen para pruebas y picos.                                                                                  
                                                                                                                                         
  Arquitectura POC recomendada                                                                                                           
                                                                                                                                         
  ┌─────────────────────────────────────────────────────┐                                                                                
  │                    CloudFront                        │                                                                               
  │   app.helpyy.xyz ──→ S3 (React app)                │                                                                                 
  │   widget.helpyy.xyz ──→ S3 (Web widget)            │                                                                                 
  └──────────────────────┬──────────────────────────────┘                                                                                
                         │                                                                                                               
                ┌────────▼────────┐                                                                                                      
                │   App Runner     │  ← Auto-scale 0→N                                                                                   
                │   FastAPI API    │     (paga solo por uso)                                                                             
                │   Port 8000      │                                                                                                     
                └──┬─────┬────┬───┘                                                                                                      
                   │     │    │                                                                                                          
      ┌────────────▼┐ ┌──▼──┐ ├──────────────┐                                                                                           
      │  Bedrock    │ │DDB  │ │ Lambda       │                                                                                           
      │  Haiku      │ │     │ │ ML Scoring   │                                                                                           
      │  (LLM)     │ │     │ │ (model.pkl)  │                                                                                            
      └─────────────┘ └─────┘ └──────────────┘                                                                                           
                                │                                                                                                        
                      ┌─────────▼──────────┐                                                                                             
                      │ EventBridge (cron)  │                                                                                            
                      │ → Lambda Monitor   │                                                                                             
                      └────────────────────┘                                                                                             
                                                                                                                                         
  Cambios clave vs la arquitectura CDK:                                                                                                  
                                                                                                                                         
  1. App Runner en vez de ECS + ALB — escala a 0, no pagas cuando no hay tráfico, incluye HTTPS gratis                                   
  2. Sin VPC/NAT — App Runner es serverless, no necesita VPC                                                                             
  3. Lambda para ML en vez de SageMaker — carga el .pkl en una Lambda, $0 cuando no se usa                                               
  4. Bedrock Haiku en vez de Sonnet — $0.00025/1K input vs $0.003/1K (12x más barato), suficiente para la POC                            
  5. Sin WAF — innecesario para POC                                                                                                      
                                                                                                                                         
  CI/CD con GitHub                                                                                                                       
                                                                                                                                         
  El workflow que ya creamos funciona perfecto. El flujo:                                                                                
                                                                                                                                         
  PR a main → GitHub Actions corre tests → Deploy a QA (App Runner dev)                                                                  
  Merge a main → GitHub Actions → Deploy a Prod (App Runner prod)                                                                        
                                                                                                                                         
  No necesitas CodeBuild — GitHub Actions es gratis y ya lo tenemos configurado. Solo necesitas:                                         
                                                                                                                                         
  1. Crear un IAM user/role para GitHub Actions con OIDC                                                                                 
  2. Configurar los secrets en GitHub repo settings                                                                                      
                                                                                                                                         
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
                                                                                                                                         
  Próximos pasos concretos:                                                                                                              
                                                                                                                                         
  1. Pásame el output de aws sts get-caller-identity --profile helpyy                                                                    
  2. Te digo si el usuario tiene los permisos necesarios                                                                                 
  3. Ajusto los CDK stacks a la arquitectura POC                                                                                         
  4. Desplegamos paso a paso                                                                                                             
                                                                                                                                         
  ¿Quieres que ajuste los stacks CDK a esta arquitectura POC antes de desplegar?                                                         
                                                                                                                                         
▸ Credits: 2.13 • Time: 42s                                                                                                              
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  aws sts get-caller-identity --profile helpyy                                                                                           
                                                                                                                                         
  {                                                                                                                                      
   "UserId": "AROAZBYGZF4FWDFTK6HHJ:daniela.cardenas.blanco@bbva.com",                                                                   
   "Account": "622247620363",                                                                                                            
   "Arn":                                                                                                                                
  "arn:aws:sts::622247620363:assumed-role/AWSReservedSSO_AWSAdministratorAccess_ae62f2112b4156d7/daniela.cardenas.blanco@bbva.com"       
                                                                                                                                         
  Perfecto, tienes AWSAdministratorAccess en la cuenta 622247620363 — permisos suficientes para todo.                                    
                                                                                                                                         
  Antes de desplegar, necesito ajustar los stacks CDK a la arquitectura POC. ¿Quieres que:                                               
                                                                                                                                         
  1. Reescriba los stacks CDK para la arquitectura POC (App Runner, Lambda ML, sin VPC/NAT, Bedrock Haiku) — esto es lo que realmente    
  desplegamos                                                                                                                            
  2. Mantenga los stacks actuales como referencia de producción en una carpeta separada                                                  
                                                                                                                                         
  Te recomiendo la opción 1 — reescribir para POC y cuando escalen a producción se ajusta. No tiene sentido mantener código que no se va 
  a usar ahora.                                                                                                                          
                                                                                                                                         
  También necesito saber:                                                                                                                
                                                                                                                                         
  - Región: ¿us-east-1 está bien? Bedrock con Claude Haiku está disponible ahí.                                                          
  - Dominio: ¿Tienen un dominio propio (ej: helpyy.xyz) o usamos los URLs de CloudFront/App Runner directamente?                         
  - Bedrock: ¿Ya tienen acceso a Bedrock habilitado en la cuenta? Si no, hay que solicitarlo primero en la consola (tarda ~5 min).       
                                                                                                                                         
  Confirma y arranco con el ajuste + deploy.                                                                                             
                                                                                                                                         
▸ Credits: 1.87 • Time: 14s                                                                                                              
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  si has lo primero, la region esta bien us-east-1, no tenemos ningun dominio todo esta desde 0, y no tengo acceso a Bedrock             
                                                                                                                                         
  Primero lo de Bedrock — necesitas habilitarlo manualmente:                                                                             
                                                                                                                                         
  Habilitar Bedrock (2 minutos):                                                                                                         
                                                                                                                                         
  1. Ve a: https://us-east-1.console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess                                           
   (https://us-east-1.console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess)                                                 
  2. Click "Manage model access"                                                                                                         
  3. Busca y selecciona: Anthropic → Claude 3 Haiku                                                                                      
  4. Click "Request model access"                                                                                                        
  5. Debería aprobarse instantáneamente (es automático para Haiku)                                                                       
                                                                                                                                         
  Dime cuando lo tengas y arranco con el rewrite de los stacks + deploy. Mientras tanto voy planificando la estructura.                  
                                                                                                                                         
  Sobre los URLs — sin dominio propio usaremos:                                                                                          
                                                                                                                                         
  - App: https://d1xxxxx.cloudfront.net (CloudFront)                                                                                     
  - Widget: https://d2xxxxx.cloudfront.net (CloudFront)                                                                                  
  - API: https://xxxxx.us-east-1.awsapprunner.com (App Runner)                                                                           
                                                                                                                                         
  Funcionan perfecto para la POC, HTTPS incluido gratis.