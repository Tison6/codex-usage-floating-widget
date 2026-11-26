"""Pixel fonts keep custom painting aligned with Qt stylesheet dimensions."""

from PyQt5.QtGui import QFont


def pixel_font(family, size, weight=QFont.Normal):
    font = QFont(family)
    font.setPixelSize(max(1, int(round(size))))
    font.setWeight(weight)
    return font
