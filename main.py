"""
B站评论采集 - TK界面
"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import time
import sys
import os
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from loguru import logger as loguru_logger
import redis


# ---------- loguru -> tk 桥接 ----------
class TkLogSink:
    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, message: str):
        msg = message.strip()
        if msg:
            self._q.put(msg)

    def flush(self):
        pass


_log_queue = queue.Queue()
loguru_logger.remove()
loguru_logger.add(
    TkLogSink(_log_queue),
    format="<green>{time:HH:mm:ss}</green> | {level:8} | {message}",
    level="INFO",
    colorize=False,
)


# ---------- 工作线程 ----------
def _search_thread(keyword, pages, result_q, stop_event):
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
            result_q.put(('ok', videos))
    except Exception as e:
        result_q.put(('error', str(e)))


def _login_thread(username, password, result_q, stop_event):
    try:
        from bilibili_login import get_login_cookie
        if stop_event.is_set():
            return
        cookies = get_login_cookie(username=username, password=password)
        if not cookies:
            result_q.put(('error', '登录失败'))
            return
        if stop_event.is_set():
            return
        if isinstance(cookies, dict) and cookies.get('need_sms'):
            result_q.put(('sms', cookies))
        else:
            result_q.put(('ok', cookies))
    except Exception as e:
        result_q.put(('error', str(e)))


def _sms_thread(url, result_q, stop_event):
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
                # 短信验证完成后会跳转到 https://account.bilibili.com/account/home 或 https://www.bilibili.com
                if 'account/home' in current_url or current_url == 'https://www.bilibili.com/':
                    break
            time.sleep(1)
            # 从浏览器抓取 cookie
            cookies = {}
            for c in tab.get_cookies():
                cookies[c['name']] = c['value']
            if cookies.get('SESSDATA') and cookies.get('bili_jct'):
                result_q.put(('ok', cookies))
            else:
                result_q.put(('error', '短信验证后未获取到有效Cookie，请确认已完成验证'))
        finally:
            browser.quit()
    except Exception as e:
        result_q.put(('error', str(e)))


def _collect_thread(oid, cookies, img_key, sub_key, bvid, title, pages, result_q, stop_event):
    try:
        from comment import BiliCollector
        if stop_event.is_set():
            return
        BiliCollector.collect_comments(
            oid=oid, cookies=cookies, img_key=img_key, sub_key=sub_key,
            bvid=bvid, title=title, pages=pages,
        )
        if not stop_event.is_set():
            result_q.put(('ok', f'{bvid} 采集完成'))
    except Exception as e:
        result_q.put(('error', str(e)))


def _import_thread(videos: dict, result_q):
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
        loguru_logger.success(f'导入完成，共 {len(video_list)} 条')
        result_q.put(('ok', video_list))
    except Exception as e:
        loguru_logger.error(f'导入线程异常: {e}')
        result_q.put(('error', str(e)))


# ---------- 颜色 ----------
C = {
    'primary':    '#1a73e8',
    'primary_hi': '#1557b0',
    'primary_lt': '#e8f0fe',
    'accent':     '#34a853',
    'accent_hi':  '#2d9249',
    'warning':    '#f9ab00',
    'danger':     '#ea4335',
    'bg':         '#f8f9fa',
    'card':       '#ffffff',
    'border':     '#e0e0e0',
    'text':       '#202124',
    'text_sub':   '#5f6368',
    'text_muted': '#9aa0a6',
    'table_hdr':  '#1a73e8',
    'table_alt':  '#f8f9fe',
    'log_bg':     '#fafafa',
}

# 轮询间隔 (ms)
POLL_MS = 200


# ---------- 主窗口 ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('B站评论采集')
        self.geometry('1020x850')
        self.minsize(880, 580)
        self.configure(bg=C['bg'])

        # 线程控制 ──
        self._stop_event = threading.Event()
        self._running = True           # 窗口存活标记
        self._busy = False            # 是否有后台任务进行中

        # 数据 ──
        self._videos: list[dict] = []
        self._cookies: dict = {}
        self._img_key = ''
        self._sub_key = ''

        # 采集 ──
        self._collecting = False
        self._collect_threads: list[threading.Thread] = []
        self._collect_queue = queue.Queue()
        self._collect_bvids: list[str] = []
        self._collect_idx = 0

        self._setup_style()
        self._build_ui()
        self._start_log_poll()

        # 窗口关闭 ──
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    def _on_close(self):
        self._running = False
        self._stop_event.set()
        self._collecting = False
        # 给线程一点时间自行结束
        for t in list(self._collect_threads):
            t.join(timeout=1.5)
        self.destroy()

    # ---------- 样式 ----------
    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use('clam')

        style.configure('.', background=C['card'], foreground=C['text'])
        style.configure('TFrame', background=C['card'])
        style.configure('TLabel', background=C['card'], foreground=C['text'],
                        font=('微软雅黑', 10))

        style.configure('TButton', background=C['primary_lt'], foreground=C['primary'],
                        borderwidth=0, padding=(16, 6), font=('微软雅黑', 9), relief='flat')
        style.map('TButton',
                  background=[('active', '#d2e3fc'), ('disabled', '#f1f3f4')],
                  foreground=[('disabled', C['text_muted'])])

        style.configure('Primary.TButton', background=C['primary'], foreground='#ffffff',
                        borderwidth=0, padding=(16, 6), font=('微软雅黑', 9, 'bold'), relief='flat')
        style.map('Primary.TButton',
                  background=[('active', C['primary_hi']), ('disabled', '#dadce0')],
                  foreground=[('disabled', '#ffffff')])

        style.configure('Success.TButton', background=C['accent'], foreground='#ffffff',
                        borderwidth=0, padding=(16, 6), font=('微软雅黑', 9, 'bold'), relief='flat')
        style.map('Success.TButton',
                  background=[('active', C['accent_hi']), ('disabled', '#dadce0')],
                  foreground=[('disabled', '#ffffff')])

        style.configure('Danger.TButton', background='#ffffff', foreground=C['danger'],
                        borderwidth=1, padding=(16, 6), font=('微软雅黑', 9), relief='solid')
        style.map('Danger.TButton',
                  background=[('active', '#fce8e6'), ('disabled', '#f1f3f4')],
                  foreground=[('disabled', C['text_muted'])])

        style.configure('TEntry', fieldbackground='#f7fafc', foreground=C['text'],
                        borderwidth=1, padding=7, font=('微软雅黑', 10), relief='solid')
        style.configure('TSpinbox', fieldbackground='#f7fafc', foreground=C['text'],
                        borderwidth=1, padding=7, font=('微软雅黑', 10), relief='solid')

        style.configure('Treeview', background='#ffffff', foreground=C['text'],
                        fieldbackground='#ffffff', rowheight=32, font=('微软雅黑', 9), borderwidth=0)
        style.configure('Treeview.Heading', background=C['table_hdr'], foreground='#ffffff',
                        font=('微软雅黑', 9, 'bold'), padding=(10, 6), borderwidth=0, relief='flat')
        style.map('Treeview',
                  background=[('selected', '#c6dafc')],
                  foreground=[('selected', C['text'])])

        style.configure('TProgressbar', background=C['primary'], troughcolor='#e8eaed',
                        thickness=6, borderwidth=0)
        style.configure('TSeparator', background=C['border'])

    # ---------- UI ----------
    def _build_ui(self):
        # ── 导航栏 ──
        nav = tk.Frame(self, bg='#ffffff', height=52, highlightbackground='#e0e0e0', highlightthickness=1)
        nav.pack(fill='x')
        nav.pack_propagate(False)

        left = tk.Frame(nav, bg='#ffffff')
        left.pack(side='left', fill='y', padx=(18, 0))
        tk.Label(left, text='\u25cf', font=('', 18), fg=C['primary'], bg='#ffffff').pack(side='left')
        tk.Label(left, text='  B站评论采集',
                 font=('微软雅黑', 14, 'bold'), fg=C['text'], bg='#ffffff').pack(side='left')

        right = tk.Frame(nav, bg='#ffffff')
        right.pack(side='right', fill='y', padx=(0, 18))
        self._nav_stats = tk.Label(right, text='', font=('微软雅黑', 9), fg=C['text_sub'], bg='#ffffff')
        self._nav_stats.pack(side='left', padx=(0, 16))
        self._login_badge = tk.Label(right, text=' 未登录 ', font=('微软雅黑', 8, 'bold'),
                                     fg=C['danger'], bg='#fce8e6', padx=10, pady=2)
        self._login_badge.pack(side='left')

        # ── 搜索卡片 ──
        card1 = tk.Frame(self, bg=C['card'], highlightbackground='#e0e0e0', highlightthickness=1)
        card1.pack(fill='x', padx=16, pady=(16, 8))
        c1 = tk.Frame(card1, bg=C['card'])
        c1.pack(fill='x', padx=20, pady=(14, 12))

        tk.Label(c1, text='搜索视频', font=('微软雅黑', 11, 'bold'),
                 fg=C['text'], bg=C['card']).pack(side='left')

        self._kw_entry = tk.Entry(c1, font=('微软雅黑', 10), relief='flat',
                                  bg='#f7fafc', fg=C['text'],
                                  highlightthickness=1, highlightbackground='#cbd5e0',
                                  highlightcolor=C['primary'],
                                  insertbackground=C['primary'], width=30)
        self._kw_entry.pack(side='left', padx=(16, 10), ipadx=8, ipady=5)
        self._kw_entry.insert(0, '罗翔说刑法合集')
        self._kw_entry.bind('<FocusIn>', lambda e: self._kw_entry.selection_range(0, 'end'))

        tk.Label(c1, text='页', font=('微软雅黑', 9), fg=C['text_sub'], bg=C['card']).pack(side='left', padx=(8, 6))
        self._search_pages_var = tk.IntVar(value=3)
        ttk.Spinbox(c1, from_=1, to=20, textvariable=self._search_pages_var, width=4).pack(side='left')

        self._search_btn = ttk.Button(c1, text='搜索', style='Primary.TButton', command=self._on_search)
        self._search_btn.pack(side='left', padx=(14, 0))
        self._search_pb = ttk.Progressbar(c1, mode='indeterminate', length=80)

        # ── 列表标题行 ──
        title_row = tk.Frame(self, bg=C['bg'])
        title_row.pack(fill='x', padx=20, pady=(2, 2))
        ttk.Label(title_row, text='视频列表', font=('微软雅黑', 10, 'bold'),
                  background=C['bg']).pack(side='left')
        self._import_btn = ttk.Button(title_row, text='导入', command=self._on_import)
        self._import_btn.pack(side='left', padx=(8, 0))

        # ── 表格卡片 ──
        card2 = tk.Frame(self, bg=C['card'], highlightbackground='#e0e0e0', highlightthickness=1)
        card2.pack(fill='both', expand=True, padx=16, pady=(4, 8))
        c2 = tk.Frame(card2, bg=C['card'])
        c2.pack(fill='both', expand=True, padx=12, pady=12)

        tree_frame = tk.Frame(c2, bg=C['card'])
        tree_frame.pack(fill='both', expand=True)

        self._tree = ttk.Treeview(tree_frame, columns=('bvid', 'title', 'reply_count'),
                                  show='headings', selectmode='extended')
        self._tree.heading('bvid', text='  BV号')
        self._tree.heading('title', text='  标题')
        self._tree.heading('reply_count', text='  评论数')
        self._tree.column('bvid', width=140, anchor='w')
        self._tree.column('title', width=580, anchor='w')
        self._tree.column('reply_count', width=70, anchor='center')

        vsb = ttk.Scrollbar(tree_frame, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        self._tree.bind('<<TreeviewSelect>>', self._on_tree_select)

        # ── 操作卡片 ──
        card3 = tk.Frame(self, bg=C['card'], highlightbackground='#e0e0e0', highlightthickness=1)
        card3.pack(fill='x', padx=16, pady=(4, 8))
        c3 = tk.Frame(card3, bg=C['card'])
        c3.pack(fill='x', padx=20, pady=12)

        # 第一行: 账号 + 密码 + 参数 + 登录
        row1 = tk.Frame(c3, bg=C['card'])
        row1.pack(fill='x')
        tk.Label(row1, text='操作区', font=('微软雅黑', 10, 'bold'),
                 fg=C['text'], bg=C['card']).pack(side='left')
        ttk.Separator(row1, orient='vertical').pack(side='left', fill='y', padx=12, pady=2)

        ttk.Label(row1, text='账号', background=C['card']).pack(side='left')
        self._user_entry = tk.Entry(row1, font=('微软雅黑', 10), relief='flat',
                                    bg='#f7fafc', fg=C['text'], width=13,
                                    highlightthickness=1, highlightbackground='#cbd5e0',
                                    highlightcolor=C['primary'], insertbackground=C['primary'])
        self._user_entry.pack(side='left', padx=(6, 10), ipadx=6, ipady=4)
        self._user_entry.insert(0, '手机号')
        self._user_entry.bind('<FocusIn>', self._on_entry_focus)
        self._user_entry._placeholder = '手机号'

        ttk.Label(row1, text='密码', background=C['card']).pack(side='left')
        self._pwd_entry = tk.Entry(row1, font=('微软雅黑', 10), relief='flat',
                                   bg='#f7fafc', fg=C['text'], width=13,
                                   highlightthickness=1, highlightbackground='#cbd5e0',
                                   highlightcolor=C['primary'],
                                   insertbackground=C['primary'], show='*')
        self._pwd_entry.pack(side='left', padx=(6, 14), ipadx=6, ipady=4)

        ttk.Label(row1, text='评论页数', background=C['card']).pack(side='left')
        self._comment_pages_var = tk.IntVar(value=5)
        ttk.Spinbox(row1, from_=1, to=50, textvariable=self._comment_pages_var, width=4).pack(side='left', padx=(6, 10))

        ttk.Label(row1, text='间隔(秒)', background=C['card']).pack(side='left')
        self._interval_var = tk.DoubleVar(value=2.0)
        ttk.Spinbox(row1, from_=0, to=120, increment=0.5, textvariable=self._interval_var, width=5).pack(side='left', padx=(6, 14))

        self._login_btn = ttk.Button(row1, text='登录', style='Primary.TButton', command=self._on_login)
        self._login_btn.pack(side='left')

        # 第二行: 采集按钮
        row2 = tk.Frame(c3, bg=C['card'])
        row2.pack(fill='x', pady=(10, 0))

        self._collect_one_btn = ttk.Button(row2, text='采集选中', style='Success.TButton',
                                            command=self._on_collect_one)
        self._collect_one_btn.pack(side='left', padx=(0, 8))
        self._collect_all_btn = ttk.Button(row2, text='采集全部', style='Success.TButton',
                                            command=self._on_collect_all)
        self._collect_all_btn.pack(side='left', padx=(0, 8))
        self._stop_btn = ttk.Button(row2, text='停止', style='Danger.TButton',
                                    command=self._on_stop, state='disabled')
        self._stop_btn.pack(side='left')

        self._collect_pb = ttk.Progressbar(row2, mode='indeterminate', length=160)
        self._collect_pb.pack(side='right')

        # ── 日志卡片 ──
        card4 = tk.Frame(self, bg=C['card'], highlightbackground='#e0e0e0', highlightthickness=1)
        card4.pack(fill='both', expand=False, padx=16, pady=(4, 14))
        card4.configure(height=140)
        card4.pack_propagate(False)
        c4 = tk.Frame(card4, bg=C['log_bg'])
        c4.pack(fill='both', expand=True, padx=8, pady=8)

        self._log_text = tk.Text(c4, bg=C['log_bg'], fg=C['text_sub'],
                                 font=('Cascadia Code', 9), wrap='word',
                                 state='disabled', relief='flat',
                                 padx=12, pady=8, highlightthickness=0, borderwidth=0)
        log_sb = ttk.Scrollbar(c4, orient='vertical', command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_sb.set)
        self._log_text.pack(side='left', fill='both', expand=True)
        log_sb.pack(side='right', fill='y')

        # ── 底部状态栏 ──
        footer = tk.Frame(self, bg='#f1f3f4', height=24)
        footer.pack(fill='x', side='bottom')
        footer.pack_propagate(False)
        self._footer_label = tk.Label(footer, text='  就绪',
                                      font=('微软雅黑', 8), fg=C['text_muted'],
                                      bg='#f1f3f4', anchor='w')
        self._footer_label.pack(side='left', fill='both', expand=True)

    def _on_entry_focus(self, e):
        if e.widget.get() == getattr(e.widget, '_placeholder', ''):
            e.widget.delete(0, 'end')
            e.widget.config(fg=C['text'])

    # ---------- 安全调度 ----------
    def _safe_call(self, func):
        """仅当窗口存活时才执行 func"""
        if self._running:
            func()

    def _safe_after(self, ms, func):
        """仅当窗口存活时调度"""
        if self._running:
            self.after(ms, func)

    # ---------- 日志 ----------
    def _start_log_poll(self):
        self._drain_log()
        self._safe_after(POLL_MS, self._start_log_poll)

    def _drain_log(self):
        try:
            while True:
                self._append_log(_log_queue.get_nowait())
        except queue.Empty:
            pass

    def _append_log(self, msg: str):
        try:
            self._log_text.configure(state='normal')
            self._log_text.insert('end', msg + '\n')
            self._log_text.see('end')
            self._log_text.configure(state='disabled')
        except tk.TclError:
            pass  # 窗口已销毁

    # ---------- 搜索 ----------
    def _on_search(self):
        if self._busy:
            return
        keyword = self._kw_entry.get().strip()
        if not keyword:
            return

        self._busy = True
        self._stop_event.clear()
        self._search_btn.configure(state='disabled', text='搜索中...')
        self._search_pb.pack(side='left', padx=(10, 0))
        self._search_pb.start()
        self._footer_label.configure(text='  正在搜索 B站...')
        self._set_tree_loading()

        q = queue.Queue()
        t = threading.Thread(
            target=_search_thread,
            args=(keyword, self._search_pages_var.get(), q, self._stop_event),
            daemon=True,
        )
        t.start()
        self._safe_after(POLL_MS, lambda: self._poll_search(q, t))

    def _poll_search(self, q: queue.Queue, t: threading.Thread):
        """轮询搜索线程，线程结束后读取结果"""
        if t.is_alive():
            self._safe_after(POLL_MS, lambda: self._poll_search(q, t))
            return

        self._search_pb.stop()
        self._search_pb.pack_forget()
        self._search_btn.configure(state='normal', text='搜索')
        self._busy = False

        try:
            status, data = q.get_nowait()
        except queue.Empty:
            self._footer_label.configure(text='  搜索异常，无返回结果')
            return

        if status == 'ok':
            self._videos = data
            self._refresh_tree()
            self._nav_stats.configure(text=f'共 {len(data)} 个视频')
            self._footer_label.configure(text=f'  搜索完成，找到 {len(data)} 个视频')
        else:
            self._footer_label.configure(text='  搜索失败')
            messagebox.showerror('搜索失败', str(data))

    def _set_tree_loading(self):
        for item in self._tree.get_children():
            self._tree.delete(item)

    def _refresh_tree(self):
        self._set_tree_loading()
        for v in self._videos:
            self._tree.insert('', 'end', iid=v['bvid'],
                              values=(v['bvid'], v.get('title', ''), v.get('reply_count', '')))

    def _on_import(self):
        dlg = tk.Toplevel(self)
        dlg.title('导入视频')
        dlg.geometry('350x190')
        dlg.configure(bg=C['card'])
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        f = tk.Frame(dlg, bg=C['card'])
        f.pack(expand=True, fill='both', padx=24, pady=20)

        ttk.Label(f, text='DB 编号', background=C['card']).grid(row=0, column=0, sticky='e', pady=6)
        db_var = tk.IntVar(value=0)
        ttk.Spinbox(f, from_=0, to=15, textvariable=db_var, width=6).grid(row=0, column=1, padx=(8, 0), sticky='w')

        ttk.Label(f, text='Hash 键名', background=C['card']).grid(row=1, column=0, sticky='e', pady=6)
        key_var = tk.StringVar(value='bilibili_id')
        ttk.Entry(f, textvariable=key_var, width=20).grid(row=1, column=1, padx=(8, 0), sticky='w')

        status_lbl = tk.Label(f, text='', font=('微软雅黑', 8), fg=C['text_muted'], bg=C['card'])
        status_lbl.grid(row=2, column=1, padx=(8, 0), sticky='w', pady=(4, 0))

        btn_f = tk.Frame(f, bg=C['card'])
        btn_f.grid(row=3, column=0, columnspan=2, pady=(14, 0))

        def do_import():
            db = db_var.get()
            key = key_var.get().strip()
            if not key:
                return
            try:
                r = redis.Redis(host='localhost', port=6379, db=db, password=os.environ.get('REDIS_PASSWORD', '123456'), decode_responses=True)
                videos = r.hgetall(key)
                if not videos:
                    status_lbl.configure(text='键为空或无数据')
                    return
                dlg.destroy()
                # 在后台线程加载详情
                self._import_btn.configure(state='disabled', text='加载中...')
                self._nav_stats.configure(text='加载中...')
                self._set_tree_loading()
                q = queue.Queue()
                threading.Thread(target=_import_thread, args=(videos, q), daemon=True).start()
                self._safe_after(POLL_MS, lambda: self._poll_import(q, len(videos)))
            except Exception as e:
                status_lbl.configure(text=f'连接失败: {e}')

        ttk.Button(btn_f, text='导入', style='Primary.TButton', command=do_import).pack(side='left', padx=(0, 8))
        ttk.Button(btn_f, text='取消', command=dlg.destroy).pack(side='left')

    def _poll_import(self, q, total, count=0):
        if not self._running:
            return
        try:
            status, data = q.get_nowait()
        except queue.Empty:
            count += 1
            if count > 600:  # 2分钟超时
                self._import_btn.configure(state='normal', text='导入')
                self._footer_label.configure(text='  导入超时，请重试')
                return
            self._safe_after(POLL_MS, lambda: self._poll_import(q, total, count))
            return
        self._import_btn.configure(state='normal', text='导入')
        if status == 'ok':
            self._videos = data
            self._refresh_tree()
            self._nav_stats.configure(text=f'共 {len(data)} 个视频')
            self._footer_label.configure(text=f'  导入完成，共 {len(data)} 个视频')
            loguru_logger.success(f'导入完成，共 {len(data)} 个视频')
        else:
            self._footer_label.configure(text='  导入失败')
            messagebox.showerror('导入失败', data)

    def _on_tree_select(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        if len(sel) == 1:
            bvid = sel[0]
            video = next((v for v in self._videos if v['bvid'] == bvid), {})
            title = video.get('title', '')
            if len(title) > 60:
                title = title[:60] + '...'
            self._footer_label.configure(text=f'  选中: {bvid}  {title}')
        else:
            self._footer_label.configure(text=f'  已选中 {len(sel)} 个视频')

    # ---------- 登录 ----------
    def _on_login(self):
        if self._busy:
            return
        username = self._user_entry.get().strip()
        if username == '手机号':
            username = ''
        password = self._pwd_entry.get().strip()
        if not username or not password:
            messagebox.showwarning('提示', '请输入账号和密码')
            return

        self._busy = True
        self._stop_event.clear()
        self._login_btn.configure(state='disabled', text='登录中...')
        self._login_badge.configure(text=' 登录中... ', fg=C['warning'], bg='#fef7e0')
        self._footer_label.configure(text='  正在登录，验证码识别中...')

        q = queue.Queue()
        t = threading.Thread(
            target=_login_thread,
            args=(username, password, q, self._stop_event),
            daemon=True,
        )
        t.start()
        self._safe_after(POLL_MS, lambda: self._poll_login(q, t))

    def _poll_login(self, q: queue.Queue, t: threading.Thread):
        if t.is_alive():
            self._safe_after(POLL_MS, lambda: self._poll_login(q, t))
            return

        self._login_btn.configure(state='normal', text='登录')
        self._busy = False

        try:
            status, data = q.get_nowait()
        except queue.Empty:
            return

        if status == 'ok':
            self._set_logged_in(data)
            loguru_logger.success('登录成功')
        elif status == 'sms':
            # 需要短信验证
            messagebox.showinfo('短信验证', '已触发短信风控，将打开浏览器，请手动完成短信验证后关闭浏览器窗口')
            self._login_btn.configure(state='disabled', text='短信验证中...')
            self._login_badge.configure(text=' 短信验证... ', fg=C['warning'], bg='#fef7e0')
            self._footer_label.configure(text='  请在浏览器中完成短信验证...')
            self._busy = True
            q2 = queue.Queue()
            t2 = threading.Thread(
                target=_sms_thread,
                args=(data['url'], q2, self._stop_event),
                daemon=True,
            )
            t2.start()
            self._safe_after(POLL_MS, lambda: self._poll_sms(q2, t2))
        else:
            self._cookies = {}
            self._login_badge.configure(text=' 未登录 ', fg=C['danger'], bg='#fce8e6')
            self._footer_label.configure(text='  登录失败')
            messagebox.showerror('登录失败', data)

    def _set_logged_in(self, cookies):
        self._cookies = cookies
        try:
            from comment import BiliAuth
            bili_jct = cookies.get('bili_jct', '')
            _, self._img_key, self._sub_key = BiliAuth.build_cookies(bili_jct)
        except Exception:
            self._img_key, self._sub_key = '', ''
        self._login_btn.configure(text='已登录', style='Success.TButton')
        self._login_badge.configure(text=' 已登录 ', fg=C['accent'], bg='#e6f4ea')
        self._footer_label.configure(text='  登录成功')

    def _poll_sms(self, q: queue.Queue, t: threading.Thread):
        if t.is_alive():
            self._safe_after(POLL_MS, lambda: self._poll_sms(q, t))
            return
        self._busy = False
        try:
            status, data = q.get_nowait()
        except queue.Empty:
            return
        if status == 'ok':
            self._set_logged_in(data)
            loguru_logger.success('短信验证完成，登录成功')
        else:
            self._login_badge.configure(text=' 未登录 ', fg=C['danger'], bg='#fce8e6')
            self._footer_label.configure(text='  短信验证失败')
            messagebox.showerror('登录失败', data)
        self._login_btn.configure(state='normal', text='登录')

    # ---------- 采集 ----------
    def _on_collect_one(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning('提示', '请先在列表中选中视频 (Ctrl+点击多选)')
            return
        if len(sel) == 1:
            self._start_collect([sel[0]])
        else:
            ok = messagebox.askyesno('确认', f'已选中 {len(sel)} 个视频，开始采集？')
            if ok:
                self._start_collect(list(sel))

    def _on_collect_all(self):
        if not self._videos:
            messagebox.showwarning('提示', '请先搜索视频')
            return
        self._start_collect([v['bvid'] for v in self._videos])

    def _start_collect(self, bvids):
        if not self._cookies:
            messagebox.showwarning('提示', '请先登录')
            return
        if self._collecting:
            return
        if self._busy:
            messagebox.showwarning('提示', '请等待当前任务完成')
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
        title = video.get('title', '')
        pages = self._comment_pages_var.get()

        idx = self._collect_idx + 1
        total = len(self._collect_bvids)
        self._footer_label.configure(text=f'  采集 [{idx}/{total}] {bvid}  {title[:50]}')

        t = threading.Thread(
            target=_collect_thread,
            args=(oid, self._cookies, self._img_key, self._sub_key,
                  bvid, title, pages, self._collect_queue, self._stop_event),
            daemon=True,
        )
        self._collect_threads.append(t)
        t.start()
        # 等待线程结束再读取结果，避免竞争
        self._safe_after(POLL_MS, lambda: self._poll_collect(t))

    def _poll_collect(self, t: threading.Thread):
        """等待指定 collect 线程结束，然后取结果"""
        if t.is_alive():
            self._safe_after(POLL_MS, lambda: self._poll_collect(t))
            return

        # 线程已结束，安全读取结果并清理
        if t in self._collect_threads:
            self._collect_threads.remove(t)

        try:
            status, data = self._collect_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            if status == 'ok':
                loguru_logger.success(data)
            else:
                loguru_logger.error(data)

        self._collect_idx += 1
        if self._collecting:
            delay_ms = int(self._interval_var.get() * 1000)
            self._footer_label.configure(text=f'  等待 {self._interval_var.get():.1f}s 后继续下一个视频...')
            self._safe_after(delay_ms, self._launch_next)

    def _finish_collect(self):
        self._collecting = False
        self._busy = False
        self._set_collect_buttons(False)
        self._footer_label.configure(text='  采集完成')
        loguru_logger.success('全部采集完成')

    def _on_stop(self):
        """停止采集：设置停止标记，放弃轮询，让子线程自行结束"""
        self._collecting = False
        self._stop_event.set()
        self._busy = False
        self._set_collect_buttons(False)
        self._footer_label.configure(text='  已停止')

        # 等待所有采集线程尽快退出
        for t in list(self._collect_threads):
            t.join(timeout=2.0)
            if t in self._collect_threads:
                self._collect_threads.remove(t)

        # 清空残留队列
        while not self._collect_queue.empty():
            try:
                self._collect_queue.get_nowait()
            except queue.Empty:
                break

        loguru_logger.warning('用户手动停止')

    def _set_collect_buttons(self, active):
        s = 'disabled' if active else 'normal'
        self._collect_one_btn.configure(state=s)
        self._collect_all_btn.configure(state=s)
        self._login_btn.configure(state=s)
        self._search_btn.configure(state=s)
        self._stop_btn.configure(state='normal' if active else 'disabled')
        if active:
            self._footer_label.configure(text='  采集进行中...')


if __name__ == '__main__':
    app = App()
    app.mainloop()

