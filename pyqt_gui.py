"""
B站评论采集 - PyQt5 界面
与 main.py (Tk) 功能一致：搜索视频 / Redis导入 / 账密登录(含短信验证) / 评论采集 / 日志输出
线程通过 Qt 信号槽回调主线程，无需轮询
"""
import os
import re
import sys
import time
import threading
from html import escape
from pathlib import Path

from PyQt5.QtCore import Qt, QObject, QPointF, QRectF, QTimer, pyqtSignal as Signal
from PyQt5.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QAbstractItemView, QDialog, QDoubleSpinBox, QFrame,
    QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QStackedLayout, QStyleFactory, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from loguru import logger as loguru_logger
import redis


# ---------- 颜色 ----------
C = {
    'primary':   '#1a73e8',
    'accent':    '#34a853',
    'warning':   '#f9ab00',
    'danger':    '#d93025',
    'text':      '#202124',
    'text_sub':  '#5f6368',
    'text_muted':'#9aa0a6',
}


# ---------- 全局样式 ----------
QSS = """
* { font-family: 'Microsoft YaHei UI', '微软雅黑', 'PingFang SC', sans-serif; outline: none; }

#root { background: #f4f6f9; }

QLabel { color: #202124; font-size: 13px; background: transparent; }
QLabel[role="title"] { font-size: 15px; font-weight: 700; }
QLabel[role="h2"]    { font-size: 14px; font-weight: 700; }
QLabel[role="sub"]   { color: #5f6368; font-size: 12px; }
QLabel[role="muted"] { color: #9aa0a6; font-size: 11px; }

#nav    { background: #ffffff; border-bottom: 1px solid #e3e6ea; }
#footer { background: #f1f3f4; border-top: 1px solid #e3e6ea; }
#footer QLabel { color: #9aa0a6; font-size: 11px; }

QFrame[card="true"] { background: #ffffff; border: 1px solid #e3e6ea; border-radius: 10px; }

QPushButton {
    background: #f1f3f4; color: #202124; border: none; border-radius: 7px;
    padding: 8px 18px; font-size: 13px; font-weight: 500;
}
QPushButton:hover   { background: #e2e6ea; }
QPushButton:pressed { background: #d7dce1; }
QPushButton:disabled{ background: #eceff1; color: #9aa0a6; }

QPushButton[variant="primary"] { background: #1a73e8; color: #ffffff; font-weight: 600; }
QPushButton[variant="primary"]:hover    { background: #1765cc; }
QPushButton[variant="primary"]:pressed  { background: #1557b0; }
QPushButton[variant="primary"]:disabled { background: #c9daf8; color: #ffffff; }

QPushButton[variant="success"] { background: #34a853; color: #ffffff; font-weight: 600; }
QPushButton[variant="success"]:hover    { background: #2d9249; }
QPushButton[variant="success"]:pressed  { background: #268042; }
QPushButton[variant="success"]:disabled { background: #bfe3c8; color: #ffffff; }

QPushButton[variant="danger"] { background: #ffffff; color: #d93025; border: 1px solid #f2b8b5; }
QPushButton[variant="danger"]:hover    { background: #fce8e6; }
QPushButton[variant="danger"]:pressed  { background: #f9d7d4; }
QPushButton[variant="danger"]:disabled { background: #f5f6f7; color: #bdc1c6; border-color: #e3e6ea; }

QPushButton[variant="ghost"] { background: transparent; color: #1a73e8; padding: 6px 14px; }
QPushButton[variant="ghost"]:hover    { background: #e8f0fe; }
QPushButton[variant="ghost"]:pressed  { background: #d2e3fc; }
QPushButton[variant="ghost"]:disabled { color: #bdc1c6; background: transparent; }

QLineEdit, QSpinBox, QDoubleSpinBox {
    background: #f7f9fb; border: 1px solid #d5dbe3; border-radius: 7px;
    padding: 6px 10px; font-size: 13px; color: #202124;
    selection-background-color: #1a73e8; selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    background: #ffffff; border: 1px solid #1a73e8;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background: #f1f3f4; color: #9aa0a6;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 16px; border: none; background: transparent; border-radius: 4px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #e8eaed; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid #5f6368; width: 0px; height: 0px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid #5f6368; width: 0px; height: 0px;
}

QTableWidget {
    background: #ffffff; alternate-background-color: #f8fafd;
    border: none; gridline-color: transparent; font-size: 12px; color: #202124;
    selection-background-color: #d2e3fc; selection-color: #174ea6;
}
QTableWidget::item { padding: 4px 8px; border: none; }
QHeaderView::section {
    background: #1a73e8; color: #ffffff; border: none;
    padding: 9px 12px; font-size: 12px; font-weight: 600;
}
QHeaderView::section:first { border-top-left-radius: 8px; }
QHeaderView::section:last  { border-top-right-radius: 8px; }
QTableCornerButton::section { background: #1a73e8; border: none; border-top-right-radius: 8px; }

QProgressBar {
    background: #e8eaed; border: none; border-radius: 3px;
    min-height: 6px; max-height: 6px;
}
QProgressBar::chunk { background: #1a73e8; border-radius: 3px; }

QPlainTextEdit#log { background: #fbfcfe; border: none; color: #3c4043; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #cdd2d9; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #aab2bd; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #cdd2d9; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #aab2bd; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QDialog, QMessageBox { background: #ffffff; }
QToolTip { background: #202124; color: #ffffff; border: none; padding: 6px 8px; }
"""


