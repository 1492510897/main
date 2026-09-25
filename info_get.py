"""
info_get (γ 合并版) v3.2.0
爆枪突击存档下载工具 —— 融合 α(info_get5) 与 β(info_get_v2)

功能整合：
  • 单UID整账号下载(1~8槽)、账号转UID、导入 uid/uid,index 任务文件批量整账号下载、
    批量文件夹导入(多任务文件)、停止下载、申请节流防封、失败槽位重试、存档封禁状态列
  • 按 config.ini 的 work_dir 组织输出目录、任务文件按文件名分文件夹、进度条

服务器响应判定(v3.2.0)：
  • 返回 0（或空对象） → 未创建存档，正常现象（不计失败、不重试）
  • 返回空响应          → 申请过快，服务器拒绝访问（标记后交由节流/重试处理）
  • 返回 dict 带 data   → 正常存档；status=1/2 → 临时/永久封禁

申请节流(v3.2.0)：每申请 200 个存档（槽位）暂停 30 秒，暂停期间不发出新申请

批量下载说明(v3.1.0 起统一为整账号下载，等同“指定UID下载”)：
  • 任务行  uid        (新模式) → 下载该账号全部 1~8 槽位
  • 任务行  uid,index  (旧模式) → 同样下载全部 1~8 槽位，index 忽略（兼容旧文件）
  • 相同 uid 自动去重，避免重复下载整账号

输出目录约定(读取 config.ini Settings.work_dir，默认 test)：
  指定UID下载          → <work_dir>/<uid>/
  UID文件批量下载       → <work_dir>/<任务文件主名>/<uid>/     (整账号1~8槽)
  文件夹批量导入        → <work_dir>/<每个任务文件主名>/<uid>/
每个UID目录内含：raw/<uid>_<idx>.json、存档XML、<uid>_details.csv
"""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
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
# 路径统一以“程序所在目录”为基准（见 app_paths），从任何目录启动均读写同一份配置，
# 不再依赖 os.getcwd()（旧版从上级目录启动时会另建一套 config/test）。
CONFIG_FILE = app_paths.in_program_dir("config.ini")
DEFAULT_WORK_DIR = app_paths.in_program_dir("test")
DEFAULT_GAME_ID = "100027788"
GAMEID = DEFAULT_GAME_ID


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
MAX_CONCURRENT_TASKS = 8       # 槽位级并发（单账号内 8 槽并行，等同单UID下载）
MAX_CONCURRENT_ACCOUNTS = 2    # 批量时同时下载的账号数（账号内仍 8 槽并行，控制总请求量防封）
MAX_RETRIES = 3

# ================= 申请节流（防封） =================
# 每申请 REQUEST_BATCH_SIZE 个存档（槽位）暂停 REQUEST_PAUSE_TIME 秒；
# 由 SaveArchiver._acquire_request_slot 统一执行，暂停期间不会发出新申请。
REQUEST_BATCH_SIZE = 200
REQUEST_PAUSE_TIME = 30

