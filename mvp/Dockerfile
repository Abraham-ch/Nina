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
ENV NINA_DATA_DIR=/app/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python","-m","uvicorn","nina.main:app","--host","0.0.0.0","--port","8000"]
