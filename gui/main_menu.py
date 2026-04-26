from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt

class MenuButton(QPushButton):
    """Кастомный класс кнопки для применения QSS."""
    pass

class NavButton(QPushButton):
    """Кастомный класс для стрелочек < >."""
    pass

class MainMenuWidget(QWidget):
    def __init__(self, difficulties, on_new_game, on_resume):
        super().__init__()
        self.setObjectName("MainMenuWidget")
        
        self.difficulties = list(difficulties.keys())
        self.current_diff_index = 0
        
        self.on_new_game_callback = on_new_game
        self.on_resume_callback = on_resume
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)
        
        # 1. Логотип (Используем Юникод-символ шестеренки/солнца)
        self.logo_label = QLabel("⚙") 
        self.logo_label.setObjectName("LogoLabel")
        layout.addWidget(self.logo_label)
        
        layout.addSpacing(40) # Отступ между лого и выбором сложности
        
        # 2. Выбор сложности ( <  Extreme  > )
        diff_layout = QHBoxLayout()
        
        self.btn_prev = NavButton("<")
        self.btn_prev.setFixedSize(40, 40)
        self.btn_prev.clicked.connect(self.prev_difficulty)
        
        self.diff_label = QLabel(self.difficulties[self.current_diff_index])
        self.diff_label.setObjectName("DifficultyLabel")
        self.diff_label.setFixedWidth(150)
        
        self.btn_next = NavButton(">")
        self.btn_next.setFixedSize(40, 40)
        self.btn_next.clicked.connect(self.next_difficulty)
        
        diff_layout.addWidget(self.btn_prev)
        diff_layout.addWidget(self.diff_label)
        diff_layout.addWidget(self.btn_next)
        diff_layout.setAlignment(Qt.AlignCenter)
        
        layout.addLayout(diff_layout)
        
        layout.addSpacing(20)
        
        # 3. Кнопки (New Game, Resume)
        self.btn_new_game = MenuButton("New Game")
        self.btn_new_game.setFixedWidth(250)
        self.btn_new_game.clicked.connect(self.start_new_game)
        layout.addWidget(self.btn_new_game, alignment=Qt.AlignCenter)
        
        self.btn_resume = MenuButton("Resume")
        self.btn_resume.setFixedWidth(250)
        self.btn_resume.setEnabled(False) # Изначально выключена, пока нет начатой игры
        self.btn_resume.clicked.connect(self.on_resume_callback)
        layout.addWidget(self.btn_resume, alignment=Qt.AlignCenter)
        
        self.setLayout(layout)

    def prev_difficulty(self):
        self.current_diff_index = (self.current_diff_index - 1) % len(self.difficulties)
        self.diff_label.setText(self.difficulties[self.current_diff_index])

    def next_difficulty(self):
        self.current_diff_index = (self.current_diff_index + 1) % len(self.difficulties)
        self.diff_label.setText(self.difficulties[self.current_diff_index])

    def start_new_game(self):
        diff_name = self.difficulties[self.current_diff_index]
        self.on_new_game_callback(diff_name)
