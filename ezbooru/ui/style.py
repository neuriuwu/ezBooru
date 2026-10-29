"""Dark theme stylesheet."""


def dark_stylesheet(accent: str = "#8b7bff") -> str:
    return f"""
    QWidget {{
        background-color: #17181d;
        color: #e7e7ec;
        font-family: "Segoe UI", "Noto Sans", sans-serif;
        font-size: 13px;
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
