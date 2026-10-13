"""
Compact Dark Glassmorphism QSS Stylesheet.
Ultra-light, non-intrusive desktop floating widget theme.
Supports dynamic proportional font-size scaling based on UI scale factor.
"""

def get_main_stylesheet(scale: float = 1.0) -> str:
    """Return dark theme QSS stylesheet scaled by the given factor."""
    s = max(0.5, float(scale))
    
    def px(base: int, min_val: int = 6) -> int:
        return max(min_val, int(round(base * s + 1e-5)))

    return f"""
/* Global Widget background */
QWidget#MainWidget {{
    background-color: rgba(16, 20, 30, 0.94);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: {px(12, 8)}px;
}}

QWidget#MiniWidget {{
    background-color: rgba(16, 20, 30, 0.92);
    border: 1px solid rgba(59, 130, 246, 0.35);
    border-radius: {px(12, 8)}px;
}}

/* Card Sections */
QFrame.CardSection {{
    background-color: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: {px(8, 6)}px;
}}

QFrame.CardSection:hover {{
    background-color: rgba(255, 255, 255, 0.055);
    border: 1px solid rgba(59, 130, 246, 0.25);
}}

/* Typography */
QLabel {{
    color: #F3F4F6;
    font-family: "Segoe UI", "Microsoft YaHei UI", -apple-system, sans-serif;
}}

QLabel.TitleLabel {{
    font-size: {px(11, 8)}px;
    font-weight: 700;
    color: #FFFFFF;
}}

QLabel.SectionHeader {{
    font-size: {px(10, 7)}px;
    font-weight: 600;
    color: #9CA3AF;
    letter-spacing: 0.5px;
}}

QLabel.DeviceName {{
    font-size: {px(11, 8)}px;
    font-weight: 500;
    color: #E5E7EB;
}}

QLabel.BatteryPercent {{
    font-size: {px(11, 8)}px;
    font-weight: 700;
    font-family: "Consolas", "Segoe UI", monospace;
}}

QLabel.SubText {{
    font-size: {px(10, 7)}px;
    color: #9CA3AF;
}}

QLabel.BadgePlan {{
    background-color: rgba(59, 130, 246, 0.2);
    color: #60A5FA;
    border: 1px solid rgba(59, 130, 246, 0.4);
    border-radius: {px(4, 3)}px;
    padding: 1px {px(4, 2)}px;
    font-size: {px(9, 7)}px;
    font-weight: 700;
}}

QLabel.BadgeCredits {{
    background-color: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: {px(4, 3)}px;
    padding: 1px {px(4, 2)}px;
    font-size: {px(9, 7)}px;
    font-weight: 600;
}}

/* Icon Buttons */
QPushButton.IconButton {{
    background-color: transparent;
    border: none;
    border-radius: {px(4, 3)}px;
    color: #9CA3AF;
    font-size: {px(10, 7)}px;
    padding: 2px;
}}

QPushButton.IconButton:hover {{
    background-color: rgba(255, 255, 255, 0.1);
    color: #FFFFFF;
}}

QPushButton.IconButton:pressed {{
    background-color: rgba(255, 255, 255, 0.15);
}}

/* Progress Bars */
QProgressBar {{
    background-color: rgba(255, 255, 255, 0.08);
    border: none;
    border-radius: 2px;
    text-align: center;
    height: {px(4, 3)}px;
}}

QProgressBar::chunk {{
    border-radius: 2px;
}}

/* Scroll Areas */
QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

/* Tooltip & Menu */
QToolTip {{
    background-color: #181E2C;
    color: #F9FAFB;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: {px(4, 3)}px;
    padding: {px(4, 2)}px {px(6, 4)}px;
    font-size: {px(10, 7)}px;
}}

QMenu {{
    background-color: #141824;
    color: #E5E7EB;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: {px(6, 4)}px;
    padding: 3px;
}}

QMenu::item {{
    padding: {px(5, 3)}px {px(16, 10)}px {px(5, 3)}px {px(10, 6)}px;
    border-radius: 3px;
    font-size: {px(11, 8)}px;
}}

QMenu::item:selected {{
    background-color: #3B82F6;
    color: #FFFFFF;
}}

QMenu::separator {{
    height: 1px;
    background: rgba(255, 255, 255, 0.08);
    margin: 3px 4px;
}}
"""

MAIN_STYLESHEET = get_main_stylesheet(1.0)
