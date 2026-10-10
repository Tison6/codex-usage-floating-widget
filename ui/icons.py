"""
Vector Brand SVG Assets for Desktop Floating Widget.
Renders high-DPI crisp icons for OpenAI, Intel, and NVIDIA.
"""

from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtSvg import QSvgRenderer

OPENAI_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <path fill="#10A37F" d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.064l-4.84 2.796a4.499 4.499 0 0 1-6.14-1.653zm-1.074-9.37a4.47 4.47 0 0 1 2.34-1.974l-.004.164v5.518a.784.784 0 0 0 .392.68l5.843 3.37-2.02 1.169a.08.08 0 0 1-.073.008l-4.84-2.795a4.504 4.504 0 0 1-1.638-6.14zm15.864 2.822l-5.844-3.37 2.02-1.168a.08.08 0 0 1 .073-.008l4.84 2.795a4.504 4.504 0 0 1 1.638 6.14 4.476 4.476 0 0 1-2.335 1.974v-5.682a.78.78 0 0 0-.392-.681zm2.016-3.834l-.142-.084-4.783-2.76a.77.77 0 0 0-.78 0l-5.843 3.369V9.085a.08.08 0 0 1 .033-.064l4.84-2.796a4.499 4.499 0 0 1 6.675 4.668zm-9.84-3.578a4.476 4.476 0 0 1 2.876 1.04l-.141.081-4.779 2.758a.795.795 0 0 0-.392.681v6.737l-2.02-1.168a.07.07 0 0 1-.038-.052v-5.583a4.504 4.504 0 0 1 4.494-4.494zm1.097 5.79l2.736 1.579v3.158l-2.736 1.58-2.736-1.58v-3.158l2.736-1.58z"/>
</svg>"""

INTEL_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <path fill="#0071C5" d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm-2.4 14.5H8.2V9.8h1.4v6.7zm-.7-7.7c-.5 0-.9-.4-.9-.9s.4-.9.9-.9.9.4.9.9-.4.9-.9.9zm6.6 7.7h-1.4v-3.7c0-.9-.3-1.4-1.1-1.4-.6 0-1 .4-1.2.8v4.3h-1.4V9.8h1.4v.9c.4-.6 1.1-1 1.9-1 1.4 0 1.8 1 1.8 2.4v4.4z"/>
</svg>"""

NVIDIA_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <path fill="#76B900" d="M1.233 11.758c0-4.524 4.02-8.156 8.924-8.156 4.904 0 8.877 3.632 8.877 8.156 0 4.524-3.973 8.156-8.877 8.156-3.774 0-7.008-2.148-8.293-5.234l2.438-.857c.928 2.115 3.197 3.593 5.855 3.593 3.498 0 6.326-2.502 6.326-5.658s-2.828-5.658-6.326-5.658c-3.497 0-6.372 2.502-6.372 5.658 0 .848.204 1.642.568 2.348L2.463 17.51a8.127 8.127 0 0 1-1.23-5.752zm3.87 0c0-2.457 2.269-4.428 5.054-4.428 2.784 0 5.053 1.971 5.053 4.428s-2.269 4.429-5.053 4.429c-2.02 0-3.776-1.042-4.59-2.58l1.968-.783c.488.85 1.458 1.415 2.622 1.415 1.636 0 2.968-1.127 2.968-2.481s-1.332-2.481-2.968-2.481c-1.636 0-2.968 1.127-2.968 2.481 0 .28.05.548.14.795L5.27 12.59a4.27 4.27 0 0 1-.167-.832z"/>
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


def get_intel_pixmap(size: int = 13) -> QPixmap:
    return get_svg_pixmap(INTEL_SVG, size, size)


def get_nvidia_pixmap(size: int = 13) -> QPixmap:
    return get_svg_pixmap(NVIDIA_SVG, size, size)
