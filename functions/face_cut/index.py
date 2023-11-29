import json
import os
import boto3
import requests
import ydb
from PIL import Image
import io
from io import BytesIO
import uuid

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")

FROM_BUCKET_NAME = os.environ.get("FROM_BUCKET_NAME")
TO_BUCKET_NAME = os.environ.get("TO_BUCKET_NAME")

driver = ydb.Driver(
    endpoint=f"grpcs://{os.environ.get('YDB_ENDPOINT')}",
    database=os.environ.get('YDB_DATABASE'),
    credentials=ydb.iam.MetadataUrlCredentials(),
)
driver.wait(fail_fast=True, timeout=5)
pool = ydb.SessionPool(driver)


def insert_data(session, face_key, original_key):
    return session.transaction().execute(
        f'INSERT into faces(face_key , original_key) VALUES ("{face_key}", "{original_key}");',
        commit_tx=True,
        settings=ydb.BaseRequestSettings().with_timeout(3).with_operation_timeout(2)
    )
    

def handler(event, context):
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name="ru-central1",
    )

    s3 = session.client(
        service_name='s3',
        endpoint_url='https://storage.yandexcloud.net'
    )

    messages =  json.loads(event['messages'][0]["details"]["message"]["body"])
    orig_key_img = messages['img_key']
    coordinates = messages["coordinates"]

    url = s3.generate_presigned_url("get_object",
        Params={"Bucket": FROM_BUCKET_NAME, "Key": orig_key_img},
        ExpiresIn=100,)

    r = requests.get(url)
    img = Image.open(BytesIO(r.content))

    cropped_img = img.crop(
        (int(coordinates[0]["x"]), int(coordinates[0]["y"]), int(coordinates[2]["x"]), int(coordinates[2]["y"])))

    output = io.BytesIO()
    cropped_img.save(output, 'JPEG')
    output.seek(0)

    face_key = f"face_{uuid.uuid4()}.jpeg"
    s3.put_object(Bucket=TO_BUCKET_NAME, Key=face_key, Body=output, ContentType="image/jpeg")
    pool.retry_operation_sync(insert_data, None, face_key, orig_key_img)

    return {
        'statusCode': 200,
    }
