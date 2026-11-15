FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY nina/ ./nina/
COPY scripts/ ./scripts/
COPY data/boundaries/ ./data/boundaries/
COPY --from=web /web/dist ./web/dist
# Seed for the Fly volume, which hides /app/data: database, boundaries and the harmonized product.
COPY data/nina.duckdb ./seed/nina.duckdb
COPY data/boundaries/ ./seed/boundaries/
COPY source/review/ ./seed/source/review/
# Context layers of the territorial report and the analyst (forest, burned area, climate, events, case study).
COPY source/context/ ./seed/source/context/
ENV NINA_DATA_DIR=/app/data PYTHONUNBUFFERED=1
EXPOSE 8000
# ponytail: seeds the volume once per SEED version (marker file); bump SEED to copy a newer database and data.
ENV SEED=2
CMD ["sh","-c","[ -e /app/data/.seeded-$SEED ] || { cp -a /app/seed/. /app/data/ && touch /app/data/.seeded-$SEED; }; exec python -m uvicorn nina.main:app --host 0.0.0.0 --port 8000"]
