import sys
import os
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow

def load_stylesheet():
    """Загружает QSS файл со стилями."""
    style_path = os.path.join(os.path.dirname(__file__), "gui", "styles", "style.qss")
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def main():
    app = QApplication(sys.argv)
    
    # Применяем кастомные стили
    app.setStyleSheet(load_stylesheet())
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()