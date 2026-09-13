#!/usr/bin/env bash
# Container entrypoint. Prepares the database before handing off to the
# process named in CMD.
set -e

# Only the web process initialises the database. The Celery worker and beat
# containers run from this same image, and would otherwise race each other
# running migrations at startup.
if [ "$1" = "gunicorn" ]; then
	# Postgres is often still accepting no connections when this starts, so
	# retry rather than crash-looping the container.
	migrated=false
	for attempt in $(seq 1 30); do
		if python manage.py migrate --noinput; then
			migrated=true
			break
		fi
		echo "database not ready, retrying (${attempt}/30)..."
		sleep 2
	done

	if [ "$migrated" != "true" ]; then
		echo "migrations failed after 30 attempts, refusing to start" >&2
		exit 1
	fi

	python manage.py seed_accounts
fi

exec "$@"
