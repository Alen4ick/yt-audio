#!/usr/bin/env bash
set -uo pipefail

failures=0

check() {
    local name="$1"
    local url="$2"
    local code

    if code=$(curl --silent --show-error \
        --connect-timeout 3 \
        --max-time 10 \
        --output /dev/null \
        --write-out '%{http_code}' \
        "$url"); then

        if [[ "$code" == "200" ]]; then
            printf 'OK   %s — HTTP %s\n' "$name" "$code"
        else
            printf 'FAIL %s — HTTP %s\n' "$name" "$code"
            failures=$((failures + 1))
        fi
    else
        printf 'FAIL %s — ошибка соединения или запроса\n' "$name"
        failures=$((failures + 1))
    fi
}

check "Music frontend" "http://127.0.0.1:3230/"
check "Music backend"  "http://127.0.0.1:3240/health"
check "Markdown"       "http://127.0.0.1:3210/health"
check "Grafana"        "http://127.0.0.1:3000/api/health"

if [[ "$failures" -gt 0 ]]; then
    printf 'Не пройдено проверок: %s\n' "$failures"
    exit 1
fi

echo "Все HTTP-проверки пройдены."
