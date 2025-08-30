include .env
export

stop-postgres:
	docker stop quotes-postgres || true
	docker rm quotes-postgres || true

run-postgres: stop-postgres
	docker run --name quotes-postgres -p 5432:5432 -e POSTGRES_USER=${POSTGRES_USER} -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD} -e POSTGRES_DB=${POSTGRES_NAME} -d postgres:17-alpine
	@echo "Waiting for Postgres to be ready..."
	bash -c 'until docker exec quotes-postgres pg_isready -U ${POSTGRES_USER}; do echo "Waiting..."; sleep 2; done' || echo "Postgres is ready!"

migrate: run-postgres
	cd quotesapp && python manage.py makemigrations && python manage.py migrate

runserver: migrate
	cd quotesapp && python manage.py runserver

build:
	docker build --no-cache --progress=plain -t quotes-local .
	docker container prune -f
	docker image prune -f

run:
	docker run -p 8000:8000 quotes-local

