import sys
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Настройка стиля по умолчанию для лучшего отображения на всех ОС
    app.setStyle("Fusion") 
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
