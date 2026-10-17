FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS node
FROM python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg chromium fonts-noto-cjk ca-certificates git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r deployment/local/requirements.lock && pip install --no-deps -e .
RUN mkdir -p /opt/runtime && cp deployment/local/package*.json /opt/runtime/ && npm ci --prefix /opt/runtime
RUN cd tools/agent_studio/scene && npm ci && npm run build
ENV PATH="/opt/runtime/node_modules/.bin:${PATH}" CREATIVE_STUDIO_ROOT=/app CREATIVE_DATA_DIR=/data/creative H3_GATEWAY_DB=/data/gateway/data.sqlite3 AD_LIBRARY_ROOT=/assets/library KLING_OUTPUT_DIR=/data/kling CREATIVE_MODEL_KEY_FILE=/run/secrets/director-key CREATIVE_GSAP=/opt/runtime/node_modules/gsap/dist/gsap.min.js CREATIVE_HYPERFRAMES=/opt/runtime/node_modules/.bin/hyperframes CREATIVE_FFMPEG=/usr/bin/ffmpeg CREATIVE_FFPROBE=/usr/bin/ffprobe H3_SGLANG_URL=http://127.0.0.1:30081 H3_PRIMARY_PROVIDER=kling H3_LOCAL_PROVIDER=kling H3_EMAIL_VERIFICATION_REQUIRED=0 H3_DEFAULT_QUOTA=0 PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
EXPOSE 30080
CMD ["python", "deployment/local/start.py"]
