"""
ChatGPT / Codex Working Status Light Component.
Renders an emerald green glowing dot when idle and a smooth rotating electric orange spinner when active.
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush
from PyQt5.QtCore import Qt, QTimer, QRectF


class CodexStatusLight(QWidget):
    """Sleek status indicator: Green dot for Idle, Rotating Electric Orange Arc for Running."""
    
    def __init__(self, parent=None, size: int = 14):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self._is_running = False
        self._angle = 0
        
        # Animation timer for rotation
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(35)  # ~28 FPS
        self._anim_timer.timeout.connect(self._on_anim_frame)
        
        self.setToolTip("ChatGPT Codex: 空闲 (就绪)")
        self.setAttribute(Qt.WA_Hover, True)

    def set_size(self, size: int):
        """Update indicator size dynamically."""
        self._size = size
        self.setFixedSize(size, size)
        self.update()

    def set_running_state(self, running: bool):
        """Update state to either Running (orange spinning) or Idle (green dot)."""
        if self._is_running == running:
            return
            
        self._is_running = running
        if running:
            self.setToolTip("ChatGPT Codex: 运行中 (请求处理中)...")
            self._anim_timer.start()
        else:
            self.setToolTip("ChatGPT Codex: 空闲 (就绪)")
            self._anim_timer.stop()
            self._angle = 0
            
        self.update()

    def is_running(self) -> bool:
        return self._is_running

    def _on_anim_frame(self):
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        
        if self._is_running:
            # --- RUNNING STATE: Rotating Electric Orange Arc Spinner ---
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(self._angle)
            
            radius = (min(w, h) - 2.5) / 2.0
            rect = QRectF(-radius, -radius, radius * 2.0, radius * 2.0)
            
            # Subtle track ring for high contrast
            track_pen = QPen(QColor(245, 158, 11, 45), 1.6)
            painter.setPen(track_pen)
            painter.drawEllipse(rect)
            
            # Vibrant Orange Spinner Arc
            pen = QPen()
            pen.setWidthF(2.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setColor(QColor(245, 158, 11))  # Electric Amber Orange (#F59E0B)
            painter.setPen(pen)
            
            # Draw 270-degree spinning arc
            painter.drawArc(rect, 0, 270 * 16)
            painter.restore()
            
            # Center bright glowing orange dot
            dot_r = max(1.5, radius * 0.36)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(251, 146, 60, 240))  # #FB923C
            painter.drawEllipse(QRectF(cx - dot_r, cy - dot_r, dot_r * 2.0, dot_r * 2.0))
            
        else:
            # --- IDLE STATE: Emerald Green Glowing Dot ---
            r = min(w, h) / 2.0
            # Outer soft glow halo
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(16, 185, 129, 50))
            painter.drawEllipse(QRectF(cx - r * 0.9, cy - r * 0.9, r * 1.8, r * 1.8))
            
            # Middle ring
            painter.setBrush(QColor(16, 185, 129, 140))
            painter.drawEllipse(QRectF(cx - r * 0.65, cy - r * 0.65, r * 1.3, r * 1.3))
            
            # Inner solid core
            painter.setBrush(QColor(16, 185, 129, 255))
            painter.drawEllipse(QRectF(cx - r * 0.45, cy - r * 0.45, r * 0.9, r * 0.9))
            
            # White shine glint
            glint_r = max(0.8, r * 0.16)
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawEllipse(QRectF(cx - glint_r * 1.2, cy - r * 0.28, glint_r * 2.0, glint_r * 2.0))
            
        painter.end()
