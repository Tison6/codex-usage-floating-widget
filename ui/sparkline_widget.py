"""
7-Day Quota Burn Sparkline Widget with Full Coordinate Grid.
Draws 7-day vertical lines (1d~7d), 10% horizontal grid lines,
the ideal linear pace baseline (dashed line from 100% to 0%),
and the actual quota consumption curve with gradient fill and current-point glow.
"""

from typing import Dict, Any, List, Tuple
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath, QFont
)
from PyQt5.QtCore import Qt, QPointF, QRectF


class QuotaSparklineWidget(QWidget):
    """Mini 7-Day Quota Burn Chart with Full Coordinate Grid."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setMinimumWidth(180)
        self.analysis_data: Dict[str, Any] = {}
        self.setAttribute(Qt.WA_Hover, True)

    def set_analysis_data(self, data: Dict[str, Any]):
        """Update chart data and trigger repaint."""
        self.analysis_data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = float(self.width())
        h = float(self.height())
        
        # Margins for coordinate axes & day numbers
        pad_l = 10.0
        pad_r = 10.0
        pad_t = 6.0
        pad_b = 15.0  # Bottom label space
        
        chart_w = w - pad_l - pad_r
        chart_h = h - pad_t - pad_b
        
        if chart_w <= 10 or chart_h <= 10:
            return

        # 1. Background Card Box
        bg_rect = QRectF(0, 0, w, h)
        painter.setBrush(QColor(13, 17, 23, 200))
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))
        painter.drawRoundedRect(bg_rect, 6, 6)

        # 2. Coordinate Grid Frame (外坐标框)
        chart_rect = QRectF(pad_l, pad_t, chart_w, chart_h)
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        painter.drawRect(chart_rect)

        # 3. Y-Axis Horizontal Grid (每 10% 横线)
        for i in range(1, 10):
            y_i = pad_t + (chart_h * (i / 10.0))
            if i == 5:  # 50% line slightly clearer
                grid_pen = QPen(QColor(255, 255, 255, 25), 1, Qt.DashLine)
            else:
                grid_pen = QPen(QColor(255, 255, 255, 12), 1, Qt.DotLine)
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(pad_l, y_i), QPointF(pad_l + chart_w, y_i))

        # 4. X-Axis Vertical Grid (第1天到第7天 7等分竖线)
        for d in range(1, 7):
            x_d = pad_l + (chart_w * (d / 7.0))
            v_pen = QPen(QColor(255, 255, 255, 15), 1, Qt.DotLine)
            painter.setPen(v_pen)
            painter.drawLine(QPointF(x_d, pad_t), QPointF(x_d, pad_t + chart_h))

        # 5. Ideal Baseline (副对角线虚线: (0, 100%) -> (7d, 0%))
        ideal_pen = QPen(QColor(156, 163, 175, 140), 1.2, Qt.DashLine)
        painter.setPen(ideal_pen)
        p_ideal_start = QPointF(pad_l, pad_t)
        p_ideal_end = QPointF(pad_l + chart_w, pad_t + chart_h)
        painter.drawLine(p_ideal_start, p_ideal_end)

        # 6. Actual Usage Curve
        curve_points: List[Tuple[float, float]] = self.analysis_data.get("curve_points", [])
        if curve_points:
            pixel_points = []
            for t_norm, r_norm in curve_points:
                px = pad_l + (t_norm * chart_w)
                py = pad_t + ((100.0 - r_norm) / 100.0 * chart_h)
                pixel_points.append(QPointF(px, py))

            if len(pixel_points) >= 2:
                # Gradient fill under curve
                fill_path = QPainterPath()
                fill_path.moveTo(pixel_points[0].x(), pad_t + chart_h)
                for pt in pixel_points:
                    fill_path.lineTo(pt)
                fill_path.lineTo(pixel_points[-1].x(), pad_t + chart_h)
                fill_path.closeSubpath()

                gradient = QLinearGradient(0, pad_t, 0, pad_t + chart_h)
                gradient.setColorAt(0.0, QColor(59, 130, 246, 110))
                gradient.setColorAt(1.0, QColor(59, 130, 246, 10))
                painter.fillPath(fill_path, QBrush(gradient))

                # Smooth stroke line
                stroke_pen = QPen(QColor(96, 165, 250), 1.8)
                stroke_pen.setCapStyle(Qt.RoundCap)
                stroke_pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(stroke_pen)
                
                stroke_path = QPainterPath()
                stroke_path.moveTo(pixel_points[0])
                for pt in pixel_points[1:]:
                    stroke_path.lineTo(pt)
                painter.drawPath(stroke_path)

                # Current position glow point
                last_pt = pixel_points[-1]
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(59, 130, 246, 90))
                painter.drawEllipse(last_pt, 5.0, 5.0)
                painter.setBrush(QColor(255, 255, 255))
                painter.drawEllipse(last_pt, 2.2, 2.2)

        # 7. Bottom Day Ticks (1d, 2d, 3d, 4d, 5d, 6d, 7d)
        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        painter.setPen(QColor(156, 163, 175, 160))
        
        y_text = h - 3.0
        painter.drawText(QPointF(pad_l - 2.0, y_text), "1d")
        painter.drawText(QPointF(pad_l + (chart_w * 0.28) - 4.0, y_text), "3d")
        painter.drawText(QPointF(pad_l + (chart_w * 0.57) - 4.0, y_text), "5d")
        painter.drawText(QPointF(pad_l + chart_w - 10.0, y_text), "7d")

        painter.end()
