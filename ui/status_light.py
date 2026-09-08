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
            
            radius = (min(w, h) - 3.0) / 2.0
            rect = QRectF(-radius, -radius, radius * 2.0, radius * 2.0)
            
            # Vibrant Orange Pen
            pen = QPen()
            pen.setWidthF(1.8)
            pen.setCapStyle(Qt.RoundCap)
            pen.setColor(QColor(245, 158, 11))  # Electric Amber Orange (#F59E0B)
            painter.setPen(pen)
            
            # Draw 270-degree spinning arc
            painter.drawArc(rect, 0, 270 * 16)
            painter.restore()
            
            # Center pulsing orange dot
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(251, 146, 60, 220))  # #FB923C
            painter.drawEllipse(QRectF(cx - 1.8, cy - 1.8, 3.6, 3.6))
            
        else:
            # --- IDLE STATE: Emerald Green Glowing Dot ---
            # Outer soft glow halo
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(16, 185, 129, 50))
            painter.drawEllipse(QRectF(cx - 5.5, cy - 5.5, 11.0, 11.0))
            
            # Middle ring
            painter.setBrush(QColor(16, 185, 129, 140))
            painter.drawEllipse(QRectF(cx - 3.8, cy - 3.8, 7.6, 7.6))
            
            # Inner solid core
            painter.setBrush(QColor(16, 185, 129, 255))
            painter.drawEllipse(QRectF(cx - 2.8, cy - 2.8, 5.6, 5.6))
            
            # White shine glint
            painter.setBrush(QColor(255, 255, 255, 200))
            painter.drawEllipse(QRectF(cx - 1.2, cy - 1.8, 1.8, 1.8))
            
        painter.end()
