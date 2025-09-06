include .env
export

stop-postgres:
	docker-compose down
	docker container prune -f
	docker image prune -f

run-postgres: stop-postgres
	docker-compose up -d quotes-postgres
	@echo "Waiting for Postgres to be ready..."
	bash -c 'until docker-compose exec quotes-postgres pg_isready -U ${POSTGRES_USER}; do echo "Waiting..."; sleep 2; done' || echo "Postgres is ready!"

migrate: run-postgres
	cd quotesapp && python manage.py makemigrations && python manage.py migrate

runserver: migrate
	cd quotesapp && python manage.py runserver

# To test image build in isolation
build-image:
	docker build --no-cache --progress=plain -t quotes-local .
	docker container prune -f
	docker image prune -f

# To test image run in isolation
run-image:
	docker run -p 8000:8000 quotes-local

# Docker Compose commands for full stack
up:
	docker-compose up -d

down:
	docker-compose down
	docker container prune -f
	docker image prune -f

logs:
	docker-compose logs -f

# Clean up volumes (WARNING: This will delete all data!)
clean-volumes:
	docker-compose down -v
	docker volume prune -f

