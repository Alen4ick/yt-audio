# YouTube Audio

Учебное веб-приложение: ссылка на YouTube-видео → получение аудиопотока → воспроизведение в браузере.

Backend использует FastAPI, Uvicorn и yt-dlp. Deno нужен для JavaScript-задач YouTube. Запросы к YouTube и аудиопотоку направляются через SOCKS5-прокси, заданный в `YT_PROXY`.

## Выбор способа развёртывания

| | Docker Compose | Systemd |
|---|---|---|
| Backend | Собственный образ `yt-audio:practice` | Python-окружение в `/opt/yt-audio/venv` |
| Пользователь backend | `appuser`, UID `10001` внутри контейнера | `sys_yt_aud` на хосте |
| Xray | Контейнер, общая сеть с backend | Нативная служба `xray.service` |
| Backend на хосте | `127.0.0.1:3240` | `127.0.0.1:3250` |
| Frontend | Nginx-контейнер на `127.0.0.1:3230` | Файлы в `/var/www/yt-audio` |
| Публичный вход | Nginx на хосте: HTTP/HTTPS | Nginx на хосте: HTTP/HTTPS |

Можно оставить frontend в Nginx на хосте и переключать только backend. Именно такое переключение backend было проверено на учебном VPS. Для полностью контейнерного frontend используйте вариант `location /` из раздела Nginx ниже.

TLS завершается на Nginx хоста в обоих вариантах. Compose не устанавливает этот Nginx и не выпускает сертификаты.

## Структура проекта

```text
backend/
  .dockerignore
  Dockerfile
  Dockerfile.practice
  app.py
  requirements.txt
frontend/
  index.html
deploy/
  systemd/
    yt-audio.service
compose.yaml
README.md
```

Compose явно использует `backend/Dockerfile.practice`. Файл `backend/Dockerfile` сохранён как предыдущий вариант и в этой сборке не участвует. Тег `practice` — локальное имя варианта образа; готовый образ в registry публиковать для этой инструкции не требуется.

## Получение проекта

```bash
git clone https://github.com/Alen4ick/yt-audio.git
cd yt-audio
```

Команды Compose и пути к исходным файлам ниже рассчитаны на запуск из корня репозитория. Для скачивания публичного репозитория по HTTPS личный SSH-ключ GitHub на сервере не нужен.

## Вариант 1. Docker Compose

### Требования

