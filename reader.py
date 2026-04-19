"""
轻想纪念版 · 本地阅读器
"""
import sys, json, re
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QFileDialog,
    QGridLayout, QSizePolicy, QStackedWidget, QTabBar, QDialog, QComboBox
)
from PyQt6.QtCore import Qt, QSize, QUrl, pyqtSignal, QPoint, QRectF, QSettings
from PyQt6.QtWidgets import QGraphicsDropShadowEffect
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QPainterPath, QColor,
    QLinearGradient, QBrush, QPen, QBitmap, QRegion, QCursor
)

# ── 主题 ──────────────────────────────────────────────────────────────────

BG       = "#f5f5f5"
BG_WHITE = "#ffffff"
ACCENT   = "#5aab6e"
FG       = "#333333"
FG_DIM   = "#999999"
FG_LIGHT = "#cccccc"
BORDER   = "#e8e8e8"
SIDEBAR_W = 260


def ts_to_str(ts, fmt="%Y-%m-%d %H:%M:%S") -> str:
    try:
        return datetime.fromtimestamp(int(ts) / 1000).strftime(fmt)
    except Exception:
        return ""


def circular_pixmap(path: Path, size: int) -> QPixmap:
    src = QPixmap(str(path))
    if src.isNull():
        pix = QPixmap(size, size)
        pix.fill(QColor("#dddddd"))
        return pix
    src = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                     Qt.TransformationMode.SmoothTransformation)
    # center crop
    x = (src.width() - size) // 2
    y = (src.height() - size) // 2
    src = src.copy(x, y, size, size)
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path_obj = QPainterPath()
    path_obj.addEllipse(0, 0, size, size)
    painter.setClipPath(path_obj)
    painter.drawPixmap(0, 0, src)
    painter.end()
    return result


# ── 用户横幅 ──────────────────────────────────────────────────────────────

