#!/usr/bin/env bash
# Runs on the EC2 instance, invoked by .github/workflows/deploy-aws.yml.
# Expects docker-compose.prod.yml, quotesapp.service and env.rendered to
# have been copied to /tmp first.
#
# This is a file rather than a heredoc piped to ssh on purpose: `docker
# compose run` attaches stdin, so when the script arrived over stdin the
# migrate step consumed the remaining lines and everything after it was
# silently skipped.
set -euo pipefail

DEPLOY_DIR=/opt/quotesapp

compose() {
  sudo docker compose -f docker-compose.prod.yml "$@"
}

sudo install -o root -g root -m 644 /tmp/docker-compose.prod.yml "$DEPLOY_DIR/docker-compose.prod.yml"
sudo install -o root -g root -m 600 /tmp/env.rendered "$DEPLOY_DIR/.env"
sudo install -o root -g root -m 644 /tmp/quotesapp.service /etc/systemd/system/quotesapp.service
sudo install -o root -g root -m 644 /tmp/Caddyfile "$DEPLOY_DIR/Caddyfile"

# Origin keypair. Caddy runs as root in the container, so 600 is readable.
sudo install -d -o root -g root -m 700 "$DEPLOY_DIR/tls"
sudo install -o root -g root -m 644 /tmp/origin.pem "$DEPLOY_DIR/tls/origin.pem"
sudo install -o root -g root -m 600 /tmp/origin.key "$DEPLOY_DIR/tls/origin.key"

rm -f /tmp/env.rendered /tmp/origin.pem /tmp/origin.key
sudo systemctl daemon-reload

cd "$DEPLOY_DIR"

echo "--- pulling images ---"
compose pull

echo "--- running migrations ---"
compose run --rm -T quotes-app python manage.py migrate --noinput </dev/null

echo "--- recreating containers ---"
compose up -d --remove-orphans

echo "--- enabling start on boot ---"
sudo systemctl enable quotesapp

echo "--- pruning old images ---"
sudo docker image prune -f

echo "--- final state ---"
compose ps
