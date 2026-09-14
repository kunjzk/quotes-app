FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

WORKDIR /app/quotesapp

ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["gunicorn", "quotesapp.wsgi:application", "--bind", "0.0.0.0:8000"]