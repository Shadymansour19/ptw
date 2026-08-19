"""Entry point: registers all route blueprints on the Flask app built in core.py
and serves it via waitress when executed directly."""

from waitress import serve

from core import app, log
from routes.auth import authBp
from routes.users import usersBp
from routes.ptws import ptwsBp
from routes.ics import icsBp
from routes.risks import risksBp
from routes.documents import documentsBp
from routes.admin import adminBp

app.register_blueprint(authBp)
app.register_blueprint(usersBp)
app.register_blueprint(ptwsBp)
app.register_blueprint(icsBp)
app.register_blueprint(risksBp)
app.register_blueprint(documentsBp)
app.register_blueprint(adminBp)

if __name__ == "__main__":
    # Bound to 127.0.0.1, not 0.0.0.0 - this is the primary defense against LAN access to
    # the raw, unencrypted port (more important than any firewall rule). All external
    # traffic is meant to arrive via a reverse proxy (nginx/caddy) on the same machine,
    # which terminates TLS and forwards to this address - see KNOWN_ISSUES.md H2 and
    # deploy/nginx/ptw.conf. waitress (not the Flask dev server, and not gunicorn - which
    # is POSIX-only) so the same entry point runs on either a Linux or Windows host.
    log.info("Starting PTW server on 127.0.0.1:5000 (behind reverse proxy)")
    serve(app, host="127.0.0.1", port=5000, threads=8)
