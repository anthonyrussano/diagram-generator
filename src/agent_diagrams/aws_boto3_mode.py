#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import botocore.session
from datetime import datetime, tzinfo, timedelta
from argparse import ArgumentParser
import json
import os
import platform
import sys
import hashlib
from collections import defaultdict
import warnings
from textwrap import wrap
import math

# diagrams imports
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import EC2, Lambda, ECS, EKS
from diagrams.aws.database import RDS, Dynamodb, Elasticache, Redshift
from diagrams.aws.network import ELB, ALB, VPC, Route53, CloudFront, NATGateway, InternetGateway, Endpoint
from diagrams.aws.storage import S3, EFS, EBS
from diagrams.aws.integration import SQS, SNS
from diagrams.aws.analytics import Kinesis
from diagrams.aws.security import Shield

# Optional subnet icons (not present in all versions of diagrams)
try:
    from diagrams.aws.network import PrivateSubnet, PublicSubnet  # type: ignore
except Exception:
    PrivateSubnet = None
    PublicSubnet = None

requiredBotocoreVersion = "1.27.77"
usage = "Usage: python aws_to_diagram.py --profile <profile_name> --region <region_name> [--tag <tag_keyword>] [-o <output_file>]"

ERRORS = []
ERROR_COLOR = '\033[91m'
WARNING_COLOR = '\033[93m'
END_COLOR = '\033[0m'

# suppress the warning about endpoint url
warnings.filterwarnings('ignore', category=FutureWarning, module='botocore.client')

# -------------------- time utils --------------------
class SimpleUtc(tzinfo):
    def tzname(self):
        return "UTC"
    def utcoffset(self, dt):
        return timedelta(0)

# -------------------- console utils --------------------
def print_err(msg, warning=False):
    start_color = WARNING_COLOR if warning else ERROR_COLOR
    print(start_color + msg + END_COLOR)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.utcnow().replace(tzinfo=SimpleUtc()).isoformat()
        return json.JSONEncoder.default(self, o)

class AwsImportTarget:
    def __init__(self, profile_name, region):
        self.profile_name = profile_name
        self.region = region

# -------------------- helpers --------------------
def chunk_list(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]

def flatten_list(l):
    return [item for sublist in l for item in sublist]

def encrypt_string(raw_string):
    return hashlib.sha256(raw_string.encode()).hexdigest()

def handle_error(target_info, e, name=''):
    errorMessage = 'Error: {account}:{region}:{name} {errorMessage}'.format(
        account=target_info.profile_name, region=target_info.region, name=name, errorMessage=str(e))
    ERRORS.append(errorMessage)
    print_err(errorMessage)

def make_request(request_fn, target_info, resourceName, key, abort_on_error = False, filters = False):
    try:
        print('Executing {account}:{region}:{resourceName}'.format(
            account=target_info.profile_name, region=target_info.region, resourceName=resourceName))
        result = request_fn(Filters=filters) if filters else request_fn()
        return result.get(key, [])
    except Exception as e:
        handle_error(target_info, e, resourceName)
        return []

def paginate(fn, key, **kwargs):
    """Simple paginator that supports NextToken/Marker styles."""
    items = []
    token_keys = ["NextToken", "Marker", "NextMarker"]
    resp = fn(**kwargs)
    items += resp.get(key, [])
    while True:
        token_key = next((tk for tk in token_keys if resp.get(tk)), None)
        if not token_key:
            break
        resp = fn(**{**kwargs, token_key: resp[token_key]})
        items += resp.get(key, [])
    return items

def build_subnet_index(subnets, route_tables):
    """
    Return:
      - subnet_id -> {"az": "...", "cidr": "...", "vpc_id": "...", "public": bool, "route_table_id": "..."}
      - vpc_id -> set(subnet_ids)
      - route_table_id -> route_table
    Public detection: MapPublicIpOnLaunch OR default route to an InternetGateway.
    """
    subnet_idx = {}
    vpc_to_subnets = defaultdict(set)
    rt_by_id = {rt["RouteTableId"]: rt for rt in route_tables}

    # subnet -> route table
    rt_for_subnet = {}
    for rt in route_tables:
        for assoc in rt.get("Associations", []):
            if assoc.get("SubnetId"):
                rt_for_subnet[assoc["SubnetId"]] = rt["RouteTableId"]

    def rt_has_igw(rt):
        for r in rt.get("Routes", []):
            if r.get("DestinationCidrBlock") == "0.0.0.0/0" and str(r.get("GatewayId", "")).startswith("igw-"):
                return True
        return False

    for s in subnets:
        sid = s["SubnetId"]
        vpc_id = s["VpcId"]
        vpc_to_subnets[vpc_id].add(sid)
        rt_id = rt_for_subnet.get(sid)
        rtb = rt_by_id.get(rt_id, {})
        public = bool(s.get("MapPublicIpOnLaunch")) or rt_has_igw(rtb)
        subnet_idx[sid] = {
            "az": s.get("AvailabilityZone"),
            "cidr": s.get("CidrBlock"),
            "vpc_id": vpc_id,
            "public": public,
            "route_table_id": rt_id
        }
    return subnet_idx, vpc_to_subnets, rt_by_id

# -------------------- AWS fetchers --------------------
def get_complete_api_gateways(client, target_info):
    try:
        print('Executing {account}:{region}:apigateway:GET'.format(
            account=target_info.profile_name, region=target_info.region))
        rest_apis = []
        result = client.get_rest_apis()
        rest_apis += result.get('items', [])
        while result.get('position', None):
            result = client.get_rest_apis(position=result.get('position', None))
            rest_apis += result.get('items', [])
        for rest_api in rest_apis:
            api_id = rest_api['id']
            rest_api_resources = client.get_resources(
                restApiId=api_id, embed=['methods']).get('items')

            def get_integrations_for_resource(resource):
                integrations = []
                methods = resource.get('resourceMethods', {})
                for method in methods:
                    integration = methods[method].get('methodIntegration', None)
                    if integration:
                        integrations.append(integration)
                return integrations

            from itertools import chain
            integrations = list(chain.from_iterable(map(get_integrations_for_resource, rest_api_resources)))

            resources_obj = {
                'resources': rest_api_resources,
                'integrations': integrations
            }
            rest_api.update(resources_obj)
        return rest_apis
    except Exception as e:
        handle_error(target_info, e, 'apigateway:get_rest_apis,get_resources,get_integrations')
        return []

def get_complete_api_gateway_v2s(client, target_info):
    try:
        print('Executing {account}:{region}:apigatewayv2:GET'.format(
            account=target_info.profile_name, region=target_info.region))
        apis = []
        result = client.get_apis()
        apis += result.get('Items', [])
        while result.get('NextToken', None):
            result = client.get_apis(NextToken=result.get('NextToken', None))
            apis += result.get('Items', [])
        for api in apis:
            api_id = api['ApiId']
            api_routes = client.get_routes(ApiId = api_id).get('Items')
            api_integrations = client.get_integrations(ApiId = api_id).get('Items')
            extras_obj = {
                'Routes': api_routes,
                'Integrations': api_integrations
            }
            api.update(extras_obj)
        return apis
    except Exception as e:
        handle_error(target_info, e, 'apigatewayv2:get_apis,get_routes,get_integrations')
        return []

def get_cloudfront_distributions(client, target_info):
    try:
        print('Executing {account}:{region}:cloudfront:list_distributions'.format(
            account=target_info.profile_name, region=target_info.region))
        result = client.list_distributions().get('DistributionList', {}).get('Items', [])
        return result
    except Exception as e:
        handle_error(target_info, e, 'cloudfront:list_distributions:')
        return []

def get_lambda_functions(client, target_info):
    try:
        print('Executing {account}:{region}:lambda:list_functions'.format(
            account=target_info.profile_name, region=target_info.region))
        result = client.list_functions()
        functions = result['Functions']
        while 'NextMarker' in result:
            result = client.list_functions(Marker=result['NextMarker'])
            functions.extend(result['Functions'])
        for lambdaFunction in functions:
            if 'Environment' in lambdaFunction:
                del lambdaFunction['Environment']
            try:
                tags = client.list_tags(Resource=lambdaFunction['FunctionArn'])['Tags']
                lambdaFunction['Tags'] = tags
            except Exception as e:
                print('Error fetching tag info for lambda function "{arn}".\nError: {error}'.format(
                    arn=lambdaFunction['FunctionArn'], error=str(e)))
        return functions
    except Exception as e:
        handle_error(target_info, e, 'lambda:list_functions:')
        return []

