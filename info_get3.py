"""info_get3 —— （α 线 · v3.2.0 整合版）

定位
====
与 info_get.py（γ 合并版，按“整账号 1~8 槽”下载）并存：本文件保留 α 线的
**逐槽 (uid, index)** 任务模型（一行任务 = 一个槽位），同时整合 v3.2.0 的
全部技术改进。原 info_get_v3.py / info_get_v3_1.py 均已废弃，仅保留占位并
转交给本文件。

v3.2.0 整合要点
==============
  • 路径统一：config.ini 与 work_dir 均以“程序所在目录”为基准（app_paths），
    每次读取配置都重新解析，改设置后无需重启；
  • 响应分类：0 / {} → 未创建存档（正常现象）；空响应 → 申请过快；
    非 JSON → 解析失败；异常 → 网络异常；
  • 申请节流：每申请 REQUEST_BATCH_SIZE 个存档暂停 REQUEST_PAUSE_TIME 秒，
    暂停期间不发出新申请，可被“停止”打断；
  • 定向重试：只重试“网络异常 / 解析失败 / 申请过快”，封禁与未创建存档不重试；
    “申请过快”先冷却 30 秒；
  • 定时进度日志：批量下载中每 PROGRESS_LOG_INTERVAL 秒输出一次总进度
    （融合 info_get_v3_1.py 的“每 5 秒进度输出”）；
  • XML 命名 <uid>_<idx>_<标题>.xml，过滤非法字符与控制字符，避免同名覆盖；
  • raw/<uid>_<idx>.json 保留服务器原始响应；
  • 线程安全 UI：子线程只投递队列、主线程轮询执行，避免 Tcl_AsyncDelete 崩溃；
    支持 run_tool(parent) 以 Toplevel 子窗口嵌入主程序；
  • 运行日志：清除前二次确认，支持一键导出为 txt 文件。

任务文件格式
============
  uid,index   → 下载该账号的指定槽位
  uid         → 该账号 1~8 全部槽位（自动展开）
  # 开头      → 注释行

输出目录（config.ini [Settings] work_dir，相对路径按程序目录解析）
  指定UID下载     → <work_dir>/<uid>/
  导入任务文件     → <work_dir>/<任务文件主名>/
  批量文件夹导入   → <work_dir>/<每个任务文件主名>/
  每个目录内含：raw/<uid>_<idx>.json、<uid>_<idx>_<标题>.xml
  整账号下载额外生成 <uid>_details.csv（含封禁状态）
"""
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import requests
import hashlib
import base64
import zlib
import os
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import asyncio
import aiohttp
import json
import threading
import queue
import csv
import configparser
from pathlib import Path
import time
import app_paths

# ================= 配置区域 =================
# 路径统一以“程序所在目录”为基准（见 app_paths），从任何目录启动均读写同一份配置。
CONFIG_FILE = app_paths.in_program_dir("config.ini")
DEFAULT_WORK_DIR = app_paths.in_program_dir("test")
DEFAULT_GAME_ID = "100027788"
GAMEID = DEFAULT_GAME_ID
SAVE_URL = "https://save.api.4399.com/ranging.php/?ac=get"


def get_work_dir():
    """读取统一工作目录（兼容旧版 temp_dir 键）。

    每次调用都重新读 config.ini（不缓存），主程序修改 work_dir 后无需重启；
    相对路径按程序目录解析，兼容“main\\test”这类历史写法。
    """
    work_dir = None
    if os.path.exists(CONFIG_FILE):
        try:
            config = configparser.ConfigParser()
            config.read(CONFIG_FILE, encoding='utf-8-sig')
            work_dir = config.get('Settings', 'work_dir', fallback=None)
            if not work_dir:
                work_dir = config.get('Settings', 'temp_dir', fallback=None)
        except Exception:
            work_dir = None
    resolved = app_paths.resolve(work_dir, DEFAULT_WORK_DIR)
    try:
        os.makedirs(resolved, exist_ok=True)
    except OSError:
        return resolved
    return resolved


RAW_SUB_DIR = "raw"
MAX_CONCURRENT_TASKS = 8       # 槽位级并发
MAX_RETRIES = 3

# ================= 申请节流（防封） =================
# 每申请 REQUEST_BATCH_SIZE 个存档（槽位）暂停 REQUEST_PAUSE_TIME 秒；
# 由 SaveArchiver._acquire_request_slot 统一执行，暂停期间不会发出新申请。
REQUEST_BATCH_SIZE = 50
REQUEST_PAUSE_TIME = 10

# 分批仅用于进度展示/日志（防封统一由上面的申请节流负责，不再额外 sleep）
BATCH_SIZE = 200

# 定时进度日志间隔（秒）：对应 v3.1 的“每 5 秒输出一次总进度”
PROGRESS_LOG_INTERVAL = 30

# ================= 槽位状态标记 =================
# download_precise 返回的 ban_status 字段（字符串标记，区别于服务器返回的 status 码）
STATUS_EMPTY_SLOT = "未创建存档"   # 服务器返回 0：该槽位未创建存档，属正常现象
STATUS_TOO_FAST = "申请过快"       # 服务器返回空响应：申请过快，服务器拒绝访问
STATUS_NET_ERROR = "网络异常"      # 网络异常
STATUS_PARSE_ERROR = "解析失败"    # 响应无法解析

