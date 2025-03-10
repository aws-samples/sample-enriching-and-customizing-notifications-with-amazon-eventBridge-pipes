import os
import boto3
from botocore.exceptions import ClientError
import json

# Initialize the DynamoDB client
dynamodb = boto3.client('dynamodb')

# Getting the table name from environment variables
table_name = os.environ['TABLE_NAME']

MAX_ORDERS = 10

def get_number_of_orders(id):
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={'id': {'S': id}}
        )
        
        # Extract the number of orders and increment
        nmb_orders = int(response['Item']['orders']['S'])
        nmb_orders += 1
        
        return nmb_orders
    
    except KeyError:
        # Handle the case where the 'orders' attribute doesn't exist or the item is missing
        return 1
    except ClientError as e:
        print(f"Error fetching item: {e}")
        raise

def update_table(id, orders):
    try:
        response = dynamodb.put_item(
            TableName=table_name,
            Item={
                'id': {'S': id},
                'orders': {'S': str(orders)}
            }
        )
        print(response)
    except ClientError as e:
        print(f"Error updating item: {e}")
        raise

def lambda_handler(event, context):

    message = json.loads(event[0]['body'])

    id = message['id']
    order_content = message['order_content']
    
    nmb_orders = get_number_of_orders(id)
    
    # Calculate orders left
    orders_left = MAX_ORDERS - nmb_orders
    
    # Update the DynamoDB table with the new number of orders
    if nmb_orders == MAX_ORDERS:
        update_table(id, 0)
    else:
        update_table(id, nmb_orders)
    
    if orders_left == 0:
        return [f"Thank you for your order of {order_content}. You have earned a 10% discount code on your next order: XA5GT2SF"]
    else:  
        # Return the confirmation message
        return [f"Thank you for your order of {order_content}. This is your confirmation message! Only {orders_left} orders left until a 10% discount!"]