"""
info_get (γ 合并版) v3.0.0
爆枪突击存档下载工具 —— 融合 α(info_get5) 与 β(info_get_v2)

功能整合：
  • α：单UID全存档下载、账号转UID、导入(uid[,index])文件批量下载、
        批量文件夹导入(多任务文件)、停止下载、分批暂停防封、失败重试、存档封禁状态列
  • β：按 config.ini 的 work_dir 组织输出目录、任务文件按文件名分文件夹、
        导入仅UID列表→整账号全档下载、进度条

输出目录约定(读取 config.ini Settings.work_dir，默认 test)：
  指定UID下载          → <work_dir>/<uid>/
  UID文件批量下载       → <work_dir>/<任务文件主名>/<uid>/     (整账号或指定槽位)
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
import csv
import configparser
from pathlib import Path
import time

# ================= 配置区域 =================
CONFIG_FILE = "config.ini"
DEFAULT_GAME_ID = "100027788"
GAMEID = DEFAULT_GAME_ID


def _get_work_dir():
    """读取统一工作目录(兼容旧版 temp_dir 键)"""
    if not os.path.exists(CONFIG_FILE):
        return os.path.join(os.getcwd(), "test")
    try:
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE, encoding='utf-8-sig')
        work_dir = config.get('Settings', 'work_dir', fallback=None)
        if not work_dir:
            work_dir = config.get('Settings', 'temp_dir', fallback='test')
        os.makedirs(work_dir, exist_ok=True)
        return work_dir
    except Exception:
        return os.path.join(os.getcwd(), "test")


BASE_SAVE_DIR = _get_work_dir()
RAW_SUB_DIR = "raw"
MAX_CONCURRENT_TASKS = 8
MAX_RETRIES = 3


class SaveArchiver:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        })

    def take_verify(self, index: str, uid: str, gameid: str, gamekey: str) -> str:
        raw = f"SDALPlsldlnSLWPElsdslSE{index}{gamekey}{uid}{gameid}PKslsO"
        for _ in range(3):
            raw = hashlib.md5(raw.encode()).hexdigest()
        return raw

    def get_status_text(self, status_code):
        status_map = {"0": "正常", "1": "暂时封禁", "2": "永久封禁"}
        return status_map.get(str(status_code), "未知状态")

    async def download_single_slot(self, index, uid, gamekey, uid_folder):
        """下载单个槽位并存原始json。返回 dict 描述该槽位。"""
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
                try:
                    json_data = json.loads(resp_text)
                    with open(raw_path, "w", encoding="utf-8") as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=4)
                except Exception:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(resp_text)
                    return {"index": index, "title": "未创建存档", "status_text": "解析失败",
                            "create_time": "", "update_times": "", "datetime": "", "ban_status": "未知"}

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
                        safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')
                        save_path = os.path.join(uid_folder, f"{uid}_{index}_{safe_title}.xml")
                        with open(save_path, "w", encoding="utf-8") as f:
                            f.write(xml_content)
                return result
            except Exception:
                return {"index": index, "title": "未创建存档", "status_text": "网络异常",
                        "create_time": "", "update_times": "", "datetime": "", "ban_status": "网络异常"}

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
            uid_folder = os.path.join(BASE_SAVE_DIR, uid)
        os.makedirs(uid_folder, exist_ok=True)
        gamekey = self.calculate_gamekey()

        if update_log:
            update_log(f"[{uid}] 开始下载")
        tasks = [self.download_single_slot(str(i), uid, gamekey, uid_folder) for i in range(8)]
        raw_results = await asyncio.gather(*tasks)

        results = []
        for index in range(8):
            result = raw_results[index]
            status_text = "未创建存档"
            title = ""
            create_time = update_times = datetime_val = ban_status = ""
            if isinstance(result, dict):
                status_code = str(result.get("status", ""))
                title = result.get("title", "")
                create_time = result.get("create_time", "")
                update_times = result.get("update_times", "")
                datetime_val = result.get("datetime", "")
                ban_status = result.get("ban_status", "")
                if status_code == "1":
                    status_text = "临时封禁"
                elif status_code == "2":
                    status_text = "永久封禁"
                elif not title or title == "未创建存档":
                    status_text = "未创建存档"
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
        """下载指定槽位存档。
        返回 (success: bool, message: str, ban_status: str)"""
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
            try:
                json_data = json.loads(resp_text)
                status_code = json_data.get("status", 0)
                title = json_data.get("title", f"uid{uid}_idx{index}")
                safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')
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
                        return False, "解析失败", ban_status
                else:
                    return False, "存档为空或不存在", ban_status
            except json.JSONDecodeError:
                return False, "非JSON响应", "解析错误"
        except Exception as e:
            return False, str(e), "网络错误"


# ===================== 美化版 GUI =====================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("爆枪突击批量存档下载器 γ合并版 v3.0")
        self.root.geometry("900x600")
        self.root.configure(bg="#1e1e2e")
        self.archiver = SaveArchiver()

        # 任务数据：
        #   单文件模式:  tasks = [("account", uid) | ("slot", uid, index)]
        #   文件夹模式:  tasks = [(("account"|"slot", ...), 子文件夹名)]
        self.tasks = []
        self.task_source_file = None
        self.task_source_folder = None

        self.is_running = False
        self.stop_flag = False
        self.total_tasks = 0
        self.success_count = 0
        self.fail_count = 0
        self.ban_count = 0
        self.ban_list = []
        self.fail_list = []   # (uid, idx, out, msg, ban_status)

        self.build_ui()

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
        tk.Button(btn_frame, text="🚀 批量下载", **mk_btn("#fab387"),
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
        def _do():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n", tag or "")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def log_error(self, msg):
        self.log(msg, "error")

    def log_warn(self, msg):
        self.log(msg, "warn")

    def clear_log(self):
        def _do():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def _set_running(self, running):
        self.is_running = running
        state = tk.NORMAL if not running else tk.DISABLED
        self.import_folder_btn.config(state=state)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)

    # ---------------- 任务导入 ----------------
    @staticmethod
    def parse_task_file(path):
        """每行: uid 或 uid,index → [(kind, uid[, index]), ...]"""
        tasks = []
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "," in line:
                    parts = line.split(",", 1)
                    uid, idx = parts[0].strip(), parts[1].strip()
                    if uid.isdigit() and idx.isdigit():
                        tasks.append(("slot", uid, idx))
                else:
                    uid = line
                    if uid.isdigit():
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
            accounts = sum(1 for t in tasks if t[0] == "account")
            slots = len(tasks) - accounts
            self.log(f"📂 导入任务 {len(tasks)} 条 (文件: {Path(path).name})：整账号 {accounts} / 指定槽位 {slots}")
            messagebox.showinfo("成功", f"导入 {len(tasks)} 个任务\n整账号 {accounts} 个\n指定槽位 {slots} 个")
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
            self.log(f"📂 文件夹导入：{len(files)} 个任务文件，共 {len(tasks)} 条任务")
            messagebox.showinfo("成功", f"发现 {len(files)} 个任务文件\n共 {len(tasks)} 条任务")
        except Exception as e:
            self.log_error(f"❌ 导入失败：{str(e)}")
            messagebox.showerror("错误", str(e))

    # ---------------- 账号转UID ----------------
    def get_uid_thread(self):
        threading.Thread(target=self.get_uid, daemon=True).start()

    def get_uid(self):
        user = self.user_entry.get().strip()
        if not user:
            messagebox.showwarning("提示", "输入账号")
            return
        self.status_var.set("检测中...")
        if not self.archiver.check_account_exists(user):
            messagebox.showerror("错误", "账号不存在")
            self.status_var.set("失败")
            return
        uid = self.archiver.get_uid_from_account(user)
        if uid:
            self.uid_entry.delete(0, tk.END)
            self.uid_entry.insert(0, uid)
            self.status_var.set("✅ UID获取成功")
        else:
            messagebox.showerror("错误", "获取失败")
            self.status_var.set("失败")

    # ---------------- 指定UID整账号下载 ----------------
    def start_single(self):
        threading.Thread(target=self.run_single, daemon=True).start()

    def run_single(self):
        uid = self.uid_entry.get().strip()
        if not uid or not uid.isdigit():
            messagebox.showwarning("提示", "输入有效UID")
            return
        self.status_var.set("下载中...")
        try:
            asyncio.run(self.archiver.download_account(uid, update_log=self.log))
            self.status_var.set("✅ 单UID下载完成")
        except Exception as e:
            self.log_error(f"错误：{str(e)}")
            self.status_var.set("下载失败")

    # ---------------- 批量下载 ----------------
    def start_precise_batch(self):
        if not self.tasks:
            messagebox.showwarning("提示", "请先导入 UID/槽位 任务文件")
            return
        if self.is_running:
            return
        self._set_running(True)
        self.stop_flag = False
        self.success_count = self.fail_count = self.ban_count = 0
        self.ban_list = []
        self.fail_list = []
        threading.Thread(target=self.run_precise_async, daemon=True).start()

    def stop_batch_task(self):
        if not self.is_running:
            return
        self.stop_flag = True
        self.log_warn("正在停止...")

    def _out_dir_for(self, t, sub=None):
        """返回任务的输出uid目录"""
        uid = t[1]
        if sub:
            return os.path.join(BASE_SAVE_DIR, sub, uid)
        if self.task_source_file:
            return os.path.join(BASE_SAVE_DIR, self.task_source_file.stem, uid)
        return os.path.join(BASE_SAVE_DIR, uid)

    def run_precise_async(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_precise_task())
        except Exception as e:
            self.log_error(f"错误：{e}")
        finally:
            loop.close()
            self.root.after(0, self.on_task_complete)

    async def run_precise_task(self):
        self.total_tasks = len(self.tasks)
        self.progress["maximum"] = self.total_tasks
        self.progress["value"] = 0
        self.status_var.set("批量下载中...")
        self.log(f"===== 开始批量下载，共 {self.total_tasks} 条任务 =====")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

        async def run_task(item):
            async with semaphore:
                if self.stop_flag:
                    return
                try:
                    if self.task_source_folder:
                        t, sub = item
                    else:
                        t, sub = item, None
                    out = self._out_dir_for(t, sub)
                    if t[0] == "account":
                        await self._run_account_task(t[1], out)
                    else:
                        uid, idx = t[1], t[2]
                        ok, msg, ban_status = await self.archiver.download_precise(uid, idx, out)
                        self._record_result(uid, idx, out, ok, msg, ban_status)
                except Exception as e:
                    self.log_error(f"❌ 任务异常: {e}")
                    self.fail_count += 1

        # 分批处理防封
        BATCH_SIZE = 200
        PAUSE_TIME = 30
        total_batches = (self.total_tasks + BATCH_SIZE - 1) // BATCH_SIZE
        for batch_num in range(total_batches):
            if self.stop_flag:
                break
            s = batch_num * BATCH_SIZE
            e = min(s + BATCH_SIZE, self.total_tasks)
            self.log(f"第 {batch_num + 1}/{total_batches} 批，本批 {e - s} 条")
            await asyncio.gather(*[run_task(item) for item in self.tasks[s:e]])
            self._refresh_progress()
            if batch_num < total_batches - 1 and not self.stop_flag:
                self.log_warn(f"暂停 {PAUSE_TIME} 秒后继续下一批...")
                for _ in range(PAUSE_TIME):
                    if self.stop_flag:
                        break
                    await asyncio.sleep(1)

        # 重试失败项（非封禁）
        if not self.stop_flag:
            await self._retry_fails()

    async def _run_account_task(self, uid, out):
        results = await self.archiver.download_account(uid, uid_folder=out)
        bans = [r for r in results if r["status"] in ("临时封禁", "永久封禁")]
        for r in bans:
            self.ban_count += 1
            self.ban_list.append(f"UID: {uid}, 存档: {r['index']}, 状态: {r['status']}")
            self.log_warn(f"⚠️ UID {uid} 存档 {r['index']}: {r['status']}")
        self.success_count += 1

    def _record_result(self, uid, idx, out, ok, msg, ban_status):
        if ban_status in ("临时封禁", "永久封禁"):
            self.ban_count += 1
            self.ban_list.append(f"UID: {uid}, 存档: {idx}, 状态: {ban_status}")
            self.fail_list.append((uid, idx, out, msg, ban_status))
            self.log_warn(f"⚠️ UID {uid} 存档 {idx}: {ban_status}")
        elif not ok:
            self.fail_count += 1
            self.fail_list.append((uid, idx, out, msg, ban_status))
            self.log_error(f"❌ UID {uid} 存档 {idx}: {msg}")
        else:
            self.success_count += 1

    async def _retry_fails(self):
        normal = [x for x in self.fail_list if x[4] not in ("临时封禁", "永久封禁")]
        if not normal:
            return
        self.log_warn(f"开始重试 {len(normal)} 个失败项（非封禁）...")
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
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(1)
                self.log_error(f"❌ 重试失败 UID {uid} 存档 {idx}")

        await asyncio.gather(*[retry_one(*x[:3]) for x in normal])

    def _refresh_progress(self):
        done = min(self.success_count + self.fail_count + self.ban_count, self.total_tasks)
        self.progress["value"] = done
        self.task_var.set(f"任务 {done}/{self.total_tasks}")

    def on_task_complete(self):
        self._set_running(False)
        self.stop_flag = False
        self._refresh_progress()
        self.status_var.set("下载结束")
        if self.ban_list:
            self.log_warn(f"\n{'=' * 30}\n📋 封禁账号汇总 (共 {len(self.ban_list)} 个):")
            for info in self.ban_list:
                self.log_warn(f"   {info}")
            self.log_warn('=' * 30)
        if self.fail_list:
            real = [x for x in self.fail_list if x[4] not in ("临时封禁", "永久封禁")]
            self.log_error(f"\n{'=' * 30}\n📋 失败账号汇总 (共 {len(real)} 个):")
            for uid, idx, out, msg, bs in real:
                self.log_error(f"   UID: {uid}, 存档: {idx}, 原因: {msg}")
            self.log_error('=' * 30)
        self.log(f"下载统计：成功 {self.success_count}，失败 {self.fail_count}，封禁 {self.ban_count}")
        messagebox.showinfo("完成", f"成功：{self.success_count}\n失败：{self.fail_count}\n封禁：{self.ban_count}")


def run_tool():
    """可被外部(检测主程序)调用的启动函数"""
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    run_tool()
