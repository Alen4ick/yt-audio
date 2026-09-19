#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -f xray-config.json ]]; then
    echo "Ошибка: добавьте xray-config.json в корень проекта." >&2
    exit 1
fi

docker compose config -q

docker compose up -d --build --wait --wait-timeout 180

docker compose ps
echo "Контейнеры запущены. Далее проверьте эндпоинты сервисов."
