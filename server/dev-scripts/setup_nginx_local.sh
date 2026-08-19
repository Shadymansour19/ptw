#!/usr/bin/env bash
# One-time LOCAL-ONLY setup for testing the H2 HTTPS path (see KNOWN_ISSUES.md) against
# this same machine: installs nginx, generates the localhost dev cert if it's not there
# yet, wires up server/deploy/ptw.local.conf (this box's absolute-path copy of the
# generic server/deploy/ptw.conf template), and starts nginx on :443.
#
# This is NOT the real deployment procedure - a real deployment's cert is generated for
# the server's actual static IP/hostname (`generate_cert.sh <ip>`, not `localhost`) and
# its nginx config lives on that server, not necessarily via this exact script. This is
# just the fastest way to reproduce that setup on a dev box to confirm the client/server
# HTTPS wiring actually works end to end before a real rollout.
#
# Needs sudo - run interactively, not backgrounded, so you can enter your password.
#
# Usage: ./setup_nginx_local.sh
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_PATH="$SERVER_DIR/certs/server_cert.pem"
LOCAL_CONF="$SERVER_DIR/deploy/ptw.local.conf"

if [ ! -f "$CERT_PATH" ]; then
    echo "No dev cert found - generating one for localhost..."
    "$SERVER_DIR/deploy/generate_cert.sh" localhost
fi

if [ ! -f "$LOCAL_CONF" ]; then
    echo "error: $LOCAL_CONF not found - it's gitignored (machine-specific absolute" >&2
    echo "paths), so create it from server/deploy/ptw.conf first if it's missing." >&2
    exit 1
fi

echo "Installing nginx (sudo)..."
# `|| true`: apt-get update returns non-zero if ANY configured repo fails (a stale
# third-party PPA, an expired signing key, etc.), even when Ubuntu's own archives -
# all nginx needs - refreshed fine. Don't let an unrelated repo being broken block
# installing nginx.
sudo apt-get update || true
sudo apt-get install -y nginx

echo "Wiring in $LOCAL_CONF..."
sudo ln -sf "$LOCAL_CONF" /etc/nginx/sites-enabled/ptw.conf
sudo rm -f /etc/nginx/sites-enabled/default   # avoid it grabbing :443 too

echo "Validating + starting nginx..."
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl status nginx --no-pager

echo
echo "Sanity check (curl -k skips curl's OWN cert check for this manual test only -"
echo "unrelated to the real client's pinned verify=):"
curl -k -i https://localhost/login || true

echo
echo "If that returned a real HTTP response (401/405), not a connection error, nginx is"
echo "proxying correctly to whatever's serving the app on 127.0.0.1:5000 (flask run or"
echo "python app.py). Point client/.env's PTW_SERVER_URL at https://localhost and retry"
echo "login from the desktop client."
