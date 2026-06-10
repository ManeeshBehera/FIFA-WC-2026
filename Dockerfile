# Node serves the app; Python (in a venv at /app/.venv, where server.js
# expects it) runs the prediction engine. Single container for Render.
FROM node:20-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python engine deps
COPY requirements.txt ./
RUN python3 -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt

# Node deps
COPY webapp/package*.json webapp/
RUN cd webapp && npm ci --omit=dev

COPY . .

# Bake the knowledge base into the image at build time (10-year archive,
# model fit, squads, first export) so the app boots ready. "|| true" keeps
# image builds working even if a source is briefly down — the server can
# regenerate everything at runtime.
RUN .venv/bin/python live_engine.py setup || true
RUN .venv/bin/python live_engine.py export || true

ENV PORT=3000
EXPOSE 3000
CMD ["node", "webapp/server.js"]
