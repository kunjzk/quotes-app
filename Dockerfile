# Compile Tailwind at build time instead of in every visitor's browser.
FROM node:22-slim AS css

WORKDIR /src

COPY tailwind.config.js ./
COPY assets/ assets/
COPY quotesapp/ quotesapp/

RUN npx --yes tailwindcss@3.4.17 -c tailwind.config.js -i assets/app.css -o /out/app.css --minify

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

COPY --from=css /out/app.css /app/quotesapp/quotes/static/quotes/app.css

RUN chmod +x /app/entrypoint.sh

WORKDIR /app/quotesapp

# collectstatic only needs settings to import; the key is never used.
RUN DJANGO_SECRET_KEY=collectstatic python manage.py collectstatic --noinput

ENTRYPOINT ["/app/entrypoint.sh"]

# Several workers so one slow request (photo OCR) doesn't block everyone else.
CMD ["gunicorn", "quotesapp.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "60"]
