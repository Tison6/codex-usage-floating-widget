"""
Compact Dark Glassmorphism QSS Stylesheet.
Ultra-light, non-intrusive desktop floating widget theme.
"""

MAIN_STYLESHEET = """
/* Global Widget background */
QWidget#MainWidget {
    background-color: rgba(16, 20, 30, 0.94);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
}

QWidget#MiniWidget {
    background-color: rgba(16, 20, 30, 0.92);
    border: 1px solid rgba(59, 130, 246, 0.35);
    border-radius: 16px;
}

/* Card Sections */
QFrame.CardSection {
    background-color: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
}

QFrame.CardSection:hover {
    background-color: rgba(255, 255, 255, 0.055);
    border: 1px solid rgba(59, 130, 246, 0.25);
}

/* Typography */
QLabel {
    color: #F3F4F6;
    font-family: "Segoe UI", "Microsoft YaHei UI", -apple-system, sans-serif;
}

QLabel.TitleLabel {
    font-size: 11px;
    font-weight: 700;
    color: #FFFFFF;
}

QLabel.SectionHeader {
    font-size: 10px;
    font-weight: 600;
    color: #9CA3AF;
    letter-spacing: 0.5px;
}

QLabel.DeviceName {
    font-size: 11px;
    font-weight: 500;
    color: #E5E7EB;
}

QLabel.BatteryPercent {
    font-size: 11px;
    font-weight: 700;
    font-family: "Consolas", "Segoe UI", monospace;
}

QLabel.SubText {
    font-size: 10px;
    color: #9CA3AF;
}

QLabel.BadgePlan {
    background-color: rgba(59, 130, 246, 0.2);
    color: #60A5FA;
    border: 1px solid rgba(59, 130, 246, 0.4);
    border-radius: 4px;
    padding: 1px 4px;
    font-size: 9px;
    font-weight: 700;
}

QLabel.BadgeCredits {
    background-color: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 4px;
    padding: 1px 4px;
    font-size: 9px;
    font-weight: 600;
}

/* Icon Buttons */
QPushButton.IconButton {
    background-color: transparent;
    border: none;
    border-radius: 4px;
    color: #9CA3AF;
    font-size: 10px;
    padding: 2px;
}

QPushButton.IconButton:hover {
    background-color: rgba(255, 255, 255, 0.1);
    color: #FFFFFF;
}

QPushButton.IconButton:pressed {
    background-color: rgba(255, 255, 255, 0.15);
}

/* Progress Bars */
QProgressBar {
    background-color: rgba(255, 255, 255, 0.08);
    border: none;
    border-radius: 2px;
    text-align: center;
    height: 4px;
}

QProgressBar::chunk {
    border-radius: 2px;
}

/* Tooltip & Menu */
QToolTip {
    background-color: #181E2C;
    color: #F9FAFB;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 4px;
    padding: 4px 6px;
    font-size: 10px;
}

QMenu {
    background-color: #141824;
    color: #E5E7EB;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 6px;
    padding: 3px;
}

QMenu::item {
    padding: 5px 16px 5px 10px;
    border-radius: 3px;
    font-size: 11px;
}

QMenu::item:selected {
    background-color: #3B82F6;
    color: #FFFFFF;
}

QMenu::separator {
    height: 1px;
    background: rgba(255, 255, 255, 0.08);
    margin: 3px 4px;
}
"""
