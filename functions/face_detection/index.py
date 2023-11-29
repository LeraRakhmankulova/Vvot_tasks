import requests
import boto3
import os
import base64
import json

VISION_URL = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
FOLDER_ID = os.environ.get("FOLDER_ID")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
QUEUE_URL = os.environ.get("QUEUE_URL")

def get_json(content):
    return {
    "folderId": FOLDER_ID,    
    "analyze_specs": [{
        "content": content,
        "features": [{
            "type": "FACE_DETECTION"
            }]
        }]
    }


def get_face_detection(img, access_token, token_type):
    coordinates = []
    auth_headers = {
        'Content-Type': 'application/json',
        'Authorization': f'{token_type} {access_token}',
        }
    encoded = base64.b64encode(img).decode('UTF-8')
    json = get_json(encoded)

    res = requests.post(VISION_URL, json=json, headers=auth_headers)
    try:
        faces = res.json()['results'][0]['results'][0]['faceDetection']['faces']
        for face in faces:
            coordinates.append(face['boundingBox']['vertices'])
    except KeyError:
        print(f'Cant find faces')
    return coordinates


def get_object(bucket, img_name):
    client = boto3.client(
        service_name='s3',
        endpoint_url='https://storage.yandexcloud.net'
    )

    get_object_response = client.get_object(Bucket=bucket, Key=img_name)
    return get_object_response['Body'].read()    


def get_task(img_name, coordinates):
    return {
        'img_key': img_name,
        'coordinates': coordinates
    }


def send_task_to_queue(img_name, coordinates):
    client = boto3.client(
        service_name='sqs',
        endpoint_url='https://message-queue.api.cloud.yandex.net',
        region_name='ru-central1'
    )

    tasks = [get_task(img_name, coordinate) for coordinate in coordinates]
    for task in tasks:
        body = json.dumps(task)
        client.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=body
        )    
    return


def handler(event, context):
    bucket = event['messages'][0]['details']['bucket_id']
    img_name = event['messages'][0]['details']['object_id']

    access_token = context.token["access_token"]
    token_type = context.token["token_type"]

    img = get_object(bucket, img_name)
    coordinates = get_face_detection(img, access_token, token_type)
    send_task_to_queue(img_name, coordinates)

    return {
        'statusCode': 200,
        'body': 'ok',
    }