def get_lambda_event_source_mappings(client, target_info):
    try:
        print('Executing {account}:{region}:lambda:list_event_source_mappings'.format(
            account=target_info.profile_name, region=target_info.region))
        result = client.list_event_source_mappings(MaxItems=100)
        mappings = result['EventSourceMappings']
        while 'NextMarker' in result:
            result = client.list_event_source_mappings(Marker=result['NextMarker'], MaxItems=100)
            mappings.extend(result['EventSourceMappings'])
        return mappings
    except Exception as e:
        handle_error(target_info, e, 'lambda:list_event_source_mappings:')
        return []

def get_appsync_graphqlapis(client, target_info):
    try:
        print('Executing {account}:{region}:appsync:list_graphql_apis'.format(
            account=target_info.profile_name, region=target_info.region))
        graphql_apis = client.list_graphql_apis()['graphqlApis']
        for graphql_api in graphql_apis:
            try:
                dataSources = client.list_data_sources(apiId=graphql_api['apiId'])['dataSources']
                graphql_api['dataSources'] = dataSources
            except Exception as e:
                print('Error fetching dataSources for AppSync GraphQL API "{arn}"\nError: {error}'.format(
                    arn=graphql_api['arn'], error=str(e)))
        return graphql_apis
    except Exception as e:
        handle_error(target_info, e, 'appsync:list_graphql_apis')
        return []

def get_sns_subscription_attributes(client, subscription, target_info):
    try:
        result = client.get_subscription_attributes(SubscriptionArn=subscription['SubscriptionArn'])
        return result['Attributes']
    except Exception as e:
        handle_error(target_info, e, 'sns:get_subscription_attributes')
        return subscription

def get_sns_subscriptions(client, target_info):
    try:
        print('Executing {account}:{region}:sns:list_subscriptions'.format(
            account=target_info.profile_name, region=target_info.region))
        result = client.list_subscriptions()
        subscriptions = result.get('Subscriptions') if 'Subscriptions' in result else []
        while 'NextToken' in result:
            result = client.list_subscriptions(NextToken=result['NextToken'])
            subscriptions.extend(result.get('Subscriptions') if 'Subscriptions' in result else [])
        full_subscriptions = []
        for subscription in subscriptions:
            full_subscriptions.append(get_sns_subscription_attributes(client, subscription, target_info))
        return full_subscriptions
    except Exception as e:
        handle_error(target_info, e, 'sns:list_subscriptions')
        return []

def get_target_groups(client, target_info):
    try:
        target_groups = make_request(client.describe_target_groups, target_info, 'elbv2:describe_target_groups', 'TargetGroups')
        print('Executing {account}:{region}:elbv2:describe_target_health'.format(
            account=target_info.profile_name, region=target_info.region))
        for target_group in target_groups:
            try:
                response = client.describe_target_health(TargetGroupArn=target_group['TargetGroupArn'])['TargetHealthDescriptions']
                target_group['TargetHealthDescriptions'] = response
            except Exception as e:
                handle_error(target_info, e, 'elbv2:describe_target_health:')
                target_group['TargetHealthDescriptions'] = []
        return target_groups
    except Exception as e:
        handle_error(target_info, e, 'elbv2:describe_target_groups')
        return []

snsTopicAttributeWhitelist = {
    "TopicArn", "Owner", "Policy", "DisplayName", "SubscriptionsPending",
    "SubscriptionsConfirmed", "SubscriptionsDeleted", "DeliveryPolicy",
    "EffectiveDeliveryPolicy", "KmsMasterKeyId"
}

def get_sns_topics(client, topics, target_info):
    try:
        result = []
        for t in topics:
            attrs = client.get_topic_attributes(TopicArn=t['TopicArn'])
            whitelistedAttributes = {key: value for (key,value) in attrs['Attributes'].items() if key in snsTopicAttributeWhitelist}
            result.append({
                'Attributes': whitelistedAttributes,
                'TopicArn': t['TopicArn'],
            })
        return result
    except Exception as e:
        handle_error(target_info, e, 'sns:get_topic_attributes:')
        return []

sqsQueueAttributeWhitelist = {
    "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesDelayed",
    "ApproximateNumberOfMessagesNotVisible", "CreatedTimestamp", "DelaySeconds",
    "LastModifiedTimestamp", "MaximumMessageSize", "MessageRetentionPeriod",
    "Policy", "QueueArn", "ReceiveMessageWaitTimeSeconds", "RedrivePolicy",
    "VisibilityTimeout", "KmsMasterKeyId", "KmsDataKeyReusePeriodSeconds",
    "FifoQueue", "ContentBasedDeduplication"
}

def get_sqs_queues(client, queueUrls, target_info):
    try:
        result = []
        for url in queueUrls:
            attrs = client.get_queue_attributes(AttributeNames=['All'], QueueUrl=url)
            whitelistedAttributes = {key: value for (key,value) in attrs['Attributes'].items() if key in sqsQueueAttributeWhitelist}
            tags = {}
            try:
                tags = client.list_queue_tags(QueueUrl=url)['Tags']
            except Exception as e:
                print('Error fetching tag info for SQS Queue "{url}".\nError: {error}'.format(url=url, error=str(e)))
            result.append({
                'Attributes': whitelistedAttributes,
                'QueueUrl': url,
                'Tags': tags,
            })
        return result
    except Exception as e:
        handle_error(target_info, e, 'sqs:get_queue_attributes:')
        return []

def get_dynamoDB_tables(client, tableNames, target_info):
    try:
        response = [client.describe_table(TableName=tableName)['Table'] for tableName in tableNames]
        return response
    except Exception as e:
        handle_error(target_info, e, 'dynamodb:describe_table')
        return []

def filter_s3_buckets_to_target_region(client, buckets, target_info):
    try:
        result = []
        for bucket in buckets:
            attrs = client.get_bucket_location(Bucket=bucket['Name'])
            region = attrs['LocationConstraint']
            if region == None:
                region = 'us-east-1'
            if region == target_info.region:
                result.append(bucket)
        return result
    except Exception as e:
        handle_error(target_info, e, 's3:get_bucket_location:')
        return []

def get_complete_albs(client, albs, targetGroups):
    albsResult = []
    targetGroupsResult = []

    resourceArns = []
    arnToTypeMap = {}
    arnToObjMap = {}
    for alb in albs:
        arn = alb['LoadBalancerArn']
        resourceArns.append(arn)
        arnToTypeMap[arn] = 'alb'
        arnToObjMap[arn] = alb
    for group in targetGroups:
        arn = group['TargetGroupArn']
        resourceArns.append(arn)
        arnToTypeMap[arn] = 'group'
        arnToObjMap[arn] = group

    tagInfoForAllResources = []
    try:
        chunkedListOfArns = chunk_list(resourceArns, 20)
        listOfTagLists = [client.describe_tags(ResourceArns=l)['TagDescriptions'] for l in chunkedListOfArns]
        tagInfoForAllResources = flatten_list(listOfTagLists)
    except Exception as e:
        print_err('Error fetching tag info for albs and target groups.\nError: {error}'.format(error=str(e)))

    for tagInfo in tagInfoForAllResources:
        arn = tagInfo['ResourceArn']
        del tagInfo['ResourceArn']
        obj = arnToObjMap.get(arn, {}).copy()
        obj.update(tagInfo)
        resourceType = arnToTypeMap.get(arn)
        if resourceType == 'alb':
            albsResult.append(obj)
        elif resourceType == 'group':
            targetGroupsResult.append(obj)

    return albsResult, targetGroupsResult

def get_complete_dynamodb_table(client, table):
    result = table.copy()
    try:
        paginator = client.get_paginator('list_tags_of_resource')
        page_iterator = paginator.paginate(ResourceArn=table['TableArn'])
        list_of_tag_lists = map(lambda page: page['Tags'], page_iterator)
        result['Tags'] = flatten_list(list_of_tag_lists)
    except Exception as e:
        print_err('Error fetching tag info for dynamodb table "{arn}".\nError: {error}'.format(
            arn=table['TableArn'], error=str(e)))
        result['Tags'] = []
    return result

def get_complete_elbs(client, elbs):
    result = []

    elbNames = []
    elbMap = {}
    for val in elbs:
        elbName = val['LoadBalancerName']
        elbNames.append(elbName)
        elbMap[elbName] = val

    tagInfoForAllElbs = []
    try:
        if len(elbNames) > 0:
            chunkedListOfArns = chunk_list(elbNames, 20)
            listOfTagLists = [client.describe_tags(LoadBalancerNames=l)['TagDescriptions'] for l in chunkedListOfArns]
            tagInfoForAllElbs = flatten_list(listOfTagLists)
    except Exception as e:
        print_err('Error fetching tag info for elbs.\nError: {error}'.format(error=str(e)))

    for tagInfo in tagInfoForAllElbs:
        elbName = tagInfo['LoadBalancerName']
        completeElb = elbMap.get(elbName, {}).copy()
        completeElb.update(tagInfo)
        result.append(completeElb)

    return result

