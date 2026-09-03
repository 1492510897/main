"""info_getα.4.1.py"""
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
def _get_temp_dir():
    import configparser
    import os
    if not os.path.exists(CONFIG_FILE):
        return os.path.join(os.getcwd(), "download_cache")
    try:
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE, encoding='utf-8')
        temp_dir = config.get('Settings', 'temp_dir', fallback='download_cache')
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir
    except:
        return os.path.join(os.getcwd(), "download_cache")
BASE_SAVE_DIR = _get_temp_dir()
RAW_SUB_DIR = "raw"
ROOT_OUTPUT_DIR = "test"
MAX_CONCURRENT_TASKS = 8
MAX_RETRIES = 3
# ===========================================

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
        data = {
            'uid': uid, 'gameid': GAMEID, 'gamekey': gamekey,
            'index': index, 'verify': self.take_verify(index, uid, GAMEID, gamekey)
        }
        raw_folder = os.path.join(uid_folder, RAW_SUB_DIR)
        os.makedirs(raw_folder, exist_ok=True)
        raw_path = os.path.join(raw_folder, f"{uid}_{index}.json")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post('https://save.api.4399.com/ranging.php/?ac=get', data=data, timeout=15) as response:
                    resp_text = await response.text()
                    try:
                        json_data = json.loads(resp_text)
                        with open(raw_path, "w", encoding="utf-8") as f:
                            json.dump(json_data, f, ensure_ascii=False, indent=4)
                    except:
                        with open(raw_path, "w", encoding="utf-8") as f:
                            f.write(resp_text)
                        return {"index": index, "title": "未创建存档", "status_text": "解析失败", "create_time": "", "update_times": "", "datetime": "", "ban_status": "未知"}

                    status_code = json_data.get("status", 0)
                    
                    title = json_data.get("title") 
                    if title is None: 
                        title = "" 

                    result = {
                        "index": index, 
                        "title": title, 
                        "status": status_code,
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
                            xml_path = os.path.join(uid_folder, f"{uid}_{index}.xml")
                            with open(xml_path, "w", encoding="utf-8") as f:
                                f.write(xml_content)
                    return result
            except:
                return {"index": index, "title": "未创建存档", "status_text": "网络异常", "create_time": "", "update_times": "", "datetime": "", "ban_status": "网络异常"}

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
        except:
            return None

    async def batch_download(self, uid, update_log=None):
        gamekey = self.calculate_gamekey()
        uid_folder = os.path.join(BASE_SAVE_DIR, uid)
        os.makedirs(uid_folder, exist_ok=True)
    
        if update_log:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            update_log(f"{current_time}")
            update_log(f"[{uid}] 开始下载")

        results = []
        tasks = [self.download_single_slot(str(i), uid, gamekey, uid_folder) for i in range(8)]
        raw_results = await asyncio.gather(*tasks)

        for index in range(8):
            result = raw_results[index]
            status_text = "未创建存档"
            title = ""
            create_time = ""
            update_times = ""
            datetime_val = ""
            ban_status = ""

            if isinstance(result, dict):
                status_code = str(result.get("status", ""))
                title = result.get("title", "")
                
                if status_code == "1":
                    status_text = "临时封禁"
                elif status_code == "2":
                    status_text = "永久封禁"
                elif not title or title == "未创建存档":
                    status_text = "未创建存档"
                    title = ""
                else:
                    status_text = "正常"
                
                create_time = result.get("create_time", "")
                update_times = result.get("update_times", "")
                datetime_val = result.get("datetime", "")
                ban_status = result.get("ban_status", "")

            results.append({
                "index": index,
                "title": title,
                "status": status_text,
                "create_time": create_time,
                "update_times": update_times,
                "datetime": datetime_val,
                "ban_status": ban_status
            })

        csv_path = os.path.join(uid_folder, f"{uid}_details.csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["存档", "名称", "状态", "封禁状态", "创建时间", "存档次数", "最后存档实际"])
            for row in results:
                w.writerow([row["index"], row["title"], row["status"], row["ban_status"], row["create_time"], row["update_times"], row["datetime"]])

        if update_log:
            update_log(f"[{uid}] 下载完成")
        return True
    
    def calculate_gamekey(self):
        salt = "LPislKLodlLKKOSNlSDOAADLKADJAOADALAklsd"
        raw = DEFAULT_GAME_ID + salt + DEFAULT_GAME_ID
        md5 = hashlib.md5(hashlib.md5(raw.encode()).hexdigest().encode()).hexdigest()
        return md5[4:20]

    def check_account_exists(self, username):
        try:
            r = self.session.get("http://ptlogin.4399.com/ptlogin/isExist.do", params={"username": username}, timeout=5)
            return "已被注册" in r.text
        except:
            return False

    def get_uid_from_account(self, username):
        try:
            r = self.session.get("http://cz.4399.com/get_role_info.php", params={"ac": "cuid", "uname": username}, timeout=5)
            t = r.text.strip()
            return t if t.isdigit() else None
        except:
            return None

    async def download_precise(self, uid, index, output_folder):
        """
        修改为返回 (成功状态, 状态描述, 封禁状态)
        返回值: (success: bool, message: str, ban_status: str)
        """
        gamekey = self.calculate_gamekey()
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        
        save_path = os.path.join(output_folder, f"{uid}_{index}.xml")
        
        data = {
            'uid': uid,
            'gameid': GAMEID,
            'gamekey': gamekey,
            'index': index,
            'verify': self.take_verify(index, uid, GAMEID, gamekey)
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post('https://save.api.4399.com/ranging.php/?ac=get', data=data) as response:
                    resp_text = await response.text()
            
            try:
                json_data = json.loads(resp_text)
                status_code = json_data.get("status", 0)
                title = json_data.get("title", f"uid{uid}_idx{index}")
                b64_data = json_data.get("data", "")
                ban_status = self.get_status_text(status_code)
                
                # 处理封禁状态
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
        self.root.title("爆枪突击批量存档下载器2.α.4")
        self.root.geometry("850x550")
        self.root.configure(bg="#1e1e2e")
        self.archiver = SaveArchiver()
        self.precise_file_path = None
        self.precise_tasks = []

        # 批量任务控制
        self.is_running = False
        self.stop_flag = False
        self.total_tasks = 0
        self.success_count = 0
        self.fail_count = 0
        self.ban_count = 0
        self.pause_flag = False
        
        # 进度日志线程控制
        self.progress_thread = None
        
        # 统计日志
        self.ban_list = []  # 存储封禁的账号信息
        self.fail_list = []  # 存储失败的账号信息

        self.build_ui()

    def build_ui(self):
        main_container = tk.Frame(self.root, bg="#1e1e2e")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        left_frame = tk.Frame(main_container, bg="#28293b", bd=0, relief=tk.FLAT)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,10))

        title_label = tk.Label(left_frame, text="🎮 爆枪突击存档批量下载器", 
                               font=("微软雅黑", 14, "bold"), 
                               bg="#28293b", fg="#cba6f7")
        title_label.pack(pady=18)

        entry_style = {
            "font": ("微软雅黑", 10), 
            "bd": 0, 
            "relief": tk.FLAT, 
            "bg": "#313244", 
            "fg": "#f5e0dc", 
            "insertbackground": "#f5e0dc"
        }
        label_style = {
            "bg": "#28293b", 
            "fg": "#bac2de", 
            "font": ("微软雅黑", 10)
        }

        tk.Label(left_frame, text="4399 账号", **label_style).pack(anchor="w", padx=20, pady=(5,2))
        self.user_entry = tk.Entry(left_frame, width=38, **entry_style)
        self.user_entry.pack(padx=20, pady=2, ipady=6)

        tk.Label(left_frame, text="UID", **label_style).pack(anchor="w", padx=20, pady=(8,2))
        self.uid_entry = tk.Entry(left_frame, width=38, **entry_style)
        self.uid_entry.pack(padx=20, pady=2, ipady=6)

        # 按钮排版
        btn_frame = tk.Frame(left_frame, bg="#28293b")
        btn_frame.pack(pady=15, padx=10)

        btn_style1 = {
            "bg": "#89b4fa", "fg": "#1e1e2e", "font": ("微软雅黑", 10, "bold"),
            "bd": 0, "relief": tk.FLAT, "width": 16, "cursor": "hand2"
        }
        btn_style2 = {
            "bg": "#f38ba8", "fg": "white", "font": ("微软雅黑", 10, "bold"),
            "bd": 0, "relief": tk.FLAT, "width": 16, "cursor": "hand2"
        }
        btn_style3 = {
            "bg": "#a6e3a1", "fg": "#1e1e2e", "font": ("微软雅黑", 10, "bold"),
            "bd": 0, "relief": tk.FLAT, "width": 16, "cursor": "hand2"
        }
        btn_style4 = {
            "bg": "#fab387", "fg": "#1e1e2e", "font": ("微软雅黑", 10, "bold"),
            "bd": 0, "relief": tk.FLAT, "width": 16, "cursor": "hand2"
        }
        btn_style5 = {
            "bg": "#cba6f7", "fg": "#1e1e2e", "font": ("微软雅黑", 10, "bold"),
            "bd": 0, "relief": tk.FLAT, "width": 16, "cursor": "hand2"
        }
        btn_style6 = {
            "bg": "#f5c2e7", "fg": "#1e1e2e", "font": ("微软雅黑", 10, "bold"),
            "bd": 0, "relief": tk.FLAT, "width": 16, "cursor": "hand2"
        }
        btn_style7 = {
            "bg": "#74c7ec", "fg": "#1e1e2e", "font": ("微软雅黑", 10, "bold"),
            "bd": 0, "relief": tk.FLAT, "width": 16, "cursor": "hand2"
        }

        tk.Button(btn_frame, text="🔍 账号转UID", **btn_style1, command=self.get_uid_thread).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(btn_frame, text="⬇ 指定UID下载", **btn_style2, command=self.start_single).grid(row=0, column=1, padx=5, pady=5)

        tk.Button(btn_frame, text="📂 导入UID文件", **btn_style3, command=self.load_precise_file).grid(row=1, column=0, padx=5, pady=5)
        tk.Button(btn_frame, text="🚀 批量下载", **btn_style4, command=self.start_precise_batch).grid(row=1, column=1, padx=5, pady=5)

        self.import_btn = tk.Button(btn_frame, text="📂 批量文件夹导入", **btn_style5, command=self.load_folder_batch)
        self.import_btn.grid(row=2, column=0, padx=5, pady=5)
        
        self.stop_btn = tk.Button(btn_frame, text="⏹️ 停止下载", **btn_style6, command=self.stop_batch_task)
        self.stop_btn.grid(row=2, column=1, padx=5, pady=5)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(left_frame, textvariable=self.status_var, bg="#28293b", fg="#94e2d5", 
                 font=("微软雅黑", 10)).pack(pady=8)

        # 右侧日志
        right_frame = tk.Frame(main_container, bg="#28293b", width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        right_frame.pack_propagate(False)

        # 日志框架（包含清除按钮和日志区域）
        log_header = tk.Frame(right_frame, bg="#28293b")
        log_header.pack(fill=tk.X, pady=10)
        
        tk.Label(log_header, text="📝 实时运行日志", bg="#28293b", fg="#cba6f7", 
                 font=("微软雅黑", 11, "bold")).pack(side=tk.LEFT, padx=10)
        
        # 日志区域内的清除按钮
        self.clear_log_btn = tk.Button(log_header, text="清除", command=self.clear_log,
                                        bg="#45475a", fg="#f5e0dc", font=("微软雅黑", 9),
                                        bd=0, relief=tk.FLAT, cursor="hand2")
        self.clear_log_btn.pack(side=tk.RIGHT, padx=10)

        log_bg = "#11111b"
        self.log_text = tk.Text(right_frame, bg=log_bg, fg="#a6e3a1", font=("Consolas", 10),
                                bd=0, relief=tk.FLAT, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        self.log_text.config(state=tk.DISABLED)

        scroll = ttk.Scrollbar(right_frame, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

    def log(self, msg, is_error=False):
        """添加日志，is_error=True时强制显示错误信息"""
        def _log():
            self.log_text.config(state=tk.NORMAL)
            # 错误信息用红色显示
            if is_error:
                self.log_text.insert(tk.END, msg + "\n", "error")
                self.log_text.tag_config("error", foreground="#f38ba8")
            else:
                self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _log)
    
    def log_success(self, msg):
        """成功日志 - 不显示"""
        pass  # 成功信息不显示
    
    def log_error(self, msg):
        """错误日志 - 显示"""
        self.log(msg, is_error=True)
    
    def clear_log(self):
        """清除日志"""
        def _clear():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log("日志已清除")
        self.root.after(0, _clear)

    # 导入单个txt/csv
    def load_precise_file(self):
        path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt *.csv"), ("所有文件", "*.*")])
        if not path:
            return
        self.precise_file_path = Path(path)
        tasks = []
        try:
            self.log(f"正在导入文件: {Path(path).name}")
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "," in line:
                        parts = line.split(",", 1)
                        uid, idx = parts[0].strip(), parts[1].strip()
                        if uid.isdigit() and idx.isdigit():
                            tasks.append((uid, idx))

            self.precise_tasks = tasks
            self.log(f"文件导入完成: 有效任务 {len(tasks)} 条")
            messagebox.showinfo("成功", f"导入 {len(tasks)} 个有效任务")
        except Exception as e:
            self.log_error(f"❌ 导入失败：{str(e)}")
            messagebox.showerror("错误", str(e))

    def start_precise_batch(self):
        if not self.precise_tasks or not self.precise_file_path:
            messagebox.showwarning("提示", "请先导入 UID,序号 格式文件")
            return
        if self.is_running:
            return

        self.is_running = True
        self.stop_flag = False
        self.pause_flag = False
        self.import_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.total_tasks = len(self.precise_tasks)
        self.success_count = 0
        self.fail_count = 0
        self.ban_count = 0
        self.ban_list = []
        self.fail_list = []

        threading.Thread(target=self.run_precise_async, daemon=True).start()

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
        base = Path(ROOT_OUTPUT_DIR)
        base.mkdir(exist_ok=True)
        
        file_name_no_ext = self.precise_file_path.stem
        out_dir = base / file_name_no_ext
        out_dir.mkdir(exist_ok=True, parents=True)
        out_dir_str = str(out_dir)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        fail_list = []
        ban_list = []

        async def task(uid, idx):
            async with semaphore:
                if self.stop_flag:
                    return
                ok, msg, ban_status = await self.archiver.download_precise(uid, idx, out_dir_str)
                
                # 记录封禁信息
                if ban_status in ["临时封禁", "永久封禁"]:
                    ban_list.append((uid, idx, ban_status, msg))
                    self.ban_count += 1
                    self.log_error(f"⚠️ UID {uid} 存档 {idx}: {ban_status}")
                
                # 只记录失败和封禁，成功不显示
                elif not ok:
                    fail_list.append((uid, idx, msg, ban_status))
                    self.fail_count += 1
                    self.log_error(f"❌ UID {uid} 存档 {idx}: {msg}")
                else:
                    self.success_count += 1
                    # 成功不显示日志

        await asyncio.gather(*[task(uid, idx) for uid, idx in self.precise_tasks])

        # 输出封禁汇总
        if ban_list:
            self.log(f"\n{'='*25}")
            self.log(f"📋 封禁账号汇总 (共 {len(ban_list)} 个):")
            for uid, idx, ban_status, msg in ban_list:
                self.log_error(f"   UID: {uid}, 存档: {idx}, 状态: {ban_status}")
            self.log(f"{'='*25}\n")
        
        # 输出失败汇总
        if fail_list:
            self.log(f"\n{'='*25}")
            self.log(f"📋 失败账号汇总 (共 {len(fail_list)} 个):")
            for uid, idx, msg, ban_status in fail_list:
                self.log_error(f"   UID: {uid}, 存档: {idx}, 原因: {msg}")
            self.log(f"{'='*25}\n")

        # 重试失败项（非封禁的失败）
        normal_fails = [(uid, idx, msg) for uid, idx, msg, ban_status in fail_list 
                        if ban_status not in ["临时封禁", "永久封禁"]]
        
        if normal_fails and not self.stop_flag:
            self.log(f"开始重试 {len(normal_fails)} 个失败项（非封禁）")
            for uid, idx, _ in normal_fails:
                if self.stop_flag:
                    break
                for i in range(MAX_RETRIES):
                    ok, msg, ban_status = await self.archiver.download_precise(uid, idx, out_dir_str)
                    if ok:
                        self.success_count += 1
                        self.fail_count -= 1  # 从失败计数中移除
                        # 重试成功不显示
                        break
                    elif ban_status in ["临时封禁", "永久封禁"]:
                        self.log_error(f"⚠️ 重试发现封禁 UID {uid} 存档 {idx}: {ban_status}")
                        self.ban_count += 1
                        self.fail_count -= 1
                        break
                else:
                    self.log_error(f"❌ 重试失败 UID {uid} 存档 {idx}")

    # 账号转UID
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

    def start_single(self):
        threading.Thread(target=self.run_single, daemon=True).start()

    def run_single(self):
        uid = self.uid_entry.get().strip()
        if not uid or not uid.isdigit():
            messagebox.showwarning("提示", "输入有效UID")
            return
        self.status_var.set("下载中...")
        try:
            asyncio.run(self.archiver.batch_download(uid, self.log))
            self.status_var.set("✅ 单UID下载完成")
        except Exception as e:
            self.log_error(f"错误：{str(e)}")

    # ================== 批量文件夹导入 ==================
    def load_folder_batch(self):
        if self.is_running:
            return
            
        folder_path = filedialog.askdirectory(title="请选择包含任务文件的文件夹")
        if not folder_path:
            return

        files = [f for f in os.listdir(folder_path) if f.endswith(('.txt', '.csv'))]
        
        if not files:
            self.log_error("❌ 文件夹内无 txt/csv 文件")
            messagebox.showwarning("提示", "该文件夹内没有找到 .txt 或 .csv 文件！")
            return
        
        self.log(f"已选择文件夹：{folder_path}")
        self.log(f"发现任务文件：{len(files)} 个")
        self.is_running = True
        self.stop_flag = False
        self.pause_flag = False
        self.import_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        self.total_tasks = 0
        self.success_count = 0
        self.fail_count = 0
        self.ban_count = 0
        self.ban_list = []
        self.fail_list = []
        
        threading.Thread(target=self.run_async_task, args=(folder_path, files), daemon=True).start()

    def stop_batch_task(self):
        if not self.is_running:
            return
        self.stop_flag = True
        self.log("正在停止...")

    def run_async_task(self, folder_path, files):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_folder_batch(folder_path, files))
        except Exception as e:
            self.log_error(f"❌ 错误: {e}")
        finally:
            loop.close()
            self.root.after(0, self.on_task_complete)

    def on_task_complete(self):
        self.is_running = False
        self.stop_flag = False
        self.pause_flag = False
        self.import_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
        done = self.success_count + self.fail_count + self.ban_count
        done = min(done, self.total_tasks)
        done_percent = (done / self.total_tasks * 100) if self.total_tasks else 0
        current_time = time.strftime("%H:%M:%S")
        self.log(f"{current_time}")
        self.log(f"下载已结束\n总进度：{done}/{self.total_tasks} ({done_percent:.1f}%)")
        self.log(f"下载统计：成功 {self.success_count}，失败 {self.fail_count}，封禁 {self.ban_count}")
        
        # 输出最终封禁汇总
        if self.ban_list:
            self.log(f"\n{'='*25}")
            self.log(f"📋 最终封禁账号汇总 (共 {len(self.ban_list)} 个):")
            for info in self.ban_list:
                self.log_error(f"   {info}")
            self.log(f"{'='*25}")
        
        # 输出最终失败汇总
        if self.fail_list:
            self.log(f"\n{'='*25}")
            self.log(f"📋 最终失败账号汇总 (共 {len(self.fail_list)} 个):")
            for info in self.fail_list:
                self.log_error(f"   {info}")
            self.log(f"{'='*25}")
        
        messagebox.showinfo("完成", f"成功：{self.success_count}\n失败：{self.fail_count}\n封禁：{self.ban_count}")

    async def run_folder_batch(self, folder_path, files):
        root_output_dir = Path(ROOT_OUTPUT_DIR)
        root_output_dir.mkdir(exist_ok=True)
        all_tasks = []

        for filename in files:
            if self.stop_flag: break
            file_path = Path(folder_path) / filename
            sub_folder = root_output_dir / file_path.stem
            sub_folder.mkdir(exist_ok=True, parents=True)
            
            self.log(f"正在解析: {filename}")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    count = 0
                    for line in f:
                        if self.stop_flag: break
                        line = line.strip()
                        if ',' in line:
                            uid, idx = line.split(',', 1)
                            uid, idx = uid.strip(), idx.strip()
                            if uid.isdigit() and idx.isdigit():
                                all_tasks.append((uid, idx, str(sub_folder)))
                                count += 1
                    self.log(f"解析完成, 任务数: {count}")
            except Exception as e:
                self.log_error(f"❌ 读取失败：{filename} - {str(e)}")
        
        self.total_tasks = len(all_tasks)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        fails = []
        
        # 分批下载配置
        BATCH_SIZE = 200
        PAUSE_TIME = 15
        
        async def dl(uid, idx, out):
            async with semaphore:
                if self.stop_flag:
                    return
                ok, msg, ban_status = await self.archiver.download_precise(uid, idx, out)
                
                # 记录封禁
                if ban_status in ["临时封禁", "永久封禁"]:
                    self.ban_list.append(f"UID: {uid}, 存档: {idx}, 状态: {ban_status}")
                    self.ban_count += 1
                    self.log_error(f"⚠️ UID {uid} 存档 {idx}: {ban_status}")
                
                # 只记录失败和封禁，成功不显示
                elif not ok:
                    fails.append((uid, idx, out, msg, ban_status))
                    self.fail_count += 1
                    self.fail_list.append(f"UID: {uid}, 存档: {idx}, 原因: {msg}")
                    self.log_error(f"❌ UID {uid} 存档 {idx}: {msg}")
                else:
                    self.success_count += 1
                    # 成功不显示日志
                return ok
        
        # 初始日志
        current_time = time.strftime("%H:%M:%S")
        loading_time = len(all_tasks)//600 + (len(all_tasks) // BATCH_SIZE + 1) * PAUSE_TIME // 60

        self.log(f"文件夹解析完成\n总任务: {len(all_tasks)} 条\n"+"="*25)
        self.log(f"{current_time}\n开始下载任务")
        self.log(f"每批{BATCH_SIZE}条")
        self.log(f"预计总耗时: {loading_time} 分钟")
        self.log("="*25)

        # 分批处理任务
        total_batches = (len(all_tasks) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_num in range(total_batches):
            if self.stop_flag:
                break
            
            start_idx = batch_num * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, len(all_tasks))
            batch_tasks = all_tasks[start_idx:end_idx]
            
            batch_num_display = batch_num + 1
            current_time = time.strftime("%H:%M:%S")
            self.log(f"{current_time}")
            self.log(f"第 {batch_num_display}/{total_batches} 批\n本批任务数: {len(batch_tasks)}\n")
            
            # 执行当前批次
            await asyncio.gather(*[
                dl(uid, idx, out) 
                for uid, idx, out in batch_tasks
            ])
            
            # 显示当前总进度（只显示统计，不显示成功详情）
            current_time = time.strftime("%H:%M:%S")
            self.log(f"{current_time}")
            self.log(f"第{batch_num_display}批完成")
            self.log(f"当前总进度：成功 {self.success_count} / 失败 {self.fail_count} / 封禁 {self.ban_count} / 总计 {self.total_tasks}")
            
            # 如果不是最后一批，且没有停止标志，则暂停
            if batch_num < total_batches - 1 and not self.stop_flag:
                self.log(f"暂停 {PAUSE_TIME} 秒后继续下一批...\n")
                for remaining in range(PAUSE_TIME, 0, -1):
                    if self.stop_flag:
                        break
                    await asyncio.sleep(1)
        
        # ========== 失败重试（排除封禁的账号） ==========
        normal_fails = [(uid, idx, out) for uid, idx, out, msg, ban_status in fails 
                        if ban_status not in ["临时封禁", "永久封禁"]]
        
        if normal_fails and not self.stop_flag:
            self.log(f"\n{'='*25}")
            self.log(f"开始重试 {len(normal_fails)} 个失败项（非封禁账号）")
            self.log(f"{'='*25}")
            
            retry_total_batches = (len(normal_fails) + BATCH_SIZE - 1) // BATCH_SIZE
            
            for batch_num in range(retry_total_batches):
                if self.stop_flag:
                    break
                
                start_idx = batch_num * BATCH_SIZE
                end_idx = min(start_idx + BATCH_SIZE, len(normal_fails))
                batch_fails = normal_fails[start_idx:end_idx]
                
                batch_num_display = batch_num + 1
                current_time = time.strftime("%H:%M:%S")
                self.log(f"{current_time}")
                self.log(f"重试第 {batch_num_display}/{retry_total_batches} 批\n本批重试数: {len(batch_fails)}")
                
                async def retry_dl(uid, idx, out):
                    async with semaphore:
                        if self.stop_flag:
                            return False
                        for attempt in range(MAX_RETRIES):
                            if self.stop_flag:
                                return False
                            ok, msg, ban_status = await self.archiver.download_precise(uid, idx, out)
                            
                            # 重试时发现封禁
                            if ban_status in ["临时封禁", "永久封禁"]:
                                self.ban_list.append(f"UID: {uid}, 存档: {idx}, 状态: {ban_status}")
                                self.ban_count += 1
                                self.fail_count -= 1
                                self.log_error(f"⚠️ 重试发现封禁 UID {uid} 存档 {idx}: {ban_status}")
                                return False
                            
                            if ok:
                                self.success_count += 1
                                self.fail_count -= 1
                                # 重试成功不显示
                                return True
                            
                            if attempt < MAX_RETRIES - 1:
                                await asyncio.sleep(1)
                        # 重试失败，保留在失败列表中
                        self.log_error(f"❌ 重试失败 UID {uid} 存档 {idx}")
                        return False
                
                await asyncio.gather(*[
                    retry_dl(uid, idx, out) 
                    for uid, idx, out in batch_fails
                ])
                
                current_time = time.strftime("%H:%M:%S")
                self.log(f"{current_time}")
                self.log(f"重试第{batch_num_display}批完成")
                self.log(f"当前总进度：成功 {self.success_count} / 失败 {self.fail_count} / 封禁 {self.ban_count} / 总计 {self.total_tasks}")
                
                if batch_num < retry_total_batches - 1 and not self.stop_flag:
                    self.log(f"重试批次暂停 {PAUSE_TIME} 秒后继续...\n")
                    for remaining in range(PAUSE_TIME, 0, -1):
                        if self.stop_flag:
                            break
                        await asyncio.sleep(1)
        
        # 输出最终封禁汇总
        if self.ban_list:
            self.log(f"\n{'='*25}")
            self.log(f"📋 封禁账号汇总 (共 {len(self.ban_list)} 个):")
            for info in self.ban_list:
                self.log_error(f"   {info}")
            self.log(f"{'='*25}")
        
        # 输出最终失败汇总
        if self.fail_list:
            self.log(f"\n{'='*25}")
            self.log(f"📋 失败账号汇总 (共 {len(self.fail_list)} 个):")
            for info in self.fail_list:
                self.log_error(f"   {info}")
            self.log(f"{'='*25}")

def run_tool():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    run_tool()