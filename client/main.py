import os, tempfile
import qtawesome as qta
from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from Login import LoginWindow

app = QApplication([])
app.setWindowIcon(QIcon('./sh-logo.png'))

_pixmap = qta.icon('fa5s.check', color='white').pixmap(16, 16)
_tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
_tmp.close()
_pixmap.save(_tmp.name, 'PNG')
_checkmark_path = _tmp.name.replace('\\', '/')

app.setStyleSheet(f"""
    QRadioButton::indicator {{width: 20px; height: 20px; border: 2px solid darkgreen; border-radius: 6px;}}
    QRadioButton::indicator:checked {{background-color: green; border-color: green; image: url({_checkmark_path});}}
    QCheckBox::indicator {{width: 20px; height: 20px; border: 2px solid darkgreen; border-radius: 6px;}}
    QCheckBox::indicator:checked {{background-color: green; border-color: green; image: url({_checkmark_path});}}
""")
loginWindow = LoginWindow()
loginWindow.show()
app.exec()
