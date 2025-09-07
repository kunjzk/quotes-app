# Quotes App

## How to run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# add suitable values to .env file
make up
```

Go to `localhost:8000` on browser to view app.

## What make up does

1. Run postgres image locally with the values saved in .env
2. Build app image locally & run it once postgres successfully starts up
3. Creates a volume for postgres to persist data independantly of container lifecycle
