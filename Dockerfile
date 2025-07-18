# Base image with Python and Playwright dependencies
FROM mcr.microsoft.com/playwright/python:v1.51.0-noble
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    playwright install --with-deps chromium
 
COPY . .

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