rds_engine_filter = {
    'Name': 'engine',
    'Values': [
        'aurora-mysql', 'aurora-postgresql', 'mariadb', 'mysql',
        'oracle-ee', 'oracle-ee-cdb', 'oracle-se2', 'oracle-se2-cdb',
        'postgres', 'sqlserver-ee', 'sqlserver-se', 'sqlserver-ex', 'sqlserver-web',
    ]
},

def get_complete_rds_instances(client, target_info):
    try:
        print('Executing {account}:{region}:rds.describe_db_instances'.format(
            account=target_info.profile_name, region=target_info.region))
        instances = []
        result = client.describe_db_instances(Filters=rds_engine_filter)
        instances += result.get('DBInstances', [])
        while result.get('Marker', None):
            result = client.describe_db_instances(Marker=result.get('Marker', None), Filters=rds_engine_filter)
            instances += result.get('DBInstances', [])
        return instances
    except Exception as e:
        handle_error(target_info, e, 'rds:describe_db_instances')
        return []

def get_complete_rds_resource(client, resource, arnProp):
    arn = resource[arnProp]
    result = resource.copy()
    try:
        tagInfo = client.list_tags_for_resource(ResourceName=arn)
        del tagInfo['ResponseMetadata']
        result.update(tagInfo)
    except Exception as e:
        print_err('Error fetching tag info for rds resource with ARN: "{arn}".\nError: {error}'.format(
            arn=arn, error=str(e)))
        result['TagList'] = []
    return result

def get_complete_s3_bucket(client, bucket):
    result = bucket.copy()
    import botocore
    try:
        tagInfo = client.get_bucket_tagging(Bucket=bucket['Name'])
        del tagInfo['ResponseMetadata']
        result.update(tagInfo)
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchTagSet':
            print_err('Error ({code}) fetching tag info for bucket "{name}".\nError: {error}'.format(
                code=e.response['Error']['Code'], name=bucket['Name'], error=str(e)))
        result['TagSet'] = []

    try:
        policyStatus = client.get_bucket_policy_status(Bucket=bucket['Name'])
        del policyStatus['ResponseMetadata']
        result.update(policyStatus['PolicyStatus'])
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchBucketPolicy':
            print_err('Error ({code}) fetching policy info for bucket "{name}".\nError: {error}'.format(
                code=e.response['Error']['Code'], name=bucket['Name'], error=str(e)))
        result['IsPublic'] = False

    try:
        encryptionInfo = client.get_bucket_encryption(Bucket=bucket['Name'])
        del encryptionInfo['ResponseMetadata']
        result.update(encryptionInfo['ServerSideEncryptionConfiguration'])
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != 'ServerSideEncryptionConfigurationNotFoundError':
            print_err('Error ({code}) fetching encryption info for bucket "{name}".\nError: {error}'.format(
                code=e.response['Error']['Code'], name=bucket['Name'], error=str(e)))
        result['Rules'] = []

    try:
        notificationConfiguration = client.get_bucket_notification_configuration(Bucket=bucket['Name'])
        del notificationConfiguration['ResponseMetadata']
        result.update(notificationConfiguration)
    except botocore.exceptions.ClientError:
        result['LambdaFunctionConfigurations'] = []

    return result

def get_complete_sns_topic(client, topic):
    result = topic.copy()
    try:
        tagInfo = client.list_tags_for_resource(ResourceArn=topic['TopicArn'])
        del tagInfo['ResponseMetadata']
        result.update(tagInfo)
    except Exception as e:
        print_err('Error fetching tag info for topic "{name}".\nError: {error}'.format(
            name=topic['TopicArn'], error=str(e)))
        result['Tags'] = []
    return result

def get_ecs_clusters(ecs, target_info):
    resource_name = "ecs:describe_clusters"
    print('Executing {account}:{region}:{resource_name}'.format(
        account=target_info.profile_name, region=target_info.region, resource_name=resource_name))
    try:
        result = ecs.list_clusters()
        all_clusters = result.get("clusterArns") if "clusterArns" in result else []
        while "nextToken" in result:
            result = ecs.list_clusters(nextToken = result["nextToken"])
            if "clusterArns" in result:
                all_clusters.extend(result.get("clusterArns"))
        r = []
        step = 100
        for i in range(0, len(all_clusters), step):
            r.extend(ecs.describe_clusters(clusters=all_clusters[i:i+step]).get("clusters", []))
        return r
    except Exception as e:
        handle_error(target_info, e, resource_name)
        return []

def get_eks_cluster(eks, target_info):
    resource_name = "eks:describe_cluster"
    print('Executing {account}:{region}:{resource_name}'.format(
        account=target_info.profile_name, region=target_info.region, resource_name=resource_name))
    try:
        result = eks.list_clusters()
        clusters = result.get("clusters") if "clusters" in result else []
        while "nextToken" in result:
            result = eks.list_clusters(nextToken = result["nextToken"])
            if "clusters" in result:
                clusters.extend(result.get("clusters"))
        all_clusters = []
        for cluster in clusters:
            all_clusters.append(eks.describe_cluster(name=cluster).get("cluster", []))
        return all_clusters
    except Exception as e:
        handle_error(target_info, e, resource_name)
        return []

def get_hosted_zones(route53, target_info):
    resource_name = "route53:list_hosted_zones"
    print('Executing {account}:{region}:{resource_name}'.format(
        account=target_info.profile_name, region=target_info.region, resource_name=resource_name))
    try:
        result = route53.list_hosted_zones()
        all_hosted_zones = result.get("HostedZones") if "HostedZones" in result else []
        while "NextMarker" in result:
            result = route53.list_hosted_zones(Marker = result["NextMarker"])
            if "HostedZones" in result:
                all_hosted_zones.extend(result.get("HostedZones"))
        # tags
        zone_id_to_zone = {z["Id"]: z for z in all_hosted_zones}
        for zone_id, zone in zone_id_to_zone.items():
            stripped_id = zone_id.split("/hostedzone/")[1]
            result = route53.list_tags_for_resource(ResourceId = stripped_id, ResourceType = "hostedzone")
            tags = result.get("ResourceTagSet", {}).get("Tags", [])
            zone["Tags"] = tags
        return all_hosted_zones
    except Exception as e:
        handle_error(target_info, e, resource_name)
        return []

