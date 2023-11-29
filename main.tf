terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
  }
  required_version = ">= 0.13"
}

provider "yandex" {
  service_account_key_file = "key.json"
  cloud_id                 = var.cloud_id
  folder_id                = var.folder_id
  zone                     = "ru-central1-a"
}

locals {
  service_account_id = jsondecode(file("key.json")).service_account_id
}

resource "yandex_iam_service_account_static_access_key" "sa-static-key" {
  service_account_id = local.service_account_id
}

resource "yandex_storage_bucket" "photos" {
  access_key = yandex_iam_service_account_static_access_key.sa-static-key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa-static-key.secret_key
  bucket     = "${var.user}-photos"
  max_size   = 1048576
  anonymous_access_flags {
    read = false
    list = false
  }
}

resource "yandex_storage_bucket" "faces" {
  access_key = yandex_iam_service_account_static_access_key.sa-static-key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa-static-key.secret_key
  bucket     = "${var.user}-faces"
  max_size   = 1048576
  anonymous_access_flags {
    read = false
    list = false
  }
}

resource "yandex_message_queue" "queue-task" {
  access_key                 = yandex_iam_service_account_static_access_key.sa-static-key.access_key
  secret_key                 = yandex_iam_service_account_static_access_key.sa-static-key.secret_key
  name                       = "${var.user}-task"
  visibility_timeout_seconds = 30
  receive_wait_time_seconds  = 20
  message_retention_seconds  = 86400
}


data "archive_file" "zip-detection-face" {
  type        = "zip"
  output_path = "face_detection.zip"
  source_dir  = "./functions/face_detection"
}

resource "yandex_function" "face-detection" {
  name               = "${var.user}-face-detection"
  description        = "Функция для поиска лиц"
  user_hash          = "any_user_defined_string"
  runtime            = "python311"
  entrypoint         = "index.handler"
  memory             = "128"
  execution_timeout  = "10"
  service_account_id = local.service_account_id
  tags               = ["my_tag"]
  content {
    zip_filename = "face_detection.zip"
  }
  environment = {
    AWS_ACCESS_KEY_ID     = yandex_iam_service_account_static_access_key.sa-static-key.access_key
    AWS_SECRET_ACCESS_KEY = yandex_iam_service_account_static_access_key.sa-static-key.secret_key
    FOLDER_ID             = var.folder_id
    QUEUE_URL             = yandex_message_queue.queue-task.id
  }
}

resource "yandex_function_trigger" "photo-trigger" {
  name        = "${var.user}-photo"
  description = "Триггер для запуска обработчика face-detection"
  object_storage {
    batch_cutoff = 5
    bucket_id    = yandex_storage_bucket.photos.id
    create       = true
  }
  function {
    id                 = yandex_function.face-detection.id
    service_account_id = local.service_account_id
  }
}

resource "yandex_ydb_database_serverless" "ydb" {
  name        = "${var.user}-db-photo-face"
  location_id = "ru-central1"

  serverless_database {
    storage_size_limit = 5
  }
}

resource "yandex_ydb_table" "ydb-table" {
  path              = "faces"
  connection_string = yandex_ydb_database_serverless.ydb.ydb_full_endpoint

  column {
    name = "face_key"
    type = "String"
  }

  column {
    name = "face_name"
    type = "String"
  }

  column {
    name = "original_key"
    type = "String"
  }

  primary_key = ["face_key"]
}

data "archive_file" "zip-face-cut" {
  type        = "zip"
  output_path = "face_cut.zip"
  source_dir  = "./functions/face_cut"
}

resource "yandex_function" "face-cut" {
  name               = "${var.user}-face-cut"
  description        = "Функция создания фото по координатам"
  user_hash          = "any_user_defined_string"
  runtime            = "python311"
  entrypoint         = "index.handler"
  memory             = "128"
  execution_timeout  = "10"
  service_account_id = local.service_account_id
  tags               = ["my_tag"]
  content {
    zip_filename = "face_cut.zip"
  }
  environment = {
    AWS_ACCESS_KEY_ID     = yandex_iam_service_account_static_access_key.sa-static-key.access_key
    AWS_SECRET_ACCESS_KEY = yandex_iam_service_account_static_access_key.sa-static-key.secret_key
    FROM_BUCKET_NAME      = "${var.user}-photos"
    TO_BUCKET_NAME        = "${var.user}-faces"
    YDB_DATABASE          = yandex_ydb_database_serverless.ydb.database_path
    YDB_ENDPOINT          = yandex_ydb_database_serverless.ydb.ydb_api_endpoint
  }
}

resource "yandex_function_trigger" "task_trigger" {
  name        = "${var.user}-task"
  description = "Триггер для разгрузки очереди"
  message_queue {
    queue_id           = yandex_message_queue.queue-task.arn
    service_account_id = local.service_account_id
    batch_size         = "1"
    batch_cutoff       = "0"
  }
  function {
    id                 = yandex_function.face-cut.id
    service_account_id = local.service_account_id
  }
}

resource "yandex_api_gateway" "gateway" {
  name = "${var.user}-apigw"
  spec = <<-EOT
openapi: 3.0.0
info:
  title: Sample API
  version: 1.0.0
paths:
  /:
    get:
      parameters:
        - name: face
          in: query
          required: true
          schema:
            type: string
      x-yc-apigateway-integration:
        type: object_storage
        bucket: ${yandex_storage_bucket.faces.id}
        object: '{face}'
        error_object: error.html
        service_account_id: ${local.service_account_id}
EOT
}

data "archive_file" "zip-tg-boott" {
  type        = "zip"
  output_path = "tg_boot.zip"
  source_dir  = "./functions/tg_boot"
}


resource "yandex_function" "boot" {
  name               = "${var.user}-boot"
  description        = "Функция обработчик для tg бота"
  user_hash          = "any_user_defined_string"
  runtime            = "python311"
  entrypoint         = "index.handler"
  memory             = "128"
  execution_timeout  = "10"
  service_account_id = local.service_account_id
  tags               = ["my_tag"]
  content {
    zip_filename = "tg_boot.zip"
  }
  environment = {
    TELEGRAM_BOT_TOKEN    = var.tgkey
    AWS_ACCESS_KEY_ID     = yandex_iam_service_account_static_access_key.sa-static-key.access_key
    AWS_SECRET_ACCESS_KEY = yandex_iam_service_account_static_access_key.sa-static-key.secret_key
    YDB_DATABASE          = yandex_ydb_database_serverless.ydb.database_path
    YDB_ENDPOINT          = yandex_ydb_database_serverless.ydb.ydb_api_endpoint
    API_GATEWAY           = yandex_api_gateway.gateway.domain
    BUCKET_NAME           = "${var.user}-photos"
  }
}

resource "yandex_function_iam_binding" "boot--iam" {
  function_id = yandex_function.boot.id
  role        = "functions.functionInvoker"
  members = [
    "system:allUsers",
  ]
}

data "http" "webhook" {
  url = "https://api.telegram.org/bot${var.tgkey}/setWebhook?url=https://functions.yandexcloud.net/${yandex_function.boot.id}"
}




