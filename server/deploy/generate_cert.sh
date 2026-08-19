#!/usr/bin/env bash
# Generates the single self-signed TLS cert/key pair used by the nginx/caddy reverse
# proxy in front of the PTW server - see KNOWN_ISSUES.md H2 and ptw.conf in this folder.
#
# There is deliberately no CA here: this cert is pinned directly by every client via
# `verify=` (see client/network/requestConfig.py's PTW_CA_CERT_PATH), not validated
# against a trust store. That's fine for a small, fixed set of known client machines,
# and means the cert only needs to be trusted by the clients it's handed to, not
# publicly - so a long (multi-decade) validity is fine too; there's no CA/browser
# lifespan policy capping it.
#
# Usage:
#   ./generate_cert.sh <server-ip-or-hostname> [output-dir]
#
# Re-run this only when the server's IP/hostname changes (see the SAN note below) or
# the key needs rotating - otherwise the generated cert is a one-time thing, not
# something re-run per deployment.
set -euo pipefail

SERVER_ADDR="${1:?Usage: $0 <server-ip-or-hostname> [output-dir]}"
OUT_DIR="${2:-$(dirname "$0")/../certs}"
DAYS=7300   # ~20 years - multi-decade, since this is privately pinned, not CA-issued.

mkdir -p "$OUT_DIR"
KEY_PATH="$OUT_DIR/server_key.pem"
CERT_PATH="$OUT_DIR/server_cert.pem"

# SAN includes the static server IP/hostname passed in, plus localhost/127.0.0.1 so the
# client can also be run on the server machine itself for testing. SERVER_ADDR itself
# must land in the SAN as IP:... or DNS:... depending on which it actually is - openssl
# rejects a bare hostname passed as IP:, so don't just assume it's always an IP.
if [[ "$SERVER_ADDR" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
    SAN="DNS:localhost,IP:127.0.0.1,IP:${SERVER_ADDR}"
elif [ "$SERVER_ADDR" = "localhost" ]; then
    SAN="DNS:localhost,IP:127.0.0.1"
else
    SAN="DNS:localhost,IP:127.0.0.1,DNS:${SERVER_ADDR}"
fi

openssl req -x509 -newkey rsa:4096 -sha256 -days "$DAYS" -nodes \
    -keyout "$KEY_PATH" -out "$CERT_PATH" \
    -subj "/CN=${SERVER_ADDR}" \
    -addext "subjectAltName=${SAN}"

# Private key must not be world-readable - lock it down to the OS user that will run
# nginx/caddy right away, not as an afterthought.
chmod 600 "$KEY_PATH"

# Also drop a copy at client/certs/dev-server-cert.pem - requestConfig.py's
# PTW_CA_CERT_PATH default (see client/.env.example) - so a checkout of this repo is
# immediately ready for local dev/testing without a manual copy step. This is only a
# convenience for THIS checkout; it does nothing for distributing the cert to other,
# real client machines - that copy still has to happen manually (step 2 below).
CLIENT_CERT_DIR="$(dirname "$0")/../../client/certs"
if [ -d "$(dirname "$0")/../../client" ]; then
    mkdir -p "$CLIENT_CERT_DIR"
    cp "$CERT_PATH" "$CLIENT_CERT_DIR/dev-server-cert.pem"
fi

echo "Generated:"
echo "  Private key (keep on server only, mode 600): $KEY_PATH"
echo "  Public cert (distribute to clients):          $CERT_PATH"
echo "  Copied to client/certs/dev-server-cert.pem for local dev in this checkout."
echo
echo "Next steps:"
echo "  1. Point ptw.conf's ssl_certificate/ssl_certificate_key at these two files."
echo "  2. For any OTHER client machine, copy $CERT_PATH to it and set PTW_CA_CERT_PATH"
echo "     to wherever it ends up there."