# 需要重试的槽位状态（既非封禁，也非“正常/未创建存档”）
RETRYABLE_STATUSES = (STATUS_NET_ERROR, STATUS_PARSE_ERROR, STATUS_TOO_FAST)
TOO_FAST_RETRY_COOLDOWN = 30   # 重试“申请过快”槽位前的冷却秒数

# Windows 文件名非法字符
_INVALID_FILENAME_CHARS = set('\\/:*?"<>|')


def sanitize_filename(name):
    """清理存档标题用于文件名。

    除 Windows 保留字符外，还必须剔除控制字符（实测有存档标题含 \\x08 退格符，
    直接拼接会 open() 报 OSError 而被误当成“网络异常”，导致存档内容丢失）。
    """
    cleaned = "".join(c for c in str(name)
                      if c not in _INVALID_FILENAME_CHARS and ord(c) >= 32)
    cleaned = cleaned.strip().rstrip(".")     # Windows 不允许结尾的点/空格
    return cleaned or "unnamed"


class SaveArchiver:
    """逐槽下载器：一次请求对应一个 (uid, index) 槽位。"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        })
        # 申请节流状态（每 REQUEST_BATCH_SIZE 个存档暂停 REQUEST_PAUSE_TIME 秒）
        self.request_count = 0
        self.throttle_lock = None      # asyncio.Lock，延迟到事件循环内创建
        self.on_throttle = None        # 回调(msg, warn)，供 GUI 输出暂停日志
        self.should_stop = None        # 回调() -> bool，暂停中可提前中断

    def take_verify(self, index: str, uid: str, gameid: str, gamekey: str) -> str:
        raw = f"SDALPlsldlnSLWPElsdslSE{index}{gamekey}{uid}{gameid}PKslsO"
        for _ in range(3):
            raw = hashlib.md5(raw.encode()).hexdigest()
        return raw

    def get_status_text(self, status_code):
        status_map = {"0": "正常", "1": "暂时封禁", "2": "永久封禁"}
        return status_map.get(str(status_code), "未知状态")

    # ---- 申请节流：每申请 200 个存档暂停 30 秒（防“申请过快，服务器拒绝访问”）----
    def reset_throttle(self):
        """重置申请计数与锁（每次下载任务开始前调用，避免跨事件循环复用锁）"""
        self.request_count = 0
        self.throttle_lock = None

    async def _acquire_request_slot(self):
        """发起一次存档申请前先过闸：累计到 REQUEST_BATCH_SIZE 个则暂停 REQUEST_PAUSE_TIME 秒。

        用锁保证暂停期间不会有新的存档申请发出。
        """
        if self.throttle_lock is None:
            self.throttle_lock = asyncio.Lock()
        async with self.throttle_lock:
            if self.request_count >= REQUEST_BATCH_SIZE:
                self.request_count = 0
                if self.on_throttle:
                    self.on_throttle(f"⏸ 已申请 {REQUEST_BATCH_SIZE} 个存档，"
                                     f"暂停 {REQUEST_PAUSE_TIME} 秒（防申请过快）...", True)
                for _ in range(REQUEST_PAUSE_TIME):
                    if self.should_stop and self.should_stop():
                        break
                    await asyncio.sleep(1)
                if self.on_throttle:
                    self.on_throttle("▶️ 暂停结束，继续申请存档")
            self.request_count += 1

    @staticmethod
    def _write_raw(path, text):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass

    @staticmethod
    def _slot_result(ok, msg, ban_status, index, title="", extra=None):
        """统一返回结构（ok/msg/ban_status + 槽位元数据）。"""
        result = {
            "ok": ok, "msg": msg, "ban_status": ban_status,
            "index": str(index), "title": title,
            "create_time": "", "update_times": "", "datetime": "",
        }
        if extra:
            result.update(extra)
        return result

    async def download_precise(self, uid, index, output_folder):
        """下载单个槽位 (uid, index)，写 raw json 与 XML。

        服务器响应形态：
          • dict 且含 data → 正常存档
          • 0 / 空对象    → 未创建存档（正常现象，不算失败）
          • 空响应        → 申请过快，服务器拒绝访问（交由节流/重试处理）
        返回 dict：ok / msg / ban_status / index / title / 时间字段。
        """
        await self._acquire_request_slot()
        gamekey = self.calculate_gamekey()
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        raw_folder = os.path.join(output_folder, RAW_SUB_DIR)
        os.makedirs(raw_folder, exist_ok=True)
        raw_path = os.path.join(raw_folder, f"{uid}_{index}.json")

        data = {
            'uid': uid, 'gameid': GAMEID, 'gamekey': gamekey,
            'index': index, 'verify': self.take_verify(index, uid, GAMEID, gamekey)
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(SAVE_URL, data=data) as response:
                    resp_text = await response.text()
        except Exception:
            return self._slot_result(False, STATUS_NET_ERROR, STATUS_NET_ERROR, index)

        stripped = resp_text.strip()

        # 空响应：申请过快，服务器拒绝访问（等节流后由重试处理）
        if not stripped:
            self._write_raw(raw_path, "")
            return self._slot_result(False, STATUS_TOO_FAST, STATUS_TOO_FAST, index)

        # 服务器返回 0（或空对象）：该槽位未创建存档，属正常现象
        if stripped in ("0", "{}"):
            self._write_raw(raw_path, stripped)
            return self._slot_result(False, STATUS_EMPTY_SLOT, STATUS_EMPTY_SLOT, index)

        try:
            json_data = json.loads(stripped)
        except json.JSONDecodeError:
            self._write_raw(raw_path, resp_text)
            return self._slot_result(False, STATUS_PARSE_ERROR, STATUS_PARSE_ERROR, index)

        if not isinstance(json_data, dict):
            self._write_raw(raw_path, resp_text)
            return self._slot_result(False, STATUS_EMPTY_SLOT, STATUS_EMPTY_SLOT, index)

        self._write_raw(raw_path, json.dumps(json_data, ensure_ascii=False, indent=4))

        status_code = json_data.get("status", 0)
        status_str = str(status_code)
        title = json_data.get("title") or f"uid{uid}_idx{index}"
        meta = {
            "create_time": json_data.get("create_time", ""),
            "update_times": json_data.get("update_times", ""),
            "datetime": json_data.get("datetime", ""),
        }

        if status_str == "1":
            return self._slot_result(False, "账号临时封禁", "临时封禁", index, title, meta)
        if status_str == "2":
            return self._slot_result(False, "账号永久封禁", "永久封禁", index, title, meta)

        ban_status = self.get_status_text(status_code)
        b64_data = json_data.get("data", "")
        if status_str != "0" or not b64_data:
            return self._slot_result(False, STATUS_EMPTY_SLOT, STATUS_EMPTY_SLOT, index, title, meta)

        xml_content = self.process_save_data(b64_data)
        if not xml_content:
            return self._slot_result(False, STATUS_PARSE_ERROR, ban_status, index, title, meta)

        safe_title = sanitize_filename(title)
        save_path = os.path.join(output_folder, f"{uid}_{index}_{safe_title}.xml")
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(xml_content)
        except OSError as e:
            return self._slot_result(False, f"写入失败: {e}", STATUS_PARSE_ERROR, index, title, meta)
        return self._slot_result(True, "下载成功", ban_status, index, title, meta)

    def process_save_data(self, b64_string):
        try:
            compressed = base64.b64decode(b64_string)
            try:
                decompressed = zlib.decompress(compressed)
            except zlib.error:
                decompressed = zlib.decompress(compressed, -15)
            xml_start = decompressed.find(b"<")
            if xml_start == -1:
                return None
            return decompressed[xml_start:].decode("utf-8", errors="ignore")
        except Exception:
            return None

    async def download_account(self, uid, uid_folder=None):
        """整账号下载（1~8 槽，逐槽调用 download_precise），写 XML + <uid>_details.csv。"""
        if uid_folder is None:
            uid_folder = os.path.join(get_work_dir(), uid)
        os.makedirs(uid_folder, exist_ok=True)

        results = await asyncio.gather(*[
            self.download_precise(uid, str(i), uid_folder) for i in range(8)
        ])

        rows = []
        for r in results:
            ban_status = r["ban_status"]
            if r["ok"]:
                status_text = "正常"
            elif ban_status in ("临时封禁", "永久封禁"):
                status_text = ban_status
            else:
                status_text = r["msg"]
            rows.append({
                "index": r["index"], "title": r["title"], "status": status_text,
                "ban_status": ban_status,
                "create_time": r["create_time"], "update_times": r["update_times"],
                "datetime": r["datetime"],
            })

        # 统一 _details.csv（存档/标题/状态 → 兼容封禁缓存读取）
        csv_path = os.path.join(uid_folder, f"{uid}_details.csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["存档", "标题", "状态", "封禁状态", "创建时间", "存档次数", "最后存档实际"])
            for row in rows:
                w.writerow([row["index"], row["title"], row["status"], row["ban_status"],
                            row["create_time"], row["update_times"], row["datetime"]])
        return rows

    def calculate_gamekey(self):
        salt = "LPislKLodlLKKOSNlSDOAADLKADJAOADALAklsd"
        raw = DEFAULT_GAME_ID + salt + DEFAULT_GAME_ID
        md5 = hashlib.md5(hashlib.md5(raw.encode()).hexdigest().encode()).hexdigest()
        return md5[4:20]

    def check_account_exists(self, username):
        try:
            r = self.session.get("http://ptlogin.4399.com/ptlogin/isExist.do",
                                 params={"username": username, "appId": "u4399"}, timeout=5)
            return "已被注册" in r.text
        except Exception:
            return False

    def get_uid_from_account(self, username):
        try:
            r = self.session.get("http://cz.4399.com/get_role_info.php",
                                 params={"ac": "cuid", "uname": username}, timeout=5)
            t = r.text.strip()
            return t if t.isdigit() else None
        except Exception:
            return None


# ===================== 美化版 GUI =====================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("爆枪突击逐槽存档下载器 α3 · v3.2.0")
        self.root.geometry("920x620")
        self.root.configure(bg="#1e1e2e")
        self.archiver = SaveArchiver()

        # 任务数据：[(uid, index, sub_folder_or_None), ...]
        #   单文件导入: sub=None（输出到 <work_dir>/<任务文件主名>/）
        #   文件夹导入: sub=<任务文件主名>
        self.tasks = []
        self.task_source_file = None
        self.task_source_folder = None

        self.is_running = False
        self.stop_flag = False
        self.total_tasks = 0
        self.done_tasks = 0
        self.success_count = 0
        self.fail_count = 0
        self.ban_count = 0
        self.empty_count = 0      # 未创建存档槽位（服务器返回0，正常现象）
        self.toofast_count = 0    # 申请过快槽位（服务器返回空响应）
        self.ban_list = []
        self.fail_list = []   # 失败槽位: (uid, idx, out, msg, ban_status)

        # ★ 跨线程 UI 调度队列：子线程只能**投递**界面操作，由主线程轮询执行。
        #   tkinter 的 Tcl 异步处理器归属于创建它的线程，子线程直接调
        #   root.after()/控件方法会在解释器退出时于错误线程清理，触发
        #   “Tcl_AsyncDelete: async handler deleted by the wrong thread”
        #   —— 进程直接中止。
        self._ui_queue = queue.Queue()
        self._ui_after_id = None
        self._alive = True
        self._progress_stop = threading.Event()   # 定时进度日志线程停止信号

        self.build_ui()
        self._poll_ui_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- 主线程 UI 调度 ----------------
    def _ui_call(self, fn, *args, **kwargs):
        """线程安全：把界面操作排入主线程队列（任意线程均可调用）。"""
        try:
            self._ui_queue.put((fn, args, kwargs))
        except Exception:
            pass

    def _poll_ui_queue(self):
        """在主线程执行队列中积累的界面操作，然后重新排程。"""
        while self._alive:
            try:
                fn, args, kwargs = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args, **kwargs)
            except Exception:
                pass    # 单个回调失败不影响后续刷新
        if not self._alive:
            return
        try:
            self._ui_after_id = self.root.after(50, self._poll_ui_queue)
        except Exception:
            self._ui_after_id = None    # 窗口已销毁

    def on_close(self):
        """关闭窗口：停止轮询并销毁，确保 Tcl 在主线程清理。"""
        self._alive = False
        self.stop_flag = True       # 通知下载任务退出
        self._stop_progress_logger()
        if self._ui_after_id is not None:
            try:
                self.root.after_cancel(self._ui_after_id)
            except Exception:
                pass
            self._ui_after_id = None
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------------- UI ----------------
    def build_ui(self):
        main_container = tk.Frame(self.root, bg="#1e1e2e")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        left_frame = tk.Frame(main_container, bg="#28293b", bd=0, relief=tk.FLAT)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        tk.Label(left_frame, text="🎮 爆枪突击逐槽存档下载器",
                 font=("微软雅黑", 14, "bold"), bg="#28293b", fg="#cba6f7").pack(pady=14)

        entry_style = {"font": ("微软雅黑", 10), "bd": 0, "relief": tk.FLAT,
                       "bg": "#313244", "fg": "#f5e0dc", "insertbackground": "#f5e0dc"}
        label_style = {"bg": "#28293b", "fg": "#bac2de", "font": ("微软雅黑", 10)}

        tk.Label(left_frame, text="4399 账号", **label_style).pack(anchor="w", padx=20, pady=(3, 2))
        self.user_entry = tk.Entry(left_frame, width=40, **entry_style)
        self.user_entry.pack(padx=20, pady=2, ipady=6)

        tk.Label(left_frame, text="UID", **label_style).pack(anchor="w", padx=20, pady=(6, 2))
        self.uid_entry = tk.Entry(left_frame, width=40, **entry_style)
        self.uid_entry.pack(padx=20, pady=2, ipady=6)

        btn_frame = tk.Frame(left_frame, bg="#28293b")
        btn_frame.pack(pady=10, padx=10)

        def mk_btn(color, fg="#1e1e2e"):
            return {"bg": color, "fg": fg, "font": ("微软雅黑", 10, "bold"),
                    "bd": 0, "relief": tk.FLAT, "width": 17, "cursor": "hand2"}

        tk.Button(btn_frame, text="🔍 账号转UID", **mk_btn("#89b4fa"),
                  command=self.get_uid_thread).grid(row=0, column=0, padx=5, pady=5)
        self.single_btn = tk.Button(btn_frame, text="⬇ 指定UID下载(1~8槽)", **mk_btn("#f38ba8", "white"),
                                    command=self.start_single)
        self.single_btn.grid(row=0, column=1, padx=5, pady=5)

        self.import_task_btn = tk.Button(btn_frame, text="📂 导入任务文件", **mk_btn("#a6e3a1"),
                                         command=self.load_task_file)
        self.import_task_btn.grid(row=1, column=0, padx=5, pady=5)
        self.batch_btn = tk.Button(btn_frame, text="🚀 批量下载", **mk_btn("#fab387"),
                                   command=self.start_precise_batch)
        self.batch_btn.grid(row=1, column=1, padx=5, pady=5)

        self.import_folder_btn = tk.Button(btn_frame, text="📂 批量文件夹导入", **mk_btn("#cba6f7"),
                                           command=self.load_folder_batch)
        self.import_folder_btn.grid(row=2, column=0, padx=5, pady=5)
        self.stop_btn = tk.Button(btn_frame, text="⏹️ 停止下载", **mk_btn("#f5c2e7"),
                                  command=self.stop_batch_task, state=tk.DISABLED)
        self.stop_btn.grid(row=2, column=1, padx=5, pady=5)
        tk.Button(btn_frame, text="🧹 清除日志", **mk_btn("#74c7ec"),
                  command=self.clear_log).grid(row=3, column=0, padx=5, pady=5)
        tk.Button(btn_frame, text="💾 导出日志", **mk_btn("#94e2d5"),
                  command=self.export_log).grid(row=3, column=1, padx=5, pady=5)

        status_line = tk.Frame(left_frame, bg="#28293b")
        status_line.pack(fill=tk.X, padx=15)
        self.status_var = tk.StringVar(value="就绪")
        self.task_var = tk.StringVar(value="任务 0/0")
        tk.Label(status_line, textvariable=self.status_var, bg="#28293b", fg="#94e2d5",
                 font=("微软雅黑", 10), anchor="w").pack(side=tk.LEFT)
        tk.Label(status_line, textvariable=self.task_var, bg="#28293b", fg="#f9e2af",
                 font=("微软雅黑", 10), anchor="e").pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(left_frame, orient=tk.HORIZONTAL, length=360,
                                        mode="determinate")
        self.progress.pack(pady=6)

        # 右侧日志
        right_frame = tk.Frame(main_container, bg="#28293b", width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        right_frame.pack_propagate(False)

        tk.Label(right_frame, text="📝 实时运行日志", bg="#28293b", fg="#cba6f7",
                 font=("微软雅黑", 11, "bold")).pack(pady=10)

        self.log_text = tk.Text(right_frame, bg="#11111b", fg="#a6e3a1", font=("Consolas", 10),
                                bd=0, relief=tk.FLAT, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log_text.config(state=tk.DISABLED)
        self.log_text.tag_config("error", foreground="#f38ba8")
        self.log_text.tag_config("warn", foreground="#fab387")

        scroll = ttk.Scrollbar(right_frame, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

    # ---------------- 日志 ----------------
    def log(self, msg, tag=None):
        """线程安全日志入口：任意线程可调，界面刷新投递到主线程。"""
        self._ui_call(self._append_log, msg, tag)

    def _append_log(self, msg, tag=None):
        if not self._alive:
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n", tag or "")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def log_error(self, msg):
        self.log(msg, "error")

    def log_warn(self, msg):
        self.log(msg, "warn")

    def clear_log(self):
        """线程安全：确认与清除都在主线程执行。"""
        self._ui_call(self._confirm_clear_log)

    def _confirm_clear_log(self):
        if not self._alive:
            return
        if not messagebox.askyesno("确认清除", "确定要清除当前运行日志吗？\n（清除后无法恢复，建议先导出）",
                                   parent=self.root):
            return
        self._clear_log_widget()

    def _clear_log_widget(self):
        if not self._alive:
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def export_log(self):
        """线程安全：把当前日志内容导出到文本文件，保存对话框在主线程弹出。"""
        self._ui_call(self._export_log_widget)

    def _export_log_widget(self):
        if not self._alive:
            return
        content = self.log_text.get("1.0", tk.END).rstrip("\n")
        if not content.strip():
            messagebox.showinfo("提示", "当前没有可导出的日志内容", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="导出运行日志",
            initialfile=time.strftime("运行日志_%Y%m%d_%H%M%S.txt"),
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(content + "\n")
        except OSError as e:
            messagebox.showerror("导出失败", f"无法写入文件：\n{e}", parent=self.root)
            return
        self.log(f"💾 日志已导出：{path}")
        messagebox.showinfo("导出成功", f"日志已保存到：\n{path}", parent=self.root)

    # ---------------- 申请节流 ----------------
    def _on_throttle(self, msg, warn=False):
        """节流回调：显示“每申请200个存档暂停30秒”的暂停/恢复日志"""
        if warn:
            self.log_warn(msg)
        else:
            self.log(msg)

    def _setup_throttle(self):
        """每次下载任务开始前重置申请计数并挂上节流回调"""
        self.archiver.reset_throttle()
        self.archiver.on_throttle = self._on_throttle
        self.archiver.should_stop = lambda: self.stop_flag

    def _set_running(self, running):
        self.is_running = running
        self._ui_call(self._apply_running_state, running)

    def _apply_running_state(self, running):
        if not self._alive:
            return
        state = tk.DISABLED if running else tk.NORMAL
        for btn in (self.single_btn, self.import_task_btn, self.batch_btn, self.import_folder_btn):
            btn.config(state=state)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)

    def _reset_counters(self):
        self.total_tasks = 0
        self.done_tasks = 0
        self.success_count = 0
        self.fail_count = 0
        self.ban_count = 0
        self.empty_count = 0
        self.toofast_count = 0
        self.ban_list = []
        self.fail_list = []

    # ---------------- 定时进度日志（每 5 秒） ----------------
    def _start_progress_logger(self):
        """启动定时进度日志线程：每 PROGRESS_LOG_INTERVAL 秒输出一次总进度。

        日志经 _ui_call 投递主线程，因此该线程不直接触碰控件。
        """
        self._stop_progress_logger()
        self._progress_stop = threading.Event()
        stop_event = self._progress_stop

        def loop():
            while not stop_event.wait(PROGRESS_LOG_INTERVAL):
                if not self.is_running or self._alive is False:
                    break
                done = min(self.done_tasks, self.total_tasks)
                percent = (done / self.total_tasks * 100) if self.total_tasks else 0
                stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                self.log(f"{stamp} 进度：{done}/{self.total_tasks}（{percent:.2f}%）"
                         f"｜成功 {self.success_count}｜未创建 {self.empty_count}"
                         f"｜失败 {self.fail_count}｜封禁 {self.ban_count}")

        threading.Thread(target=loop, daemon=True).start()

    def _stop_progress_logger(self):
        try:
            self._progress_stop.set()
        except Exception:
            pass

    # ---------------- 任务导入 ----------------
    @staticmethod
    def parse_task_file(path):
        """每行: uid,index → 指定槽位；纯 uid → 展开 1~8 槽位。返回 [(uid, idx), ...]"""
        tasks = []
        seen = set()
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "," in line:
                    parts = line.split(",", 1)
                    uid, idx = parts[0].strip(), parts[1].strip()
                    if not (uid.isdigit() and idx.isdigit()):
                        continue
                    pairs = [(uid, idx)]
                else:
                    if not line.isdigit():
                        continue
                    pairs = [(line, str(i)) for i in range(8)]
                for uid, idx in pairs:
                    if (uid, idx) in seen:
                        continue
                    seen.add((uid, idx))
                    tasks.append((uid, idx))
        return tasks

    def load_task_file(self):
        if self.is_running:
            return
        path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt *.csv"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            pairs = self.parse_task_file(path)
            if not pairs:
                messagebox.showwarning("提示", "文件中没有有效的 uid,index 或 uid 行")
                return
            self.tasks = [(uid, idx, None) for uid, idx in pairs]
            self.task_source_file = Path(path)
            self.task_source_folder = None
            out_dir = os.path.join(get_work_dir(), self.task_source_file.stem)
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.log(f"{stamp} 📂 导入任务 {len(self.tasks)} 个槽位")
            self.log(f"任务文件：{self.task_source_file}")
            self.log(f"保存目录：{out_dir}")
            messagebox.showinfo("成功", f"导入 {len(self.tasks)} 个槽位任务\n"
                                       f"输出目录: {out_dir}")
        except Exception as e:
            self.log_error(f"❌ 导入失败：{str(e)}")
            messagebox.showerror("错误", str(e))

    def load_folder_batch(self):
        if self.is_running:
            return
        folder_path = filedialog.askdirectory(title="请选择包含任务文件的文件夹")
        if not folder_path:
            return
        files = [f for f in os.listdir(folder_path) if f.lower().endswith((".txt", ".csv"))]
        if not files:
            self.log_error("❌ 文件夹内无 txt/csv 文件")
            messagebox.showwarning("提示", "该文件夹内没有找到 .txt 或 .csv 文件！")
            return
        try:
            tasks = []
            for fn in files:
                sub = os.path.splitext(fn)[0]
                for uid, idx in self.parse_task_file(os.path.join(folder_path, fn)):
                    tasks.append((uid, idx, sub))
            if not tasks:
                messagebox.showwarning("提示", "文件夹中所有文件都没有有效任务")
                return
            self.tasks = tasks
            self.task_source_folder = folder_path
            self.task_source_file = None
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.log(f"{stamp} 📂 文件夹导入：{len(files)} 个任务文件，共 {len(tasks)} 个槽位任务")
            self.log(f"任务文件夹：{folder_path}")
            self.log(f"保存目录：{get_work_dir()}")
            messagebox.showinfo("成功", f"发现 {len(files)} 个任务文件\n共 {len(tasks)} 个槽位任务\n"
                                       f"点击「🚀 批量下载」开始")
        except Exception as e:
            self.log_error(f"❌ 导入失败：{str(e)}")
            messagebox.showerror("错误", str(e))

    # ---------------- 账号转UID ----------------
    def get_uid_thread(self):
        """主线程：先取值再启动子线程（tkinter 控件只能在主线程读）。"""
        user = self.user_entry.get().strip()
        threading.Thread(target=self.get_uid, args=(user,), daemon=True).start()

    def get_uid(self, user=""):
        """账号转 UID（在子线程运行 → 界面操作全部投递主线程）。"""
        if not user:
            self._ui_call(messagebox.showwarning, "提示", "输入账号")
            return
        self._ui_call(self.status_var.set, "检测中...")
        if not self.archiver.check_account_exists(user):
            self._ui_call(messagebox.showerror, "错误", "账号不存在")
            self._ui_call(self.status_var.set, "失败")
            return
        uid = self.archiver.get_uid_from_account(user)
        if uid:
            self._ui_call(self._fill_uid, uid)
            self._ui_call(self.status_var.set, "✅ UID获取成功")
            self.log(f"✅ 账号 {user} → UID {uid}")
        else:
            self._ui_call(messagebox.showerror, "错误", "获取失败")
            self._ui_call(self.status_var.set, "失败")

    def _fill_uid(self, uid):
        """主线程：把 UID 写入输入框。"""
        if not self._alive:
            return
        self.uid_entry.delete(0, tk.END)
        self.uid_entry.insert(0, uid)

    # ---------------- 指定UID整账号下载 ----------------
    def start_single(self):
        """主线程：先取值再启动子线程（tkinter 控件只能在主线程读）。"""
        if self.is_running:
            messagebox.showwarning("提示", "已有任务正在运行")
            return
        uid = self.uid_entry.get().strip()
        threading.Thread(target=self.run_single, args=(uid,), daemon=True).start()

    def run_single(self, uid=""):
        """指定 UID 下载 1~8 槽（在子线程运行 → 界面操作全部投递主线程）。"""
        if not uid or not uid.isdigit():
            self._ui_call(messagebox.showwarning, "提示", "输入有效UID")
            return
        self._set_running(True)
        self.stop_flag = False
        self._reset_counters()
        self.total_tasks = 8
        self._ui_call(self._set_total_tasks_ui, 8)
        self._setup_throttle()
        self._ui_call(self.status_var.set, "下载中...")
        self.log(f"===== 指定 UID 下载：{uid}（1~8 槽）=====")
        try:
            rows = asyncio.run(self.archiver.download_account(uid))
            ok = sum(1 for r in rows if r["status"] == "正常")
            empty = sum(1 for r in rows if r["status"] == STATUS_EMPTY_SLOT)
            too_fast = sum(1 for r in rows if r["status"] == STATUS_TOO_FAST)
            ban = sum(1 for r in rows if r["status"] in ("临时封禁", "永久封禁"))
            self.success_count, self.empty_count = ok, empty
            self.toofast_count, self.ban_count = too_fast, ban
            self.done_tasks = 8
            self._refresh_progress()
            self.log(f"[{uid}] 下载完成：正常 {ok} 槽，未创建存档 {empty} 槽"
                     + (f"，{STATUS_TOO_FAST} {too_fast} 槽" if too_fast else "")
                     + (f"，封禁 {ban} 槽" if ban else ""))
            self._ui_call(self.status_var.set, "✅ 单UID下载完成")
        except Exception as e:
            self.log_error(f"错误：{str(e)}")
            self._ui_call(self.status_var.set, "下载失败")
        finally:
            self.on_task_complete(show_dialog=False)

    # ---------------- 批量下载 ----------------
    def start_precise_batch(self):
        if self.is_running:
            return
        if not self.tasks:
            messagebox.showwarning("提示", "请先导入任务文件或文件夹")
            return
        self._reset_counters()
        self._set_running(True)
        self.stop_flag = False
        threading.Thread(target=self.run_batch_async, args=(list(self.tasks),), daemon=True).start()

    def stop_batch_task(self):
        if not self.is_running:
            return
        self.stop_flag = True
        self.log_warn("正在停止...")

    def _out_dir_for(self, uid, sub=None):
        """返回任务的输出目录（基准目录取自最新配置的 work_dir）。"""
        base = get_work_dir()
        if sub:
            return os.path.join(base, sub)
        if self.task_source_file:
            return os.path.join(base, self.task_source_file.stem)
        return os.path.join(base, uid)

    def run_batch_async(self, tasks):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_batch(tasks))
        except Exception as e:
            self.log_error(f"错误：{e}")
        finally:
            loop.close()
            self.on_task_complete()

    async def run_batch(self, tasks):
        entries = [(uid, idx, self._out_dir_for(uid, sub)) for uid, idx, sub in tasks]
        self.total_tasks = len(entries)
        self._ui_call(self._set_total_tasks_ui, self.total_tasks)
        self._ui_call(self.status_var.set, "批量下载中...")
        self._setup_throttle()
        if not entries:
            return

        total_batches = (len(entries) + BATCH_SIZE - 1) // BATCH_SIZE
        est_seconds = (len(entries) / MAX_CONCURRENT_TASKS * 0.4
                       + (len(entries) // REQUEST_BATCH_SIZE) * REQUEST_PAUSE_TIME)
        est_minutes = max(1, int(round(est_seconds / 60)))

        self.log("=" * 30)
        self.log(f"开始下载：{len(entries)} 个槽位，每批 {BATCH_SIZE} 个（共 {total_batches} 批）")
        self.log(f"并发 {MAX_CONCURRENT_TASKS}；申请节流：每 {REQUEST_BATCH_SIZE} 次申请"
                 f"暂停 {REQUEST_PAUSE_TIME} 秒")
        self.log(f"粗估耗时：约 {est_minutes} 分钟")
        self.log("=" * 30)
        self._start_progress_logger()

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        fails = []

        async def run_one(uid, idx, out):
            async with semaphore:
                if self.stop_flag:
                    return
                result = await self.archiver.download_precise(uid, idx, out)
                self._handle_result(result, uid, idx, out, fails)
                self.done_tasks += 1
                self._refresh_progress()

        for batch_num in range(total_batches):
            if self.stop_flag:
                break
            batch = entries[batch_num * BATCH_SIZE:(batch_num + 1) * BATCH_SIZE]
            self.log(f"—— 第 {batch_num + 1}/{total_batches} 批：{len(batch)} 个槽位 ——")
            await asyncio.gather(*(run_one(uid, idx, out) for uid, idx, out in batch))
            percent = (self.done_tasks / self.total_tasks * 100) if self.total_tasks else 0
            self.log(f"第 {batch_num + 1}/{total_batches} 批完成：{self.done_tasks}/{self.total_tasks}"
                     f"（{percent:.1f}%），成功 {self.success_count}，未创建 {self.empty_count}，"
                     f"失败 {self.fail_count}")

        # 重试失败槽位（非封禁）
        if fails and not self.stop_flag:
            await self._retry_fails(fails)

    def _handle_result(self, result, uid, idx, out, fails):
        """统计一个槽位结果；只有可重试状态才进入重试队列。"""
        if result["ok"]:
            self.success_count += 1
            return
        ban_status = result["ban_status"]
        if ban_status in ("临时封禁", "永久封禁"):
            self.ban_count += 1
            info = f"UID: {uid}, 存档: {idx}, 状态: {ban_status}"
            self.ban_list.append(info)
            self.log_warn(f"⚠️ {info}")
            return
        if ban_status == STATUS_EMPTY_SLOT:
            self.empty_count += 1
            return
        self.fail_count += 1
        if ban_status == STATUS_TOO_FAST:
            self.toofast_count += 1
        info = (uid, idx, out, result["msg"], ban_status)
        self.fail_list.append(info)
        if ban_status in RETRYABLE_STATUSES:
            fails.append(info)      # 只有可重试状态才进入重试队列
        self.log_warn(f"❌ UID {uid} 存档 {idx}: {result['msg']}")

    def _remove_fail(self, uid, idx, out):
        self.fail_list = [x for x in self.fail_list
                          if not (x[0] == uid and x[1] == idx and x[2] == out)]

    async def _retry_fails(self, fails):
        # “申请过快”属服务端限流，先冷却再重试
        too_fast = [x for x in fails if x[4] == STATUS_TOO_FAST]
        if too_fast:
            self.log_warn(f"其中 {len(too_fast)} 个槽位为「{STATUS_TOO_FAST}」，"
                          f"先冷却 {TOO_FAST_RETRY_COOLDOWN} 秒再重试...")
            for _ in range(TOO_FAST_RETRY_COOLDOWN):
                if self.stop_flag:
                    return
                await asyncio.sleep(1)

        self.log_warn(f"开始重试 {len(fails)} 个失败槽位（非封禁）...")
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

        async def retry_one(uid, idx, out):
            async with semaphore:
                for attempt in range(MAX_RETRIES):
                    if self.stop_flag:
                        return
                    result = await self.archiver.download_precise(uid, idx, out)
                    if result["ok"]:
                        self.success_count += 1
                        self.fail_count = max(0, self.fail_count - 1)
                        self._remove_fail(uid, idx, out)
                        return
                    ban_status = result["ban_status"]
                    if ban_status in ("临时封禁", "永久封禁"):
                        self.ban_count += 1
                        self.fail_count = max(0, self.fail_count - 1)
                        info = f"UID: {uid}, 存档: {idx}, 状态: {ban_status}"
                        self.ban_list.append(info)
                        self._remove_fail(uid, idx, out)
                        self.log_warn(f"⚠️ 重试发现封禁 {info}")
                        return
                    if ban_status == STATUS_EMPTY_SLOT:
                        self.empty_count += 1
                        self.fail_count = max(0, self.fail_count - 1)
                        self._remove_fail(uid, idx, out)
                        return
                    if ban_status == STATUS_TOO_FAST:
                        self.toofast_count += 1
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(1)
                self.log_error(f"❌ 重试失败 UID {uid} 存档 {idx}")

        await asyncio.gather(*[retry_one(*x[:3]) for x in fails])

    def _set_total_tasks_ui(self, total):
        """主线程：重置进度条量程。"""
        if not self._alive:
            return
        self.progress["maximum"] = total
        self.progress["value"] = 0
        self.task_var.set(f"任务 0/{total}")

    def _refresh_progress(self):
        done = min(self.done_tasks, self.total_tasks)
        self._ui_call(self._refresh_progress_ui, done, self.total_tasks)

    def _refresh_progress_ui(self, done, total):
        if not self._alive:
            return
        self.progress["value"] = done
        self.task_var.set(f"任务 {done}/{total}")

    def on_task_complete(self, show_dialog=True):
        """下载结束（可能从子线程调）→ 界面更新全部走主线程。"""
        self._ui_call(self._on_task_complete_ui, show_dialog)

    def _on_task_complete_ui(self, show_dialog=True):
        if not self._alive:
            return
        self._stop_progress_logger()
        self._set_running(False)
        self.stop_flag = False
        self._refresh_progress()
        self.status_var.set("下载结束")
        if self.ban_list:
            self.log_warn("\n" + "=" * 30)
            self.log_warn(f"📋 封禁槽位汇总 (共 {len(self.ban_list)} 个):")
            for info in self.ban_list:
                self.log_warn(f"   {info}")
            self.log_warn("=" * 30)
        if self.fail_list:
            self.log_error("\n" + "=" * 30)
            self.log_error(f"📋 失败槽位汇总 (共 {len(self.fail_list)} 个):")
            for uid, idx, out, msg, ban_status in self.fail_list:
                self.log_error(f"   UID: {uid}, 存档: {idx}, 原因: {msg}")
            self.log_error("=" * 30)
        done = min(self.done_tasks, self.total_tasks)
        self.log(f"下载统计：成功槽位 {self.success_count}，失败槽位 {self.fail_count}，"
                 f"封禁槽位 {self.ban_count}，未创建存档 {self.empty_count}，"
                 f"申请过快 {self.toofast_count}（任务 {done}/{self.total_tasks}）")
        if show_dialog:
            messagebox.showinfo("完成", f"任务处理：{done}/{self.total_tasks}\n"
                                       f"成功槽位：{self.success_count}\n"
                                       f"失败槽位：{self.fail_count}\n"
                                       f"封禁槽位：{self.ban_count}\n"
                                       f"未创建存档：{self.empty_count}\n"
                                       f"申请过快：{self.toofast_count}")


def run_tool(parent=None):
    """启动逐槽下载工具界面。

    parent 非空时创建 **Toplevel 子窗口**（复用主程序的 Tcl 解释器，可被子窗口
    与主程序共用 UI 线程）；parent 为空时创建独立 Tk 根窗口（单独运行/打包）。

    ★ 必须在主线程调用：tkinter 的 Tcl 解释器只能由创建它的线程访问与销毁。
    """
    if parent is not None:
        win = tk.Toplevel(parent)
        App(win)
        return win
    root = tk.Tk()
    App(root)
    root.mainloop()
    return root


if __name__ == "__main__":
    run_tool()
