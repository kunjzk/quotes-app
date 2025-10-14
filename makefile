include .env
export

stop-postgres:
	docker-compose down quotes-postgres
	docker-compose rm -f quotes-postgres

run-postgres: stop-postgres
	docker-compose up -d --force-recreate quotes-postgres
	@echo "Waiting for Postgres to be ready..."
	bash -c 'until docker-compose exec quotes-postgres pg_isready -U ${POSTGRES_USER}; do echo "Waiting..."; sleep 2; done' || echo "Postgres is ready!"

migrate: run-postgres
	cd quotesapp && python manage.py makemigrations && python manage.py migrate

runserver: migrate
	cd quotesapp && python manage.py runserver

test: run-postgres
	cd quotesapp && python manage.py test

coverage: run-postgres
	cd quotesapp && coverage erase && coverage run --rcfile=../.coveragerc manage.py test && coverage report --show-missing

coverage-html: run-postgres
	cd quotesapp && coverage erase && coverage run --rcfile=../.coveragerc manage.py test &&coverage html && open htmlcov/index.html

stop-redis:
	docker-compose down quotes-redis
	docker-compose rm -f quotes-redis

run-redis: stop-redis
	docker-compose up -d --force-recreate quotes-redis
	@echo "Waiting for Redis to be ready..."
	bash -c 'until docker-compose exec quotes-redis redis-cli ping; do echo "Waiting..."; sleep 2; done' || echo "Redis is ready!"

run-celery-worker: run-redis run-postgres
	cd quotesapp && celery -A quotesapp.celery.app worker -l info

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

