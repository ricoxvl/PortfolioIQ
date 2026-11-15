# Multi-stage build. This Dockerfile needs internet access to package registries.
FROM node:22-alpine AS webbuild
WORKDIR /source/web
COPY production/web/package*.json ./
RUN npm install --no-audit --no-fund
COPY production/web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY production/requirements.txt /app/production/requirements.txt
RUN pip install --no-cache-dir -r /app/production/requirements.txt
COPY backend/ /app/backend/
COPY production/ /app/production/
COPY --from=webbuild /source/web/dist /app/production/web/dist
RUN useradd --create-home --uid 10001 portfolioiq && chown -R portfolioiq:portfolioiq /app
USER portfolioiq
EXPOSE 8000
CMD ["uvicorn", "production.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
