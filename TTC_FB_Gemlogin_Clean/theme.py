# -*- coding: utf-8 -*-
import re
from PySide6.QtGui import QColor, QFont, QFontDatabase

# Palette màu sắc Premium
DARK_BG = "#0D1117"
DARK_PANEL = "#161B22"
DARK_BORDER = "#30363D"
TEXT_PRIMARY = "#E6EDF3"
TEXT_MUTED = "#8B949E"
ACCENT_BLUE = "#1F6FEB"
ACCENT_GREEN = "#2EA043"

STYLE_SHEET = """
QWidget {
    background-color: #0D1117;
    color: #E6EDF3;
    font-family: "Segoe UI", -apple-system, sans-serif;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #30363D;
    border-radius: 6px;
    margin-top: 12px;
    font-weight: bold;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: #58A6FF;
}
QPushButton {
    background-color: #21262D;
    border: 1px solid #30363D;
    border-radius: 6px;
    padding: 6px 12px;
    color: #C9D1D9;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #30363D;
    border-color: #8B949E;
}
QPushButton:pressed {
    background-color: #161B22;
}
QLineEdit, QComboBox, QSpinBox {
    background-color: #0D1117;
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 4px;
    color: #E6EDF3;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #58A6FF;
}
QTableWidget {
    background-color: #0D1117;
    border: 1px solid #30363D;
    gridline-color: #161B22;
    border-radius: 6px;
}
QHeaderView::section {
    background-color: #161B22;
    color: #8B949E;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #30363D;
    font-weight: bold;
}
QListWidget {
    background-color: #161B22;
    border: 1px solid #30363D;
    border-radius: 6px;
}
QListWidget::item {
    padding: 8px;
    border-bottom: 1px solid #21262D;
}
QListWidget::item:selected {
    background-color: #1F6FEB;
    color: #FFFFFF;
    border-radius: 4px;
}
QScrollBar:vertical {
    border: none;
    background: #0D1117;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #30363D;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #8B949E;
}
"""

LOG_LEVEL_TO_ICON = {
    "success": "success",
    "error": "error",
    "warning": "warning",
    "waiting": "waiting",
    "wait": "waiting",
    "browser": "browser",
    "job": "job",
    "api": "api",
    "gemlogin": "gemlogin",
    "facebook": "facebook",
    "livecheck": "livecheck",
    "reaction": "reaction",
    "comment": "comment",
    "share": "share",
    "skip": "skip",
    "retry": "retry",
    "config": "config",
    "start": "start",
    "stop": "stop",
    "token": "token",
    "info": "info",
    "debug": "debug",
}

LOG_COLORS = {
    "success": "#3FB950",
    "error": "#F85149",
    "warning": "#D29922",
    "waiting": "#FF9800",
    "wait": "#FF9800",
    "browser": "#42A5F5",
    "job": "#CE93D8",
    "reaction": "#FF6B9A",
    "comment": "#64B5F6",
    "share": "#4DD0E1",
    "api": "#00BCD4",
    "token": "#FFD54F",
    "config": "#B0BEC5",
    "start": "#81C784",
    "stop": "#EF5350",
    "skip": "#FFB74D",
    "retry": "#BA68C8",
    "livecheck": "#26C6DA",
    "gemlogin": "#90CAF9",
    "debug": "#78909C",
    "info": "#D6DEEB",
    "facebook": "#42A5F5",
}

FALLBACK_ICONS = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "waiting": "⏳",
    "wait": "⏳",
    "browser": "🌐",
    "job": "💼",
    "api": "📦",
    "gemlogin": "🌐",
    "facebook": "👤",
    "livecheck": "🔍",
    "reaction": "👍",
    "comment": "💬",
    "share": "🔄",
    "skip": "⏭️",
    "retry": "🔁",
    "config": "⚙️",
    "start": "🚀",
    "stop": "🛑",
    "token": "🔑",
    "info": "ℹ️",
    "debug": "🐛",
}

def get_log_font():
    families = set(QFontDatabase.families())
    for font_name in ("Cascadia Mono", "JetBrains Mono", "Consolas"):
        if font_name in families:
            return QFont(font_name, 9)
    return QFont("Monospace", 9)

def fix_mojibake(text):
    if not isinstance(text, str):
        text = str(text)
    markers = (
        "\u00c3",
        "\u00c4",
        "\u00e2",
        "\u00f0",
        "\ufffd",
        "\u00ba",
        "\u00bb",
        "\u00bc",
        "\u0153",
        "\u2021",
        "\u2014",
        "\u008f",
    )
    if not any(marker in text for marker in markers):
        return text

    def score(value):
        bad_count = sum(value.count(marker) for marker in markers)
        replacement_count = value.count("\ufffd")
        return -(bad_count * 10 + replacement_count * 20)

    current = text
    for _ in range(2):
        candidates = [current]
        for encoding in ("latin1", "cp1252"):
            try:
                candidates.append(current.encode(encoding, errors="strict").decode("utf-8", errors="strict"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        best = max(candidates, key=score)
        if score(best) <= score(current):
            break
        current = best
    return current

def strip_existing_log_prefix(line):
    line = fix_mojibake(line).strip()
    timestamp = None
    match = re.match(r"^(?:\S+\s+)?\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$", line)
    if match:
        timestamp = match.group(1)
        line = match.group(2).strip()
    return timestamp, line

def resolve_level(message, default_level="info"):
    fixed = fix_mojibake(message)
    lowered = fixed.lower()
    if (
        "hiện chưa có job" in lowered
        or "hết nhiệm vụ loại này" in lowered
        or "không có nhiệm vụ" in lowered
        or "không có job" in lowered
    ):
        return "waiting"
    if ("thử" in lowered and "lại" in lowered) or "retry" in lowered:
        return "retry"
    if "traceback" in lowered or "lỗi" in lowered or "error" in lowered or "thất bại" in lowered:
        return "error"
    if "job đã đủ" in lowered or "full" in lowered or "bỏ qua" in lowered or "skip" in lowered:
        return "skip"
    if "livecheck" in lowered or "kiểm tra trạng thái" in lowered or "check post live" in lowered:
        return "livecheck"
    if "gemlogin" in lowered or "profile id" in lowered:
        return "gemlogin"
    if "token" in lowered or "auth" in lowered:
        return "token"
    if "config" in lowered or "cấu hình" in lowered:
        return "config"
    if "tool started" in lowered or "start" in lowered:
        return "start"
    if "stop" in lowered or "stopped" in lowered:
        return "stop"
    if "thành công" in lowered or "đã tải được" in lowered or "success" in lowered:
        return "success"
    if "cảnh báo" in lowered or "warning" in lowered:
        return "warning"
    if "chờ" in lowered or "waiting" in lowered:
        return "waiting"
    if "reaction" in lowered or "like_facebook" in lowered:
        return "reaction"
    if "comment" in lowered or "like_poster" in lowered:
        return "comment"
    if "share" in lowered or "chia sẻ" in lowered:
        return "share"
    if "facebook" in lowered or "browser" in lowered or "mở bài viết" in lowered:
        return "browser"
    if "api" in lowered or "mission list" in lowered or "lấy job" in lowered:
        return "api"
    if "mission" in lowered or "job" in lowered:
        return "job"
    if "[debug]" in lowered:
        return "debug"
    return default_level
