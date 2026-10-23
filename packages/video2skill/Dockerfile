FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 app && mkdir /data && chown app /data
USER app
ENV V2S_DATA_DIR=/data
EXPOSE 8088
CMD ["video2skill", "serve", "--host", "0.0.0.0"]