# -------------------- JSON builder --------------------
def create_json(session, target_info):
    """Create AWS infrastructure JSON data."""
    elbv2 = session.create_client('elbv2', region_name=target_info.region)
    apigateway = session.create_client('apigateway', region_name=target_info.region)
    apigatewayv2 = session.create_client('apigatewayv2', region_name=target_info.region)
    appsync = session.create_client('appsync', region_name=target_info.region)
    autoscaling = session.create_client('autoscaling', region_name=target_info.region)
    dynamodb = session.create_client('dynamodb', region_name=target_info.region)
    ec2 = session.create_client('ec2', region_name=target_info.region)
    elb = session.create_client('elb', region_name=target_info.region)
    lambdaClient = session.create_client('lambda', region_name=target_info.region)
    rds = session.create_client('rds', region_name=target_info.region)
    s3 = session.create_client('s3', region_name=target_info.region)
    sns = session.create_client('sns', region_name=target_info.region)
    sqs = session.create_client('sqs', region_name=target_info.region)
    ecs = session.create_client('ecs', region_name=target_info.region)
    eks = session.create_client('eks', region_name=target_info.region)

    apiGateways = get_complete_api_gateways(apigateway, target_info)
    apiGatewayV2s = get_complete_api_gateway_v2s(apigatewayv2, target_info)

    try:
        snsTopics = make_request(sns.list_topics, target_info, 'sns:list_topics', 'Topics')
    except Exception as e:
        handle_error(target_info, e, "sns:list_topics")
        snsTopics = []

    try:
        sqsQueueUrls = make_request(sqs.list_queues, target_info, 'sqs:list_queues', 'QueueUrls')
    except Exception as e:
        handle_error(target_info, e, "sqs.list_queues")
        sqsQueueUrls = []

    try:
        dynamoDbTableNames = make_request(dynamodb.list_tables, target_info, 'dynamodb:list_tables', 'TableNames')
    except Exception as e:
        handle_error(target_info, e, "dynamodb.list_tables")
        dynamoDbTableNames = []

    dynamoDbTables = get_dynamoDB_tables(dynamodb, dynamoDbTableNames, target_info)

    try:
        vpcs = make_request(ec2.describe_vpcs, target_info, 'ec2:describe_vpcs', 'Vpcs')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_vpcs")
        vpcs = []

    try:
        subnets = make_request(ec2.describe_subnets, target_info, 'ec2:describe_subnets', 'Subnets')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_subnets")
        subnets = []

    try:
        instances = make_request(ec2.describe_instances, target_info, 'ec2:describe_instances', 'Reservations', True)
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_instances")
        instances = []

    try:
        volumes = make_request(ec2.describe_volumes, target_info, 'ec2:describe_volumes', 'Volumes')
    except Exception as e:
        handle_error(target_info, e, "ec2.describe_volumes")
        volumes = []

    try:
        elbLoadBalancers = make_request(elb.describe_load_balancers, target_info, 'elb:describe_load_balancers', 'LoadBalancerDescriptions')
    except Exception as e:
        handle_error(target_info, e, "elb:describe_load_balancers")
        elbLoadBalancers = []

    try:
        albLoadBalancers = make_request(elbv2.describe_load_balancers, target_info, 'elbv2:describe_load_balancers', 'LoadBalancers')
    except Exception as e:
        handle_error(target_info, e, "elbv2:describe_load_balancers")
        albLoadBalancers = []

    targetGroups = get_target_groups(elbv2, target_info)

    try:
        autoscalingGroups = make_request(autoscaling.describe_auto_scaling_groups, target_info, 'autoscaling:describe_auto_scaling_groups', 'AutoScalingGroups')
    except Exception as e:
        handle_error(target_info, e, "autoscaling:describe_auto_scaling_groups")
        autoscalingGroups = []

    try:
        allS3Buckets = make_request(s3.list_buckets, target_info, 's3:list_buckets', 'Buckets')
    except Exception as e:
        handle_error(target_info, e, "s3:list_buckets")
        allS3Buckets = []

    # NEW: network primitives
    try:
        routeTables = make_request(ec2.describe_route_tables, target_info, 'ec2:describe_route_tables', 'RouteTables')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_route_tables")
        routeTables = []

    try:
        natGateways = paginate(ec2.describe_nat_gateways, 'NatGateways')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_nat_gateways")
        natGateways = []

    try:
        igws = make_request(ec2.describe_internet_gateways, target_info, 'ec2:describe_internet_gateways', 'InternetGateways')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_internet_gateways")
        igws = []

    try:
        vpcEndpoints = make_request(ec2.describe_vpc_endpoints, target_info, 'ec2:describe_vpc_endpoints', 'VpcEndpoints')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_vpc_endpoints")
        vpcEndpoints = []

    try:
        vpcPeerings = make_request(ec2.describe_vpc_peering_connections, target_info, 'ec2:describe_vpc_peering_connections', 'VpcPeeringConnections')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_vpc_peering_connections")
        vpcPeerings = []

    try:
        azs = make_request(ec2.describe_availability_zones, target_info, 'ec2:describe_availability_zones', 'AvailabilityZones')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_availability_zones")
        azs = []

    bucketsForRegion = filter_s3_buckets_to_target_region(s3, allS3Buckets, target_info)
    topics = get_sns_topics(sns, snsTopics, target_info)
    queues = get_sqs_queues(sqs, sqsQueueUrls, target_info)
    rdsDbInstances = get_complete_rds_instances(rds, target_info)
    graphqlApis = get_appsync_graphqlapis(appsync, target_info)
    snsSubscriptions = get_sns_subscriptions(sns, target_info)
    lambdaFunctions = get_lambda_functions(lambdaClient, target_info)
    lambdaEventSourceMapping = get_lambda_event_source_mappings(lambdaClient, target_info)

    try:
        rdsDbClusters = make_request(rds.describe_db_clusters, target_info, 'rds.describe_db_clusters', 'DBClusters', False, rds_engine_filter)
    except Exception as e:
        handle_error(target_info, e, "rds.describe_db_clusters")
        rdsDbClusters = []

    try:
        securityGroups = make_request(ec2.describe_security_groups, target_info, 'ec2:describe_security_groups', 'SecurityGroups')
    except Exception as e:
        handle_error(target_info, e, "ec2:describe_security_groups")
        securityGroups = []

    ecsClusters = get_ecs_clusters(ecs, target_info)
    eksClusters = get_eks_cluster(eks, target_info)

    # enrich
    print('Getting additional metadata for region resources')
    albLoadBalancers, targetGroups = get_complete_albs(elbv2, albLoadBalancers, targetGroups)
    dynamoDbTables = [get_complete_dynamodb_table(dynamodb, table) for table in dynamoDbTables]
    elbLoadBalancers = get_complete_elbs(elb, elbLoadBalancers)
    rdsDbInstances = [get_complete_rds_resource(rds, instance, 'DBInstanceArn') for instance in rdsDbInstances]
    rdsDbClusters = [get_complete_rds_resource(rds, cluster, 'DBClusterArn') for cluster in rdsDbClusters]
    bucketsForRegion = [get_complete_s3_bucket(s3, bucket) for bucket in bucketsForRegion]
    topics = [get_complete_sns_topic(sns, topic) for topic in topics]

    infrastructure_data = {
        'alb': {
            'loadBalancersV2': albLoadBalancers,
            'targetGroups': targetGroups,
        },
        'apigateway': {
            'restApis': apiGateways,
        },
        'apigatewayv2': {
            'apis': apiGatewayV2s,
        },
        'appsync': {
            'graphqlApis': graphqlApis,
        },
        'autoscaling': {
            'groups': autoscalingGroups,
        },
        'dynamoDB': {
            'tables': dynamoDbTables,
        },
        'ec2': {
            'instances': instances,
            'securityGroups': securityGroups,
            'subnets': subnets,
            'volumes': volumes,
            'vpcs': vpcs,
            'routeTables': routeTables,            # NEW
            'internetGateways': igws,              # NEW
            'natGateways': natGateways,            # NEW
            'vpcEndpoints': vpcEndpoints,          # NEW
            'vpcPeerings': vpcPeerings,            # NEW
            'availabilityZones': azs,              # NEW
        },
        'elb': {
            'loadBalancers': elbLoadBalancers,
        },
        'lambda': {
            'functions': lambdaFunctions,
            'eventSourceMappings': lambdaEventSourceMapping,
        },
        'rds': {
            'dbInstances': rdsDbInstances,
            'dbClusters': rdsDbClusters,
        },
        's3': {
            'buckets': bucketsForRegion,
        },
        'sns': {
            'topics': topics,
            'subscriptions': snsSubscriptions,
        },
        'sqs': {
            'queues': queues,
        },
        'ecs': {
            'clusters': ecsClusters,
        },
        'eks': {
            'eksClusters': eksClusters,
        },
    }

    return infrastructure_data

def get_account(target_info, session):
    try:
        sts = session.create_client('sts', region_name=target_info.region)
        account = make_request(sts.get_caller_identity, target_info, 'sts:get_caller_identity', 'Account')
        return account
    except Exception as e:
        handle_error(target_info, e, 'Could not create session:')
        return None

def get_account_aliases(target_info, session):
    try:
        iam = session.create_client('iam')
        account_aliases = make_request(iam.list_account_aliases, target_info, 'iam:list_account_aliases', 'AccountAliases')
        return account_aliases
    except Exception as e:
        handle_error(target_info, e, 'Could not create session:')
        return None

def get_account_resources(session, target_info):
    """Get account-level resources like Route53."""
    route53 = session.create_client('route53', region_name=target_info.region)
    hosted_zones = get_hosted_zones(route53, target_info)
    return {'route53': {'hostedZones': hosted_zones}}

# -------------------- diagram helpers --------------------
def format_label(text, max_width=20):
    if not text:
        return "Unknown"
    text = text.replace('\n', ' ')
    wrapped = wrap(str(text), width=max_width, break_long_words=True)
    return '\n'.join(wrapped[:3])

def has_tag_keyword(resource, keyword):
    if not keyword:
        return True
    tags = resource.get('Tags', [])
    if isinstance(tags, dict):
        return any(keyword.lower() in str(v).lower() or keyword.lower() in str(k).lower()
                   for k, v in tags.items())
    elif isinstance(tags, list):
        return any(keyword.lower() in tag.get('Value', '').lower() or
                   keyword.lower() in tag.get('Key', '').lower()
                   for tag in tags)
    return False

def get_resource_name(resource, resource_type):
    tags = resource.get('Tags', [])
    if isinstance(tags, list):
        for tag in tags:
            if tag.get('Key') == 'Name':
                name = tag.get('Value', '')
                if name:
                    return name[:40]
    elif isinstance(tags, dict):
        if 'Name' in tags and tags['Name']:
            return tags['Name'][:40]
    for field in ['Name','FunctionName','DBInstanceIdentifier','LoadBalancerName',
                  'ClusterIdentifier','BucketName','TopicArn','QueueUrl','InstanceId',
                  'GroupName','TableName','clusterName','VpcId']:
        if field in resource:
            value = resource[field]
            if value:
                return str(value).split('/')[-1][:40]
    return f"{resource_type[:20]}"

