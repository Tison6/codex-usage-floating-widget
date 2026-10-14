"""
GPU Server View Component.
Redesigned with unified Dark Glassmorphism aesthetic matching the left column.
Displays 5 GPUs (8号 A100 x2, 7号 L40S x3) in a sleek vertical stack and native history timeline.
"""

from typing import Dict, Any, List, Optional
import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QProgressBar, QComboBox, QStackedWidget
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont

from core.gpu_monitor import (
    GPUMonitor, get_hex_for_gpu_vram, clean_gpu_name, get_cn_name
)
from ui.icons import get_nvidia_pixmap


class GPUCardRow(QFrame):
    """Sleek dark card for a single GPU card matching the left Bluetooth/Codex aesthetic."""
    def __init__(self, sid: str, model: str, index: str, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.sid = sid
        self.model = model
        self.index = index
        self.scale = max(0.5, float(scale))
        self._last_cdata: Optional[Dict[str, Any]] = None

        self.setObjectName("GPUCardRow")
        self.setStyleSheet("""
            QFrame#GPUCardRow {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 5px;
            }
            QFrame#GPUCardRow:hover {
                background-color: rgba(255, 255, 255, 0.065);
                border: 1px solid rgba(118, 185, 0, 0.35);
            }
        """)

        layout = QVBoxLayout(self)
        pad_h = max(3, int(round(5 * self.scale)))
        pad_v = max(2, int(round(3 * self.scale)))
        layout.setContentsMargins(pad_h, pad_v, pad_h, pad_v)
        layout.setSpacing(max(1, int(round(2 * self.scale))))

        # 1. Top Row: Title badge & User / Idle status
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(max(1, int(round(2 * self.scale))))

        title_fs = max(7, int(round(9.5 * self.scale)))
        sub_fs = max(6, int(round(8.5 * self.scale)))

        self.lbl_title = QLabel(f"{sid}号 · {model} [{index}]", self)
        self.lbl_title.setStyleSheet(f"""
            color: #E2E8F0;
            font-size: {title_fs}px;
            font-weight: 700;
        """)

        self.lbl_user = QLabel("🟢 空闲", self)
        self.lbl_user.setStyleSheet(f"""
            color: #10B981;
            font-size: {sub_fs}px;
            font-weight: 700;
        """)

        top_row.addWidget(self.lbl_title)
        top_row.addStretch()
        top_row.addWidget(self.lbl_user)
        layout.addLayout(top_row)

        # 2. VRAM Progress Bar
        self.prog_bar = QProgressBar(self)
        self.prog_bar.setFixedHeight(max(2, int(round(3 * self.scale))))
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background-color: #10B981;
                border-radius: 1px;
            }
        """)
        layout.addWidget(self.prog_bar)

        # 3. Bottom Stats Row: Memory, Power, Utilization
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(max(1, int(round(2 * self.scale))))

        self.lbl_mem = QLabel("🧠 0.0 / 0G (0%)", self)
        self.lbl_mem.setStyleSheet("font-size: 8px; color: #CBD5E1; font-family: 'Consolas', monospace;")
        self.lbl_mem.setToolTip("显存占用")

        self.lbl_power = QLabel("⚡ 0/0W", self)
        self.lbl_power.setStyleSheet("font-size: 8px; color: #94A3B8; font-family: 'Consolas', monospace;")
        self.lbl_power.setToolTip("功耗 / 额定")

        self.lbl_util = QLabel("⚙️ 0%", self)
        self.lbl_util.setStyleSheet("font-size: 8px; color: #94A3B8; font-family: 'Consolas', monospace;")
        self.lbl_util.setToolTip("利用率")

        self._apply_scale_styles()
        stats_row.addWidget(self.lbl_mem)
        stats_row.addStretch()
        stats_row.addWidget(self.lbl_power)
        stats_row.addWidget(self.lbl_util)
        layout.addLayout(stats_row)

    def set_scale(self, scale: float):
        """Update scale and reapply styles."""
        self.scale = max(0.5, float(scale))
        self._apply_scale_styles()
        if self._last_cdata:
            self.update_data(self._last_cdata, self.model)

    def _apply_scale_styles(self):
        title_fs = max(7, int(round(9.5 * self.scale)))
        sub_fs = max(6, int(round(8.5 * self.scale)))
        pbar_h = max(2, int(round(3 * self.scale)))
        self.prog_bar.setFixedHeight(pbar_h)
        self.lbl_title.setStyleSheet(f"color: #E2E8F0; font-size: {title_fs}px; font-weight: 700;")
        self.lbl_mem.setStyleSheet(f"font-size: {sub_fs}px; color: #CBD5E1; font-family: 'Consolas', monospace;")
        self.lbl_power.setStyleSheet(f"font-size: {sub_fs}px; color: #94A3B8; font-family: 'Consolas', monospace;")
        self.lbl_util.setStyleSheet(f"font-size: {sub_fs}px; color: #94A3B8; font-family: 'Consolas', monospace;")

    def update_data(self, cdata: Dict[str, Any], model_name: str):
        """Update GPU metrics."""
        self._last_cdata = cdata
        self.model = model_name
        self.lbl_title.setText(f"{self.sid}号 · {model_name} [{self.index}]")

        is_busy = cdata.get("is_busy", False)
        display_user = cdata.get("display_user", "Idle")
        sub_fs = max(6, int(round(8.5 * self.scale)))

        if is_busy:
            self.lbl_user.setText(f"👤 {display_user}")
            self.lbl_user.setStyleSheet(f"""
                background-color: rgba(239, 68, 68, 0.18);
                color: #F87171;
                border: 1px solid rgba(239, 68, 68, 0.35);
                border-radius: 3px;
                padding: 0px 4px;
                font-size: {sub_fs}px;
                font-weight: 700;
            """)
        else:
            self.lbl_user.setText("🟢 空闲")
            self.lbl_user.setStyleSheet(f"""
                color: #10B981;
                font-size: {sub_fs}px;
                font-weight: 700;
                background: transparent;
                border: none;
            """)

        vram_pct = cdata.get("vram_pct", 0.0)
        self.prog_bar.setValue(int(round(vram_pct)))
        chunk_col = get_hex_for_gpu_vram(vram_pct)
        self.prog_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_col};
                border-radius: 1px;
            }}
        """)

        mem_u = cdata.get("memory_used_gb", 0.0)
        mem_t = cdata.get("memory_total_gb", 0.0)
        self.lbl_mem.setText(f"🧠 {mem_u:.1f}/{int(mem_t)}G ({vram_pct:.0f}%)")
        self.lbl_mem.setToolTip(f"显存: {cdata.get('memory_used', 0)} / {cdata.get('memory_total', 0)} MB")

        p_draw = cdata.get("power_draw", "0")
        p_lim = cdata.get("power_limit", "0")
        self.lbl_power.setText(f"⚡ {p_draw}/{p_lim}W")

        util = cdata.get("utilization", 0)
        self.lbl_util.setText(f"⚙️ {util}%")


