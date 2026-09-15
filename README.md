# YouTube Audio

Учебное веб-приложение, которое получает ссылку на YouTube-видео
и предоставляет аудиопоток.

Проект разворачивается двумя способами:

1. Docker Compose.
2. Нативные systemd-сервисы.

## Архитектура

### Docker

- frontend: Nginx container, `127.0.0.1:3230`;
- backend: FastAPI + Uvicorn, `127.0.0.1:3240`;
- Xray: SOCKS5-прокси внутри общего network namespace;
- host Nginx: TLS termination и reverse proxy.

### Systemd

- host Nginx: TLS и статический frontend;
- `yt-audio.service`: FastAPI + Uvicorn на `127.0.0.1:3250`;
- `xray.service`: SOCKS5 на `127.0.0.1:10808`.

## Структура проекта

```text
backend/
  Dockerfile
  app.py
  requirements.txt
frontend/
  index.html
deploy/
  systemd/
    yt-audio.service
compose.yaml
## Docker Compose

### Требования

- Docker Engine;
- Docker Compose plugin;
- пользовательская конфигурация Xray.

Поместите собственную конфигурацию Xray в корень проекта:

```text
xray-config.json
```

Файл содержит VPN-реквизиты и не должен добавляться в Git.

### Запуск

```bash
sudo docker compose up -d --build
sudo docker compose ps
```

Проверка frontend:

```bash
curl http://127.0.0.1:3230/
```

Проверка backend:

```bash
curl http://127.0.0.1:3240/health
```

Остановка:

```bash
sudo docker compose stop
```

## Systemd

### Требования

- Ubuntu 24.04;
- Python 3.12;
- `python3-venv`;
- Nginx;
- установленный Xray.

Xray устанавливается отдельно из официального проекта:

https://github.com/XTLS/Xray-install

Он должен предоставлять SOCKS5-прокси:

```text
127.0.0.1:10808
```

### Системный пользователь

```bash
sudo useradd \
  --system \
  --user-group \
  --home-dir /var/lib/yt-audio \
  --no-create-home \
  --shell /usr/sbin/nologin \
  sys_yt_aud
```

### Установка backend

```bash
sudo install \
  --directory \
  --owner=root \
  --group=sys_yt_aud \
  --mode=0750 \
  /opt/yt-audio
```

```bash
sudo install \
  --owner=root \
  --group=sys_yt_aud \
  --mode=0640 \
  backend/app.py \
  backend/requirements.txt \
  /opt/yt-audio/
```

```bash
sudo python3 -m venv /opt/yt-audio/venv
sudo /opt/yt-audio/venv/bin/pip install \
  --no-cache-dir \
  -r /opt/yt-audio/requirements.txt
```

### Переменные окружения

Создайте файл:

```text
/etc/yt-audio/environment
```

Содержимое:

```ini
YT_PROXY=socks5://127.0.0.1:10808
```

Файл должен принадлежать `root:sys_yt_aud` и иметь права `0640`.

### Установка unit-файла

```bash
sudo install \
  --owner=root \
  --group=root \
  --mode=0644 \
  deploy/systemd/yt-audio.service \
  /etc/systemd/system/yt-audio.service
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yt-audio.service
```

Проверка:

```bash
systemctl status yt-audio.service
curl http://127.0.0.1:3250/health
```

### Frontend и Nginx

Статический frontend устанавливается в:

```text
/var/www/yt-audio/index.html
```

Nginx должен:

- раздавать `/var/www/yt-audio`;
- перенаправлять `/api/` на `http://127.0.0.1:3250/`;
- завершать TLS;
- перенаправлять HTTP на HTTPS.

## Порты

| Адрес | Назначение |
|---|---|
| `127.0.0.1:3230` | Docker frontend |
| `127.0.0.1:3240` | Docker backend |
| `127.0.0.1:3250` | Systemd backend |
| `127.0.0.1:10808` | Нативный Xray SOCKS5 |
| `0.0.0.0:80` | Nginx HTTP |
| `0.0.0.0:443` | Nginx HTTPS |
