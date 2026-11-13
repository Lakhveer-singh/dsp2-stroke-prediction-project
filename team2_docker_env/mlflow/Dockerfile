FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Full mlflow = tracking server + UI + model registry. psycopg2 -> PostgreSQL backend store.
RUN pip install --no-cache-dir mlflow==3.17.2 psycopg2-binary==2.9.12

EXPOSE 5000
