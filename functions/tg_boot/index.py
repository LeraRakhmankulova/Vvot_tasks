import os
import json
import requests
import ydb
import ydb.iam
import boto3

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
API_GATEWAY = f"https://{os.environ.get('API_GATEWAY')}"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
BUCKET_NAME = os.environ.get("BUCKET_NAME")
FUNC_RESPONSE = {
    'statusCode': 200,
    'body': ''
}
driver = ydb.Driver(
    endpoint=f"grpcs://{os.environ.get('YDB_ENDPOINT')}",
    database=os.environ.get('YDB_DATABASE'),
    credentials=ydb.iam.MetadataUrlCredentials(),
)
driver.wait(fail_fast=True, timeout=5)
pool = ydb.SessionPool(driver)


def get_res(session, sql_req):
  try:
    result = session.transaction().execute(
        sql_req,
        commit_tx=True,
        settings=ydb.BaseRequestSettings().with_timeout(3).with_operation_timeout(2)
    )
    return result
  except ValueError:
    return None


def get_face(session):
  return session.transaction().execute(
    f'SELECT face_key from faces where face_name is null;',
    commit_tx=True,
    settings=ydb.BaseRequestSettings().with_timeout(3).with_operation_timeout(2)
  )

def update_name(session, new_name, img_key):
  return session.transaction().execute(
    f'UPDATE faces SET face_name="{new_name}" WHERE face_key="{img_key}";',
    commit_tx=True,
    settings=ydb.BaseRequestSettings().with_timeout(3).with_operation_timeout(2)
  )


def send_message(text, message):
  message_id = message['message_id']
  chat_id = message['chat']['id']
  reply_message = {'chat_id': chat_id,'text': text,'reply_to_message_id': message_id}
  requests.post(url=f'{TELEGRAM_API_URL}/sendMessage', json=reply_message)


def send_photo(img_key, message):
    img_url = f"{API_GATEWAY}/?face={img_key}"
    message_id = message['message_id']
    chat_id = message['chat']['id']
    reply_message = {'chat_id': chat_id,
                     'photo': img_url,
                     'caption': img_key,
                     'reply_to_message_id': message_id}
    requests.post(url=f'{TELEGRAM_API_URL}/sendPhoto', json=reply_message)


def send_media_group(img_arr, message):
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name="ru-central1",
    )

    s3 = session.client(
        service_name='s3',
        endpoint_url='https://storage.yandexcloud.net'
    )
    list_img = []

    for img in img_arr:
      img_orig_key_bytes = img['original_key']
      img_key_str = img_orig_key_bytes.decode('utf-8')
      img_key = img_key_str.strip("b'").strip("'")

      img_url = s3.generate_presigned_url("get_object",
        Params={"Bucket": BUCKET_NAME, "Key": img_key},
        ExpiresIn=100,)
      list_img.append({'type': 'photo', 'media': img_url})
      
    message_id = message['message_id']
    chat_id = message['chat']['id']
    reply_message = {'chat_id': chat_id,
                     'media': list_img,
                     'reply_to_message_id': message_id}
    requests.post(url=f'{TELEGRAM_API_URL}/sendMediaGroup', json=reply_message)


def handler(event, context):
  body = json.loads(event['body'])
  message_in = body['message']

  if TELEGRAM_BOT_TOKEN is None:
    return FUNC_RESPONSE

  elif 'message' not in body:
    return FUNC_RESPONSE

  elif ("/start" in message_in['text']):
    send_message('Выберите команду /getface или /find {name}', message_in)
    return FUNC_RESPONSE

  elif ("/getface" in message_in['text']):
    result = pool.retry_operation_sync(get_face)
    
    if len(result[0].rows) == 0:
      send_message('Все изображения имеют названия', message_in)
      return FUNC_RESPONSE

    img_key_bytes = result[0].rows[0]['face_key']
    img_key_str = img_key_bytes.decode('utf-8')
    img_key = img_key_str.strip("b'").strip("'")
    
    send_photo(img_key, message_in)
    return FUNC_RESPONSE

  elif ('reply_to_message' in message_in ):
    reply_to_message = message_in['reply_to_message']

    if ('photo' in reply_to_message):
      new_name = str(message_in['text'])
      img_key = str(body['message']['reply_to_message']['caption'])

      result = pool.retry_operation_sync(update_name, None, new_name, img_key) 
      send_message(f'Новое название изображения - {new_name}', message_in)

    else:  
      send_message('Ошибка', message_in)

    return FUNC_RESPONSE


  elif ("/find" in message_in['text']):
    name = str(body['message']['text'].split(" ")[1])
    
    if len(name) == 0:
      send_message(f'Введите название ', message_in)
      return FUNC_RESPONSE 

    new_sql = "SELECT * FROM faces WHERE face_name='" + name + "';"
    result = pool.retry_operation_sync(get_res, None, new_sql)

    if result[0].rows  == []:
      send_message(f'Фотографии с {name} не найдены', message_in)
      return FUNC_RESPONSE

    send_media_group(result[0].rows, message_in)
    return FUNC_RESPONSE
  
  else:
    send_message('Ошибка', message_in)
    return FUNC_RESPONSE