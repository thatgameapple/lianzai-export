"""
轻想连载数据导出工具
"""
import sys, re, json, time
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QProgressBar,
    QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont

import requests

# ── 主题色 ────────────────────────────────────────────────────────────────

BG       = "#ffffff"
BG_INPUT = "#f5f5f5"
BG_BTN   = "#eeeeee"
ACCENT   = "#5aab6e"
FG       = "#1a1a1a"
FG_DIM   = "#888888"
BORDER   = "#e0e0e0"
SUCCESS  = "#5aab6e"
ERROR    = "#d94f4f"


# ── 抓取逻辑（Worker 线程）────────────────────────────────────────────────

class ExportWorker(QThread):
    log      = pyqtSignal(str, str)    # message, color
    progress = pyqtSignal(int, int, str)  # current, total, plan_name
    finished = pyqtSignal(bool, str)   # success, message

    def __init__(self, uid: int, cookie: str, out_dir: Path):
        super().__init__()
        self.uid        = uid
        self.cookie     = cookie
        self.out_dir    = out_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.finished.emit(False, str(e))

    def _session(self):
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Cookie": self.cookie,
            "Referer": "https://www.lianzai365.com",
        })
        return s

    def _get(self, s, url, **kwargs):
        for attempt in range(3):
            try:
                return s.get(url, timeout=30, **kwargs)
            except Exception:
                if attempt == 2: raise
                time.sleep(3)

    def _post(self, s, url, **kwargs):
        for attempt in range(3):
            try:
                return s.post(url, timeout=30, **kwargs)
            except Exception:
                if attempt == 2: raise
                time.sleep(3)

    def _ts(self, ts):
        try:
            return datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(ts)

    def _safe_name(self, name: str) -> str:
        return re.sub(r'[/\\:*?"<>|]', '_', name).strip() or "未命名"

    def _download_image(self, s, url: str, path: Path) -> bool:
        if path.exists():
            return True
        try:
            r = s.get(url.split("|")[0], timeout=30)
            if r.status_code == 200:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                return True
        except Exception:
            pass
        return False

    def _run(self):
        s = self._session()

        # 1. 验证 Cookie + 获取用户信息
        self.log.emit("正在验证账号…", FG_DIM)
        r = self._post(s, "https://www.lianzai365.com/lianzai/PlanCtrl/showHomePage",
                       data={"uid": self.uid, "curPage": 1, "pageSize": 1})
        data = r.json()
        user = data.get("results", {}).get("userInfoDto", {})
        nickname = user.get("nickName", "")
        if not nickname:
            self.finished.emit(False, "Cookie 无效或已过期，请重新复制登录后的 Cookie")
            return
        self.log.emit(f"账号验证成功：{nickname}", SUCCESS)

        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "user_info.json").write_text(
            json.dumps(user, ensure_ascii=False, indent=2), encoding="utf-8")

        avatar = user.get("avatar", "")
        if avatar:
            ext = avatar.split(".")[-1].split("?")[0] or "jpg"
            self._download_image(s, avatar, self.out_dir / f"avatar.{ext}")

        # 2. 连载列表
        self.log.emit("正在获取连载列表…", FG_DIM)
        plans, page = [], 1
        while True:
            r = self._post(s, "https://www.lianzai365.com/lianzai/PlanCtrl/showHomePage",
                           data={"uid": self.uid, "curPage": page, "pageSize": 100})
            res = r.json().get("results", {})
            batch = res.get("userPlanDetailDtos", [])
            page_count = res.get("pageCount", 1)
            plans.extend(batch)
            if page >= page_count or not batch:
                break
            page += 1
            time.sleep(0.5)

        total = len(plans)
        self.log.emit(f"共找到 {total} 个连载，开始导出…", FG_DIM)

        skipped = 0
        failed  = 0
        for i, plan in enumerate(plans):
            if self._cancelled:
                self.finished.emit(False, "已取消")
                return
            title = plan.get("goal", f"连载_{plan.get('planId')}")
            self.progress.emit(i, total, title)
            try:
                did_skip = self._save_plan(s, plan, user)
                if did_skip:
                    skipped += 1
            except Exception as e:
                failed += 1
                self.log.emit(f"  ⚠️ 「{title}」导出失败：{e}", ERROR)
            time.sleep(0.5)

        self.progress.emit(total, total, "")
        summary = f"导出完成！共 {total} 个连载"
        if skipped:
            summary += f"，{skipped} 个已是最新（跳过）"
        if failed:
            summary += f"，{failed} 个失败"
        self.finished.emit(True, str(self.out_dir) + "|" + summary)

    def _save_plan(self, s, plan: dict, user: dict) -> bool:
        """返回 True 表示跳过（增量）"""
        plan_id    = plan.get("planId")
        plan_uid   = plan.get("uid", self.uid)
        title      = plan.get("goal", f"连载_{plan_id}")
        desc       = plan.get("description", "")
        cover_url  = plan.get("cover", "")
        is_private = plan.get("privacy", 0)
        created    = self._ts(plan.get("createdTs", 0))
        updated_ts = plan.get("updatedTs", 0)

        safe_title = self._safe_name(title)
        plan_dir = self.out_dir / safe_title
        # 如果目录已存在但 planId 不同，用 planId 区分
        if plan_dir.exists():
            existing_raw = plan_dir / "raw.json"
            if existing_raw.exists():
                try:
                    existing_id = json.loads(existing_raw.read_text(encoding="utf-8")).get("plan_info", {}).get("planId")
                    if existing_id and existing_id != plan_id:
                        plan_dir = self.out_dir / f"{safe_title}_{plan_id}"
                except Exception:
                    pass
        plan_dir.mkdir(exist_ok=True)
        img_dir = plan_dir / "images"
        img_dir.mkdir(exist_ok=True)

        # 增量检查：raw.json 存在且 updatedTs 没变则跳过
        raw_path = plan_dir / "raw.json"
        if raw_path.exists():
            try:
                existing = json.loads(raw_path.read_text(encoding="utf-8"))
                if existing.get("plan_info", {}).get("updatedTs") == updated_ts and updated_ts:
                    self.log.emit(f"  ✓ 「{title}」已是最新，跳过", FG_DIM)
                    return True
            except Exception:
                pass

        lock = "🔒 " if is_private else ""
        self.log.emit(f"  {lock}「{title}」", FG)

        if cover_url:
            tail = cover_url.split("|")[0].rstrip("/").split("/")[-1]
            ext = tail.split(".")[-1] if "." in tail else "jpg"
            self._download_image(s, cover_url.split("|")[0], img_dir / f"cover.{ext}")

        # 抓阶段
        stages, page = [], 1
        while True:
            r = self._get(s, "https://www.lianzai365.com/api/v2/stage/stages",
                          params={"planUid": plan_uid, "planId": plan_id,
                                  "curPage": page, "pageSize": 15,
                                  "isOrderByCreatedTsDesc": "false"})
            data = r.json()
            batch = data.get("results", {}).get("planStages", [])
            stages.extend(batch)
            if page >= data.get("pageCount", 1) or not batch:
                break
            page += 1
            time.sleep(0.3)

        # 生成 Markdown + 抓评论
        md = [f"# {title}\n"]
        if desc:
            md.append(f"> {desc}\n")
        md.append(f"创建时间：{created}  {'🔒 私密' if is_private else '🌐 公开'}\n")
        md.append("---\n")

        for i, stage in enumerate(stages, 1):
            stage_id      = stage.get("stageId", i)
            html_text     = stage.get("html", "").strip()
            img_field     = stage.get("img", "")
            pub_time      = self._ts(stage.get("publishTs", 0))
            praise        = stage.get("praiseCount", 0)
            comment_count = stage.get("commentCount", 0)

            clean = re.sub(r"<[^>]+>", "", html_text).strip()
            md.append(f"## 第 {i} 篇  `{pub_time}`\n")
            if clean:
                md.append(clean + "\n")

            if img_field:
                for entry in img_field.split(","):
                    img_url = entry.split("|")[0].strip()
                    if not img_url:
                        continue
                    tail = img_url.rstrip("/").split("/")[-1]
                    tail = re.sub(r'[\\:*?"<>|]', '_', tail)
                    img_name = f"stage_{stage_id}_{tail}"
                    if "." not in img_name.split("_")[-1]:
                        img_name += ".jpg"
                    if self._download_image(s, img_url, img_dir / img_name):
                        md.append(f"![图片](images/{img_name})\n")

            if praise or comment_count:
                md.append(f"*❤️ {praise}  💬 {comment_count}*\n")

            stage_comments = []
            if comment_count:
                stage_comments = self._fetch_comments(s, plan_id, stage_id)
                if stage_comments:
                    md.append("\n**评论：**\n")
                    for c in stage_comments:
                        author  = c.get("commentAuthorNick", "匿名")
                        content = re.sub(r"<[^>]+>", "", c.get("comment", "")).strip()
                        ctime   = c.get("createdTsStr", self._ts(c.get("createdTs", 0)))
                        reply   = c.get("commentParentNick", "")
                        if reply and c.get("commentParentId"):
                            md.append(f"> **{author}** 回复 **{reply}**（{ctime}）：{content}\n")
                        else:
                            md.append(f"> **{author}**（{ctime}）：{content}\n")
            stage["comments"] = stage_comments

            md.append("\n---\n")
            time.sleep(0.2)

        (plan_dir / "content.md").write_text("\n".join(md), encoding="utf-8")
        (plan_dir / "raw.json").write_text(
            json.dumps({"plan_info": plan, "user_info": user, "stages": stages},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        return False

    def _fetch_comments(self, s, plan_id, stage_id) -> list:
        comments, page = [], 1
        while True:
            for attempt in range(3):
                try:
                    r = s.post("https://www.lianzai365.com/lianzai/CommentCtrl/showPlanComment",
                               data={"planId": plan_id, "stageId": stage_id,
                                     "curPage": page, "pageSize": 15}, timeout=30)
                    data = r.json()
                    break
                except Exception:
                    if attempt == 2: return comments
                    time.sleep(2)
            results = data.get("results", [])
            batch = results if isinstance(results, list) else results.get("planComments", [])
            if not batch:
                break
            comments.extend(batch)
            if page >= data.get("pageCount", 1):
                break
            page += 1
            time.sleep(0.2)
        return comments


# ── 主窗口 ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("轻想连载 · 数据导出")
        self.setFixedSize(560, 780)
        self._worker   = None
        self._settings = QSettings("lianzai", "exporter")
        self._out_dir  = Path(self._settings.value(
            "out_dir", str(Path.home() / "Downloads" / "lianzai_backup")))
        self._build_ui()
        self._restore_settings()

    def _build_ui(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {BG}; color: {FG}; }}
            QLabel {{ color: {FG}; }}
            QLineEdit, QTextEdit {{
                background: {BG_INPUT}; color: {FG};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 8px 10px; font-size: 13px;
                selection-background-color: {ACCENT};
            }}
            QLineEdit:focus, QTextEdit:focus {{ border-color: {ACCENT}; }}
            QPushButton {{
                background: {BG_BTN}; color: {FG};
                border: none; border-radius: 6px;
                padding: 8px 18px; font-size: 13px;
            }}
            QPushButton:hover {{ background: #e0e0e0; }}
            QPushButton:disabled {{ color: {FG_DIM}; }}
            QProgressBar {{
                background: {BG_INPUT}; border: none; border-radius: 4px; height: 6px;
            }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #cccccc; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(32, 32, 32, 24)
        root.setSpacing(20)

        # 标题
        title = QLabel("轻想连载")
        title.setFont(QFont("PingFang SC", 22, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT};")
        sub = QLabel("数据导出工具  ·  备份你的记忆")
        sub.setStyleSheet(f"color: {FG_DIM}; font-size: 13px;")
        root.addWidget(title)
        root.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER};")
        root.addWidget(line)

        # UID
        self._uid_edit = QLineEdit()
        self._uid_edit.setPlaceholderText("你的轻想号")
        self._uid_edit.setFixedHeight(38)
        root.addWidget(self._uid_edit)

        # Cookie（分两行，更清晰）
        cookie_hint = QLabel("含私密内容必填 · F12 → Application → Cookies → www.lianzai365.com")
        cookie_hint.setStyleSheet(f"color: {FG_DIM}; font-size: 12px;")
        root.addWidget(cookie_hint)

        self._play_session_edit = QLineEdit()
        self._play_session_edit.setPlaceholderText("PLAY_SESSION 的值（点击该行后在下方 Cookie Value 复制）")
        self._play_session_edit.setFixedHeight(38)
        root.addWidget(self._label("PLAY_SESSION"))
        root.addWidget(self._play_session_edit)

        self._rememberme_edit = QLineEdit()
        self._rememberme_edit.setPlaceholderText("rememberme 的值")
        self._rememberme_edit.setFixedHeight(38)
        root.addWidget(self._label("rememberme"))
        root.addWidget(self._rememberme_edit)

        # 保存路径
        root.addWidget(self._label("保存位置"))
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._path_edit = QLineEdit(str(self._out_dir))
        self._path_edit.setFixedHeight(38)
        self._path_edit.setReadOnly(True)
        browse_btn = QPushButton("选择…")
        browse_btn.setFixedSize(90, 38)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self._path_edit)
        path_row.addWidget(browse_btn)
        root.addLayout(path_row)

        # 开始/取消按钮
        self._start_btn = QPushButton("开始导出")
        self._start_btn.setFixedHeight(42)
        self._start_btn.setStyleSheet(self._accent_btn_style())
        self._start_btn.clicked.connect(self._start)
        root.addWidget(self._start_btn)

        # 进度条 + 当前连载名
        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setValue(0)
        root.addWidget(self._progress)

        self._progress_lbl = QLabel("")
        self._progress_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 11px;")
        self._progress_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._progress_lbl)

        # 日志
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("导出日志将显示在这里…")
        self._log.setFont(QFont("Menlo", 12))
        self._log.setStyleSheet(f"""
            QTextEdit {{
                background: {BG_INPUT}; color: {FG_DIM};
                border: 1px solid {BORDER}; border-radius: 6px;
                padding: 8px; font-size: 12px;
            }}
        """)
        root.addWidget(self._log, 1)

        # 底部按钮行
        bottom = QHBoxLayout()
        hint = QLabel("导出完成后可直接在轻想纪念版中查看")
        hint.setStyleSheet(f"color: {FG_DIM}; font-size: 11px;")
        bottom.addWidget(hint)
        bottom.addStretch()
        self._open_reader_btn = QPushButton("打开轻想纪念版")
        self._open_reader_btn.setFixedHeight(30)
        self._open_reader_btn.setVisible(False)
        self._open_reader_btn.clicked.connect(self._open_reader)
        bottom.addWidget(self._open_reader_btn)
        root.addLayout(bottom)

    def _accent_btn_style(self, cancel=False):
        if cancel:
            return f"""
                QPushButton {{
                    background: #e0e0e0; color: {FG};
                    border: none; border-radius: 6px;
                    font-size: 14px; font-weight: bold;
                }}
                QPushButton:hover {{ background: #d0d0d0; }}
            """
        return f"""
            QPushButton {{
                background: {ACCENT}; color: white;
                border: none; border-radius: 6px;
                font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{ background: #4e9860; }}
            QPushButton:disabled {{ background: {BG_BTN}; color: {FG_DIM}; }}
        """

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 12px;")
        return lbl

    def _restore_settings(self):
        uid = self._settings.value("uid", "")
        if uid:
            self._uid_edit.setText(uid)

    def _save_settings(self):
        self._settings.setValue("uid", self._uid_edit.text().strip())
        self._settings.setValue("out_dir", str(self._out_dir))

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择保存位置", str(self._out_dir))
        if path:
            self._out_dir = Path(path)
            self._path_edit.setText(path)
            self._save_settings()

    def _start(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._start_btn.setText("开始导出")
            self._start_btn.setStyleSheet(self._accent_btn_style())
            return

        uid_text = self._uid_edit.text().strip()
        if not uid_text.isdigit():
            self._append_log("⚠️  请输入正确的轻想号（纯数字）", ERROR)
            return

        self._save_settings()
        uid = int(uid_text)
        ps  = self._play_session_edit.text().strip().strip('"')
        rm  = self._rememberme_edit.text().strip().strip('"')
        cookie = ""
        if ps:
            cookie += f'PLAY_SESSION="{ps}"'
        if rm:
            cookie += f'; rememberme="{rm}"' if cookie else f'rememberme="{rm}"'
        out_dir = Path(self._path_edit.text()) / f"lianzai_{uid}"

        self._log.clear()
        self._progress.setValue(0)
        self._progress.setMaximum(100)
        self._progress_lbl.setText("")
        self._open_reader_btn.setVisible(False)
        self._start_btn.setText("取消")
        self._start_btn.setStyleSheet(self._accent_btn_style(cancel=True))
        self._last_out_dir = out_dir

        self._worker = ExportWorker(uid, cookie, out_dir)
        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _append_log(self, msg: str, color: str = FG_DIM):
        self._log.append(f'<span style="color:{color};">{msg}</span>')

    def _on_progress(self, cur: int, total: int, plan_name: str):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(cur)
            if plan_name:
                self._progress_lbl.setText(f"{cur + 1} / {total}  {plan_name}")

    def _on_finished(self, success: bool, msg: str):
        self._start_btn.setText("开始导出")
        self._start_btn.setStyleSheet(self._accent_btn_style())
        self._progress_lbl.setText("")
        if success:
            out_dir, summary = msg.split("|", 1)
            self._append_log(f"\n✅ {summary}", SUCCESS)
            self._append_log(f"保存位置：{out_dir}", SUCCESS)
            self._progress.setValue(self._progress.maximum())
            self._open_reader_btn.setVisible(True)
        else:
            self._append_log(f"\n❌ {msg}", ERROR)

    def _open_reader(self):
        reader_path = Path(__file__).parent / "reader.py"
        if reader_path.exists():
            import subprocess
            subprocess.Popen([sys.executable, str(reader_path)])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("PingFang SC", 13))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
