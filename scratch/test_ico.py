from pathlib import Path
from PySide6.QtGui import QIcon, QGuiApplication
import sys
app = QGuiApplication(sys.argv)
ico_path = Path('assets/icons/app_icon.ico')
icon = QIcon(str(ico_path))
print('ICO isNull:', icon.isNull(), 'Available sizes:', [f'{s.width()}x{s.height()}' for s in icon.availableSizes()])
