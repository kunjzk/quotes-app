FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

WORKDIR /app/quotesapp

CMD ["gunicorn", "quotesapp.wsgi:application", "--bind", "0.0.0.0:8000"]