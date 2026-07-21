import tempfile
import qtawesome as qta
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QIcon
from Login import LoginWindow
from MainWindow import MainWindow, GuestMainWindow, AdminMainWindow, UserMainWindow, CoordinatorMainWindow, IssuingMainWindow, SafetyMainWindow, ManagerMainWindow, IsolatorMainWindow
from User import UserRoles
from utils import resource_path
from qdarktheme import load_palette, load_stylesheet
import i18n
    
def on_login_success(user):
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
    loginWindow.reset()
    loginWindow.show()


app = QApplication([])

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
