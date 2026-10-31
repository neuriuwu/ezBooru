"""Dark theme stylesheet."""


def dark_stylesheet(accent: str = "#8b7bff") -> str:
    return f"""
    QWidget {{
        background-color: #17181d;
        color: #e7e7ec;
        font-family: "Segoe UI", "SF Pro Text", "Noto Sans", sans-serif;
        font-size: 13px;
    }}
    QWidget#sidebar {{
        background-color: #20222a;
        border-right: 1px solid #343641;
    }}
    QLabel#brand {{ font-size: 25px; font-weight: 700; color: #ffffff; }}
    QLabel#sidebarCaption {{
        color: #9295a3; font-size: 10px; font-weight: 700;
        letter-spacing: 1px; padding-top: 8px;
    }}
    QLineEdit, QComboBox {{
        background: #23252d;
        border: 1px solid #393b46;
        border-radius: 7px;
        padding: 8px 10px;
        selection-background-color: {accent};
    }}
    QPushButton {{
        background: #292b34;
        border: 1px solid #3c3e49;
        border-radius: 7px;
        padding: 8px 12px;
    }}
    QPushButton:hover {{ background: #353743; }}
    QPushButton:pressed {{ background: {accent}; }}
    QPushButton#primaryButton {{
        background: {accent}; color: white; border: none; font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{ background: {accent}; }}
    QPushButton#navigationButton {{ text-align: left; font-weight: 600; }}
    QListWidget {{
        background: #191a20; border: 1px solid #343641; border-radius: 7px;
        outline: none;
    }}
    QListWidget::item {{ padding: 8px; border-radius: 4px; }}
    QListWidget::item:selected {{ background: {accent}; color: white; }}
    QProgressBar {{
        background: #23252d; border: 1px solid #393b46; border-radius: 5px;
        text-align: center; min-height: 16px;
    }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{
        background: #1b1c22; width: 10px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: #484a56; border-radius: 4px; min-height: 28px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QDialog {{ background: #17181d; }}
    """