class BannerWidget(QWidget):
    switch_clicked  = pyqtSignal(int, int)  # 昵称标签底部中心全局坐标 (x, y)
    random_clicked  = pyqtSignal()   # 随机回忆
    today_clicked   = pyqtSignal()   # 那年今日

    def __init__(self, user_info: dict, backup_dir: Path):
        super().__init__()
        self.setFixedHeight(260)
        self._bg_pix = None

        avatar_files = list(backup_dir.glob("avatar.*"))
        if avatar_files:
            pix = QPixmap(str(avatar_files[0]))
            if not pix.isNull():
                self._bg_pix = pix.scaled(
                    1200, 260,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )

        # 主体：居中排列头像/昵称/签名/统计
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(6)

        center = QWidget()
        center.setStyleSheet("background: transparent;")
        center_l = QVBoxLayout(center)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.setSpacing(6)
        center_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        avatar_lbl = QLabel()
        avatar_lbl.setFixedSize(70, 70)
        avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_lbl.setStyleSheet("background: transparent;")
        if avatar_files:
            avatar_lbl.setPixmap(circular_pixmap(avatar_files[0], 70))

        nick = user_info.get("nickName", "")
        name = QLabel(nick)
        name.setFont(QFont("PingFang SC", 17, QFont.Weight.Bold))
        name.setStyleSheet("color: white; background: transparent;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sig = user_info.get("sign", user_info.get("signature", user_info.get("bio", "")))
        sig_lbl = QLabel(sig[:50] if sig else "")
        sig_lbl.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 13px; background: transparent;")
        sig_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        stats_w = QWidget()
        stats_w.setStyleSheet("background: transparent;")
        stats_l = QHBoxLayout(stats_w)
        stats_l.setContentsMargins(0, 4, 0, 0)
        stats_l.setSpacing(0)
        stats_l.addStretch()
        for val, lbl in [
            (user_info.get("followCount", 0), "关注"),
            (user_info.get("fanCount", user_info.get("fansCount", 0)), "粉丝"),
            (user_info.get("witnessCount", 0), "见证"),
        ]:
            col = QWidget()
            col.setStyleSheet("background: transparent;")
            col_l = QVBoxLayout(col)
            col_l.setSpacing(1)
            col_l.setContentsMargins(24, 0, 24, 0)
            v = QLabel(str(val or 0))
            v.setFont(QFont("PingFang SC", 14, QFont.Weight.Bold))
            v.setStyleSheet("color: white; background: transparent;")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t = QLabel(lbl)
            t.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px; background: transparent;")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col_l.addWidget(v)
            col_l.addWidget(t)
            stats_l.addWidget(col)
        stats_l.addStretch()

        center_l.addWidget(avatar_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
        center_l.addWidget(name)
        if sig:
            center_l.addWidget(sig_lbl)
        center_l.addWidget(stats_w)

        # 昵称可点击（触发切换），传递标签底部中心的全局坐标
        self._name_lbl = name
        name.setCursor(Qt.CursorShape.PointingHandCursor)
        def _name_clicked(e, lbl=name):
            bottom_center = lbl.mapToGlobal(QPoint(lbl.width() // 2, lbl.height()))
            self.switch_clicked.emit(bottom_center.x(), bottom_center.y())
        name.mousePressEvent = _name_clicked

        layout.addWidget(center, 1)

        # 底部栏：右侧随机回忆/那年今日
        bottom = QWidget()
        bottom.setFixedHeight(32)
        bottom.setStyleSheet("background: transparent;")
        bottom_l = QHBoxLayout(bottom)
        bottom_l.setContentsMargins(0, 0, 16, 8)
        bottom_l.setSpacing(0)
        bottom_l.addStretch()

        for label, sig_name in [("随机回忆", self.random_clicked), ("那年今日", self.today_clicked)]:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: none;
                    color: rgba(255,255,255,0.7); font-size: 12px;
                    padding: 0 8px;
                }
                QPushButton:hover { color: white; }
            """)
            btn.clicked.connect(sig_name)
            bottom_l.addWidget(btn)

        layout.addWidget(bottom)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._bg_pix:
            x = (self._bg_pix.width() - self.width()) // 2
            painter.drawPixmap(0, 0, self._bg_pix, x, 0, self.width(), self.height())
        else:
            grad = QLinearGradient(0, 0, self.width(), self.height())
            grad.setColorAt(0, QColor("#3a7a50"))
            grad.setColorAt(1, QColor("#5aab6e"))
            painter.fillRect(self.rect(), grad)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        painter.end()
        super().paintEvent(event)


# ── 左侧栏 ────────────────────────────────────────────────────────────────

class SidebarWidget(QWidget):
    plan_clicked = pyqtSignal(int)  # plan index

    def __init__(self, user_info: dict, plan_dirs: list, plan_metas: list):
        super().__init__()
        self.setFixedWidth(SIDEBAR_W)
        self.setStyleSheet(f"background: {BG_WHITE}; border-right: 1px solid {BORDER};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 统计
        stats_w = QWidget()
        stats_w.setStyleSheet(f"background: {BG_WHITE}; border-bottom: 1px solid {BORDER};")
        stats_l = QHBoxLayout(stats_w)
        stats_l.setContentsMargins(0, 14, 0, 14)

        for val, lbl in [
            (user_info.get("followCount", 0), "关注"),
            (user_info.get("fanCount", user_info.get("fansCount", 0)), "粉丝"),
            (user_info.get("witnessCount", 0), "见证"),
        ]:
            col = QWidget()
            col_l = QVBoxLayout(col)
            col_l.setSpacing(2)
            col_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v = QLabel(str(val or 0))
            v.setFont(QFont("PingFang SC", 15, QFont.Weight.Bold))
            v.setStyleSheet(f"color: {FG};")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t = QLabel(lbl)
            t.setStyleSheet(f"color: {FG_DIM}; font-size: 12px;")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col_l.addWidget(v)
            col_l.addWidget(t)
            stats_l.addWidget(col)

        root.addWidget(stats_w)

        # 连载列表（滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {BG_WHITE}; }}
            QScrollBar:vertical {{ background: transparent; width: 4px; }}
            QScrollBar::handle:vertical {{ background: #cccccc; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        container = QWidget()
        container.setStyleSheet(f"background: {BG_WHITE};")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 8, 0, 8)
        vbox.setSpacing(0)

        for i, (d, meta) in enumerate(zip(plan_dirs, plan_metas)):
            btn = QPushButton(meta["title"])
            btn.setFixedHeight(40)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {FG};
                    border: none; border-bottom: 1px solid {BORDER};
                    text-align: left; padding: 0 16px;
                    font-size: 13px;
                }}
                QPushButton:hover {{ background: #f0f8f2; color: {ACCENT}; }}
            """)
            btn.clicked.connect(lambda _, idx=i: self.plan_clicked.emit(idx))
            vbox.addWidget(btn)

        vbox.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)


# ── 连载封面卡片 ──────────────────────────────────────────────────────────

class PlanCard(QWidget):
    clicked = pyqtSignal()

    CARD_W = 180
    CARD_H = 220
    IMG_H  = 156
    RADIUS = 8
    BW     = 2

    def __init__(self, meta: dict, plan_dir: Path):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self._hovered = False
        self._title   = meta["title"]
        self._cover   = None

        img_dir = plan_dir / "images"
        covers  = list(img_dir.glob("cover.*")) if img_dir.exists() else []
        if covers:
            pix = QPixmap(str(covers[0]))
            if not pix.isNull():
                pix = pix.scaled(
                    self.CARD_W, self.IMG_H,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                x = (pix.width()  - self.CARD_W) // 2
                y = (pix.height() - self.IMG_H)  // 2
                self._cover = pix.copy(x, y, self.CARD_W, self.IMG_H)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        bw = self.BW
        r  = self.RADIUS
        w, h = self.CARD_W, self.CARD_H

        # 完整圆角路径（用于裁切）
        full_rect = QRectF(bw/2, bw/2, w - bw, h - bw)
        full_path = QPainterPath()
        full_path.addRoundedRect(full_rect, r, r)

        # 1. 裁切到圆角，防止图片溢出
        p.setClipPath(full_path)

        # 2. 画封面图（或灰色占位）
        if self._cover:
            p.drawPixmap(0, 0, self._cover)
        else:
            p.fillRect(0, 0, w, self.IMG_H, QColor("#eeeeee"))

        # 3. 白色底部区域
        p.fillRect(0, self.IMG_H, w, h - self.IMG_H, QColor(BG_WHITE))

        # 4. 标题文字
        p.setClipping(False)
        p.setPen(QColor(FG))
        p.setFont(QFont("PingFang SC", 12))
        text_rect = QRectF(8, self.IMG_H + 4, w - 16, h - self.IMG_H - 8)
        p.drawText(text_rect,
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter |
                   Qt.TextFlag.TextWordWrap,
                   self._title)

        # 5. 边框（hover 绿色，否则淡灰）—— 画在最上层
        border_color = QColor(ACCENT) if self._hovered else QColor(BORDER)
        pen = QPen(border_color, bw)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(full_path)

        p.end()


# ── 连载网格（主页右侧）─────────────────────────────────────────────────

class PlanGrid(QScrollArea):
    plan_selected = pyqtSignal(int)

    def __init__(self, plan_dirs: list, plan_metas: list, filter_finished=False):
        super().__init__()
        self.setWidgetResizable(True)
        self.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {BG}; }}
            QScrollBar:vertical {{ background: transparent; width: 4px; }}
            QScrollBar::handle:vertical {{ background: #cccccc; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        container = QWidget()
        container.setStyleSheet(f"background: {BG};")
        grid = QGridLayout(container)
        grid.setContentsMargins(24, 32, 24, 24)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(28)

        col = 0
        row = 0
        for i, (d, meta) in enumerate(zip(plan_dirs, plan_metas)):
            finished = meta.get("finished", False)
            if filter_finished and not finished:
                continue
            if not filter_finished and finished:
                continue
            card = PlanCard(meta, d)
            card.clicked.connect(lambda idx=i: self.plan_selected.emit(idx))
            grid.addWidget(card, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

        grid.setRowStretch(row + 1, 1)
        self.setWidget(container)


# ── 回忆浮层 ─────────────────────────────────────────────────────────────

class MemoryDialog(QDialog):
    def __init__(self, parent, header: str, items: list):
        super().__init__(parent)
        self.setWindowTitle("")
        self.setModal(True)
        self.setFixedWidth(480)
        self.setMaximumHeight(560)
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG_WHITE};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏
        hdr = QWidget()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet(f"background: {BG_WHITE}; border-bottom: 1px solid {BORDER};")
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(20, 0, 12, 0)
        title_lbl = QLabel(header)
        title_lbl.setFont(QFont("PingFang SC", 14, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {FG};")
        hdr_l.addWidget(title_lbl, 1)
        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {FG_DIM}; font-size: 20px; }}
            QPushButton:hover {{ color: {FG}; }}
        """)
        close_btn.clicked.connect(self.close)
        hdr_l.addWidget(close_btn)
        root.addWidget(hdr)

        # 内容
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {BG_WHITE}; }}
            QScrollBar:vertical {{ background: transparent; width: 4px; }}
            QScrollBar::handle:vertical {{ background: #cccccc; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        container = QWidget()
        container.setStyleSheet(f"background: {BG_WHITE};")
        content_l = QVBoxLayout(container)
        content_l.setContentsMargins(20, 16, 20, 20)
        content_l.setSpacing(12)

        if not items:
            empty = QLabel("今天还没有往年的记忆")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {FG_DIM}; font-size: 14px; padding: 40px 0;")
            content_l.addWidget(empty)
        else:
            for item in items:
                card = QWidget()
                card.setStyleSheet(f"background: {BG}; border-radius: 8px;")
                card_l = QVBoxLayout(card)
                card_l.setContentsMargins(14, 12, 14, 12)
                card_l.setSpacing(6)
                meta = QLabel(f"{item['plan_title']}  ·  {item['date']}")
                meta.setStyleSheet(f"color: {FG_DIM}; font-size: 11px;")
                card_l.addWidget(meta)
                text_lbl = QLabel(item['text'][:300] + ("…" if len(item['text']) > 300 else ""))
                text_lbl.setWordWrap(True)
                text_lbl.setStyleSheet(f"color: {FG}; font-size: 14px; line-height: 1.6;")
                text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                card_l.addWidget(text_lbl)
                content_l.addWidget(card)

        content_l.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)


# ── 主页 ──────────────────────────────────────────────────────────────────

class HomeView(QWidget):
    plan_selected  = pyqtSignal(int)
    switch_account = pyqtSignal(int, int)  # 昵称底部中心全局坐标

    def __init__(self, user_info: dict, plan_dirs: list, plan_metas: list, backup_dir: Path):
        super().__init__()
        self._plan_dirs  = plan_dirs
        self._plan_metas = plan_metas
        self.setStyleSheet(f"background: {BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 横幅
        banner = BannerWidget(user_info, backup_dir)
        banner.switch_clicked.connect(lambda x, y: self.switch_account.emit(x, y))
        banner.random_clicked.connect(self._show_random)
        banner.today_clicked.connect(self._show_on_this_day)
        root.addWidget(banner)


        # 内容区（全宽，无侧边栏）
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        right = QWidget()
        right.setStyleSheet(f"background: {BG};")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(0)

        # Tab 栏
        tab_bar = QWidget()
        tab_bar.setFixedHeight(48)
        tab_bar.setStyleSheet(f"background: {BG_WHITE}; border-bottom: 1px solid {BORDER};")
        tab_l = QHBoxLayout(tab_bar)
        tab_l.setContentsMargins(24, 0, 24, 0)
        tab_l.setSpacing(32)

        ongoing = [m for m in plan_metas if not m.get("finished")]
        finished = [m for m in plan_metas if m.get("finished")]

        self._tab_ongoing = QPushButton(f"进行中  {len(ongoing)}")
        self._tab_finished = QPushButton(f"已完结  {len(finished)}")
        for btn in [self._tab_ongoing, self._tab_finished]:
            btn.setFixedHeight(48)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: none;
                    color: {FG_DIM}; font-size: 14px;
                }}
                QPushButton:hover {{ color: {ACCENT}; }}
            """)
        self._tab_ongoing.setStyleSheet(self._tab_ongoing.styleSheet().replace(
            f"color: {FG_DIM}", f"color: {ACCENT}; font-weight: bold; border-bottom: 2px solid {ACCENT}"
        ))

        tab_l.addWidget(self._tab_ongoing)
        tab_l.addWidget(self._tab_finished)
        tab_l.addStretch()
        right_l.addWidget(tab_bar)

        # 网格区（stacked）
        self._grid_stack = QStackedWidget()
        self._grid_ongoing = PlanGrid(plan_dirs, plan_metas, filter_finished=False)
        self._grid_ongoing.plan_selected.connect(self.plan_selected)
        self._grid_finished = PlanGrid(plan_dirs, plan_metas, filter_finished=True)
        self._grid_finished.plan_selected.connect(self.plan_selected)
        self._grid_stack.addWidget(self._grid_ongoing)
        self._grid_stack.addWidget(self._grid_finished)
        right_l.addWidget(self._grid_stack)

        self._tab_ongoing.clicked.connect(lambda: self._switch_tab(0))
        self._tab_finished.clicked.connect(lambda: self._switch_tab(1))

        content.addWidget(right)
        content_w = QWidget()
        content_w.setLayout(content)
        root.addWidget(content_w, 1)

    def _switch_tab(self, idx):
        self._grid_stack.setCurrentIndex(idx)
        btns = [self._tab_ongoing, self._tab_finished]
        for i, btn in enumerate(btns):
            if i == idx:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; border: none; border-bottom: 2px solid {ACCENT};
                        color: {ACCENT}; font-size: 14px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; border: none;
                        color: {FG_DIM}; font-size: 14px;
                    }}
                    QPushButton:hover {{ color: {ACCENT}; }}
                """)

    def _collect_stages(self):
        results = []
        for plan_dir, meta in zip(self._plan_dirs, self._plan_metas):
            raw_path = plan_dir / "raw.json"
            if not raw_path.exists():
                continue
            try:
                raw = json.loads(raw_path.read_text(encoding="utf-8"))
                for stage in raw.get("stages", []):
                    html = stage.get("html", "")
                    text = re.sub(r"<[^>]+>", "", html).strip()
                    if text:
                        results.append((stage, meta["title"]))
            except Exception:
                pass
        return results

    def _show_random(self):
        import random
        all_stages = self._collect_stages()
        if not all_stages:
            return
        stage, plan_title = random.choice(all_stages)
        html = stage.get("html", "")
        text = re.sub(r"<[^>]+>", "", html).strip()
        date = ts_to_str(stage.get("publishTs", 0), "%Y-%m-%d")
        dlg = MemoryDialog(self, "随机回忆", [{"plan_title": plan_title, "date": date, "text": text}])
        dlg.exec()

    def _show_on_this_day(self):
        from datetime import datetime
        today = datetime.now()
        items = []
        for stage, plan_title in self._collect_stages():
            ts = stage.get("publishTs", 0)
            if not ts:
                continue
            dt = datetime.fromtimestamp(int(ts) / 1000)
            if dt.month == today.month and dt.day == today.day and dt.year != today.year:
                html = stage.get("html", "")
                text = re.sub(r"<[^>]+>", "", html).strip()
                if text:
                    items.append({"plan_title": plan_title, "date": ts_to_str(ts, "%Y-%m-%d"), "text": text})
        items.sort(key=lambda x: x["date"], reverse=True)
        dlg = MemoryDialog(self, "那年今日", items)
        dlg.exec()


# ── 封面英雄横幅 ─────────────────────────────────────────────────────────

class HeroCoverWidget(QWidget):
    """全宽封面图，底部叠加渐变+标题+副标题"""
    HERO_H = 280

    def __init__(self, cover_path: Path | None, title: str, subtitle: str):
        super().__init__()
        self.setFixedHeight(self.HERO_H)
        self._title    = title
        self._subtitle = subtitle
        self._cover    = None
        if cover_path and cover_path.exists():
            pix = QPixmap(str(cover_path))
            if not pix.isNull():
                self._cover = pix

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 1. 背景：封面图或纯绿渐变
        if self._cover:
            scaled = self._cover.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (scaled.width()  - w) // 2
            y = (scaled.height() - h) // 2
            p.drawPixmap(0, 0, scaled, x, y, w, h)
        else:
            grad = QLinearGradient(0, 0, w, h)
            grad.setColorAt(0, QColor("#3a7a50"))
            grad.setColorAt(1, QColor("#5aab6e"))
            p.fillRect(0, 0, w, h, grad)

        # 2. 底部渐变遮罩（透明 → 黑）
        overlay = QLinearGradient(0, h * 0.3, 0, h)
        overlay.setColorAt(0, QColor(0, 0, 0, 0))
        overlay.setColorAt(1, QColor(0, 0, 0, 180))
        p.fillRect(0, 0, w, h, overlay)

        # 3. 标题
        p.setPen(QColor("white"))
        title_font = QFont("PingFang SC", 20, QFont.Weight.Bold)
        p.setFont(title_font)
        title_rect = QRectF(24, h - 72, w - 48, 36)
        p.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title)

        # 4. 副标题
        p.setPen(QColor(255, 255, 255, 180))
        sub_font = QFont("PingFang SC", 12)
        p.setFont(sub_font)
        sub_rect = QRectF(24, h - 34, w - 48, 22)
        p.drawText(sub_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._subtitle)

        p.end()


# ── 阶段卡片 ──────────────────────────────────────────────────────────────

class StageCard(QWidget):
    def __init__(self, stage: dict, img_dir: Path, index: int):
        super().__init__()
        self.setStyleSheet(f"background: {BG};")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # ── 左侧：绿色编号列 ──────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(60)
        left.setStyleSheet("background: transparent;")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 16, 4, 0)
        left_l.setSpacing(2)

        # 编号 + 小绿点
        num_row = QWidget()
        num_row.setStyleSheet("background: transparent;")
        num_row_l = QHBoxLayout(num_row)
        num_row_l.setContentsMargins(0, 0, 0, 0)
        num_row_l.setSpacing(2)
        num_row_l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        num_lbl = QLabel(str(index))
        num_lbl.setFont(QFont("PingFang SC", 15, QFont.Weight.Bold))
        num_lbl.setStyleSheet(f"color: {ACCENT}; background: transparent;")
        num_row_l.addWidget(num_lbl)

        dot_lbl = QLabel("●")
        dot_lbl.setFont(QFont("PingFang SC", 8))
        dot_lbl.setStyleSheet(f"color: {ACCENT}; background: transparent;")
        num_row_l.addWidget(dot_lbl)

        left_l.addWidget(num_row)

        # 细连接线（贯穿到底）
        line_wrap = QWidget()
        line_wrap.setStyleSheet("background: transparent;")
        line_wrap_l = QHBoxLayout(line_wrap)
        line_wrap_l.setContentsMargins(0, 0, 0, 0)
        line_wrap_l.setSpacing(0)
        line_wrap_l.addStretch()
        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFixedWidth(1)
        vline.setStyleSheet("color: #dddddd;")
        line_wrap_l.addWidget(vline)
        line_wrap_l.addSpacing(4)
        left_l.addWidget(line_wrap, 1)

        row.addWidget(left)

        # ── 右侧：内容区 ─────────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(8, 12, 16, 20)
        right_l.setSpacing(8)

        # 日期
        pub = ts_to_str(stage.get("publishTs", 0))
        date_lbl = QLabel(pub)
        date_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 12px;")
        right_l.addWidget(date_lbl)

        # 内容卡片
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {BG_WHITE};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(16, 14, 16, 0)
        card_l.setSpacing(10)

        # 正文
        html = stage.get("html", "").strip()
        text = re.sub(r"<[^>]+>", "", html).strip()
        if text:
            text_lbl = QLabel(text)
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet(f"color: {FG}; font-size: 14px; line-height: 1.6; border: none;")
            text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            card_l.addWidget(text_lbl)

        # 图片
        img_field = stage.get("img", "")
        if img_field:
            stage_id = stage.get("stageId", "")
            for entry in img_field.split(","):
                img_url = entry.split("|")[0].strip()
                if not img_url:
                    continue
                tail = img_url.rstrip("/").split("/")[-1]
                tail = re.sub(r'[\\:*?"<>|]', '_', tail)
                img_name = f"stage_{stage_id}_{tail}"
                if "." not in img_name.split("_")[-1]:
                    img_name += ".jpg"
                img_path = img_dir / img_name
                if img_path.exists():
                    pix = QPixmap(str(img_path))
                    if not pix.isNull():
                        pix = pix.scaledToWidth(480, Qt.TransformationMode.SmoothTransformation)
                        img_lbl = QLabel()
                        img_lbl.setPixmap(pix)
                        img_lbl.setStyleSheet("border: none;")
                        card_l.addWidget(img_lbl)

        # 底部统计行（推荐 | 评论 | 点赞）三等分
        praise        = stage.get("praiseCount", 0)
        recommend     = stage.get("recommendCount", 0)
        comment_count = stage.get("commentCount", 0)

        stats_bar = QWidget()
        stats_bar.setStyleSheet("border: none; background: transparent;")
        stats_l = QHBoxLayout(stats_bar)
        stats_l.setContentsMargins(0, 8, 0, 4)
        stats_l.setSpacing(16)

        for icon, val in [("推荐", recommend), ("评论", comment_count), ("👍", praise)]:
            cell = QLabel(f"{icon} {val}")
            cell.setStyleSheet(f"color: {FG_DIM}; font-size: 12px; border: none; background: transparent;")
            stats_l.addWidget(cell)
        stats_l.addStretch()

        card_l.addWidget(stats_bar)

        # 评论列表
        comments = stage.get("comments", [])
        if comments:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {BORDER};")
            card_l.addWidget(sep)
            for c in comments:
                author  = c.get("commentAuthorNick", "匿名")
                content = re.sub(r"<[^>]+>", "", c.get("comment", "")).strip()
                ctime   = c.get("createdTsStr", "")
                reply   = c.get("commentParentNick", "")
                if reply and c.get("commentParentId"):
                    txt = f"<b>{author}</b> 回复 <b>{reply}</b>  <span style='color:{FG_DIM};font-size:11px;'>{ctime}</span><br>{content}"
                else:
                    txt = f"<b>{author}</b>  <span style='color:{FG_DIM};font-size:11px;'>{ctime}</span><br>{content}"
                c_lbl = QLabel(txt)
                c_lbl.setWordWrap(True)
                c_lbl.setStyleSheet(f"color: {FG}; font-size: 12px; border: none; padding: 4px 0;")
                c_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                card_l.addWidget(c_lbl)

        card_l.addSpacing(4)
        right_l.addWidget(card)
        row.addWidget(right, 1)


# ── 连载详情页 ────────────────────────────────────────────────────────────

class PlanDetailView(QWidget):
    back = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background: {BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶栏
        topbar = QWidget()
        topbar.setFixedHeight(48)
        topbar.setStyleSheet(f"background: {BG_WHITE}; border-bottom: 1px solid {BORDER};")
        top_l = QHBoxLayout(topbar)
        top_l.setContentsMargins(16, 0, 16, 0)

        back_btn = QPushButton("← 返回")
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {ACCENT}; font-size: 14px;
            }}
            QPushButton:hover {{ color: #3a7a50; }}
        """)
        back_btn.clicked.connect(self.back)
        top_l.addWidget(back_btn)
        top_l.addStretch()

        root.addWidget(topbar)

        # 内容滚动区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {BG}; }}
            QScrollBar:vertical {{ background: transparent; width: 4px; }}
            QScrollBar::handle:vertical {{ background: #cccccc; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._container = QWidget()
        self._container.setStyleSheet(f"background: {BG};")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 32)
        self._layout.setSpacing(0)
        self._layout.addStretch()
        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll)

    def load_plan(self, plan_dir: Path):
        # 清空
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        raw_path = plan_dir / "raw.json"
        if not raw_path.exists():
            return
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        plan   = raw.get("plan_info", {})
        stages = raw.get("stages", [])
        img_dir = plan_dir / "images"

        title = plan.get("goal", plan_dir.name)

        # 封面英雄横幅
        covers = list(img_dir.glob("cover.*")) if img_dir.exists() else []
        cover_path = covers[0] if covers else None

        witnesses  = plan.get("witnessCount", 0) or 0
        is_private = bool(plan.get("privacy", 0))
        subtitle_parts = [f"共 {len(stages)} 篇"]
        if witnesses:
            subtitle_parts.append(f"{witnesses} 人见证")
        if is_private:
            subtitle_parts.append("私密")
        subtitle = "  ·  ".join(subtitle_parts)

        hero = HeroCoverWidget(cover_path, title, subtitle)
        self._layout.insertWidget(self._layout.count() - 1, hero)


        # 阶段列表区域（带左边距的容器）
        stages_container = QWidget()
        stages_container.setStyleSheet(f"background: {BG};")
        stages_l = QVBoxLayout(stages_container)
        stages_l.setContentsMargins(16, 4, 0, 0)
        stages_l.setSpacing(0)  # 无间距，让左侧细线视觉上连续

        stages_sorted = sorted(stages, key=lambda s: s.get("publishTs", 0))
        total = len(stages_sorted)
        for i, stage in enumerate(reversed(stages_sorted)):
            card = StageCard(stage, img_dir, total - i)
            stages_l.addWidget(card)

        self._layout.insertWidget(self._layout.count() - 1, stages_container)
        self._scroll.verticalScrollBar().setValue(0)