# ---------- loguru -> Qt 桥接 ----------
class _LogBridge(QObject):
    msg = Signal(str)

    def write(self, message: str):
        msg = message.strip()
        if msg:
            self.msg.emit(msg)

    def flush(self):
        pass


class _Bridge(QObject):
    """后台线程 -> 主线程 结果桥"""
    done = Signal(object)


# ---------- 工作线程 ----------
def _search_worker(keyword, pages, emit, stop_event):
    try:
        from get_id import get_video_ids, save_to_redis
        if stop_event.is_set():
            return
        videos = get_video_ids(keyword=keyword, pages=pages)
        if videos and not stop_event.is_set():
            try:
                save_to_redis(videos)
            except Exception as e:
                loguru_logger.warning(f'Redis写入失败: {e}')
        if not stop_event.is_set():
            emit(('ok', videos))
    except Exception as e:
        emit(('error', str(e)))


def _login_worker(username, password, emit, stop_event):
    try:
        from bilibili_login import get_login_cookie
        if stop_event.is_set():
            return
        cookies = get_login_cookie(username=username, password=password)
        if not cookies:
            emit(('error', '登录失败'))
            return
        if stop_event.is_set():
            return
        if isinstance(cookies, dict) and cookies.get('need_sms'):
            emit(('sms', cookies))
        else:
            emit(('ok', cookies))
    except Exception as e:
        emit(('error', str(e)))


def _sms_worker(url, emit, stop_event):
    """打开浏览器让用户手动完成短信验证，然后抓取cookie"""
    try:
        from DrissionPage import Chromium, ChromiumOptions
        if stop_event.is_set():
            return
        co = ChromiumOptions()
        browser = Chromium(co)
        try:
            tab = browser.latest_tab
            tab.get(url)
            # 等待用户完成短信验证并跳转，最长 120s
            for i in range(240):
                if stop_event.is_set():
                    return
                time.sleep(0.5)
                current_url = tab.url
                if 'account/home' in current_url or current_url == 'https://www.bilibili.com/':
                    break
            time.sleep(1)
            cookies = {}
            for c in tab.get_cookies():
                cookies[c['name']] = c['value']
            if cookies.get('SESSDATA') and cookies.get('bili_jct'):
                emit(('ok', cookies))
            else:
                emit(('error', '短信验证后未获取到有效Cookie，请确认已完成验证'))
        finally:
            browser.quit()
    except Exception as e:
        emit(('error', str(e)))


def _collect_worker(oid, cookies, img_key, sub_key, bvid, title, pages, emit, stop_event):
    try:
        from comment import BiliCollector
        if stop_event.is_set():
            return
        BiliCollector.collect_comments(
            oid=oid, cookies=cookies, img_key=img_key, sub_key=sub_key,
            bvid=bvid, title=title, pages=pages,
        )
        if not stop_event.is_set():
            emit(('ok', f'{bvid} 采集完成'))
    except Exception as e:
        emit(('error', f'{bvid} 采集异常: {e}'))