# ================= 槽位状态标记 =================
# download_single_slot 返回的 status 字段（字符串标记，区别于服务器返回的 status 码）
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

    async def download_single_slot(self, index, uid, gamekey, uid_folder):
        """下载单个槽位并存原始json。返回 dict 描述该槽位。

        服务器响应形态：
          • dict 且含 data → 正常存档
          • 0 / 空对象    → 未创建存档（正常现象，不算失败）
          • 空响应        → 申请过快，服务器拒绝访问（标记后交由节流/重试处理）
        """
        await self._acquire_request_slot()
        data = {
            'uid': uid, 'gameid': GAMEID, 'gamekey': gamekey,
            'index': index, 'verify': self.take_verify(index, uid, GAMEID, gamekey)
        }
        raw_folder = os.path.join(uid_folder, RAW_SUB_DIR)
        os.makedirs(raw_folder, exist_ok=True)
        raw_path = os.path.join(raw_folder, f"{uid}_{index}.json")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post('https://save.api.4399.com/ranging.php/?ac=get',
                                        data=data, timeout=15) as response:
                    resp_text = await response.text()
                stripped = resp_text.strip()

                # 空响应：申请过快，服务器拒绝访问（等节流后由重试处理）
                if not stripped:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write("")
                    return {"index": index, "title": "", "status": STATUS_TOO_FAST,
                            "create_time": "", "update_times": "", "datetime": "",
                            "data": "", "ban_status": STATUS_TOO_FAST}

                # 服务器返回 0（或空对象）：该槽位未创建存档，属正常现象
                if stripped in ("0", "{}"):
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(stripped)
                    return {"index": index, "title": "", "status": STATUS_EMPTY_SLOT,
                            "create_time": "", "update_times": "", "datetime": "",
                            "data": "", "ban_status": STATUS_EMPTY_SLOT}

                try:
                    json_data = json.loads(stripped)
                    with open(raw_path, "w", encoding="utf-8") as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=4)
                except Exception:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(resp_text)
                    return {"index": index, "title": "", "status": STATUS_PARSE_ERROR,
                            "create_time": "", "update_times": "", "datetime": "",
                            "data": "", "ban_status": STATUS_PARSE_ERROR}

                # 其它非对象响应（如 null）同样按未创建存档处理
                if not isinstance(json_data, dict):
                    return {"index": index, "title": "", "status": STATUS_EMPTY_SLOT,
                            "create_time": "", "update_times": "", "datetime": "",
                            "data": "", "ban_status": STATUS_EMPTY_SLOT}

                status_code = json_data.get("status", 0)
                title = json_data.get("title")
                if title is None:
                    title = f"uid{uid}_idx{index}"

                result = {
                    "index": index, "title": title, "status": status_code,
                    "create_time": json_data.get("create_time", ""),
                    "update_times": json_data.get("update_times", ""),
                    "datetime": json_data.get("datetime", ""),
                    "data": json_data.get("data", ""),
                    "ban_status": self.get_status_text(status_code)
                }

                b64_data = json_data.get("data", "")
                if b64_data and status_code == 0:
                    xml_content = self.process_save_data(b64_data)
                    if xml_content:
                        safe_title = sanitize_filename(title)
                        save_path = os.path.join(uid_folder, f"{uid}_{index}_{safe_title}.xml")
                        with open(save_path, "w", encoding="utf-8") as f:
                            f.write(xml_content)
                return result
            except Exception:
                return {"index": index, "title": "", "status": STATUS_NET_ERROR,
                        "create_time": "", "update_times": "", "datetime": "",
                        "data": "", "ban_status": STATUS_NET_ERROR}

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

    async def download_account(self, uid, uid_folder=None, update_log=None):
        """整账号全存档下载（8 槽位），写 XML + <uid>_details.csv。
        返回 results 列表（每槽位 dict，含 status_text/ban_status）"""
        if uid_folder is None:
            uid_folder = os.path.join(get_work_dir(), uid)
        os.makedirs(uid_folder, exist_ok=True)
        gamekey = self.calculate_gamekey()

        if update_log:
            update_log(f"[{uid}] 开始下载")
        tasks = [self.download_single_slot(str(i), uid, gamekey, uid_folder) for i in range(8)]
        raw_results = await asyncio.gather(*tasks)

        results = []
        for index in range(8):
            result = raw_results[index]
            status_text = STATUS_EMPTY_SLOT
            title = ""
            create_time = update_times = datetime_val = ban_status = ""
            if isinstance(result, dict):
                status_code = str(result.get("status", ""))
                title = result.get("title", "")
                create_time = result.get("create_time", "")
                update_times = result.get("update_times", "")
                datetime_val = result.get("datetime", "")
                ban_status = result.get("ban_status", "")
                if status_code in (STATUS_PARSE_ERROR, STATUS_NET_ERROR,
                                   STATUS_TOO_FAST, STATUS_EMPTY_SLOT):
                    # 槽位级标记（download_single_slot 返回，status 为字符串而非服务器码）
                    status_text = status_code
                elif status_code == "1":
                    status_text = "临时封禁"
                elif status_code == "2":
                    status_text = "永久封禁"
                elif not title:
                    status_text = STATUS_EMPTY_SLOT
                    title = ""
                else:
                    status_text = "正常"
            results.append({
                "index": index, "title": title, "status": status_text,
                "create_time": create_time, "update_times": update_times,
                "datetime": datetime_val, "ban_status": ban_status
            })

        # 统一 _details.csv（存档/标题/状态 → 兼容封禁缓存读取）
        csv_path = os.path.join(uid_folder, f"{uid}_details.csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["存档", "标题", "状态", "封禁状态", "创建时间", "存档次数", "最后存档实际"])
            for row in results:
                w.writerow([row["index"], row["title"], row["status"], row["ban_status"],
                            row["create_time"], row["update_times"], row["datetime"]])

        if update_log:
            bans = [r for r in results if r["status"] in ("临时封禁", "永久封禁")]
            update_log(f"[{uid}] 下载完成" + (f"（封禁槽位 {len(bans)} 个）" if bans else ""))
        return results

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

    async def download_precise(self, uid, index, output_folder):
        """下载指定槽位存档（失败槽位重试用）。
        返回 (success: bool, message: str, ban_status: str)"""
        await self._acquire_request_slot()
        gamekey = self.calculate_gamekey()
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        data = {
            'uid': uid, 'gameid': GAMEID, 'gamekey': gamekey,
            'index': index, 'verify': self.take_verify(index, uid, GAMEID, gamekey)
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post('https://save.api.4399.com/ranging.php/?ac=get',
                                        data=data) as response:
                    resp_text = await response.text()

            stripped = resp_text.strip()
            # 空响应：申请过快，服务器拒绝访问（稍后重试）
            if not stripped:
                return False, STATUS_TOO_FAST, STATUS_TOO_FAST
            # 服务器返回 0：该槽位未创建存档（正常现象，无需重试）
            if stripped in ("0", "{}"):
                return False, STATUS_EMPTY_SLOT, STATUS_EMPTY_SLOT

            try:
                json_data = json.loads(stripped)
            except json.JSONDecodeError:
                return False, "非JSON响应", STATUS_PARSE_ERROR

            if not isinstance(json_data, dict):
                return False, STATUS_EMPTY_SLOT, STATUS_EMPTY_SLOT

            status_code = json_data.get("status", 0)
            title = json_data.get("title") or f"uid{uid}_idx{index}"
            safe_title = sanitize_filename(title)
            save_path = os.path.join(output_folder, f"{uid}_{index}_{safe_title}.xml")
            b64_data = json_data.get("data", "")
            ban_status = self.get_status_text(status_code)

            if status_code == 1:
                return False, "账号临时封禁", "临时封禁"
            elif status_code == 2:
                return False, "账号永久封禁", "永久封禁"

            if status_code == 0 and b64_data:
                xml_content = self.process_save_data(b64_data)
                if xml_content:
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(xml_content)
                    return True, "下载成功", ban_status
                else:
                    return False, STATUS_PARSE_ERROR, ban_status
            else:
                return False, STATUS_EMPTY_SLOT, STATUS_EMPTY_SLOT
        except Exception as e:
            return False, str(e), STATUS_NET_ERROR


# ===================== 美化版 GUI =====================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("爆枪突击批量存档下载器 γ合并版 v3.1")
        self.root.geometry("900x600")
        self.root.configure(bg="#1e1e2e")
        self.archiver = SaveArchiver()

        # 任务数据（统一整账号，每账号下载全部1~8槽位）：
        #   单文件模式:  tasks = [("account", uid), ...]
        #   文件夹模式:  tasks = [(("account", uid), 子文件夹名), ...]
        #   旧格式 uid,index 导入时 index 被忽略，仍按整账号处理并去重
        self.tasks = []
        self.task_source_file = None
        self.task_source_folder = None

        self.is_running = False
        self.stop_flag = False
        self.total_tasks = 0
        self._account_done = 0   # 批量进度：已处理的整账号数
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

        tk.Label(left_frame, text="🎮 爆枪突击存档批量下载器",
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
        tk.Button(btn_frame, text="⬇ 指定UID下载(全档)", **mk_btn("#f38ba8", "white"),
                  command=self.start_single).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(btn_frame, text="📂 导入UID/槽位文件", **mk_btn("#a6e3a1"),
                  command=self.load_task_file).grid(row=1, column=0, padx=5, pady=5)
        tk.Button(btn_frame, text="🚀 批量下载(全档)", **mk_btn("#fab387"),
                  command=self.start_precise_batch).grid(row=1, column=1, padx=5, pady=5)

        self.import_folder_btn = tk.Button(btn_frame, text="📂 批量文件夹导入", **mk_btn("#cba6f7"),
                                           command=self.load_folder_batch)
        self.import_folder_btn.grid(row=2, column=0, padx=5, pady=5)
        self.stop_btn = tk.Button(btn_frame, text="⏹️ 停止下载", **mk_btn("#f5c2e7"),
                                  command=self.stop_batch_task, state=tk.DISABLED)
        self.stop_btn.grid(row=2, column=1, padx=5, pady=5)
        tk.Button(btn_frame, text="🧹 清除日志", **mk_btn("#74c7ec"),
                  command=self.clear_log).grid(row=3, column=0, columnspan=2, padx=5, pady=5)

        status_line = tk.Frame(left_frame, bg="#28293b")
        status_line.pack(fill=tk.X, padx=15)
        self.status_var = tk.StringVar(value="就绪")
        self.task_var = tk.StringVar(value="任务 0/0")
        tk.Label(status_line, textvariable=self.status_var, bg="#28293b", fg="#94e2d5",
                 font=("微软雅黑", 10), anchor="w").pack(side=tk.LEFT)
        tk.Label(status_line, textvariable=self.task_var, bg="#28293b", fg="#f9e2af",
                 font=("微软雅黑", 10), anchor="e").pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(left_frame, orient=tk.HORIZONTAL, length=340, mode="determinate")
        self.progress.pack(pady=6)

        # 右侧日志
        right_frame = tk.Frame(main_container, bg="#28293b", width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        right_frame.pack_propagate(False)

        log_header = tk.Frame(right_frame, bg="#28293b")
        log_header.pack(fill=tk.X, pady=8)
        tk.Label(log_header, text="📝 实时运行日志", bg="#28293b", fg="#cba6f7",
                 font=("微软雅黑", 11, "bold")).pack(side=tk.LEFT, padx=10)

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
        self._ui_call(self._clear_log_widget)

    def _clear_log_widget(self):
        if not self._alive:
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

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
        state = tk.NORMAL if not running else tk.DISABLED
        self.import_folder_btn.config(state=state)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)

    # ---------------- 任务导入 ----------------
    @staticmethod
    def parse_task_file(path):
        """每行: uid 或 uid,index → 统一整账号 [(account, uid), ...]
        旧模式(uid,index)与新模式(uid)都下载该账号全部1~8槽位，index 忽略。
        相同 uid 去重，避免旧文件同一账号多行重复下载整账号。"""
        tasks = []
        seen = set()
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "," in line:
                    parts = line.split(",", 1)
                    uid = parts[0].strip()
                else:
                    uid = line
                uid = uid.strip()
                if uid.isdigit() and uid not in seen:
                    seen.add(uid)
                    tasks.append(("account", uid))
        return tasks

    def load_task_file(self):
        path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt *.csv"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            tasks = self.parse_task_file(path)
            if not tasks:
                messagebox.showwarning("提示", "文件中没有有效的 UID 或 uid,index 行")
                return
            self.tasks = tasks
            self.task_source_file = Path(path)
            self.task_source_folder = None
            self.log(f"📂 导入整账号任务 {len(tasks)} 个 (文件: {Path(path).name})：每个账号下载全部 1~8 槽位")
            messagebox.showinfo("成功", f"导入 {len(tasks)} 个整账号任务\n每账号下载 1~8 全部槽位\n(旧格式 uid,index 的 index 已忽略)")
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
                for t in self.parse_task_file(os.path.join(folder_path, fn)):
                    tasks.append((t, sub))
            if not tasks:
                messagebox.showwarning("提示", "文件夹中所有文件都没有有效任务")
                return
            self.tasks = tasks
            self.task_source_folder = folder_path
            self.task_source_file = None
            self.log(f"📂 文件夹导入：{len(files)} 个任务文件，共 {len(tasks)} 个整账号（每账号下载 1~8 全部槽位）")
            messagebox.showinfo("成功", f"发现 {len(files)} 个任务文件\n共 {len(tasks)} 个整账号任务\n(旧格式 uid,index 的 index 已忽略)")
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
        uid = self.uid_entry.get().strip()
        threading.Thread(target=self.run_single, args=(uid,), daemon=True).start()

    def run_single(self, uid=""):
        """指定 UID 下载（在子线程运行 → 界面操作全部投递主线程）。"""
        if not uid or not uid.isdigit():
            self._ui_call(messagebox.showwarning, "提示", "输入有效UID")
            return
        self._ui_call(self.status_var.set, "下载中...")
        self._setup_throttle()
        try:
            results = asyncio.run(self.archiver.download_account(uid, update_log=self.log))
            ok = sum(1 for r in results if r.get("status") == "正常")
            empty = sum(1 for r in results if r.get("status") == STATUS_EMPTY_SLOT)
            too_fast = sum(1 for r in results if r.get("status") == STATUS_TOO_FAST)
            self._ui_call(self.status_var.set, "✅ 单UID下载完成")
            self.log(f"下载完成：正常 {ok} 槽，未创建存档 {empty} 槽"
                     + (f"，{STATUS_TOO_FAST} {too_fast} 槽" if too_fast else ""))
        except Exception as e:
            self.log_error(f"错误：{str(e)}")
            self._ui_call(self.status_var.set, "下载失败")

    # ---------------- 批量下载 ----------------
    def start_precise_batch(self):
        if not self.tasks:
            messagebox.showwarning("提示", "请先导入 UID 任务文件")
            return
        if self.is_running:
            return
        self._set_running(True)
        self.stop_flag = False
        self._account_done = 0
        self.success_count = self.fail_count = self.ban_count = 0
        self.empty_count = self.toofast_count = 0
        self.ban_list = []
        self.fail_list = []
        threading.Thread(target=self.run_precise_async, daemon=True).start()

    def stop_batch_task(self):
        if not self.is_running:
            return
        self.stop_flag = True
        self.log_warn("正在停止...")

    def _out_dir_for(self, t, sub=None):
        """返回任务的输出uid目录（基准目录取自最新配置的 work_dir）。"""
        base_save_dir = get_work_dir()
        uid = t[1]
        if sub:
            return os.path.join(base_save_dir, sub, uid)
        if self.task_source_file:
            return os.path.join(base_save_dir, self.task_source_file.stem, uid)
        return os.path.join(base_save_dir, uid)

    def run_precise_async(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_precise_task())
        except Exception as e:
            self.log_error(f"错误：{e}")
        finally:
            loop.close()
            self.on_task_complete()

    async def run_precise_task(self):
        self.total_tasks = len(self.tasks)   # 按整账号计数（每账号下载 1~8 槽）
        self._ui_call(self._set_total_tasks_ui, self.total_tasks)
        self._ui_call(self.status_var.set, "批量下载中...")
        self.log(f"===== 开始批量下载，共 {self.total_tasks} 个账号（每账号下载 1~8 全部槽位）=====")
        self.log(f"⏱ 申请节流：每申请 {REQUEST_BATCH_SIZE} 个存档暂停 {REQUEST_PAUSE_TIME} 秒")

        # 申请节流：全账号共用同一计数器/闸门（每 REQUEST_BATCH_SIZE 个存档暂停一次）
        self._setup_throttle()

        # 账号级并发限制：每个账号内 8 槽并行(等同单uid下载)，但同一时间只跑少数账号，控制总请求量
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_ACCOUNTS)
        self._account_done = 0   # 已处理完的整账号数（进度用）

        async def run_task(item):
            async with semaphore:
                if self.stop_flag:
                    return
                try:
                    if self.task_source_folder:
                        t, sub = item
                    else:
                        t, sub = item, None
                    uid = t[1]
                    out = self._out_dir_for(t, sub)
                    # 新旧任务格式统一为整账号，复用与“指定UID下载”相同的下载逻辑
                    await self._run_account_task(uid, out)
                except Exception as e:
                    self.log_error(f"❌ 任务异常: {e}")
                    self.fail_count += 1
                finally:
                    self._account_done += 1
                    self._refresh_progress()

        # 全部任务一次性提交：防封暂停由申请节流控制（每申请 REQUEST_BATCH_SIZE 个存档暂停一次），
        # 不再按账号分批暂停（旧逻辑每批 200 个账号 = 最多 1600 次申请，对服务端太激进）
        await asyncio.gather(*[run_task(item) for item in self.tasks])

        # 重试失败槽位（非封禁）
        if not self.stop_flag:
            await self._retry_fails()

    async def _run_account_task(self, uid, out):
        """下载一个整账号(1~8槽,与单uid一致)，逐槽记录成功/封禁/失败。"""
        results = await self.archiver.download_account(uid, uid_folder=out)
        for r in results:
            st = r.get("status", "")
            idx = r.get("index", "")
            if st in ("临时封禁", "永久封禁"):
                self.ban_count += 1
                self.ban_list.append(f"UID: {uid}, 存档: {idx}, 状态: {st}")
                self.log_warn(f"⚠️ UID {uid} 存档 {idx}: {st}")
            elif st == "正常":
                self.success_count += 1
            elif st == STATUS_EMPTY_SLOT:
                # 服务器返回 0：未创建存档，正常现象（不算失败）
                self.empty_count += 1
            elif st in RETRYABLE_STATUSES:
                # 网络/解析异常、申请过快 → 计入失败并重试
                if st == STATUS_TOO_FAST:
                    self.toofast_count += 1
                    self.log_warn(f"⏳ UID {uid} 存档 {idx}: {STATUS_TOO_FAST}（服务器拒绝访问），稍后重试")
                self.fail_count += 1
                self.fail_list.append((uid, idx, out, st, ""))

    async def _retry_fails(self):
        normal = [x for x in self.fail_list if x[4] not in ("临时封禁", "永久封禁")]
        if not normal:
            return

        # “申请过快”属服务端限流，先冷却再重试
        too_fast = [x for x in normal if x[3] == STATUS_TOO_FAST]
        if too_fast:
            self.log_warn(f"其中 {len(too_fast)} 个槽位为「{STATUS_TOO_FAST}」，"
                          f"先冷却 {TOO_FAST_RETRY_COOLDOWN} 秒再重试...")
            for _ in range(TOO_FAST_RETRY_COOLDOWN):
                if self.stop_flag:
                    return
                await asyncio.sleep(1)

        self.log_warn(f"开始重试 {len(normal)} 个失败槽位（非封禁）...")
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

        async def retry_one(uid, idx, out):
            async with semaphore:
                for attempt in range(MAX_RETRIES):
                    if self.stop_flag:
                        return
                    ok, msg, ban_status = await self.archiver.download_precise(uid, idx, out)
                    if ban_status in ("临时封禁", "永久封禁"):
                        self.ban_count += 1
                        self.ban_list.append(f"UID: {uid}, 存档: {idx}, 状态: {ban_status}")
                        self.log_warn(f"⚠️ 重试发现封禁 UID {uid} 存档 {idx}: {ban_status}")
                        self.fail_count = max(0, self.fail_count - 1)
                        return
                    if ok:
                        self.success_count += 1
                        self.fail_count = max(0, self.fail_count - 1)
                        return
                    if ban_status == STATUS_EMPTY_SLOT:
                        # 服务器返回 0：未创建存档，正常现象，无需重试
                        self.empty_count += 1
                        self.fail_count = max(0, self.fail_count - 1)
                        return
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(1)
                self.log_error(f"❌ 重试失败 UID {uid} 存档 {idx}")

        await asyncio.gather(*[retry_one(*x[:3]) for x in normal])

    def _set_total_tasks_ui(self, total):
        """主线程：重置进度条量程。"""
        if not self._alive:
            return
        self.progress["maximum"] = total
        self.progress["value"] = 0

    def _refresh_progress(self):
        # 进度按账号计数推进，与槽位成功/失败/封禁统计解耦
        done = min(self._account_done, self.total_tasks)
        total = self.total_tasks
        self._ui_call(self._refresh_progress_ui, done, total)

    def _refresh_progress_ui(self, done, total):
        if not self._alive:
            return
        self.progress["value"] = done
        self.task_var.set(f"账号 {done}/{total}")

    def on_task_complete(self):
        """下载结束（可能从子线程调）→ 界面更新全部走主线程。"""
        self._ui_call(self._on_task_complete_ui)

    def _on_task_complete_ui(self):
        if not self._alive:
            return
        self._set_running(False)
        self.stop_flag = False
        self._refresh_progress()
        self.status_var.set("下载结束")
        if self.ban_list:
            self.log_warn(f"\n{'=' * 30}\n📋 封禁槽位汇总 (共 {len(self.ban_list)} 个):")
            for info in self.ban_list:
                self.log_warn(f"   {info}")
            self.log_warn('=' * 30)
        if self.fail_list:
            real = [x for x in self.fail_list if x[4] not in ("临时封禁", "永久封禁")]
            self.log_error(f"\n{'=' * 30}\n📋 失败槽位汇总 (共 {len(real)} 个):")
            for uid, idx, out, msg, bs in real:
                self.log_error(f"   UID: {uid}, 存档: {idx}, 原因: {msg}")
            self.log_error('=' * 30)
        self.log(f"下载统计：成功槽位 {self.success_count}，失败槽位 {self.fail_count}，封禁槽位 {self.ban_count}"
                 f"，未创建存档 {self.empty_count}，申请过快 {self.toofast_count}（账号 {self._account_done}/{self.total_tasks}）")
        messagebox.showinfo("完成", f"账号处理：{self._account_done}/{self.total_tasks}\n成功槽位：{self.success_count}\n"
                                   f"失败槽位：{self.fail_count}\n封禁槽位：{self.ban_count}\n"
                                   f"未创建存档：{self.empty_count}\n申请过快：{self.toofast_count}")


def run_tool(parent=None):
    """启动下载工具界面。

    parent 非空时创建 **Toplevel 子窗口**（复用主程序的 Tcl 解释器，可被子窗口
    与主程序共用 UI 线程）；parent 为空时创建独立 Tk 根窗口（单独运行/打包）。

    ★ 必须在主线程调用：tkinter 的 Tcl 解释器只能由创建它的线程访问与销毁。
      旧实现在子线程里调本函数，内部再 tk.Tk() 出第二个解释器，退出时于错误
      线程清理 → “Tcl_AsyncDelete: async handler deleted by the wrong thread”，
      进程无声中止。
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