def get_resource_details(resource, resource_type):
    details = []
    name = get_resource_name(resource, resource_type)
    if resource_type == 'EC2':
        instance_type = resource.get('InstanceType', '')
        state = resource.get('State', {}).get('Name', '')
        private_ip = resource.get('PrivateIpAddress', '')
        if instance_type: details.append(instance_type)
        if state: details.append(state)
        if private_ip: details.append(private_ip)
    elif resource_type == 'RDS':
        engine = resource.get('Engine', '')
        instance_class = resource.get('DBInstanceClass', '')
        if engine: details.append(engine)
        if instance_class: details.append(instance_class)
    elif resource_type in ('ALB', 'ELB'):
        scheme = resource.get('Scheme', '')
        state = resource.get('State', {}).get('Code', '') if resource_type == 'ALB' else ''
        if scheme: details.append(scheme)
        if state: details.append(state)
    elif resource_type == 'Lambda':
        runtime = resource.get('Runtime', '')
        if runtime: details.append(runtime)
    if details:
        formatted_name = format_label(name, max_width=25)
        formatted_details = format_label(', '.join(details[:2]), max_width=25)
        return f"{formatted_name}\n({formatted_details})"
    return format_label(name, max_width=25)

def calculate_diagram_attributes(total_resources):
    base_width = 20
    base_height = 15
    if total_resources > 50:
        scale_factor = math.sqrt(total_resources / 50)
        width = int(base_width * scale_factor)
        height = int(base_height * scale_factor)
    else:
        width = base_width
        height = base_height
    dpi = 300 if total_resources < 30 else 200
    return {
        'graph_attr': {
            'size': f'{width},{height}!',
            'dpi': str(dpi),
            'fontsize': '12',
            'labelloc': 't',
            'labeljust': 'c',
            'nodesep': '1.0',
            'ranksep': '1.5',
            'pad': '1.0',
            'splines': 'ortho',
        },
        'node_attr': {
            'fontsize': '11',
            'height': '1.2',
            'width': '2.0',
            'fixedsize': 'false',
            'margin': '0.2',
        },
        'edge_attr': {
            'fontsize': '9',
            'labeldistance': '2.5',
            'labelangle': '0',
        }
    }

# -------------------- filtering --------------------
def filter_resources_by_tag(data, keyword):
    # -------- registries from the full (unfiltered) region payloads --------
    # so we can "promote" network dependencies even if they don't match the tag
    all_vpcs_by_id = {}
    all_subnets_by_id = {}
    all_rts_by_id = {}
    igws_by_vpc = defaultdict(list)
    ngw_by_subnet = defaultdict(list)
    vpc_endpoints_by_vpc = defaultdict(list)

    for account in data.get('accounts', []):
        for region in account.get('regions', []):
            res = region.get('resources', {})
            for v in res.get('ec2', {}).get('vpcs', []):
                all_vpcs_by_id[v['VpcId']] = v
            for s in res.get('ec2', {}).get('subnets', []):
                all_subnets_by_id[s['SubnetId']] = s
            for rt in res.get('ec2', {}).get('routeTables', []):
                all_rts_by_id[rt['RouteTableId']] = rt
            for igw in res.get('ec2', {}).get('internetGateways', []):
                for att in igw.get('Attachments', []):
                    vid = att.get('VpcId')
                    if vid:
                        igws_by_vpc[vid].append(igw)
            for ngw in res.get('ec2', {}).get('natGateways', []):
                sid = ngw.get('SubnetId')
                if sid:
                    ngw_by_subnet[sid].append(ngw)
            for ep in res.get('ec2', {}).get('vpcEndpoints', []):
                vid = ep.get('VpcId')
                if vid:
                    vpc_endpoints_by_vpc[vid].append(ep)

    # -------- initial tag-based filter (same as before) --------
    filtered = {
        'ec2_instances': [], 'lambda_functions': [], 'rds_instances': [],
        'albs': [], 'elbs': [], 's3_buckets': [], 'dynamodb_tables': [],
        'vpcs': [], 'subnets': [], 'security_groups': [], 'ecs_clusters': [],
        'eks_clusters': [], 'sqs_queues': [], 'sns_topics': [], 'route53_zones': [],
        'ebs_volumes': [], 'target_groups': [],
        'route_tables': [], 'internet_gateways': [], 'nat_gateways': [],
        'vpc_endpoints': [], 'vpc_peerings': [], 'availability_zones': [],
    }

    for account in data.get('accounts', []):
        for region in account.get('regions', []):
            resources = region.get('resources', {})

            for reservation in resources.get('ec2', {}).get('instances', []):
                for instance in reservation.get('Instances', []):
                    if has_tag_keyword(instance, keyword):
                        filtered['ec2_instances'].append(instance)

            for func in resources.get('lambda', {}).get('functions', []):
                if has_tag_keyword(func, keyword):
                    filtered['lambda_functions'].append(func)

            for db in resources.get('rds', {}).get('dbInstances', []):
                if has_tag_keyword(db, keyword):
                    filtered['rds_instances'].append(db)

            for alb in resources.get('alb', {}).get('loadBalancersV2', []):
                if has_tag_keyword(alb, keyword):
                    filtered['albs'].append(alb)

            for elb in resources.get('elb', {}).get('loadBalancers', []):
                if has_tag_keyword(elb, keyword):
                    filtered['elbs'].append(elb)

            for bucket in resources.get('s3', {}).get('buckets', []):
                if has_tag_keyword(bucket, keyword):
                    filtered['s3_buckets'].append(bucket)

            for table in resources.get('dynamoDB', {}).get('tables', []):
                if has_tag_keyword(table, keyword):
                    filtered['dynamodb_tables'].append(table)

            for vpc in resources.get('ec2', {}).get('vpcs', []):
                if has_tag_keyword(vpc, keyword):
                    filtered['vpcs'].append(vpc)

            for subnet in resources.get('ec2', {}).get('subnets', []):
                if has_tag_keyword(subnet, keyword):
                    filtered['subnets'].append(subnet)

            for sg in resources.get('ec2', {}).get('securityGroups', []):
                if has_tag_keyword(sg, keyword):
                    filtered['security_groups'].append(sg)

            for cluster in resources.get('ecs', {}).get('clusters', []):
                if has_tag_keyword(cluster, keyword):
                    filtered['ecs_clusters'].append(cluster)

            for cluster in resources.get('eks', {}).get('eksClusters', []):
                if has_tag_keyword(cluster, keyword):
                    filtered['eks_clusters'].append(cluster)

            for queue in resources.get('sqs', {}).get('queues', []):
                if has_tag_keyword(queue, keyword):
                    filtered['sqs_queues'].append(queue)

            for topic in resources.get('sns', {}).get('topics', []):
                if has_tag_keyword(topic, keyword):
                    filtered['sns_topics'].append(topic)

            for tg in resources.get('alb', {}).get('targetGroups', []):
                if has_tag_keyword(tg, keyword):
                    filtered['target_groups'].append(tg)

            for volume in resources.get('ec2', {}).get('volumes', []):
                if has_tag_keyword(volume, keyword):
                    filtered['ebs_volumes'].append(volume)

            for rt in resources.get('ec2', {}).get('routeTables', []):
                if has_tag_keyword(rt, keyword):
                    filtered['route_tables'].append(rt)

            for pcx in resources.get('ec2', {}).get('vpcPeerings', []):
                if has_tag_keyword(pcx, keyword):
                    filtered['vpc_peerings'].append(pcx)

            for az in resources.get('ec2', {}).get('availabilityZones', []):
                filtered['availability_zones'].append(az)

        for zone in account.get('resources', {}).get('route53', {}).get('hostedZones', []):
            if has_tag_keyword(zone, keyword):
                filtered['route53_zones'].append(zone)

    # -------- enrichment pass: ensure parents (VPCs/Subnets/RTs) exist --------
    needed_vpc_ids = set()
    needed_subnet_ids = set()

    # EC2
    for i in filtered['ec2_instances']:
        if i.get('VpcId'): needed_vpc_ids.add(i['VpcId'])
        if i.get('SubnetId'): needed_subnet_ids.add(i['SubnetId'])

    # RDS
    for db in filtered['rds_instances']:
        vpc = db.get('DBSubnetGroup', {}).get('VpcId')
        if vpc: needed_vpc_ids.add(vpc)
        for sn in db.get('DBSubnetGroup', {}).get('Subnets', []):
            sid = sn.get('SubnetIdentifier') or sn.get('SubnetId')
            if sid: needed_subnet_ids.add(sid)

    # ALB
    for alb in filtered['albs']:
        if alb.get('VpcId'): needed_vpc_ids.add(alb['VpcId'])
        for az in alb.get('AvailabilityZones', []):
            sid = az.get('SubnetId') if isinstance(az, dict) else None
            if sid: needed_subnet_ids.add(sid)

    # ELB (classic)
    for elb in filtered['elbs']:
        if elb.get('VPCId'): needed_vpc_ids.add(elb['VPCId'])

    # Lambda in VPC
    for fn in filtered['lambda_functions']:
        vconf = fn.get('VpcConfig') or {}
        if vconf.get('VpcId'): needed_vpc_ids.add(vconf['VpcId'])
        for sid in (vconf.get('SubnetIds') or []):
            needed_subnet_ids.add(sid)

    # Bring in those VPCs/Subnets/RouteTables even if not tagged
    have_vpc_ids = {v['VpcId'] for v in filtered['vpcs']}
    for vpc_id in sorted(needed_vpc_ids - have_vpc_ids):
        v = all_vpcs_by_id.get(vpc_id)
        if v: filtered['vpcs'].append(v)

    have_subnet_ids = {s['SubnetId'] for s in filtered['subnets']}
    for sid in sorted(needed_subnet_ids - have_subnet_ids):
        s = all_subnets_by_id.get(sid)
        if s: filtered['subnets'].append(s)

    # Add route tables associated with the pulled-in subnets
    # (association SubnetId lives on route table objects)
    needed_rt_ids = set()
    for rt in all_rts_by_id.values():
        for assoc in rt.get('Associations', []):
            if assoc.get('SubnetId') in needed_subnet_ids:
                needed_rt_ids.add(rt['RouteTableId'])
                break
    have_rt_ids = {rt['RouteTableId'] for rt in filtered['route_tables']}
    for rtid in sorted(needed_rt_ids - have_rt_ids):
        rt = all_rts_by_id.get(rtid)
        if rt: filtered['route_tables'].append(rt)

    # Internet Gateways / Endpoints / NATs for included VPCs
    for vpc_id in needed_vpc_ids:
        for igw in igws_by_vpc.get(vpc_id, []):
            filtered['internet_gateways'].append(igw)
        for ep in vpc_endpoints_by_vpc.get(vpc_id, []):
            filtered['vpc_endpoints'].append(ep)
    for sid in needed_subnet_ids:
        for ngw in ngw_by_subnet.get(sid, []):
            filtered['nat_gateways'].append(ngw)

    return filtered

