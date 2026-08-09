"""Client entry point.

Creates the QApplication, sets `setQuitOnLastWindowClosed(False)` so hiding a window to the
system tray never implicitly quits the app, wires global styling/i18n/OCR configuration, and
shows the login window; a successful login routes to the role-appropriate main window.
"""

import sys
import logging
import tempfile
import traceback
import qtawesome as qta
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QIcon
from Login import LoginWindow
from windows.MainWindow import MainWindow
from windows.GuestMainWindow import GuestMainWindow
from windows.UserMainWindow import UserMainWindow
from windows.CoordinatorMainWindow import CoordinatorMainWindow
from windows.IssuingMainWindow import IssuingMainWindow
from windows.SafetyMainWindow import SafetyMainWindow
from windows.ManagerMainWindow import ManagerMainWindow
from windows.AdminMainWindow import AdminMainWindow
from windows.IsolatorMainWindow import IsolatorMainWindow
from models.User import UserRoles
from helper.utils import resource_path
from qdarktheme import load_palette, load_stylesheet
from helper.OcrConfig import configureTesseract
import helper.i18n as i18n

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("client")


def _excepthook(exc_type, exc_value, exc_tb):
    """PyQt6 aborts the process by default when a slot raises - log and warn instead so the app stays up."""
    log.error("Unhandled exception:\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    if QApplication.instance() is not None:
        QMessageBox.critical(
            None,
            "Unexpected Error",
            f"An unexpected error occurred and was logged:\n\n{exc_value}\n\n"
            "The application will keep running, but please save your work and consider restarting.",
        )


sys.excepthook = _excepthook

def on_login_success(user):
    """Handle a successful login by opening the role-appropriate main window.

    Connected to `LoginWindow.on_login_success`. Picks a `*MainWindow` subclass based on
    `user.getRole()`, connects its `on_logout` signal to `on_logout`, shows it maximized,
    and hides the login window.
    """
    mainWindow = None
    if user.getRole() == UserRoles.GUEST:
        mainWindow = GuestMainWindow(user)
    elif user.getRole() == UserRoles.USER:
        mainWindow = UserMainWindow(user)
    elif user.getRole() == UserRoles.COORDINATOR:
        mainWindow = CoordinatorMainWindow(user)
    elif user.getRole() == UserRoles.ISSUING:
        mainWindow = IssuingMainWindow(user)
    elif user.getRole() == UserRoles.SAFETY:
        mainWindow = SafetyMainWindow(user)
    elif user.getRole() == UserRoles.PGM:
        mainWindow = ManagerMainWindow(user, "PGM")
    elif user.getRole() == UserRoles.PDH:
        mainWindow = ManagerMainWindow(user, "PDH")
    elif user.getRole() == UserRoles.SOD:
        mainWindow = ManagerMainWindow(user, "SOD")
    elif user.getRole() == UserRoles.DFGM:
        mainWindow = ManagerMainWindow(user, "DFGM")
    elif user.getRole() == UserRoles.ADMIN:
        mainWindow = AdminMainWindow(user)
    elif user.getRole() == UserRoles.ISOLATOR:
        mainWindow = IsolatorMainWindow(user)
    else:
        mainWindow = MainWindow(user)

    if not mainWindow:
        QMessageBox.warning("Error", "Your user role is not recognized. Please contact the administrator.")
        return

    mainWindow.on_logout.connect(on_logout)
    mainWindow.showMaximized()
    loginWindow.hide()


def on_logout():
    """Handle a logout request by resetting and re-showing the login window.

    Connected to a main window's `on_logout` signal.
    """
    loginWindow.reset()
    loginWindow.show()


app = QApplication([])
app.setQuitOnLastWindowClosed(False)

configureTesseract()

_lang = QLocale.system().name()[:2]   # e.g. 'ar', 'en', 'fr'
i18n.init(_lang)
if i18n.is_rtl():
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

# app.setPalette(load_palette('dark'))
# app.setStyleSheet(load_stylesheet('dark'))
app.setApplicationName("PTW")
app.setDesktopFileName("ptw")
app.setWindowIcon(QIcon(resource_path('assets/sh-logo-trans.png')))

_pixmap = qta.icon('fa5s.check', color='white').pixmap(16, 16)
_tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
_tmp.close()
_pixmap.save(_tmp.name, 'PNG')
_checkmark_path = _tmp.name.replace('\\', '/')

app.setStyleSheet(f"""
    QRadioButton::indicator {{width: 20px; height: 20px; border: 2px solid gray; border-radius: 6px;}}
    QRadioButton::indicator:disabled  {{background-color: palette(mid);}}
    QRadioButton::indicator:checked {{background-color: palette(highlight); border-color: palette(highlight); image: url({_checkmark_path});}}
    QCheckBox::indicator {{width: 20px; height: 20px; border: 2px solid gray; border-radius: 6px;}}
    QCheckBox::indicator:disabled  {{background-color: palette(mid);}}
    QCheckBox::indicator:checked {{background-color: palette(highlight); border-color: palette(highlight); image: url({_checkmark_path});}}
""")
loginWindow = LoginWindow()
loginWindow.on_login_success.connect(on_login_success)
loginWindow.show()
app.exec()
