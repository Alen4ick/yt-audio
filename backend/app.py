import os
import asyncio
import time
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

YT_PROXY = os.getenv("YT_PROXY")
app = FastAPI(title="YouTube Audio API")

STREAM_TTL = 1800
streams: dict[str, dict] = {}


class ResolveRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)


def validate_youtube_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    is_youtube = (
        hostname == "youtu.be"
        or hostname == "youtube.com"
        or hostname.endswith(".youtube.com")
    )

    if parsed.scheme not in {"http", "https"} or not is_youtube:
        raise ValueError("Разрешены только ссылки youtube.com и youtu.be")

    return url


def extract_audio(url: str) -> dict:
    options = {
        "format": (
            "bestaudio[protocol=https][ext=m4a]/"
            "bestaudio[protocol=https]/"
            "bestaudio[ext=m4a]/"
            "bestaudio"
        ),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "proxy": YT_PROXY,
        "socket_timeout": 10,
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    media_url = info.get("url")

    if not media_url:
        raise RuntimeError("yt-dlp не вернул URL аудиопотока")

    return {
        "url": media_url,
        "title": info.get("title") or "YouTube audio",
        "duration": info.get("duration"),
        "http_headers": info.get("http_headers") or {},
    }


def delete_expired_streams() -> None:
    now = time.monotonic()

    expired_tokens = [
        token
        for token, item in streams.items()
        if now - item["created_at"] > STREAM_TTL
    ]

    for token in expired_tokens:
        streams.pop(token, None)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/resolve")
async def resolve(payload: ResolveRequest) -> dict:
    try:
        url = validate_youtube_url(payload.url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    delete_expired_streams()

    try:
        stream_data = await asyncio.wait_for(
            asyncio.to_thread(extract_audio, url),
            timeout=20,
        )
    except TimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail="YouTube не ответил за 20 секунд",
        ) from error
    except DownloadError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка yt-dlp: {error}",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка backend: {error}",
        ) from error

    token = uuid.uuid4().hex

    streams[token] = {
        **stream_data,
        "created_at": time.monotonic(),
    }

    return {
        "title": stream_data["title"],
        "duration": stream_data["duration"],
        "audio_url": f"/api/stream/{token}",
    }


@app.get("/stream/{token}")
async def stream_audio(
    token: str,
    range_header: str | None = Header(default=None, alias="Range"),
):
    delete_expired_streams()
    stream_data = streams.get(token)

    if stream_data is None:
        raise HTTPException(
            status_code=404,
            detail="Поток не найден или срок ссылки истёк",
        )

    upstream_headers = dict(stream_data["http_headers"])
    upstream_headers["Accept-Encoding"] = "identity"

    if range_header:
        upstream_headers["Range"] = range_header

    client = httpx.AsyncClient(
        proxy=YT_PROXY,
        follow_redirects=True,
        timeout=httpx.Timeout(
            connect=10,
            read=None,
            write=10,
            pool=10,
        ),
    )

    request = client.build_request(
        "GET",
        stream_data["url"],
        headers=upstream_headers,
    )

    try:
        response = await client.send(request, stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось подключиться к аудиопотоку: {error}",
        ) from error

    response_headers = {}

    for header_name in (
        "content-type",
        "content-length",
        "content-range",
        "accept-ranges",
        "cache-control",
    ):
        header_value = response.headers.get(header_name)

        if header_value:
            response_headers[header_name] = header_value

    async def close_upstream() -> None:
        await response.aclose()
        await client.aclose()

    return StreamingResponse(
        response.aiter_raw(chunk_size=64 * 1024),
        status_code=response.status_code,
        headers=response_headers,
        background=BackgroundTask(close_upstream),
    )