- Linux с Docker Engine, плагинами Buildx и Compose. Установка: [Docker Engine](https://docs.docker.com/engine/install/), [Compose plugin](https://docs.docker.com/compose/install/linux/).
- Доступ к реестрам Docker Hub и GHCR, а также к источникам Python-пакетов для сборки.
- Собственная рабочая конфигурация Xray.
- Для публичного HTTPS: Nginx и сертификат на хосте, см. отдельный раздел ниже.

### Конфигурация Xray

Поместите собственный файл `xray-config.json` в корень проекта **до запуска Compose**. Это должен быть обычный JSON-файл, не каталог и не URL подписки. Настройте SOCKS5 inbound на `127.0.0.1:10808` внутри контейнера; исходящие подключения настройте по реквизитам своего провайдера.

Файл монтируется в контейнер по пути `/etc/xray/config.json` только для чтения. Он должен быть доступен на чтение пользователю процесса Xray в выбранном образе. Не публикуйте конфигурацию с VPN-реквизитами в Git.

```bash
test -f xray-config.json
git check-ignore xray-config.json
```

Первая команда должна завершиться успешно. Вторая должна вывести `xray-config.json`. Если не выводит, добавьте `/xray-config.json` в корневой `.gitignore` перед дальнейшими коммитами.

В Compose backend имеет `network_mode: "service:xray"`: контейнеры разделяют сетевое пространство. Поэтому `YT_PROXY=socks5://127.0.0.1:10808` указывает на контейнерный Xray. Публикация `127.0.0.1:3240:8000` находится в секции `xray`, хотя порт `8000` слушает backend. Нативная служба Xray для этого варианта не нужна.

### Сборка и запуск

```bash
sudo systemctl enable --now docker.service
sudo docker compose config -q
sudo docker compose build backend
sudo docker compose up -d
sudo docker compose ps
```

При ошибке любого шага исправьте её перед выполнением следующего. `config -q` проверяет описание сервисов; доступ к YouTube и работоспособность Xray эта команда не проверяет.

Образ backend содержит Python 3.12, Deno 2.9.6 и зависимости из `requirements.txt`. Приложение запускается от `appuser`, UID `10001`. Build context — `backend`; `.dockerignore` исключает локальные виртуальные окружения, кеш Python и `.env`-файлы.

У backend ожидается статус `healthy`. Проверка может сначала показывать `starting`.

```bash
curl --fail --show-error http://127.0.0.1:3230/
curl --fail --show-error http://127.0.0.1:3240/health
sudo docker compose exec backend id
sudo docker compose exec backend deno --version
```

Frontend должен вернуть HTML, backend — `{"status":"ok"}`. Порт `3230` нужен для проверки HTML; для использования приложения с API откройте общий адрес Nginx, настроенный ниже.

### Healthcheck, логи и остановка

Compose проверяет `/health` внутри backend с интервалом `30s`, тайм-аутом `5s`, тремя последовательными неудачами до `unhealthy` и начальным периодом `15s`. Проверка не подтверждает доступность YouTube или прокси.

```bash
sudo docker compose logs --tail=60 backend xray
sudo docker compose stop
```

`stop` останавливает контейнеры, сохраняя их. Повторный запуск — `sudo docker compose up -d`. Для удаления контейнеров проекта и управляемых Compose сетей используйте `sudo docker compose down`; исходники и файл конфигурации на хосте останутся.

`restart: unless-stopped` позволяет поднимать контейнеры после запуска Docker, если они не были остановлены вручную. Сам статус `unhealthy` не вызывает автоматический перезапуск.

### Обновление

Из чистой рабочей директории, для клона с настроенной отслеживаемой веткой:

```bash
git pull --ff-only
sudo docker compose build backend
sudo docker compose up -d
```

Если после пересоздания Xray backend сообщает об отсутствующем сетевом namespace, пересоздайте оба контейнера вместе:

```bash
sudo docker compose up -d --force-recreate xray backend
```

Обновление backend прерывает активные потоки и очищает временные ссылки в памяти. После обновления повторно отправьте ссылку на видео.

## Вариант 2. Systemd

### Требования

- Ubuntu 24.04, Python 3.12 и `python3-venv`.
- Nginx на хосте.
- Deno, установленный для всей системы, например в `/usr/local/bin/deno`.
- Настроенная нативная служба `xray.service`, SOCKS5 на `127.0.0.1:10808`.

```bash
sudo apt update
sudo apt install python3 python3-venv nginx
```

Xray устанавливается и настраивается отдельно: [официальный Xray-install](https://github.com/XTLS/Xray-install). Настройте собственные исходящие подключения и проверьте службу:

```bash
sudo systemctl enable --now xray.service
systemctl status xray.service --no-pager
```

Deno можно скачать по [официальной инструкции](https://docs.deno.com/runtime/getting_started/installation/#manual-download). Выберите архив под архитектуру сервера, распакуйте и установите бинарник в `/usr/local/bin/deno` с правами `0755`. Для соответствия Docker-варианту используется версия `2.9.6`. Установка только в домашний каталог администратора не делает Deno доступным сервисному пользователю.

### Пользователь и каталоги

Создание пользователя выполняется один раз. Если он уже существует, этот шаг пропустите.

```bash
sudo useradd --system --user-group \
  --home-dir /var/lib/yt-audio --no-create-home \
  --shell /usr/sbin/nologin sys_yt_aud
sudo install -d -o root -g sys_yt_aud -m 0750 /opt/yt-audio
sudo install -d -o sys_yt_aud -g sys_yt_aud -m 0750 /var/lib/yt-audio
sudo install -d -o root -g sys_yt_aud -m 0750 /etc/yt-audio
```

Исходники принадлежат root; домашний каталог сервисного пользователя доступен ему для записи кеша.

### Backend и окружение

```bash
sudo install -o root -g sys_yt_aud -m 0640 \
  backend/app.py backend/requirements.txt /opt/yt-audio/
sudo python3 -m venv /opt/yt-audio/venv
sudo /opt/yt-audio/venv/bin/python -m pip install \
  --no-cache-dir -r /opt/yt-audio/requirements.txt
sudo nano /etc/yt-audio/environment
```

Содержимое `/etc/yt-audio/environment`:

```ini
YT_PROXY=socks5://127.0.0.1:10808
```

```bash
sudo chown root:sys_yt_aud /etc/yt-audio/environment
sudo chmod 0640 /etc/yt-audio/environment
sudo -u sys_yt_aud /usr/local/bin/deno --version
```

### Установка и запуск службы

```bash
sudo install -o root -g root -m 0644 \
  deploy/systemd/yt-audio.service /etc/systemd/system/yt-audio.service
sudo systemctl daemon-reload
sudo systemctl enable --now yt-audio.service
systemctl status yt-audio.service --no-pager
curl --fail --show-error http://127.0.0.1:3250/health
```

Unit из репозитория использует пользователя `sys_yt_aud`, рабочий каталог `/opt/yt-audio`, файл `/etc/yt-audio/environment` и слушает `127.0.0.1:3250`.

Логи:

```bash
sudo journalctl -u yt-audio.service -n 60 --no-pager
```

### Установка frontend

```bash
sudo install -d -o root -g root -m 0755 /var/www/yt-audio
sudo install -o root -g root -m 0644 frontend/index.html /var/www/yt-audio/index.html
```

### Обновление

Получите новый коммит в клоне, повторите копирование `app.py`, `requirements.txt`, установку Python-зависимостей и копирование frontend, затем выполните:

```bash
sudo systemctl restart yt-audio.service
```

Если менялся unit, также повторно установите его и выполните `sudo systemctl daemon-reload` перед перезапуском.

## Общий Nginx и HTTPS

### Предварительные условия

Нужны публичный домен или IP-адрес, доступные снаружи порты `80`/`443` и действительный сертификат именно для выбранного адреса. Сертификат и ключ не входят в репозиторий. Выпуск зависит от домена/IP и способа ACME-проверки; используйте [инструкцию Certbot](https://certbot.eff.org/instructions).

Ниже — шаблон для уже выпущенного сертификата. Замените `YOUR_DOMAIN_OR_IP` и оба пути `YOUR_CERT_NAME` на реальные значения. Конфигурация не пройдёт проверку, пока указанные файлы сертификата и ключа не существуют.

На Ubuntu файл сайта можно разместить в `/etc/nginx/sites-available/yt-audio`, создав ссылку на него в `sites-enabled`. Если сайт уже настроен, изменяйте существующий файл, не создавая второй блок с тем же адресом.

### Шаблон сайта: Docker

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name YOUR_DOMAIN_OR_IP;

    ssl_certificate /etc/letsencrypt/live/YOUR_CERT_NAME/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/YOUR_CERT_NAME/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3230;
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:3240/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

Каталог `/var/www/letsencrypt` в шаблоне относится к ACME webroot-проверке. Если используете webroot, создайте его и укажите тот же каталог в Certbot. При другом способе проверки сохраните соответствующую рабочую ACME-конфигурацию.

Для systemd-варианта замените `location /` в HTTPS-блоке на:

```nginx
location / {
    root /var/www/yt-audio;
    index index.html;
    try_files $uri $uri/ =404;
}
```

В `location /api/` замените upstream на `http://127.0.0.1:3250/`. Этот же статический `location /` можно оставить и при Docker-backend, если frontend установлен на хосте.

Завершающий `/` в `proxy_pass` для API нужен: `/api/health` снаружи превращается в `/health` для backend. [Справочник Nginx: proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).

Для нового сайта включите конфигурацию ссылкой (один раз):

```bash
sudo ln -s /etc/nginx/sites-available/yt-audio /etc/nginx/sites-enabled/yt-audio
```

После изменения проверьте конфигурацию. Только при успешной проверке перечитайте её:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Проверьте `https://YOUR_DOMAIN_OR_IP/api/health`, затем откройте приложение в браузере, запустите видео и проверьте перемотку. Не обходите проверку сертификата через `curl -k`.

### Продление сертификата

Certbot должен запускаться по расписанию. Имя таймера зависит от способа установки; в snap-варианте это `snap.certbot.renew.timer`.

```bash
systemctl list-timers --all --no-pager
sudo certbot certificates
sudo certbot renew --cert-name YOUR_CERT_NAME --dry-run
```

`--dry-run` проверяет продление через тестовый сервер, не заменяя рабочий сертификат. Успешная проверка сама по себе не доказывает, что Nginx перечитает сертификат после реального продления. Для этого должен быть настроен installer или deploy-hook с проверкой и reload Nginx; например, команда `nginx -t && systemctl reload nginx`. Сначала проверьте уже существующие hooks, чтобы не дублировать их. [Документация Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).

## Переключение между Docker и systemd

Сначала запустите и проверьте целевой backend напрямую, затем переключите Nginx. Старый backend останавливайте после успешного воспроизведения нового видео через HTTPS.

| Выбор | API upstream в Nginx | Frontend |
|---|---|---|
| Docker | `http://127.0.0.1:3240/` | Контейнер `3230` или установленные файлы на хосте |
| Systemd | `http://127.0.0.1:3250/` | `/var/www/yt-audio` |

### Systemd → Docker

1. Подготовьте `xray-config.json`, соберите образ и запустите `sudo docker compose up -d --build`.
2. Проверьте `http://127.0.0.1:3240/health` и статус `healthy`.
3. В Nginx выберите порт API `3240`. При переходе на контейнерный frontend также выберите порт `3230` для `location /`.
4. Выполните `sudo nginx -t`; при успехе — `sudo systemctl reload nginx`.
5. Проверьте HTTPS и новое видео, затем выполните `sudo systemctl disable --now yt-audio.service`.
6. Проверьте воспроизведение ещё одного видео после остановки службы. Убедитесь, что `docker.service` включён в автозапуск.

Нативный Xray можно отключать отдельно только после проверки, что его не используют другие приложения.

### Docker → Systemd

1. Подготовьте нативные Xray, Deno, Python-окружение, environment-файл и статический frontend по инструкции выше.
2. Запустите `sudo systemctl enable --now xray.service yt-audio.service`.
3. Проверьте `http://127.0.0.1:3250/health`.
4. В Nginx выберите API upstream `3250` и статический frontend на хосте.
5. Выполните `sudo nginx -t`; при успехе — `sudo systemctl reload nginx`.
6. Проверьте новое видео через HTTPS и только затем выполните `sudo docker compose stop`.
7. Повторно проверьте воспроизведение после остановки контейнеров.

## Порты

| Адрес | Назначение |
|---|---|
| `127.0.0.1:3230` на хосте | Docker frontend |
| `127.0.0.1:3240` на хосте | Docker backend через сеть Xray |
| `127.0.0.1:3250` на хосте | Systemd backend |
| `127.0.0.1:10808` на хосте | Нативный Xray SOCKS5 |
| `127.0.0.1:10808` в общей сети контейнеров | Контейнерный Xray SOCKS5, не опубликован на хост |
| `8000` в общей сети контейнеров | Uvicorn backend |
| `80`/`443` на хосте | Публичный Nginx |

Loopback на хосте и loopback в контейнерной сети — разные адресные пространства. Подключение frontend/backend к loopback хоста ограничивает прямой доступ извне; публичный доступ обеспечивает Nginx.

## Проверенный результат и ограничения

- В учебном развёртывании проверены сборка собственного образа, UID `10001`, запуск Deno, healthcheck, HTTPS, воспроизведение аудио и работа Docker-backend после остановки systemd-backend.
- Пробное продление сертификата Certbot прошло успешно; автоматическое перечитывание сертификата Nginx после реального продления отдельно не подтверждено.
- Инструкция новой установки целиком на чистом VPS не прогонялась.
- Работоспособность YouTube зависит от доступности видео, прокси и изменений на стороне YouTube.
- Состояние потоков хранится в памяти одного процесса; после перезапуска старые ссылки на поток перестают работать.
- Теги образов, включая `python:3.12-slim`, `nginx:alpine` и Xray `latest`, могут обновляться. Эта конфигурация не гарантирует побайтово одинаковую повторную сборку.
