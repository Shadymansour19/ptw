from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from Login import LoginWindow

app = QApplication([])
app.setWindowIcon(QIcon('./sh-logo.png'))
loginWindow = LoginWindow()
loginWindow.show()
app.exec()
