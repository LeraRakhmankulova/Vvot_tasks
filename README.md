# Обработка фотографий с лицами людей
### Разработка информационной системы на базе сервисов облачного провайдера «Yandex Cloud».

## Запуск конфигурации terraform
### Выполнить команды в корне папки с помощью CLI Yandex Cloud
```
1. yc iam service-account create --name <имя_сервисного_аккаунта> --folder-name=<имя_папки>

2. yc <service-name> <resource> add-access-binding <resource-name>|<resource-id> \
  --role <role-id> \
  --subject serviceAccount:<service-account-id>

3. yc iam key create \
  --service-account-id <идентификатор_сервисного_аккаунта> \
  --folder-name <имя_каталога_с_сервисным_аккаунтом> \
  --output key.json
```
Изменить переменные в файле terraform.tfvars

### Выполнить команды
```
terraform init
terraform fmt
terraform validate
terraform plan 
terraform apply 
```
## Облачные функции
Код для обработчиков face-detection, face-cut, tg-boot находится в папке functions
Ссылка на доступного бота - https://t.me/vvot29_2023_bot