# -------------------- diagram generator --------------------
def generate_diagram(filtered_resources, output_file='aws_architecture', keyword='', output_format='png', direction_override=None):
    total = sum(len(v) for v in filtered_resources.values())
    if total == 0:
        print(f"No resources found with tag keyword: '{keyword}'")
        return

    print(f"\nGenerating diagram with {total} resources...")
    for resource_type, resources in filtered_resources.items():
        if resources:
            print(f"  - {len(resources)} {resource_type}")

    title = f"AWS Architecture Diagram"
    if keyword:
        title += f" (Tag: {keyword})"

    attrs = calculate_diagram_attributes(total)
    direction = direction_override if direction_override else ("LR" if total > 30 else "TB")

    with Diagram(
        title,
        filename=output_file,
        show=False,
        direction=direction,
        outformat=output_format,
        graph_attr=attrs['graph_attr'],
        node_attr=attrs['node_attr'],
        edge_attr=attrs['edge_attr']
    ):
        nodes = {}

        # Network-aware placement indexes
        subnet_idx, vpc_to_subnets, rt_by_id = build_subnet_index(
            filtered_resources.get('subnets', []),
            filtered_resources.get('route_tables', [])
        )

        vpcs_by_id = {v['VpcId']: v for v in filtered_resources.get('vpcs', [])}

        igws_by_vpc = defaultdict(list)
        for igw in filtered_resources.get('internet_gateways', []):
            for att in igw.get('Attachments', []):
                if att.get('VpcId'):
                    igws_by_vpc[att['VpcId']].append(igw)

        nat_by_subnet = defaultdict(list)
        for ngw in filtered_resources.get('nat_gateways', []):
            sn = ngw.get('SubnetId')
            if sn:
                nat_by_subnet[sn].append(ngw)

        ep_by_vpc = defaultdict(list)
        for ep in filtered_resources.get('vpc_endpoints', []):
            if ep.get('VpcId'):
                ep_by_vpc[ep['VpcId']].append(ep)

        # Cluster registries (for scoping)
        vpc_clusters = {}
        az_clusters = {}
        subnet_clusters = {}

        # Render VPCs first
        all_vpc_ids = set(vpc_to_subnets.keys()) | set(vpcs_by_id.keys())
        for vpc_id in all_vpc_ids:
            v = vpcs_by_id.get(vpc_id, {})
            vpc_name = get_resource_name(v, 'VPC') if v else vpc_id
            cidr = v.get('CidrBlock', '') if v else ''
            vpc_label = f"VPC: {format_label(vpc_name, 30)}"
            if cidr:
                vpc_label += f"\n{cidr}"

            with Cluster(vpc_label, graph_attr={'bgcolor': 'lightblue', 'style': 'rounded'}):
                vpc_clusters[vpc_id] = True

                # IGW(s)
                igw_nodes = []
                for igw in igws_by_vpc.get(vpc_id, []):
                    igw_id = igw.get('InternetGatewayId', 'igw')
                    igw_nodes.append(InternetGateway(igw_id))

                # VPC Endpoints
                ep_nodes = []
                for ep in ep_by_vpc.get(vpc_id, []):
                    ep_id = ep.get('VpcEndpointId', 'vpce')
                    ep_svc = (ep.get('ServiceName', '') or '').split('.')[-1]
                    ep_nodes.append(Endpoint(f"{ep_id}\n{format_label(ep_svc, 18)}"))

                # Build AZ clusters
                az_names = sorted({subnet_idx[s]['az'] for s in vpc_to_subnets.get(vpc_id, []) if s in subnet_idx})
                for az in az_names or ["Unknown AZ"]:
                    az_key = (vpc_id, az)
                    az_label = f"AZ: {az}" if az else "AZ: Unknown"
                    with Cluster(az_label, graph_attr={'bgcolor': 'white', 'style': 'dotted'}):
                        az_clusters[az_key] = True

                        # Build per-subnet clusters
                        for sid in sorted(vpc_to_subnets.get(vpc_id, [])):
                            meta = subnet_idx.get(sid)
                            if not meta or meta["az"] != az:
                                continue
                            pub = meta["public"]
                            cidr = meta["cidr"] or ""
                            sub_label = f"{sid}\n{cidr}\n({'Public' if pub else 'Private'})"

                            # Render either as special icon or a plain cluster
                            if pub and PublicSubnet:
                                with Cluster("", graph_attr={'style': 'invis'}):
                                    subnet_node = PublicSubnet(sub_label)
                            elif (not pub) and PrivateSubnet:
                                with Cluster("", graph_attr={'style': 'invis'}):
                                    subnet_node = PrivateSubnet(sub_label)
                            else:
                                with Cluster(sub_label, graph_attr={'bgcolor': '#f7f7f7'}):
                                    subnet_node = None  # visual container only

                            subnet_clusters[(vpc_id, az, sid)] = subnet_node

                            # NAT GW inside its hosting subnet
                            for ngw in nat_by_subnet.get(sid, []):
                                ngw_id = ngw.get('NatGatewayId', 'nat')
                                nodes[ngw_id] = NATGateway(ngw_id)

                # Security groups at VPC scope (draw once)
                vpc_security_groups = {}
                for sg in filtered_resources.get('security_groups', []):
                    if sg.get('VpcId') == vpc_id:
                        sg_id = sg.get('GroupId')
                        sg_name = format_label(get_resource_name(sg, 'SG'), max_width=20)
                        vpc_security_groups[sg_id] = Shield(f"SG:\n{sg_name}")

                # Place EC2 in subnets
                for instance in filtered_resources.get('ec2_instances', []):
                    if instance.get('VpcId') != vpc_id:
                        continue
                    sid = instance.get('SubnetId')
                    az = subnet_idx.get(sid, {}).get('az')
                    key = (vpc_id, az, sid)
                    name = get_resource_details(instance, 'EC2')
                    iid = instance.get('InstanceId')
                    nodes[iid] = EC2(name)  # draw even if subnet cluster missing
                    # SG edges
                    for sg in instance.get('SecurityGroups', []):
                        sg_id = sg.get('GroupId')
                        if sg_id in vpc_security_groups:
                            vpc_security_groups[sg_id] >> Edge(style="dashed", color="gray") >> nodes[iid]

                # Place RDS (best-effort: one subnet from its DBSubnetGroup)
                for db in filtered_resources.get('rds_instances', []):
                    sg_vpc = db.get('DBSubnetGroup', {}).get('VpcId')
                    if sg_vpc != vpc_id:
                        continue
                    subnet_ids = [s.get('SubnetIdentifier') or s.get('SubnetId') for s in db.get('DBSubnetGroup', {}).get('Subnets', [])]
                    sid = next((s for s in subnet_ids if s in subnet_idx), None)
                    az = subnet_idx.get(sid, {}).get('az')
                    key = (vpc_id, az, sid)
                    name = get_resource_details(db, 'RDS')
                    db_id = db.get('DBInstanceIdentifier')
                    nodes[db_id] = RDS(name)
                    for sg in db.get('VpcSecurityGroups', []):
                        sg_id = sg.get('VpcSecurityGroupId')
                        if sg_id in vpc_security_groups:
                            vpc_security_groups[sg_id] >> Edge(style="dashed", color="gray") >> nodes[db_id]

                # Place ALBs (pick first AZ's subnet if present)
                for alb in filtered_resources.get('albs', []):
                    if alb.get('VpcId') != vpc_id:
                        continue
                    az_objs = alb.get('AvailabilityZones', [])
                    sid = None
                    if az_objs:
                        first = az_objs[0]
                        if isinstance(first, dict):
                            sid = first.get('SubnetId')
                    name = get_resource_details(alb, 'ALB')
                    alb_arn = alb.get('LoadBalancerArn')
                    nodes[alb_arn] = ALB(name)
                    for sg_id in alb.get('SecurityGroups', []):
                        if sg_id in vpc_security_groups:
                            vpc_security_groups[sg_id] >> Edge(style="dashed", color="gray") >> nodes[alb_arn]

                # Place classic ELBs
                for elb in filtered_resources.get('elbs', []):
                    if elb.get('VPCId') != vpc_id:
                        continue
                    name = get_resource_details(elb, 'ELB')
                    elb_name = elb.get('LoadBalancerName')
                    nodes[elb_name] = ELB(name)
                    for sg_id in elb.get('SecurityGroups', []):
                        if sg_id in vpc_security_groups:
                            vpc_security_groups[sg_id] >> Edge(style="dashed", color="gray") >> nodes[elb_name]

                # Place VPC Lambdas (choose one configured subnet)
                for func in filtered_resources.get('lambda_functions', []):
                    vconf = func.get('VpcConfig') or {}
                    if vconf.get('VpcId') != vpc_id:
                        continue
                    sid = next((s for s in (vconf.get('SubnetIds') or []) if s in subnet_idx), None)
                    name = get_resource_details(func, 'Lambda')
                    nodes[func.get('FunctionArn')] = Lambda(name)

                # Visual wiring (best-effort)
                # IGW → public subnets (representative edges to indicate reachability)
                for igw_node in igw_nodes:
                    for sid in vpc_to_subnets.get(vpc_id, []):
                        meta = subnet_idx.get(sid)
                        if meta and meta["public"]:
                            # connect IGW to the public subnet cluster by drawing a dummy edge
                            igw_node >> Edge(color="darkgreen", style="bold")

                # NAT → private subnets in same AZ (dotted hint)
                for sid, ngws in nat_by_subnet.items():
                    if subnet_idx.get(sid, {}).get('vpc_id') != vpc_id:
                        continue
                    for ngw in ngws:
                        ngw_id = ngw.get('NatGatewayId')
                        if ngw_id not in nodes:
                            nodes[ngw_id] = NATGateway(ngw_id)
                        az = subnet_idx.get(sid, {}).get('az')
                        for sid2 in vpc_to_subnets.get(vpc_id, []):
                            m2 = subnet_idx.get(sid2)
                            if not m2 or m2["public"] or m2["az"] != az:
                                continue
                            nodes[ngw_id] >> Edge(color="orange", style="dotted")

                # Endpoints are VPC-scoped; already rendered as nodes (no edges here)

        # Non-VPC Lambdas cluster
        non_vpc_lambdas = [f for f in filtered_resources.get('lambda_functions', []) if not f.get('VpcConfig', {}).get('VpcId')]
        if non_vpc_lambdas:
            with Cluster("Lambda Functions (Non-VPC)", graph_attr={'bgcolor': 'lightyellow'}):
                for func in non_vpc_lambdas:
                    name = get_resource_details(func, 'Lambda')
                    nodes[func.get('FunctionArn')] = Lambda(name)

        # S3 cluster
        if filtered_resources.get('s3_buckets'):
            with Cluster("S3 Storage", graph_attr={'bgcolor': 'lightgreen'}):
                for bucket in filtered_resources['s3_buckets']:
                    bucket_name = bucket.get('Name', '')
                    name = format_label(bucket_name, max_width=25)
                    public_status = '(Public)' if bucket.get('IsPublic') else '(Private)'
                    nodes[bucket_name] = S3(f"{name}\n{public_status}")

        # DynamoDB cluster
        if filtered_resources.get('dynamodb_tables'):
            with Cluster("DynamoDB", graph_attr={'bgcolor': 'lightyellow'}):
                for table in filtered_resources['dynamodb_tables']:
                    table_name = table.get('TableName', '')
                    name = format_label(table_name, max_width=25)
                    status = table.get('TableStatus', '')
                    label = f"{name}\n({status})" if status else name
                    nodes[table.get('TableArn')] = Dynamodb(label)

        # SQS cluster
        if filtered_resources.get('sqs_queues'):
            with Cluster("SQS Queues", graph_attr={'bgcolor': 'lightcoral'}):
                for queue in filtered_resources['sqs_queues']:
                    queue_url = queue.get('QueueUrl', '')
                    name = format_label(queue_url.split('/')[-1], max_width=25)
                    nodes[queue_url] = SQS(name)

        # SNS cluster
        if filtered_resources.get('sns_topics'):
            with Cluster("SNS Topics", graph_attr={'bgcolor': 'lightcoral'}):
                for topic in filtered_resources['sns_topics']:
                    topic_arn = topic.get('TopicArn', topic.get('Attributes', {}).get('TopicArn', ''))
                    name = format_label(topic_arn.split(':')[-1], max_width=25)
                    nodes[topic_arn] = SNS(name)

        # Route53 cluster
        if filtered_resources.get('route53_zones'):
            with Cluster("DNS (Route53)", graph_attr={'bgcolor': 'lightcyan'}):
                for zone in filtered_resources['route53_zones']:
                    zone_name = zone.get('Name', 'unknown')
                    name = format_label(zone_name, max_width=30)
                    nodes[zone.get('Id')] = Route53(name)

        # EBS cluster + EC2 attachments
        if filtered_resources.get('ebs_volumes'):
            with Cluster("EBS Volumes", graph_attr={'bgcolor': 'lightgray'}):
                for volume in filtered_resources['ebs_volumes']:
                    vol_name = format_label(get_resource_name(volume, 'EBS'), max_width=20)
                    size = volume.get('Size', '')
                    vol_type = volume.get('VolumeType', '')
                    state = volume.get('State', '')
                    label = f"{vol_name}\n{size}GB {vol_type}\n({state})" if size else vol_name
                    volume_id = volume.get('VolumeId')
                    nodes[volume_id] = EBS(label)

        # Relationships from original logic that benefit from better placement:

        # EBS -> EC2
        for volume in filtered_resources.get('ebs_volumes', []):
            volume_id = volume.get('VolumeId')
            if volume_id not in nodes:
                continue
            for attachment in volume.get('Attachments', []):
                instance_id = attachment.get('InstanceId')
                if instance_id and instance_id in nodes:
                    nodes[volume_id] >> Edge(label="attached", color="darkgray", style="dotted") >> nodes[instance_id]

        # ALB -> TargetGroups -> EC2 targets
        for alb in filtered_resources.get('albs', []):
            alb_arn = alb.get('LoadBalancerArn')
            if alb_arn not in nodes:
                continue
            for tg in filtered_resources.get('target_groups', []):
                for lb_arn in tg.get('LoadBalancerArns', []):
                    if lb_arn == alb_arn:
                        for target_health in tg.get('TargetHealthDescriptions', []):
                            target = target_health.get('Target', {})
                            target_id = target.get('Id')
                            if target_id and target_id.startswith('i-') and target_id in nodes:
                                nodes[alb_arn] >> Edge(label="→", color="blue", style="bold") >> nodes[target_id]

        # ELB -> EC2
        for elb in filtered_resources.get('elbs', []):
            elb_name = elb.get('LoadBalancerName')
            if elb_name not in nodes:
                continue
            for instance_info in elb.get('Instances', []):
                instance_id = instance_info.get('InstanceId')
                if instance_id and instance_id in nodes:
                    nodes[elb_name] >> Edge(label="→", color="blue", style="bold") >> nodes[instance_id]

    print(f"\nDiagram generated successfully!")
    print(f"Output: {output_file}.{output_format}")
    print(f"Total resources visualized: {total}")
    if total > 50:
        print(f"\nNote: Large diagram generated. Consider filtering by tag for better clarity.")