class ServerHostCard(QFrame):
    """
    Compact card showing a server's host metrics:
    Line 1: Server name (left) | CPU utilization with color threshold (right)
    Line 2: 🧠 RAM used/total (%) (left) | 💾 Disk free space (right)
    """
    def __init__(self, sid: str, name: str, s_type: str = "gpu", parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.sid = sid
        self.display_name = name
        self.s_type = s_type
        self.scale = max(0.5, float(scale))

        self.setObjectName("ServerHostCard")
        self.setStyleSheet("""
            QFrame#ServerHostCard {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 4px;
            }
            QFrame#ServerHostCard:hover {
                background-color: rgba(255, 255, 255, 0.065);
                border-color: rgba(255, 255, 255, 0.12);
            }
        """)

        pad_v = max(2, int(round(3 * self.scale)))
        pad_h = max(4, int(round(5 * self.scale)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad_h, pad_v, pad_h, pad_v)
        layout.setSpacing(max(1, int(round(2 * self.scale))))

        # Row 1: Name & CPU
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(3)

        self.lbl_name = QLabel(self.display_name, self)
        name_fs = max(7, int(round(9.5 * self.scale)))
        self.lbl_name.setStyleSheet(f"font-size: {name_fs}px; font-weight: 700; color: #E2E8F0; background: transparent; border: none;")

        self.lbl_cpu = QLabel("CPU: --", self)
        cpu_fs = max(7, int(round(9.0 * self.scale)))
        self.lbl_cpu.setStyleSheet(f"font-size: {cpu_fs}px; font-weight: 700; color: #64748B; background: transparent; border: none;")

        row1.addWidget(self.lbl_name)
        row1.addStretch()
        row1.addWidget(self.lbl_cpu)
        layout.addLayout(row1)

        # Row 2: RAM & Disk
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(3)

        sub_fs = max(6, int(round(8.0 * self.scale)))
        self.lbl_ram = QLabel("🧠 --/--G (--%)", self)
        self.lbl_ram.setStyleSheet(f"font-size: {sub_fs}px; color: #94A3B8; background: transparent; border: none;")

        self.lbl_disk = QLabel("💾 -- 剩余", self)
        self.lbl_disk.setStyleSheet(f"font-size: {sub_fs}px; color: #CBD5E1; background: transparent; border: none;")

        row2.addWidget(self.lbl_ram)
        row2.addStretch()
        row2.addWidget(self.lbl_disk)
        layout.addLayout(row2)

    def set_scale(self, scale: float):
        self.scale = max(0.5, float(scale))
        pad_v = max(2, int(round(3 * self.scale)))
        pad_h = max(4, int(round(5 * self.scale)))
        self.layout().setContentsMargins(pad_h, pad_v, pad_h, pad_v)
        self.layout().setSpacing(max(1, int(round(2 * self.scale))))
        name_fs = max(7, int(round(9.5 * self.scale)))
        self.lbl_name.setStyleSheet(f"font-size: {name_fs}px; font-weight: 700; color: #E2E8F0; background: transparent; border: none;")
        cpu_fs = max(7, int(round(9.0 * self.scale)))
        cur_style = self.lbl_cpu.styleSheet()
        col_pos = cur_style.find("color:")
        col_str = cur_style[col_pos:] if col_pos != -1 else "color: #64748B;"
        self.lbl_cpu.setStyleSheet(f"font-size: {cpu_fs}px; font-weight: 700; background: transparent; border: none; {col_str}")
        sub_fs = max(6, int(round(8.0 * self.scale)))
        self.lbl_ram.setStyleSheet(f"font-size: {sub_fs}px; color: #94A3B8; background: transparent; border: none;")
        self.lbl_disk.setStyleSheet(f"font-size: {sub_fs}px; color: #CBD5E1; background: transparent; border: none;")

    def update_stats(self, cpu: float, mem_used: float, mem_total: float, mem_pct: float, disk_free: float):
        if cpu < 0:
            c_color = "#64748B"
            c_text = "CPU: 离线"
        elif cpu < 10:
            c_color = "#10B981"
            c_text = f"CPU: {int(round(cpu))}%"
        elif cpu < 30:
            c_color = "#F59E0B"
            c_text = f"CPU: {int(round(cpu))}%"
        else:
            c_color = "#EF4444"
            c_text = f"CPU: {int(round(cpu))}%"

        cpu_fs = max(7, int(round(9.0 * self.scale)))
        self.lbl_cpu.setText(c_text)
        self.lbl_cpu.setStyleSheet(f"font-size: {cpu_fs}px; font-weight: 700; color: {c_color}; background: transparent; border: none;")

        if mem_total > 0:
            self.lbl_ram.setText(f"🧠 {mem_used:.1f}/{mem_total:.0f}G ({int(round(mem_pct))}%)")
        else:
            self.lbl_ram.setText("🧠 --/--G (--%)")

        if disk_free > 0:
            self.lbl_disk.setText(f"💾 {disk_free:.1f}G 剩余")
        else:
            self.lbl_disk.setText("💾 -- 剩余")


class GanttLabelsWidget(QWidget):
    """Pinned left column showing GPU card labels for the history Gantt timeline."""
    DEFAULT_TASKS = [
        "L40S [0]",
        "L40S [1]",
        "L40S [2]",
        "A100 [0]",
        "A100 [1]",
    ]

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.scale = max(0.5, float(scale))
        self.tasks: List[str] = list(self.DEFAULT_TASKS)
        self._target_scroll_area: Optional[QScrollArea] = None
        self.setStyleSheet("background-color: rgba(15, 23, 42, 0.6); border-top-left-radius: 4px; border-bottom-left-radius: 4px;")
        self._recalc_size()

    def set_target_scroll_area(self, scroll_area: QScrollArea):
        self._target_scroll_area = scroll_area

    def _recalc_size(self):
        row_h = max(15, int(round(19 * self.scale)))
        header_h = max(12, int(round(15 * self.scale)))
        needed_h = max(95, len(self.tasks) * row_h + header_h + 6)
        label_w = max(52, int(round(62 * self.scale)))
        self.setFixedSize(label_w, needed_h + 8)

    def set_scale(self, scale: float):
        self.scale = max(0.5, float(scale))
        self._recalc_size()
        self.update()

    def set_tasks(self, tasks: List[str]):
        self.tasks = tasks
        self._recalc_size()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        row_h = max(15, int(round(19 * self.scale)))
        header_h = max(12, int(round(15 * self.scale)))
        w = self.width()

        for r_idx, task_name in enumerate(self.tasks):
            y = header_h + r_idx * row_h
            if r_idx % 2 == 1:
                painter.fillRect(0, y, w, row_h, QColor(255, 255, 255, 4))

            # Subtle baseline separator
            painter.setPen(QPen(QColor(255, 255, 255, 10), 1))
            painter.drawLine(0, y + row_h, w, y + row_h)

            painter.setPen(QColor("#CBD5E1"))
            painter.setFont(QFont("Segoe UI", max(5, int(round(7.5 * self.scale))), QFont.Bold))
            painter.drawText(2, y + 1, w - 4, row_h - 2, Qt.AlignVCenter | Qt.AlignLeft, task_name)

    def wheelEvent(self, event):
        if self._target_scroll_area:
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta != 0:
                sb = self._target_scroll_area.horizontalScrollBar()
                if sb:
                    sb.setValue(sb.value() - delta // 2)
                    event.accept()
                    return
        super().wheelEvent(event)


class GanttTimelineCanvas(QWidget):
    """Native PyQt5 Gantt Chart Canvas for 7号 (L40S) & 8号 (A100) server GPU history timeline."""
    DEFAULT_TASKS = [
        "L40S [0]",
        "L40S [1]",
        "L40S [2]",
        "A100 [0]",
        "A100 [1]",
    ]

    def __init__(self, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.scale = max(0.5, float(scale))
        self.intervals: List[Dict[str, Any]] = []
        self.days: int = 1
        self.tasks: List[str] = list(self.DEFAULT_TASKS)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: rgba(15, 23, 42, 0.6); border-top-right-radius: 4px; border-bottom-right-radius: 4px;")

        self.user_palette = [
            "#3B82F6", "#10B981", "#F59E0B", "#EC4899",
            "#8B5CF6", "#06B6D4", "#E11D48", "#14B8A6"
        ]
        self.user_color_map: Dict[str, str] = {}
        self._recalc_size()

    def _recalc_size(self):
        row_h = max(15, int(round(19 * self.scale)))
        header_h = max(12, int(round(15 * self.scale)))
        needed_h = max(95, len(self.tasks) * row_h + header_h + 6)
        self.setFixedHeight(needed_h)
        base_w = 260 + self.days * 85
        needed_w = max(int(round(300 * self.scale)), int(round(base_w * self.scale)))
        self.setMinimumWidth(needed_w)

    def set_scale(self, scale: float):
        """Update scale and recalculate row heights and minimum width."""
        self.scale = max(0.5, float(scale))
        self._recalc_size()
        self.update()

    def set_data(self, intervals: List[Dict[str, Any]], days: int = 1):
        import re
        filtered = []
        for x in intervals:
            if x.get("sid") in ("7", "8"):
                clean_t = re.sub(r'^\d+号\s*', '', x.get("task", "")).strip()
                x["task"] = clean_t
                filtered.append(x)
        self.intervals = filtered
        self.days = days

        tasks = list(self.DEFAULT_TASKS)
        for x in self.intervals:
            t = x.get("task", "")
            if t and t not in tasks:
                tasks.append(t)
        self.tasks = tasks

        self._recalc_size()
        self.update()

    def _get_user_color(self, username: str) -> str:
        if username not in self.user_color_map:
            idx = len(self.user_color_map) % len(self.user_palette)
            self.user_color_map[username] = self.user_palette[idx]
        return self.user_color_map[username]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = max(self.width(), self.minimumWidth())
        h = self.height()

        now = datetime.datetime.now()
        start_time = now - datetime.timedelta(days=self.days)
        total_seconds = (now - start_time).total_seconds()
        if total_seconds <= 0:
            return

        tasks = getattr(self, "tasks", self.DEFAULT_TASKS)
        row_h = max(15, int(round(19 * self.scale)))
        header_h = max(12, int(round(15 * self.scale)))
        chart_w = max(40.0, float(w - 6))

        # 1. Draw time header ticks
        painter.setPen(QColor("#64748B"))
        painter.setFont(QFont("Segoe UI", max(5, int(round(7 * self.scale)))))
        num_ticks = 4 if self.days == 1 else (6 if self.days == 3 else 7)
        for i in range(num_ticks + 1):
            t_frac = i / num_ticks
            tick_time = start_time + datetime.timedelta(seconds=total_seconds * t_frac)
            x = chart_w * t_frac
            time_str = tick_time.strftime("%m-%d %H:%M" if self.days > 1 else "%H:%M")
            if i == 0:
                painter.drawText(int(x), 1, 45, 12, Qt.AlignLeft | Qt.AlignVCenter, time_str)
            elif i == num_ticks:
                painter.drawText(int(x - 45), 1, 45, 12, Qt.AlignRight | Qt.AlignVCenter, "现在" if self.days == 1 else time_str)
            else:
                painter.drawText(int(x - 25), 1, 50, 12, Qt.AlignCenter | Qt.AlignVCenter, time_str)

            painter.setPen(QPen(QColor(255, 255, 255, 12), 1, Qt.DashLine))
            painter.drawLine(int(x), header_h, int(x), h - 2)
            painter.setPen(QColor("#64748B"))

        # 2. Draw alternating row background lines
        for r_idx, task_name in enumerate(tasks):
            y = header_h + r_idx * row_h
            if r_idx % 2 == 1:
                painter.fillRect(0, y, int(chart_w), row_h, QColor(255, 255, 255, 4))
            painter.setPen(QPen(QColor(255, 255, 255, 8), 1))
            painter.drawLine(0, y + row_h, int(chart_w), y + row_h)

        # 3. Draw intervals
        if not self.intervals:
            painter.setPen(QColor("#475569"))
            painter.setFont(QFont("Segoe UI", max(6, int(round(8 * self.scale)))))
            painter.drawText(0, header_h, int(chart_w), h - header_h, Qt.AlignCenter, "区间内暂无任务占用")
            return

        for itv in self.intervals:
            task_name = itv["task"]
            if task_name not in tasks:
                continue
            r_idx = tasks.index(task_name)
            y = header_h + r_idx * row_h + 2

            itv_start = max(start_time, itv["start_dt"])
            itv_finish = min(now, itv["finish_dt"])
            if itv_finish <= itv_start:
                continue

            sec_start = (itv_start - start_time).total_seconds()
            sec_end = (itv_finish - start_time).total_seconds()

            x1 = (sec_start / total_seconds) * chart_w
            x2 = (sec_end / total_seconds) * chart_w
            bar_w = max(4.0, x2 - x1)

            user_color = QColor(self._get_user_color(itv["user"]))
            painter.setBrush(QBrush(user_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(x1, y, bar_w, row_h - 4), 3, 3)

            if bar_w > 24:
                painter.setPen(QColor("#FFFFFF"))
                painter.setFont(QFont("Segoe UI", max(5, int(round(7 * self.scale))), QFont.Bold))
                painter.drawText(QRectF(x1 + 1, y, bar_w - 2, row_h - 4), Qt.AlignCenter, itv["user"])

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta != 0:
            parent = self.parent()
            while parent and not isinstance(parent, QScrollArea):
                parent = parent.parent()
            if parent and isinstance(parent, QScrollArea):
                sb = parent.horizontalScrollBar()
                if sb:
                    sb.setValue(sb.value() - delta // 2)
                    event.accept()
                    return
        super().wheelEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        w = max(self.width(), self.minimumWidth())
        now = datetime.datetime.now()
        start_time = now - datetime.timedelta(days=self.days)
        total_seconds = (now - start_time).total_seconds()
        if total_seconds <= 0 or not self.intervals:
            super().mouseMoveEvent(event)
            return

        chart_w = max(40.0, float(w - 6))
        header_h = max(12, int(round(15 * self.scale)))
        row_h = max(15, int(round(19 * self.scale)))

        found_tip = None
        for itv in self.intervals:
            task_name = itv["task"]
            if task_name not in self.tasks:
                continue
            r_idx = self.tasks.index(task_name)
            y = header_h + r_idx * row_h + 2

            itv_start = max(start_time, itv["start_dt"])
            itv_finish = min(now, itv["finish_dt"])
            if itv_finish <= itv_start:
                continue

            sec_start = (itv_start - start_time).total_seconds()
            sec_end = (itv_finish - start_time).total_seconds()
            x1 = (sec_start / total_seconds) * chart_w
            x2 = (sec_end / total_seconds) * chart_w
            bar_w = max(4.0, x2 - x1)

            rect = QRectF(x1, y, bar_w, row_h - 4)
            if rect.contains(pos):
                found_tip = f"{itv['task']} · {itv['user']}\n时段: {itv['start']} ~ {itv['finish']}\n时长: {itv['duration_min']} 分钟"
                break

        if found_tip:
            self.setToolTip(found_tip)
        else:
            self.setToolTip("")
        super().mouseMoveEvent(event)


class GPUServerView(QWidget):
    """
    Complete GPU Server Monitoring View.
    Unified dark glassmorphism styling, single vertical stack of 5 GPUs (8号 x2, 7号 x3).
    Supports dynamic proportional font and dimension scaling.
    """
    refresh_requested = pyqtSignal()

    def __init__(self, monitor: GPUMonitor, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self.monitor = monitor
        self.scale = max(0.5, float(scale))

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 1, 2, 2)
        root.setSpacing(max(2, int(round(3 * self.scale))))

        # 1. Header Bar: Title with NVIDIA logo, Refresh, Timestamp, DB badge
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(max(2, int(round(4 * self.scale))))

        icon_sz = max(9, int(round(13 * self.scale)))
        self.title_icon = QLabel(self)
        self.title_icon.setPixmap(get_nvidia_pixmap(icon_sz))

        title_fs = max(8, int(round(10.5 * self.scale)))
        self.title_lbl = QLabel("GPU 服务器", self)
        self.title_lbl.setStyleSheet(f"font-size: {title_fs}px; font-weight: 800; color: #FFFFFF;")

        btn_sz = max(14, int(round(18 * self.scale)))
        self.btn_refresh = QPushButton("🔄", self)
        self.btn_refresh.setFixedSize(btn_sz, btn_sz)
        self.btn_refresh.setToolTip("点击刷新 GPU 实时状态")
        self.btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 3px;
                font-size: {max(7, int(round(9.5 * self.scale)))}px;
            }}
            QPushButton:hover {{
                background-color: #0284C7;
                color: #FFFFFF;
                border-color: #0284C7;
            }}
        """)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)

        self.badge_time = QLabel("🕒 --:--:--", self)
        self.badge_time.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.05);
            color: #94A3B8;
            padding: 1px 3px;
            border-radius: 3px;
            font-size: 8.5px;
            font-family: 'Consolas', monospace;
        """)

        header.addWidget(self.title_icon)
        header.addWidget(self.title_lbl)
        header.addWidget(self.btn_refresh)
        header.addStretch()
        header.addWidget(self.badge_time)
        root.addLayout(header)

        # 2. Tab Bar: [⚡ 实时状态] | [📅 历史占用]
        tab_bar = QHBoxLayout()
        tab_bar.setContentsMargins(0, 0, 0, 0)
        tab_bar.setSpacing(max(2, int(round(3 * self.scale))))

        tab_h = max(16, int(round(20 * self.scale)))
        self.btn_tab_live = QPushButton("⚡ 实时状态", self)
        self.btn_tab_live.setFixedHeight(tab_h)
        self.btn_tab_live.setCursor(Qt.PointingHandCursor)
        self.btn_tab_live.clicked.connect(lambda: self.switch_tab(0))

        self.btn_tab_hist = QPushButton("📅 历史占用", self)
        self.btn_tab_hist.setFixedHeight(tab_h)
        self.btn_tab_hist.setCursor(Qt.PointingHandCursor)
        self.btn_tab_hist.clicked.connect(lambda: self.switch_tab(1))

        tab_bar.addWidget(self.btn_tab_live)
        tab_bar.addWidget(self.btn_tab_hist)
        tab_bar.addStretch()
        root.addLayout(tab_bar)

        # 3. Stacked View
        self.stack = QStackedWidget(self)

        # --- View 0: Real-time Live Cards (Single Vertical Stack) ---
        self.scroll_live = QScrollArea(self)
        self.scroll_live.setWidgetResizable(True)
        self.scroll_live.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_live.viewport().setAutoFillBackground(False)
        self.scroll_live.setStyleSheet("""
            QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.02);
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
        """)

        self.live_container = QWidget()
        self.live_container.setStyleSheet("background: transparent;")
        self.live_layout = QVBoxLayout(self.live_container)
        self.live_layout.setContentsMargins(0, 1, 1, 1)
        self.live_layout.setSpacing(max(2, int(round(3 * self.scale))))

        # Pre-create the 5 GPU card rows in order: 7号(3卡) + 8号(2卡)
        self.card_rows: Dict[str, GPUCardRow] = {}

        # 7号 cards (L40S - 0, 1, 2)
        for idx in ["0", "1", "2"]:
            key = f"7-{idx}"
            row = GPUCardRow("7", "L40S", idx, self.live_container, scale=self.scale)
            self.live_layout.addWidget(row)
            self.card_rows[key] = row

        # 8号 cards (A100 - 0, 1)
        for idx in ["0", "1"]:
            key = f"8-{idx}"
            row = GPUCardRow("8", "A100", idx, self.live_container, scale=self.scale)
            self.live_layout.addWidget(row)
            self.card_rows[key] = row

        # Divider between GPU cards and Host Resource cards
        self.host_divider = QFrame(self.live_container)
        self.host_divider.setFrameShape(QFrame.HLine)
        self.host_divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); height: 1px; border: none;")
        self.live_layout.addWidget(self.host_divider)

        # Host section header row: Title + Filter Buttons [全部] [GPU] [CPU]
        self.host_header = QHBoxLayout()
        self.host_header.setContentsMargins(0, 2, 0, 1)
        self.host_header.setSpacing(max(2, int(round(3 * self.scale))))

        self.host_title = QLabel("🖥️ 主机资源", self.live_container)
        host_title_fs = max(7, int(round(9.5 * self.scale)))
        self.host_title.setStyleSheet(f"font-size: {host_title_fs}px; font-weight: 700; color: #CBD5E1;")

        self.host_filter_mode = "all"
        self.btn_filter_all = QPushButton("全部", self.live_container)
        self.btn_filter_gpu = QPushButton("GPU", self.live_container)
        self.btn_filter_cpu = QPushButton("CPU", self.live_container)

        self.filter_btns = {
            "all": self.btn_filter_all,
            "gpu": self.btn_filter_gpu,
            "cpu": self.btn_filter_cpu,
        }

        pill_h = max(13, int(round(16 * self.scale)))
        for mode, btn in self.filter_btns.items():
            btn.setFixedHeight(pill_h)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, m=mode: self._set_host_filter(m))

        self.host_header.addWidget(self.host_title)
        self.host_header.addStretch()
        self.host_header.addWidget(self.btn_filter_all)
        self.host_header.addWidget(self.btn_filter_gpu)
        self.host_header.addWidget(self.btn_filter_cpu)
        self.live_layout.addLayout(self.host_header)

        # Pre-create Host Cards for 3 GPU servers + 3 CPU servers
        self.host_cards: Dict[str, ServerHostCard] = {}
        host_definitions = [
            ("7", "GPU 7号 · L40S", "gpu"),
            ("8", "GPU 8号 · A100", "gpu"),
            ("4", "GPU 4号 · 2080Ti", "gpu"),
            ("quad", "CPU server-quad", "cpu"),
            ("e5", "CPU server-e5", "cpu"),
            ("8375c", "CPU server-8375c", "cpu"),
        ]
        for sid, name, stype in host_definitions:
            card = ServerHostCard(sid, name, s_type=stype, parent=self.live_container, scale=self.scale)
            self.live_layout.addWidget(card)
            self.host_cards[sid] = card

        self._update_filter_button_styles()

        self.live_layout.addStretch()
        self.scroll_live.setWidget(self.live_container)
        self.stack.addWidget(self.scroll_live)

        # --- View 1: History Gantt & Timeline (Supports Horizontal Scroll) ---
        self.hist_container = QWidget(self)
        hist_layout = QVBoxLayout(self.hist_container)
        hist_layout.setContentsMargins(0, 1, 0, 1)
        hist_layout.setSpacing(max(2, int(round(4 * self.scale))))

        hist_ctrl_row = QHBoxLayout()
        hist_ctrl_row.setContentsMargins(0, 0, 0, 0)
        hist_ctrl_row.setSpacing(4)

        hist_lbl = QLabel("查看范围:", self.hist_container)
        hist_lbl.setStyleSheet(f"font-size: {max(7, int(round(9.5 * self.scale)))}px; color: #94A3B8;")

        self.combo_days = QComboBox(self.hist_container)
        self.combo_days.addItem("过去 1 天", 1)
        self.combo_days.addItem("过去 3 天", 3)
        self.combo_days.addItem("过去 7 天", 7)
        self.combo_days.setStyleSheet(f"""
            QComboBox {{
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 3px;
                padding: 1px 4px;
                font-size: {max(7, int(round(9.5 * self.scale)))}px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #1E293B;
                color: #E2E8F0;
                selection-background-color: #0284C7;
            }}
        """)
        self.combo_days.currentIndexChanged.connect(self._on_days_changed)

        self.btn_hist_refresh = QPushButton("↻ 载入历史", self.hist_container)
        btn_w = max(42, int(round(60 * self.scale)))
        btn_h = max(16, int(round(19 * self.scale)))
        self.btn_hist_refresh.setFixedSize(btn_w, btn_h)
        self.btn_hist_refresh.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 3px;
                font-size: {max(6, int(round(8.5 * self.scale)))}px;
            }}
            QPushButton:hover {{
                background-color: #0284C7;
                color: #FFFFFF;
            }}
        """)
        self.btn_hist_refresh.clicked.connect(self._on_hist_refresh_clicked)

        hist_ctrl_row.addWidget(hist_lbl)
        hist_ctrl_row.addWidget(self.combo_days)
        hist_ctrl_row.addWidget(self.btn_hist_refresh)
        hist_ctrl_row.addStretch()
        hist_layout.addLayout(hist_ctrl_row)

        hist_body = QHBoxLayout()
        hist_body.setContentsMargins(0, 0, 0, 0)
        hist_body.setSpacing(0)

        self.gantt_labels = GanttLabelsWidget(self.hist_container, scale=self.scale)
        hist_body.addWidget(self.gantt_labels, 0, Qt.AlignTop)

        self.scroll_hist = QScrollArea(self.hist_container)
        self.scroll_hist.setFrameShape(QFrame.NoFrame)
        self.scroll_hist.viewport().setStyleSheet("background: transparent; border: none;")
        self.scroll_hist.setWidgetResizable(True)
        self.scroll_hist.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_hist.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_hist.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.02);
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
            QScrollBar:horizontal {
                background: rgba(255, 255, 255, 0.02);
                height: 5px;
                border-radius: 2px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 2px;
                min-width: 25px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(2, 132, 199, 0.6);
            }
        """)
        self.gantt_canvas = GanttTimelineCanvas(self.hist_container, scale=self.scale)
        self.scroll_hist.setWidget(self.gantt_canvas)
        self.scroll_hist.setFixedHeight(self.gantt_canvas.height() + 8)
        self.gantt_labels.set_target_scroll_area(self.scroll_hist)
        hist_body.addWidget(self.scroll_hist, 1)
        hist_layout.addLayout(hist_body)
        hist_layout.addStretch()

        self.stack.addWidget(self.hist_container)
        root.addWidget(self.stack, 1)

        self.switch_tab(0)

        self.monitor.realtime_updated.connect(self.update_live_data)
        self.monitor.history_updated.connect(self.update_history_data)

    def set_scale(self, scale: float):
        """Update scale and propagate to child card rows and gantt chart."""
        self.scale = max(0.5, float(scale))
        icon_sz = max(9, int(round(13 * self.scale)))
        self.title_icon.setPixmap(get_nvidia_pixmap(icon_sz))
        title_fs = max(8, int(round(10.5 * self.scale)))
        self.title_lbl.setStyleSheet(f"font-size: {title_fs}px; font-weight: 800; color: #FFFFFF;")
        btn_sz = max(14, int(round(18 * self.scale)))
        self.btn_refresh.setFixedSize(btn_sz, btn_sz)
        tab_h = max(16, int(round(20 * self.scale)))
        self.btn_tab_live.setFixedHeight(tab_h)
        self.btn_tab_hist.setFixedHeight(tab_h)
        for row in self.card_rows.values():
            row.set_scale(self.scale)
        if hasattr(self, "host_cards"):
            for card in self.host_cards.values():
                card.set_scale(self.scale)
        if hasattr(self, "host_title"):
            host_title_fs = max(7, int(round(9.5 * self.scale)))
            self.host_title.setStyleSheet(f"font-size: {host_title_fs}px; font-weight: 700; color: #CBD5E1;")
        if hasattr(self, "filter_btns"):
            self._update_filter_button_styles()
        if hasattr(self, "gantt_labels"):
            self.gantt_labels.set_scale(self.scale)
        if hasattr(self, "gantt_canvas"):
            self.gantt_canvas.set_scale(self.scale)
        if hasattr(self, "scroll_hist") and hasattr(self, "gantt_canvas"):
            self.scroll_hist.setFixedHeight(self.gantt_canvas.height() + 8)
        if hasattr(self, "badge_time"):
            self.badge_time.setStyleSheet(f"""
                background-color: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                padding: 1px 3px;
                border-radius: 3px;
                font-size: {max(6, int(round(8.5 * self.scale)))}px;
                font-family: 'Consolas', monospace;
            """)
        self.switch_tab(self.stack.currentIndex())

    def _set_host_filter(self, mode: str):
        """Filter host cards by category: 'all', 'gpu', or 'cpu'."""
        self.host_filter_mode = mode
        for card in self.host_cards.values():
            if mode == "all" or card.s_type == mode:
                card.show()
            else:
                card.hide()
        self._update_filter_button_styles()

    def _update_filter_button_styles(self):
        """Update active and inactive styling for host filter pill buttons."""
        fs = max(6, int(round(8.5 * self.scale)))
        pad = max(2, int(round(4 * self.scale)))
        pill_h = max(13, int(round(16 * self.scale)))
        for mode, btn in self.filter_btns.items():
            btn.setFixedHeight(pill_h)
            if mode == self.host_filter_mode:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #0284C7;
                        color: #FFFFFF;
                        border: none;
                        border-radius: 3px;
                        font-size: {fs}px;
                        font-weight: 700;
                        padding: 0px {pad}px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: rgba(255, 255, 255, 0.05);
                        color: #94A3B8;
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 3px;
                        font-size: {fs}px;
                        font-weight: 600;
                        padding: 0px {pad}px;
                    }}
                    QPushButton:hover {{
                        background-color: rgba(255, 255, 255, 0.1);
                        color: #FFFFFF;
                    }}
                """)

    def update_host_stats(self, stats: Dict[str, Dict[str, Any]]):
        """Update host stats (CPU, RAM, Disk) for all 6 servers."""
        if not stats:
            return
        for sid, card in self.host_cards.items():
            if sid in stats:
                sdata = stats[sid]
                cpu = float(sdata.get("cpu", -1.0))
                mem_u = float(sdata.get("mem_used", 0.0))
                mem_t = float(sdata.get("mem_total", 0.0))
                mem_p = float(sdata.get("mem_pct", 0.0))
                disk_f = float(sdata.get("disk_free", 0.0))
                card.update_stats(cpu, mem_u, mem_t, mem_p, disk_f)

    def switch_tab(self, index: int):
        """Switch active tab between Live (0) and History (1)."""
        self.stack.setCurrentIndex(index)
        tab_fs = max(7, int(round(9.5 * self.scale)))
        if index == 0:
            self.btn_tab_live.setStyleSheet(f"""
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: {tab_fs}px;
                font-weight: 700;
                padding: 2px 8px;
            """)
            self.btn_tab_hist.setStyleSheet(f"""
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                font-size: {tab_fs}px;
                font-weight: 600;
                padding: 2px 8px;
            """)
        else:
            self.btn_tab_hist.setStyleSheet(f"""
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: {tab_fs}px;
                font-weight: 700;
                padding: 2px 8px;
            """)
            self.btn_tab_live.setStyleSheet(f"""
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                font-size: {tab_fs}px;
                font-weight: 600;
                padding: 2px 8px;
            """)
            if not self.gantt_canvas.intervals:
                days = self.combo_days.currentData()
                self.monitor.fetch_history_async(days=days)
            QTimer.singleShot(60, lambda: self.scroll_hist.horizontalScrollBar().setValue(
                self.scroll_hist.horizontalScrollBar().maximum()
            ))

    def _on_refresh_clicked(self):
        self.refresh_requested.emit()
        self.monitor.live_worker.start()

    def _on_days_changed(self):
        days = self.combo_days.currentData()
        self.monitor.fetch_history_async(days=days)

    def _on_hist_refresh_clicked(self):
        days = self.combo_days.currentData()
        self.monitor.fetch_history_async(days=days)

    def update_live_data(self, data: Dict[str, Any]):
        """Render live GPU cards in single vertical column."""
        if not data.get("success"):
            return

        self.badge_time.setText(f"🕒 {data.get('last_update', '')}")

        servers = data.get("servers", {})
        for sid in ["8", "7"]:
            sinfo = servers.get(sid)
            if not sinfo:
                continue
            model_name = sinfo.get("model", "GPU")
            for cdata in sinfo.get("cards", []):
                idx = cdata.get("index", "0")
                key = f"{sid}-{idx}"
                if key in self.card_rows:
                    self.card_rows[key].update_data(cdata, model_name)

    def update_history_data(self, intervals: List[Dict[str, Any]]):
        """Render history Gantt visualization."""
        days = self.combo_days.currentData()
        self.gantt_canvas.set_data(intervals, days=days)
        if hasattr(self, "gantt_labels"):
            self.gantt_labels.set_tasks(self.gantt_canvas.tasks)
        if hasattr(self, "scroll_hist") and hasattr(self, "gantt_canvas"):
            self.scroll_hist.setFixedHeight(self.gantt_canvas.height() + 8)
        QTimer.singleShot(60, lambda: self.scroll_hist.horizontalScrollBar().setValue(
            self.scroll_hist.horizontalScrollBar().maximum()
        ))
