build:
	docker build --no-cache --progress=plain -t quotes-local .
	docker container prune -f
	docker image prune -f

run:
	docker run -p 8000:8000 quotes-local