# -------------------- CLI --------------------
def main():
    parser = ArgumentParser(description='Generate AWS architecture diagrams from AWS resources')
    parser.add_argument('-p', '--profile', required=True, help='AWS profile name')
    parser.add_argument('-r', '--region', required=True, help='AWS region name')
    parser.add_argument('-t', '--tag', default='', help='Filter resources by tag keyword (case-insensitive)')
    parser.add_argument('-o', '--output', default='aws_architecture', help='Output filename (without extension)')
    parser.add_argument('--format', default='png', choices=['png', 'pdf', 'svg'], help='Output format (default: png)')
    parser.add_argument('--direction', choices=['TB', 'LR', 'BT', 'RL'], help='Diagram direction (TB=top-to-bottom, LR=left-to-right). Auto-detected if not specified.')
    args = parser.parse_args()

    print(f"Fetching AWS resources from profile '{args.profile}' in region '{args.region}'...")

    target = AwsImportTarget(args.profile, args.region)
    session = botocore.session.Session(profile=target.profile_name)

    account = get_account(target, session)
    account_aliases = get_account_aliases(target, session)

    if not account:
        print_err('Could not get account info (check your profile name / region)')
        sys.exit(1)

    print(f"Account: {account}")
    if account_aliases:
        print(f"Aliases: {', '.join(account_aliases)}")

    region_resources = create_json(session, target)
    account_resources = get_account_resources(session, target)

    data = {
        'accounts': [{
            'accountId': account,
            'accountAliases': account_aliases,
            'resources': account_resources,
            'regions': [{
                'regionId': target.region,
                'resources': region_resources
            }]
        }]
    }

    if ERRORS:
        print_err("\nErrors occurred while importing:")
        for error in ERRORS:
            print_err(error)
        print_err("\nContinuing with diagram generation...\n", warning=True)

    filter_message = f"tag keyword: '{args.tag}'" if args.tag else "all resources"
    print(f"\nFiltering resources by {filter_message}")
    filtered = filter_resources_by_tag(data, args.tag)

    generate_diagram(
        filtered,
        args.output,
        args.tag,
        args.format,
        args.direction
    )

