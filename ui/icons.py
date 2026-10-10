"""
Vector Brand SVG Assets for Desktop Floating Widget.
Renders high-DPI crisp icons for OpenAI, CPU Chip, and NVIDIA.
"""

from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtSvg import QSvgRenderer

OPENAI_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <path fill="#FFFFFF" d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.064l-4.84 2.796a4.499 4.499 0 0 1-6.14-1.653zm-1.074-9.37a4.47 4.47 0 0 1 2.34-1.974l-.004.164v5.518a.784.784 0 0 0 .392.68l5.843 3.37-2.02 1.169a.08.08 0 0 1-.073.008l-4.84-2.795a4.504 4.504 0 0 1-1.638-6.14zm15.864 2.822l-5.844-3.37 2.02-1.168a.08.08 0 0 1 .073-.008l4.84 2.795a4.504 4.504 0 0 1 1.638 6.14 4.476 4.476 0 0 1-2.335 1.974v-5.682a.78.78 0 0 0-.392-.681zm2.016-3.834l-.142-.084-4.783-2.76a.77.77 0 0 0-.78 0l-5.843 3.369V9.085a.08.08 0 0 1 .033-.064l4.84-2.796a4.499 4.499 0 0 1 6.675 4.668zm-9.84-3.578a4.476 4.476 0 0 1 2.876 1.04l-.141.081-4.779 2.758a.795.795 0 0 0-.392.681v6.737l-2.02-1.168a.07.07 0 0 1-.038-.052v-5.583a4.504 4.504 0 0 1 4.494-4.494zm1.097 5.79l2.736 1.579v3.158l-2.736 1.58-2.736-1.58v-3.158l2.736-1.58z"/>
</svg>"""

CPU_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="4" y="4" width="16" height="16" rx="2"/>
  <rect x="9" y="9" width="6" height="6" rx="1"/>
  <path d="M15 2v2"/>
  <path d="M15 20v2"/>
  <path d="M2 15h2"/>
  <path d="M2 9h2"/>
  <path d="M20 15h2"/>
  <path d="M20 9h2"/>
  <path d="M9 2v2"/>
  <path d="M9 20v2"/>
</svg>"""

NVIDIA_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <path fill="#76B900" d="M8.948 8.798v-1.43a6.7 6.7 0 0 1 .424-.018c3.922-.124 6.493 3.374 6.493 3.374s-2.774 3.851-5.75 3.851c-.398 0-.787-.062-1.158-.185v-4.346c1.528.185 1.837.857 2.747 2.385l2.04-1.714s-1.492-1.952-4-1.952a6.016 6.016 0 0 0-.796.035m0-4.735v2.138l.424-.027c5.45-.185 9.01 4.47 9.01 4.47s-4.08 4.964-8.33 4.964c-.37 0-.733-.035-1.095-.097v1.325c.3.035.61.062.91.062 3.957 0 6.82-2.023 9.593-4.408.459.371 2.34 1.263 2.73 1.652-2.633 2.208-8.772 3.984-12.253 3.984-.335 0-.653-.018-.971-.053v1.864H24V4.063zm0 10.326v1.131c-3.657-.654-4.673-4.46-4.673-4.46s1.758-1.944 4.673-2.262v1.237H8.94c-1.528-.186-2.73 1.245-2.73 1.245s.68 2.412 2.739 3.11M2.456 10.9s2.164-3.197 6.5-3.533V6.201C4.153 6.59 0 10.653 0 10.653s2.35 6.802 8.948 7.42v-1.237c-4.84-.6-6.492-5.936-6.492-5.936z"/>
</svg>"""


def get_svg_pixmap(svg_str: str, w: int = 13, h: int = 13) -> QPixmap:
    """Render high-DPI antialiased QPixmap from SVG string."""
    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
    pix = QPixmap(w * 2, h * 2)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pix.setDevicePixelRatio(2.0)
    return pix


def get_openai_pixmap(size: int = 13) -> QPixmap:
    return get_svg_pixmap(OPENAI_SVG, size, size)


def get_cpu_pixmap(size: int = 13) -> QPixmap:
    return get_svg_pixmap(CPU_SVG, size, size)


def get_nvidia_pixmap(size: int = 13) -> QPixmap:
    return get_svg_pixmap(NVIDIA_SVG, size, size)
