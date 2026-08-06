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
    log.info("Starting PTW server on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