# ── 主窗口 ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("轻想纪念版")
        self.setFixedSize(900, 680)
        self._backup_dir = None
        self._plan_dirs = []
        self._plan_metas = []
        self._settings = QSettings("lianzai", "reader")
        self.setAcceptDrops(True)
        self._build_ui()
        # 启动时恢复上次打开的文件夹
        self._restore_last_session()

    def _build_ui(self):
        self.setStyleSheet(f"QMainWindow {{ background: {BG}; }}")

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # 欢迎页
        welcome = QWidget()
        welcome.setStyleSheet(f"background: {BG_WHITE};")
        wl = QVBoxLayout(welcome)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.setSpacing(16)

        logo = QLabel("轻想纪念版")
        logo.setFont(QFont("PingFang SC", 28, QFont.Weight.Bold))
        logo.setStyleSheet(f"color: {ACCENT};")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("将备份文件夹拖入此处，或点击下方按钮打开")
        hint.setStyleSheet(f"color: {FG_DIM}; font-size: 14px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        open_btn = QPushButton("打开备份文件夹")
        open_btn.setFixedSize(180, 42)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: white;
                border: none; border-radius: 8px; font-size: 14px;
            }}
            QPushButton:hover {{ background: #4e9860; }}
        """)
        open_btn.clicked.connect(self._open_folder)

        wl.addWidget(logo)
        wl.addWidget(hint)
        wl.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._stack.addWidget(welcome)

        # 主页和详情页后续动态添加
        self._home_view = None
        self._detail_view = PlanDetailView()
        self._detail_view.back.connect(self._show_home)
        self._stack.addWidget(self._detail_view)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and Path(urls[0].toLocalFile()).is_dir():
                event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = Path(urls[0].toLocalFile())
            if path.is_dir():
                self._load_backup(path)

    def _open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择备份文件夹")
        if path:
            self._load_backup(Path(path))

    def _load_backup(self, backup_dir: Path):
        self._backup_dir = backup_dir
        self._save_to_history(backup_dir)

        # 读用户信息
        user_info = {}
        ui_path = backup_dir / "user_info.json"
        if ui_path.exists():
            user_info = json.loads(ui_path.read_text(encoding="utf-8"))

        # 读连载列表
        self._plan_dirs = sorted([
            d for d in backup_dir.iterdir()
            if d.is_dir() and (d / "raw.json").exists()
        ])

        self._plan_metas = []
        for d in self._plan_dirs:
            try:
                raw = json.loads((d / "raw.json").read_text(encoding="utf-8"))
                plan = raw.get("plan_info", {})
                stages = raw.get("stages", [])
                finished = bool(plan.get("isFinish", plan.get("planStatus", plan.get("status", 0)) in (2, "COMPLETE", "FINISHED")))
                self._plan_metas.append({
                    "title": plan.get("goal", d.name),
                    "count": len(stages),
                    "finished": finished,
                    "private": bool(plan.get("privacy", 0)),
                })
            except Exception:
                self._plan_metas.append({"title": d.name, "count": 0, "finished": False})

        # 移除旧主页
        if self._home_view:
            self._stack.removeWidget(self._home_view)
            self._home_view.deleteLater()

        self._home_view = HomeView(user_info, self._plan_dirs, self._plan_metas, backup_dir)
        self._home_view.plan_selected.connect(self._show_plan)
        self._home_view.switch_account.connect(self._switch_account_menu)
        self._stack.insertWidget(1, self._home_view)
        self._stack.setCurrentWidget(self._home_view)

    def _show_plan(self, idx: int):
        if 0 <= idx < len(self._plan_dirs):
            self._detail_view.load_plan(self._plan_dirs[idx])
            self._stack.setCurrentWidget(self._detail_view)

    def _show_home(self):
        if self._home_view:
            self._stack.setCurrentWidget(self._home_view)

    def _save_to_history(self, path: Path):
        """保存文件夹到历史记录（最多5个）"""
        history = self._settings.value("history", [])
        if not isinstance(history, list):
            history = [history] if history else []
        path_str = str(path)
        if path_str in history:
            history.remove(path_str)
        history.insert(0, path_str)
        history = history[:5]
        self._settings.setValue("history", history)
        self._update_combo(history)

    def _update_combo(self, history: list):
        pass  # combo 已移除，切换通过点横幅实现

    def _folder_display_name(self, path: Path) -> str:
        ui = path / "user_info.json"
        if ui.exists():
            try:
                info = json.loads(ui.read_text(encoding="utf-8"))
                nick = info.get("nickName", info.get("nickname", ""))
                if nick:
                    return nick
            except Exception:
                pass
        return path.name

    def _on_account_selected(self, idx: int):
        path_str = self._account_combo.itemData(idx)
        if path_str:
            self._load_backup(Path(path_str))

    def _switch_account_menu(self, anchor_x: int = -1, anchor_y: int = -1):
        """弹出账号切换浮层，定位在昵称标签正下方"""
        history = self._settings.value("history", [])
        if not isinstance(history, list):
            history = [history] if history else []
        valid = [p for p in history if Path(p).exists()]

        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setStyleSheet(f"""
            QFrame {{
                background: {BG_WHITE};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(20)
        effect.setOffset(0, 4)
        effect.setColor(QColor(0, 0, 0, 40))
        popup.setGraphicsEffect(effect)

        pop_l = QVBoxLayout(popup)
        pop_l.setContentsMargins(8, 10, 8, 10)
        pop_l.setSpacing(2)

        # 标题
        title = QLabel("我的记忆")
        title.setStyleSheet(f"color: {FG_DIM}; font-size: 11px; padding: 0 8px 4px 8px; border: none;")
        pop_l.addWidget(title)

        current = str(self._backup_dir) if self._backup_dir else ""

        for p in valid:
            name = self._folder_display_name(Path(p))
            is_current = p == current

            row = QWidget()
            row.setStyleSheet(f"""
                QWidget {{
                    background: {'#e8f5ec' if is_current else 'transparent'};
                    border-radius: 6px;
                    border-left: {'3px solid ' + ACCENT if is_current else '3px solid transparent'};
                }}
                QWidget:hover {{ background: #f0f8f2; }}
            """)
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(10, 6, 8, 6)
            row_l.setSpacing(8)

            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(f"color: {ACCENT if is_current else FG}; font-size: 13px; {'font-weight: bold;' if is_current else ''} border: none; background: transparent;")
            row_l.addWidget(name_lbl, 1)

            rm_btn = QPushButton("×")
            rm_btn.setFixedSize(18, 18)
            rm_btn.setStyleSheet(f"color: {FG_DIM}; background: transparent; border: none; font-size: 14px;")
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.clicked.connect(lambda _, path=p: self._remove_history(path, popup))
            row_l.addWidget(rm_btn)

            row.mousePressEvent = lambda e, path=p: (popup.close(), self._load_backup(Path(path)))
            pop_l.addWidget(row)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER}; border: none; background: {BORDER}; max-height: 1px; margin: 4px 0;")
        pop_l.addWidget(sep)

        # 添加按钮
        add_btn = QPushButton("+ 添加备份文件夹")
        add_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {ACCENT};
                           font-size: 13px; text-align: left; padding: 6px 10px; border-radius: 6px; }}
            QPushButton:hover {{ background: #f0f8f2; }}
        """)
        add_btn.clicked.connect(lambda: (popup.close(), self._open_folder()))
        pop_l.addWidget(add_btn)

        popup.adjustSize()
        # 定位：弹窗顶部中心对齐昵称标签底部中心，向下偏移 8px
        if anchor_x >= 0 and anchor_y >= 0:
            x = anchor_x - popup.width() // 2
            y = anchor_y + 8
        else:
            pos = QCursor.pos()
            x = pos.x() - popup.width() // 2
            y = pos.y() + 12
        # 防止超出屏幕右边
        screen_w = self.screen().geometry().width()
        if x + popup.width() > screen_w - 8:
            x = screen_w - popup.width() - 8
        if x < 8:
            x = 8
        popup.move(x, y)
        popup.show()

    def _remove_history(self, path: str, popup=None):
        if popup:
            popup.close()
        history = self._settings.value("history", [])
        if not isinstance(history, list):
            history = [history] if history else []
        if path in history:
            history.remove(path)
            self._settings.setValue("history", history)

    def _restore_last_session(self):
        history = self._settings.value("history", [])
        if not isinstance(history, list):
            history = [history] if history else []
        valid = [p for p in history if Path(p).exists()]
        self._update_combo(valid)
        if valid:
            self._load_backup(Path(valid[0]))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("PingFang SC", 13))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