def boto3_to_graph_data(
    filtered_resources: dict,
    profile: str,
    region: str,
) -> "GraphData":
    """Convert filtered boto3 discovery results into the standard GraphData model.

    Enables JSON + Mermaid output from aws-boto3 mode alongside the existing
    rich diagrams output.
    """
    from .model import Node, Edge, GraphData as GD

    graph = GD(metadata={
        "source": "aws-boto3",
        "profile": profile,
        "region": region,
    })

    # VPCs
    for vpc in filtered_resources.get("vpcs", []):
        vid = vpc.get("VpcId", "unknown")
        name = get_resource_name(vpc, "VPC")
        graph.add_node(Node(
            id=f"aws:vpc:{vid}",
            label=f"{name} ({vid})",
            kind="aws.vpc",
            source="aws-boto3",
            attrs={"cidr": vpc.get("CidrBlock", "")},
        ))

    # Subnets
    for subnet in filtered_resources.get("subnets", []):
        sid = subnet.get("SubnetId", "unknown")
        az = subnet.get("AvailabilityZone", "")
        cidr = subnet.get("CidrBlock", "")
        graph.add_node(Node(
            id=f"aws:subnet:{sid}",
            label=f"{sid} ({cidr})",
            kind="aws.subnet",
            source="aws-boto3",
            attrs={"az": az, "cidr": cidr},
        ))
        vpc_id = subnet.get("VpcId")
        if vpc_id:
            graph.add_edge(Edge(
                src=f"aws:subnet:{sid}",
                dst=f"aws:vpc:{vpc_id}",
                rel="in",
                source="aws-boto3",
            ))

    # EC2 instances
    for instance in filtered_resources.get("ec2_instances", []):
        iid = instance.get("InstanceId", "unknown")
        name = get_resource_name(instance, "EC2")
        graph.add_node(Node(
            id=f"aws:ec2:{iid}",
            label=name,
            kind="aws.ec2",
            source="aws-boto3",
            attrs={
                "instance_type": instance.get("InstanceType", ""),
                "state": instance.get("State", {}).get("Name", ""),
            },
        ))
        sid = instance.get("SubnetId")
        if sid:
            graph.add_edge(Edge(
                src=f"aws:ec2:{iid}",
                dst=f"aws:subnet:{sid}",
                rel="in",
                source="aws-boto3",
            ))

    # Lambda functions
    for func in filtered_resources.get("lambda_functions", []):
        arn = func.get("FunctionArn", func.get("FunctionName", "unknown"))
        name = func.get("FunctionName", arn)
        graph.add_node(Node(
            id=f"aws:lambda:{arn}",
            label=name,
            kind="aws.lambda",
            source="aws-boto3",
        ))
        for sid in (func.get("VpcConfig") or {}).get("SubnetIds", []):
            graph.add_edge(Edge(
                src=f"aws:lambda:{arn}",
                dst=f"aws:subnet:{sid}",
                rel="runs_in",
                source="aws-boto3",
            ))

    # RDS instances
    for db in filtered_resources.get("rds_instances", []):
        dbid = db.get("DBInstanceIdentifier", "unknown")
        graph.add_node(Node(
            id=f"aws:rds:{dbid}",
            label=dbid,
            kind="aws.rds",
            source="aws-boto3",
            attrs={"engine": db.get("Engine", "")},
        ))

    # ALBs
    for alb in filtered_resources.get("albs", []):
        arn = alb.get("LoadBalancerArn", "unknown")
        name = alb.get("LoadBalancerName", arn)
        graph.add_node(Node(
            id=f"aws:alb:{arn}",
            label=name,
            kind="aws.alb",
            source="aws-boto3",
        ))
        vpc_id = alb.get("VpcId")
        if vpc_id:
            graph.add_edge(Edge(
                src=f"aws:alb:{arn}",
                dst=f"aws:vpc:{vpc_id}",
                rel="in",
                source="aws-boto3",
            ))

    # S3 buckets
    for bucket in filtered_resources.get("s3_buckets", []):
        name = bucket.get("Name", "unknown")
        graph.add_node(Node(
            id=f"aws:s3:{name}",
            label=name,
            kind="aws.s3",
            source="aws-boto3",
        ))

    # DynamoDB tables
    for table in filtered_resources.get("dynamodb_tables", []):
        tname = table.get("TableName", "unknown")
        graph.add_node(Node(
            id=f"aws:dynamodb:{tname}",
            label=tname,
            kind="aws.dynamodb",
            source="aws-boto3",
        ))

    # SQS queues
    for queue in filtered_resources.get("sqs_queues", []):
        url = queue.get("QueueUrl", "unknown")
        name = url.rsplit("/", 1)[-1]
        graph.add_node(Node(
            id=f"aws:sqs:{name}",
            label=name,
            kind="aws.sqs",
            source="aws-boto3",
        ))

    # SNS topics
    for topic in filtered_resources.get("sns_topics", []):
        arn = topic.get("TopicArn", topic.get("Attributes", {}).get("TopicArn", "unknown"))
        name = arn.rsplit(":", 1)[-1]
        graph.add_node(Node(
            id=f"aws:sns:{arn}",
            label=name,
            kind="aws.sns",
            source="aws-boto3",
        ))

    # ECS clusters
    for cluster in filtered_resources.get("ecs_clusters", []):
        cname = cluster.get("clusterName", "unknown")
        graph.add_node(Node(
            id=f"aws:ecs:{cname}",
            label=cname,
            kind="aws.ecs",
            source="aws-boto3",
        ))

    # EKS clusters
    for cluster in filtered_resources.get("eks_clusters", []):
        cname = cluster.get("name", "unknown")
        graph.add_node(Node(
            id=f"aws:eks:{cname}",
            label=cname,
            kind="aws.eks",
            source="aws-boto3",
        ))

    return graph


if __name__ == "__main__":
    if "Windows" in platform.system():
        os.system('color')
    main()