def _import_worker(videos: dict, emit):
    """后台加载 Redis 视频详情（并发请求）"""
    import requests as req
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def fetch_one(bvid_oid):
        bvid, oid = bvid_oid
        try:
            resp = req.get(
                f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}',
                headers={'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                timeout=8,
            ).json()
            if resp.get('code') == 0:
                d = resp['data']
                return bvid, oid, d.get('title', ''), d.get('stat', {}).get('reply', 0)
        except Exception:
            pass
        return bvid, oid, '(请求失败)', 0

    try:
        items = list(videos.items())
        total = len(items)
        loguru_logger.info(f'开始并发加载 {total} 个视频详情')
        video_list = []
        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fetch_one, (bvid, oid)): bvid for bvid, oid in items}
            for future in as_completed(futures):
                bvid, oid, title, reply_count = future.result()
                video_list.append({'bvid': bvid, 'oid': oid, 'title': title, 'reply_count': reply_count})
                done += 1
                if done % 20 == 0:
                    loguru_logger.info(f'导入进度: {done}/{total}')
        emit(('ok', video_list))
    except Exception as e:
        loguru_logger.error(f'导入线程异常: {e}')
        emit(('error', str(e)))


# ---------- Logo（代码绘制，B站小电视风格） ----------
def make_logo_pixmap(size: int, color: str = C['primary']) -> QPixmap:
    """绘制 B站小电视风格 logo：圆角机身 + 双天线 + 双眼（纯代码，无需素材）"""
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = float(size * 2)
    blue = QColor(color)

    # 双天线（圆头线条，尖端压进机身）
    pen = QPen(blue, s * 0.08)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.30, s * 0.12), QPointF(s * 0.42, s * 0.28))
    p.drawLine(QPointF(s * 0.70, s * 0.12), QPointF(s * 0.58, s * 0.28))

    # 机身
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(blue))
    p.drawRoundedRect(QRectF(s * 0.08, s * 0.26, s * 0.84, s * 0.60), s * 0.14, s * 0.14)

    # 双眼（白色圆角竖条）
    p.setBrush(QBrush(QColor('#ffffff')))
    eye_w, eye_h = s * 0.09, s * 0.20
    p.drawRoundedRect(QRectF(s * 0.35 - eye_w / 2, s * 0.46, eye_w, eye_h), eye_w / 2, eye_w / 2)
    p.drawRoundedRect(QRectF(s * 0.65 - eye_w / 2, s * 0.46, eye_w, eye_h), eye_w / 2, eye_w / 2)

    p.end()
    pm.setDevicePixelRatio(2)
    return pm


# ---------- 小部件 ----------
class SelectAllEdit(QLineEdit):
    """获得焦点时全选文本"""
    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.selectAll()


def _vline():
    sep = QFrame()
    sep.setFixedSize(1, 22)
    sep.setStyleSheet('background-color: #e6e9ee; border: none;')
    return sep


