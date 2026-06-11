import tempfile
import qtawesome as qta
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from Login import LoginWindow
from utils import resource_path
from qdarktheme import load_palette, load_stylesheet

app = QApplication([])
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
    QRadioButton::indicator:checked {{background-color: palette(highlight); border-color: palette(highlight); image: url({_checkmark_path});}}
    QRadioButton::indicator:disabled  {{background-color: palette(mid);}}
    QRadioButton::indicator:checked:disabled {{border-color: gray;}}
    QCheckBox::indicator {{width: 20px; height: 20px; border: 2px solid gray; border-radius: 6px;}}
    QCheckBox::indicator:checked {{background-color: palette(highlight); border-color: palette(highlight); image: url({_checkmark_path});}}
    QCheckBox::indicator:disabled  {{background-color: palette(mid);}}
    QCheckBox::indicator:checked:disabled {{border-color: gray;}}
""")
loginWindow = LoginWindow()
loginWindow.show()
app.exec()
