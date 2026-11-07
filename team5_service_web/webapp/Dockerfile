FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Home.py .
COPY pages ./pages
COPY utils ./utils

EXPOSE 8501

CMD ["streamlit", "run", "Home.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