# ---------- 主窗口 ----------
class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('B站评论采集')
        self.setWindowIcon(QIcon(make_logo_pixmap(64)))
        self.resize(1100, 880)
        self.setMinimumSize(920, 640)

        # 线程控制 ──
        self._stop_event = threading.Event()
        self._closing = False
        self._busy = False            # 是否有后台任务进行中

        # 数据 ──
        self._videos: list[dict] = []
        self._cookies: dict = {}
        self._img_key = ''
        self._sub_key = ''

        # 采集 ──
        self._collecting = False
        self._collect_threads: list[threading.Thread] = []
        self._collect_bvids: list[str] = []
        self._collect_idx = 0
        self._collect_timer = QTimer(self)
        self._collect_timer.setSingleShot(True)
        self._collect_timer.timeout.connect(self._launch_next)

        # 日志桥接 ──
        self._log_bridge = _LogBridge()
        self._log_bridge.msg.connect(self._append_log, Qt.QueuedConnection)
        loguru_logger.remove()
        loguru_logger.add(
            self._log_bridge.write,
            format='<green>{time:HH:mm:ss}</green> | {level:8} | {message}',
            level='INFO',
            colorize=False,
        )

        # 结果桥 ──
        self._search_bridge = _Bridge()
        self._search_bridge.done.connect(self._on_search_done, Qt.QueuedConnection)
        self._login_bridge = _Bridge()
        self._login_bridge.done.connect(self._on_login_done, Qt.QueuedConnection)
        self._sms_bridge = _Bridge()
        self._sms_bridge.done.connect(self._on_sms_done, Qt.QueuedConnection)
        self._import_bridge = _Bridge()
        self._import_bridge.done.connect(self._on_import_done, Qt.QueuedConnection)
        self._collect_bridge = _Bridge()
        self._collect_bridge.done.connect(self._on_collect_done, Qt.QueuedConnection)

        self._build_ui()
        self._center()

    def _center(self):
        screen = QApplication.primaryScreen().availableGeometry()
        geo = self.frameGeometry()
        geo.moveCenter(screen.center())
        self.move(geo.topLeft())

    # ---------- UI ----------
    def _build_ui(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)

        page = QVBoxLayout(root)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)

        page.addWidget(self._build_nav())

        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 10)
        body.setSpacing(10)
        page.addLayout(body)

        body.addWidget(self._build_search_card())
        body.addLayout(self._build_table_section(), 1)
        body.addWidget(self._build_op_card())
        body.addWidget(self._build_log_card())
        page.addWidget(self._build_footer())

    def _build_nav(self):
        nav = QFrame()
        nav.setObjectName('nav')
        nav.setFixedHeight(56)
        h = QHBoxLayout(nav)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(make_logo_pixmap(28))
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignCenter)
        h.addWidget(logo)
        title = QLabel('B站评论采集')
        title.setProperty('role', 'title')
        h.addWidget(title)
        h.addStretch()

        self._stats = QLabel('')
        self._stats.setProperty('role', 'sub')
        h.addWidget(self._stats)
        h.addSpacing(12)

        self._badge = QLabel(' 未登录 ')
        self._set_badge('未登录', C['danger'], '#fce8e6')
        h.addWidget(self._badge)
        return nav

    def _card(self):
        card = QFrame()
        card.setProperty('card', True)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(15, 23, 42, 26))
        card.setGraphicsEffect(shadow)
        return card

    def _build_search_card(self):
        card = self._card()
        h = QHBoxLayout(card)
        h.setContentsMargins(18, 14, 18, 14)
        h.setSpacing(10)

        t = QLabel('搜索视频')
        t.setProperty('role', 'h2')
        h.addWidget(t)
        h.addSpacing(6)

        self._kw = SelectAllEdit()
        self._kw.setPlaceholderText('输入关键词，回车搜索')
        self._kw.setText('罗翔说刑法合集')
        self._kw.setClearButtonEnabled(True)
        self._kw.returnPressed.connect(self._on_search)
        h.addWidget(self._kw, 1)

        lbl = QLabel('搜索页数')
        lbl.setProperty('role', 'sub')
        h.addWidget(lbl)
        self._search_pages = QSpinBox()
        self._search_pages.setRange(1, 20)
        self._search_pages.setValue(3)
        self._search_pages.setFixedWidth(72)
        h.addWidget(self._search_pages)

        self._search_btn = QPushButton('搜索')
        self._search_btn.setProperty('variant', 'primary')
        self._search_btn.clicked.connect(self._on_search)
        h.addWidget(self._search_btn)

        self._search_pb = QProgressBar()
        self._search_pb.setRange(0, 0)          # 不确定进度
        self._search_pb.setFixedWidth(90)
        self._search_pb.hide()
        h.addWidget(self._search_pb)
        return card

    def _build_table_section(self):
        wrap = QVBoxLayout()
        wrap.setContentsMargins(4, 0, 4, 0)
        wrap.setSpacing(6)

        head = QHBoxLayout()
        t = QLabel('视频列表')
        t.setProperty('role', 'h2')
        head.addWidget(t)
        tip = QLabel('Ctrl+点击 可多选')
        tip.setProperty('role', 'muted')
        head.addSpacing(8)
        head.addWidget(tip)
        head.addStretch()
        self._import_btn = QPushButton('导入')
        self._import_btn.setProperty('variant', 'ghost')
        self._import_btn.clicked.connect(self._on_import)
        head.addWidget(self._import_btn)
        wrap.addLayout(head)

        card = self._card()
        wrap.addWidget(card, 1)

        stack = QStackedLayout(card)
        stack.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(['BV号', '标题', '评论数'])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(34)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 150)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._table.setColumnWidth(2, 90)
        self._table.itemSelectionChanged.connect(self._on_table_select)
        stack.addWidget(self._table)

        empty_page = QWidget()
        ev = QVBoxLayout(empty_page)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.addStretch()
        self._empty_hint = QLabel('暂无视频，请先搜索或导入')
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setProperty('role', 'muted')
        ev.addWidget(self._empty_hint)
        ev.addStretch()
        stack.addWidget(empty_page)

        self._stack = stack
        stack.setCurrentIndex(1)
        return wrap

    def _build_op_card(self):
        card = self._card()
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(10)

        # 第一行: 账号 + 密码 + 参数 + 登录
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        t = QLabel('操作区')
        t.setProperty('role', 'h2')
        row1.addWidget(t)
        row1.addWidget(_vline())

        for label, widget in self._op_fields():
            row1.addWidget(label)
            row1.addWidget(widget)

        row1.addStretch()
        self._login_btn = QPushButton('登录')
        self._login_btn.setProperty('variant', 'primary')
        self._login_btn.clicked.connect(self._on_login)
        row1.addWidget(self._login_btn)
        v.addLayout(row1)

        # 第二行: 采集按钮
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self._collect_one_btn = QPushButton('采集选中')
        self._collect_one_btn.setProperty('variant', 'success')
        self._collect_one_btn.clicked.connect(self._on_collect_one)
        row2.addWidget(self._collect_one_btn)
        self._collect_all_btn = QPushButton('采集全部')
        self._collect_all_btn.setProperty('variant', 'success')
        self._collect_all_btn.clicked.connect(self._on_collect_all)
        row2.addWidget(self._collect_all_btn)
        self._stop_btn = QPushButton('停止')
        self._stop_btn.setProperty('variant', 'danger')
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        row2.addWidget(self._stop_btn)
        row2.addStretch()

        self._collect_pb = QProgressBar()
        self._collect_pb.setRange(0, 0)
        self._collect_pb.setFixedWidth(170)
        self._collect_pb.hide()
        row2.addWidget(self._collect_pb)
        v.addLayout(row2)
        return card

    def _op_fields(self):
        def sub(text):
            lbl = QLabel(text)
            lbl.setProperty('role', 'sub')
            return lbl

        self._user = QLineEdit()
        self._user.setPlaceholderText('手机号')
        self._user.setFixedWidth(150)
        self._pwd = QLineEdit()
        self._pwd.setPlaceholderText('密码')
        self._pwd.setEchoMode(QLineEdit.Password)
        self._pwd.setFixedWidth(150)
        self._pages_spin = QSpinBox()
        self._pages_spin.setRange(1, 50)
        self._pages_spin.setValue(5)
        self._pages_spin.setFixedWidth(72)
        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.0, 120.0)
        self._interval_spin.setSingleStep(0.5)
        self._interval_spin.setDecimals(1)
        self._interval_spin.setValue(2.0)
        self._interval_spin.setFixedWidth(86)

        return [
            (sub('账号'), self._user),
            (sub('密码'), self._pwd),
            (sub('评论页数'), self._pages_spin),
            (sub('间隔(秒)'), self._interval_spin),
        ]

    def _build_log_card(self):
        card = self._card()
        v = QVBoxLayout(card)
        v.setContentsMargins(1, 1, 1, 1)
        v.setSpacing(0)
        card.setFixedHeight(150)

        # 注意：本机 Qt 5.15.2 的 QTextEdit.append* 存在崩溃问题，
        # 日志控件使用 QPlainTextEdit.appendHtml（已验证可用）
        self._log = QPlainTextEdit()
        self._log.setObjectName('log')
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self._log.setMaximumBlockCount(2000)
        f = QFont()
        f.setFamilies(['Cascadia Mono', 'Cascadia Code', 'Consolas', 'Courier New'])
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(9)
        self._log.setFont(f)
        v.addWidget(self._log)
        return card

    def _build_footer(self):
        footer = QFrame()
        footer.setObjectName('footer')
        footer.setFixedHeight(26)
        h = QHBoxLayout(footer)
        h.setContentsMargins(14, 0, 14, 0)
        self._footer = QLabel('就绪')
        h.addWidget(self._footer)
        h.addStretch()
        ver = QLabel('PyQt5')
        h.addWidget(ver)
        return footer

    # ---------- 通用 ----------
    def _set_status(self, text: str):
        self._footer.setText(text)

    def _set_badge(self, text: str, fg: str, bg: str):
        self._badge.setText(f' {text} ')
        self._badge.setStyleSheet(
            f"QLabel {{ color: {fg}; background: {bg}; border-radius: 10px;"
            f" padding: 3px 12px; font-size: 12px; font-weight: 600; }}"
        )

    def _repolish(self, w):
        w.style().unpolish(w)
        w.style().polish(w)

    def _clear_table(self, hint='暂无视频，请先搜索或导入'):
        self._table.setRowCount(0)
        self._empty_hint.setText(hint)
        self._stack.setCurrentIndex(1)

    def _refresh_table(self):
        self._table.setRowCount(0)
        for v in self._videos:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(v['bvid'])))
            self._table.setItem(row, 1, QTableWidgetItem(str(v.get('title', ''))))
            rc = QTableWidgetItem(str(v.get('reply_count', '')))
            rc.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 2, rc)
        self._stack.setCurrentIndex(0 if self._videos else 1)

    # ---------- 日志 ----------
    _LOG_RE = re.compile(r'^(\d{2}:\d{2}:\d{2})\s*\|\s*([A-Z]+)\s*\|\s*(.*)$')
    _LEVEL_COLOR = {
        'DEBUG':    '#9aa0a6',
        'INFO':     '#4a5568',
        'SUCCESS':  '#188038',
        'WARNING':  '#e37400',
        'ERROR':    '#d93025',
        'CRITICAL': '#d93025',
    }

    def _append_log(self, msg: str):
        try:
            m = self._LOG_RE.match(msg)
            if m:
                t, lvl, rest = m.groups()
                color = self._LEVEL_COLOR.get(lvl, '#4a5568')
                self._log.appendHtml(
                    f'<span style="color:#9aa0a6;">{t}</span>'
                    f'<span style="color:#c9cdd4;"> | </span>'
                    f'<span style="color:{color}; font-weight:600;">{lvl}</span>'
                    f'<span style="color:#c9cdd4;"> | </span>'
                    f'<span style="color:#3c4043;">{escape(rest)}</span>'
                )
            else:
                self._log.appendHtml(f'<span style="color:#3c4043;">{escape(msg)}</span>')
            sb = self._log.verticalScrollBar()
            sb.setValue(sb.maximum())
        except RuntimeError:
            pass  # 窗口已销毁

    # ---------- 搜索 ----------
    def _on_search(self):
        if self._busy:
            return
        keyword = self._kw.text().strip()
        if not keyword:
            return

        self._busy = True
        self._stop_event.clear()
        self._search_btn.setEnabled(False)
        self._search_btn.setText('搜索中...')
        self._search_pb.show()
        self._set_status('正在搜索 B站...')
        self._clear_table('正在搜索，请稍候...')

        t = threading.Thread(
            target=_search_worker,
            args=(keyword, self._search_pages.value(), self._search_bridge.done.emit, self._stop_event),
            daemon=True,
        )
        t.start()

    def _on_search_done(self, payload):
        if self._closing:
            return
        self._search_btn.setEnabled(True)
        self._search_btn.setText('搜索')
        self._search_pb.hide()
        self._busy = False

        status, data = payload
        if status == 'ok':
            self._videos = data
            self._refresh_table()
            self._stats.setText(f'共 {len(data)} 个视频')
            self._set_status(f'搜索完成，找到 {len(data)} 个视频')
        else:
            self._set_status('搜索失败')
            QMessageBox.critical(self, '搜索失败', str(data))

    # ---------- 导入 ----------
    def _on_import(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('导入视频')
        dlg.setFixedSize(380, 190)

        g = QGridLayout(dlg)
        g.setContentsMargins(24, 20, 24, 16)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(10)

        lb1 = QLabel('DB 编号')
        db = QSpinBox()
        db.setRange(0, 15)
        db.setValue(0)
        g.addWidget(lb1, 0, 0, Qt.AlignRight)
        g.addWidget(db, 0, 1)

        lb2 = QLabel('Hash 键名')
        key = QLineEdit('bilibili_id')
        g.addWidget(lb2, 1, 0, Qt.AlignRight)
        g.addWidget(key, 1, 1)

        status_lbl = QLabel('')
        status_lbl.setProperty('role', 'muted')
        g.addWidget(status_lbl, 2, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton('导入')
        ok.setProperty('variant', 'primary')
        cancel = QPushButton('取消')
        btns.addWidget(ok)
        btns.addSpacing(6)
        btns.addWidget(cancel)
        g.addLayout(btns, 3, 0, 1, 2)
        cancel.clicked.connect(dlg.reject)

        def do_import():
            k = key.text().strip()
            if not k:
                status_lbl.setText('请输入键名')
                return
            try:
                r = redis.Redis(
                    host='localhost', port=6379, db=db.value(),
                    password=os.environ.get('REDIS_PASSWORD', '123456'),
                    decode_responses=True,
                )
                videos = r.hgetall(k)
                if not videos:
                    status_lbl.setText('键为空或无数据')
                    return
                dlg.accept()
                self._begin_import(videos)
            except Exception as e:
                status_lbl.setText(f'连接失败: {e}')

        ok.clicked.connect(do_import)
        dlg.exec_()

    def _begin_import(self, videos: dict):
        self._import_btn.setEnabled(False)
        self._import_btn.setText('加载中...')
        self._stats.setText('加载中...')
        self._clear_table('正在加载视频详情...')
        t = threading.Thread(target=_import_worker, args=(videos, self._import_bridge.done.emit), daemon=True)
        t.start()

    def _on_import_done(self, payload):
        if self._closing:
            return
        self._import_btn.setEnabled(True)
        self._import_btn.setText('导入')

        status, data = payload
        if status == 'ok':
            self._videos = data
            self._refresh_table()
            self._stats.setText(f'共 {len(data)} 个视频')
            self._set_status(f'导入完成，共 {len(data)} 个视频')
            loguru_logger.success(f'导入完成，共 {len(data)} 个视频')
        else:
            self._set_status('导入失败')
            QMessageBox.critical(self, '导入失败', str(data))

    def _on_table_select(self):
        rows = sorted({i.row() for i in self._table.selectedItems()})
        if not rows:
            return
        if len(rows) == 1:
            bvid = self._table.item(rows[0], 0).text()
            video = next((v for v in self._videos if v['bvid'] == bvid), {})
            title = str(video.get('title', ''))
            if len(title) > 60:
                title = title[:60] + '...'
            self._set_status(f'选中: {bvid}  {title}')
        else:
            self._set_status(f'已选中 {len(rows)} 个视频')

    # ---------- 登录 ----------
    def _on_login(self):
        if self._busy:
            return
        username = self._user.text().strip()
        password = self._pwd.text().strip()
        if not username or not password:
            QMessageBox.warning(self, '提示', '请输入账号和密码')
            return

        self._busy = True
        self._stop_event.clear()
        self._login_btn.setEnabled(False)
        self._login_btn.setText('登录中...')
        self._login_btn.setProperty('variant', 'primary')
        self._repolish(self._login_btn)
        self._set_badge('登录中...', '#b06000', '#fef7e0')
        self._set_status('正在登录，验证码识别中...')

        t = threading.Thread(
            target=_login_worker,
            args=(username, password, self._login_bridge.done.emit, self._stop_event),
            daemon=True,
        )
        t.start()

    def _on_login_done(self, payload):
        if self._closing:
            return
        status, data = payload

        if status == 'ok':
            self._busy = False
            self._set_logged_in(data)
            loguru_logger.success('登录成功')
        elif status == 'sms':
            # 需要短信验证
            QMessageBox.information(
                self, '短信验证',
                '已触发短信风控，将打开浏览器，请手动完成短信验证后关闭浏览器窗口')
            self._login_btn.setEnabled(False)
            self._login_btn.setText('短信验证中...')
            self._set_badge('短信验证...', '#b06000', '#fef7e0')
            self._set_status('请在浏览器中完成短信验证...')
            self._busy = True
            t = threading.Thread(
                target=_sms_worker,
                args=(data['url'], self._sms_bridge.done.emit, self._stop_event),
                daemon=True,
            )
            t.start()
        else:
            self._busy = False
            self._cookies = {}
            self._set_badge('未登录', C['danger'], '#fce8e6')
            self._set_status('登录失败')
            self._login_btn.setEnabled(True)
            self._login_btn.setText('登录')
            QMessageBox.critical(self, '登录失败', str(data))

    def _on_sms_done(self, payload):
        if self._closing:
            return
        self._busy = False
        status, data = payload
        if status == 'ok':
            self._set_logged_in(data)
            loguru_logger.success('短信验证完成，登录成功')
        else:
            self._set_badge('未登录', C['danger'], '#fce8e6')
            self._set_status('短信验证失败')
            QMessageBox.critical(self, '登录失败', str(data))
        self._login_btn.setEnabled(True)
        self._login_btn.setText('登录')

    def _set_logged_in(self, cookies):
        self._cookies = cookies
        try:
            from comment import BiliAuth
            bili_jct = cookies.get('bili_jct', '')
            _, self._img_key, self._sub_key = BiliAuth.build_cookies(bili_jct)
        except Exception:
            self._img_key, self._sub_key = '', ''
        self._login_btn.setText('已登录')
        self._login_btn.setProperty('variant', 'success')
        self._repolish(self._login_btn)
        self._set_badge('已登录', '#188038', '#e6f4ea')
        self._set_status('登录成功')

    # ---------- 采集 ----------
    def _selected_bvids(self):
        rows = sorted({i.row() for i in self._table.selectedItems()})
        return [self._table.item(r, 0).text() for r in rows]

    def _on_collect_one(self):
        bvids = self._selected_bvids()
        if not bvids:
            QMessageBox.warning(self, '提示', '请先在列表中选中视频 (Ctrl+点击多选)')
            return
        if len(bvids) == 1:
            self._start_collect(bvids)
        else:
            if QMessageBox.question(self, '确认', f'已选中 {len(bvids)} 个视频，开始采集？') == QMessageBox.Yes:
                self._start_collect(bvids)

    def _on_collect_all(self):
        if not self._videos:
            QMessageBox.warning(self, '提示', '请先搜索视频')
            return
        self._start_collect([v['bvid'] for v in self._videos])

    def _start_collect(self, bvids):
        if not self._cookies:
            QMessageBox.warning(self, '提示', '请先登录')
            return
        if self._collecting:
            return
        if self._busy:
            QMessageBox.warning(self, '提示', '请等待当前任务完成')
            return

        self._collecting = True
        self._busy = True
        self._stop_event.clear()
        self._set_collect_buttons(True)

        self._collect_bvids = list(bvids)
        self._collect_idx = 0
        self._launch_next()

    def _launch_next(self):
        if not self._collecting or self._collect_idx >= len(self._collect_bvids):
            self._finish_collect()
            return

        bvid = self._collect_bvids[self._collect_idx]
        video = next((v for v in self._videos if v['bvid'] == bvid), {})
        oid = video.get('oid', bvid)
        title = str(video.get('title', ''))
        pages = self._pages_spin.value()

        idx = self._collect_idx + 1
        total = len(self._collect_bvids)
        self._set_status(f'采集 [{idx}/{total}] {bvid}  {title[:50]}')

        t = threading.Thread(
            target=_collect_worker,
            args=(oid, self._cookies, self._img_key, self._sub_key,
                  bvid, title, pages, self._collect_bridge.done.emit, self._stop_event),
            daemon=True,
        )
        self._collect_threads.append(t)
        t.start()

    def _on_collect_done(self, payload):
        # 移除已结束的线程引用
        if self._collect_threads:
            self._collect_threads.pop(0)

        status, data = payload
        if status == 'ok':
            loguru_logger.success(data)
        else:
            loguru_logger.error(data)

        if not self._collecting or self._closing:
            return

        self._collect_idx += 1
        interval = self._interval_spin.value()
        self._set_status(f'等待 {interval:.1f}s 后继续下一个视频...')
        self._collect_timer.start(int(interval * 1000))

    def _finish_collect(self):
        self._collecting = False
        self._busy = False
        self._set_collect_buttons(False)
        self._set_status('采集完成')
        loguru_logger.success('全部采集完成')

    def _on_stop(self):
        """停止采集：设置停止标记，让子线程自行结束"""
        self._collecting = False
        self._stop_event.set()
        self._busy = False
        self._collect_timer.stop()
        self._set_collect_buttons(False)
        self._set_status('已停止')

        # 后台等待线程退出，不阻塞界面
        threads = list(self._collect_threads)
        self._collect_threads.clear()
        threading.Thread(target=self._join_threads, args=(threads,), daemon=True).start()

        loguru_logger.warning('用户手动停止')

    @staticmethod
    def _join_threads(threads):
        for t in threads:
            t.join(timeout=2.0)

    def _set_collect_buttons(self, active):
        for b in (self._collect_one_btn, self._collect_all_btn,
                  self._login_btn, self._search_btn):
            b.setEnabled(not active)
        self._stop_btn.setEnabled(active)
        self._collect_pb.setVisible(active)
        if active:
            self._set_status('采集进行中...')

    # ---------- 关闭 ----------
    def closeEvent(self, event):
        self._closing = True
        self._stop_event.set()
        self._collecting = False
        self._collect_timer.stop()
        # 给线程一点时间自行结束
        for t in list(self._collect_threads):
            t.join(timeout=1.5)
        self._collect_threads.clear()
        event.accept()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))
    app.setStyleSheet(QSS)
    app.setFont(QFont('Microsoft YaHei UI', 9))
    app.setWindowIcon(QIcon(make_logo_pixmap(64)))
    window = App()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
