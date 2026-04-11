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

# ================= 配置区域 =================
DEFAULT_GAME_ID = "100027788"
GAMEID = DEFAULT_GAME_ID
BASE_SAVE_DIR = "test"
RAW_SUB_DIR = "raw"
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
                        return {"index": index, "title": "未创建存档", "status_text": "解析失败", "create_time": "", "update_times": "", "datetime": ""}

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
                        "data": json_data.get("data", "") 
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
                return {"index": index, "title": "未创建存档", "status_text": "网络异常", "create_time": "", "update_times": "", "datetime": ""}

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

            results.append({
                "index": index,
                "title": title,
                "status": status_text,
                "create_time": create_time,
                "update_times": update_times,
                "datetime": datetime_val
            })

        csv_path = os.path.join(uid_folder, f"{uid}_details.csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["存档", "名称", "状态", "创建时间", "存档次数", "最后存档实际"])
            for row in results:
                w.writerow([row["index"], row["title"], row["status"], row["create_time"], row["update_times"], row["datetime"]])

        if update_log:
            update_log(f"[{uid}] ✅ 下载完成")
        return True
    
    def calculate_gamekey(self):
        salt = "LPislKLodlLKKOSNlSDOAADLKADJAOADALAklsd"
        raw = DEFAULT_GAME_ID + salt + DEFAULT_GAME_ID
        md5 = hashlib.md5(hashlib.md5(raw.encode()).hexdigest().encode()).hexdigest()
        return md5[4:20]

    def check_account_exists(self, username):
        try:
            r = self.session.get("http://ptlogin.4399.com/ptlogin/isExist.do", params={"username": username, "appId": "u4399"}, timeout=5)
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

# ===================== 美化版 GUI（截图风格） =====================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("爆枪突击批量存档下载器")
        self.root.geometry("850x550")
        self.root.configure(bg="#1e1e2e")
        self.archiver = SaveArchiver()
        self.uid_list = []
        self.build_ui()

    def build_ui(self):
        # 主容器
        main_container = tk.Frame(self.root, bg="#1e1e2e")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # 左侧功能区
        left_frame = tk.Frame(main_container, bg="#28293b", bd=0, relief=tk.FLAT)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,10))

        # 标题
        title_label = tk.Label(left_frame, text="🎮 爆枪突击存档批量下载器", 
                               font=("微软雅黑", 14, "bold"), 
                               bg="#28293b", fg="#cba6f7")
        title_label.pack(pady=18)

        # 输入组样式（修复字典格式，移除不可见字符）
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

        # 账号输入（修复pack错误，先创建控件再pack）
        tk.Label(left_frame, text="4399 账号", **label_style).pack(anchor="w", padx=20, pady=(5,2))
        self.user_entry = tk.Entry(left_frame, width=38, **entry_style)
        self.user_entry.pack(padx=20, pady=2, ipady=6)

        # UID输入（修复pack错误）
        tk.Label(left_frame, text="UID", **label_style).pack(anchor="w", padx=20, pady=(8,2))
        self.uid_entry = tk.Entry(left_frame, width=38, **entry_style)
        self.uid_entry.pack(padx=20, pady=2, ipady=6)

        # 按钮样式（修复字典格式，移除不可见字符）
        btn1 = {
            "bg": "#89b4fa", 
            "fg": "#1e1e2e", 
            "font": ("微软雅黑", 10, "bold"), 
            "bd": 0, 
            "relief": tk.FLAT, 
            "width": 14, 
            "cursor": "hand2"
        }
        btn2 = {
            "bg": "#f38ba8", 
            "fg": "white", 
            "font": ("微软雅黑", 10, "bold"), 
            "bd": 0, 
            "relief": tk.FLAT, 
            "width": 14, 
            "cursor": "hand2"
        }
        btn3 = {
            "bg": "#a6e3a1", 
            "fg": "#1e1e2e", 
            "font": ("微软雅黑", 10, "bold"), 
            "bd": 0, 
            "relief": tk.FLAT, 
            "width": 35, 
            "cursor": "hand2"
        }
        btn4 = {
            "bg": "#fab387", 
            "fg": "#1e1e2e", 
            "font": ("微软雅黑", 10, "bold"), 
            "bd": 0, 
            "relief": tk.FLAT, 
            "width": 35, 
            "cursor": "hand2"
        }

        # 按钮行
        btn_frame = tk.Frame(left_frame, bg="#28293b")
        btn_frame.pack(pady=12)
        tk.Button(btn_frame, text="🔍 获取UID", **btn1, command=self.get_uid_thread).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="⬇ 单UID下载", **btn2, command=self.start_single).pack(side=tk.LEFT, padx=4)

        # 功能按钮
        tk.Button(left_frame, text="📂 导入UID列表(txt/csv)", **btn3, command=self.load_uid_file).pack(pady=4)
        tk.Button(left_frame, text="🚀 全异步批量下载", **btn4, command=self.start_async_batch).pack(pady=2)

        # 状态
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(left_frame, textvariable=self.status_var, bg="#28293b", fg="#94e2d5", 
                 font=("微软雅黑", 10)).pack(pady=8)

        # 进度条
        self.progress = ttk.Progressbar(left_frame, orient=tk.HORIZONTAL, length=320, mode="determinate")
        self.progress.pack(pady=5)

        # ==================== 右侧日志区 ====================
        right_frame = tk.Frame(main_container, bg="#28293b", width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        right_frame.pack_propagate(False)

        tk.Label(right_frame, text="📝 实时运行日志", bg="#28293b", fg="#cba6f7", 
                 font=("微软雅黑", 11, "bold")).pack(pady=10)

        log_bg = "#11111b"
        self.log_text = tk.Text(right_frame, bg=log_bg, fg="#a6e3a1", font=("Consolas", 10),
                                bd=0, relief=tk.FLAT, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))
        self.log_text.config(state=tk.DISABLED)

        # 滚动条
        scroll = ttk.Scrollbar(right_frame, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

    def log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def load_uid_file(self):
        path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt *.csv"), ("所有文件", "*.*")])
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            uids = [l.strip() for l in lines if l.strip().isdigit()]
            self.uid_list = list(set(uids))
            self.log(f"📂 导入 {len(self.uid_list)} 个UID")
            messagebox.showinfo("成功", f"导入 {len(self.uid_list)} 个UID")
        except Exception as e:
            messagebox.showerror("错误", str(e))

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
            self.log(f"错误：{str(e)}")

    def start_async_batch(self):
        if not self.uid_list:
            messagebox.showwarning("提示", "请先导入UID")
            return
        threading.Thread(target=self.run_async_batch, daemon=True).start()

    def run_async_batch(self):
        asyncio.run(self.async_batch_task())

    async def async_batch_task(self):
        uids = self.uid_list
        total = len(uids)
        self.progress["maximum"] = total
        self.progress["value"] = 0
        self.status_var.set("批量下载中...")
        self.log("===== 开始全批量下载 =====")

        tasks = [self.archiver.batch_download(uid, self.log) for uid in uids]
        await asyncio.gather(*tasks)

        for i in range(total):
            self.progress["value"] = i+1

        self.status_var.set("✅ 全部下载完成")
        messagebox.showinfo("完成", "所有UID已全下载完毕！")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()