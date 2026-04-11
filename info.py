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

        # 初始化结果列表，确保有8个槽位
        results = []
    
        # 并发下载所有槽位 (0-7)
        tasks = [self.download_single_slot(str(i), uid, gamekey, uid_folder) for i in range(8)]
        raw_results = await asyncio.gather(*tasks)

        # ================= 数据整理逻辑 =================
        for index in range(8):
            result = raw_results[index]
            
            # 初始化默认值，防止变量未定义报错
            status_text = "未创建存档"
            title = ""
            create_time = ""
            update_times = ""
            datetime_val = "" # 避免使用 datetime 作为变量名（它是内置库名）

            # 检查该槽位的返回结果
            if not isinstance(result, dict):
                # 情况A: 如果异步任务出错（网络异常等），保持默认值（未创建存档）
                pass 
            else:
                # 情况B: 获取到了字典数据，开始解析
                # 修复核心逻辑：优先读取 status 字段
                status_code = str(result.get("status", ""))
                title = result.get("title", "")
                
                # 1. 优先判断 Status (封禁逻辑)
                if status_code == "1":
                    status_text = "临时封禁"
                elif status_code == "2":
                    status_text = "永久封禁"
                # 2. 再判断 Title (存档状态逻辑)
                elif not title or title == "未创建存档":
                    status_text = "未创建存档"
                    title = "" # 确保标题列为空
                else:
                    # 3. 默认情况：有标题且 status 不是封禁码，视为正常
                    status_text = "正常"
                
                # 提取时间与次数字段 (只在 result 是 dict 时提取)
                create_time = result.get("create_time", "")
                update_times = result.get("update_times", "")
                datetime_val = result.get("datetime", "")

            # 【重要】无论是否异常，都将结果加入列表
            # 原代码中这一步缩进在 else 内部，导致异常时不会加入列表，CSV 就会少行
            results.append({
                "index": index,
                "title": title,
                "status": status_text,
                "create_time": create_time,
                "update_times": update_times,
                "datetime": datetime_val
            })

        # ================= CSV 写入逻辑 =================
        csv_path = os.path.join(uid_folder, f"{uid}_details.csv")
    
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            # 写入表头
            w.writerow(["槽位", "标题", "状态", "创建时间", "次数", "最后更新"])

            # 写入 8 个槽位的数据
            for row in results:
                w.writerow([
                    row["index"], 
                    row["title"], 
                    row["status"], 
                    row["create_time"], 
                    row["update_times"], 
                    row["datetime"]
                ])

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

# ================= GUI =================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("4399 全异步批量存档下载器")
        self.root.geometry("750x480")
        self.archiver = SaveArchiver()
        self.uid_list = []
        self.build_ui()

    def build_ui(self):
        # 左侧
        left = tk.Frame(self.root, padx=12, pady=10)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(left, text="🎮 4399 全异步批量下载器", font=("微软雅黑", 15, "bold")).pack(pady=8)

        # 账号
        tk.Label(left, text="4399 账号", font=("微软雅黑", 10)).pack(anchor="w")
        self.user_entry = tk.Entry(left, font=("微软雅黑", 10), width=42)
        self.user_entry.pack(pady=3)

        # UID
        tk.Label(left, text="UID", font=("微软雅黑", 10)).pack(anchor="w")
        self.uid_entry = tk.Entry(left, font=("微软雅黑", 10), width=42)
        self.uid_entry.pack(pady=3)

        # 按钮
        bf = tk.Frame(left)
        bf.pack(pady=8)
        tk.Button(bf, text="🔍 获取UID", bg="#0277bd", fg="white", width=13, command=self.get_uid_thread).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="⬇ 单UID下载", bg="#c62828", fg="white", width=13, command=self.start_single).pack(side=tk.LEFT, padx=4)

        # 导入
        tk.Button(left, text="📂 导入UID列表(txt/csv)", bg="#2e7d32", fg="white", width=36, command=self.load_uid_file).pack(pady=4)
        tk.Button(left, text="🚀 全异步批量下载", bg="#e65100", fg="white", width=36, command=self.start_async_batch).pack(pady=2)

        # 状态
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(left, textvariable=self.status_var, font=("微软雅黑", 9)).pack(pady=4)

        # 进度条
        self.progress = ttk.Progressbar(left, orient=tk.HORIZONTAL, length=360, mode="determinate")
        self.progress.pack(pady=5)

        # 右侧日志
        right = tk.Frame(self.root, padx=10, pady=10, width=280)
        right.pack(side=tk.RIGHT, fill=tk.BOTH)
        tk.Label(right, text="📝 实时日志", font=("微软雅黑", 10, "bold")).pack()
        self.log_text = tk.Text(right, height=28, width=32, font=("微软雅黑", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)

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

    # ========== 真正全异步批量下载 ==========
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
        self.status_var.set("批量异步下载中...")
        self.log("===== 开始全异步批量下载 =====")

        tasks = []
        for uid in uids:
            tasks.append(self.archiver.batch_download(uid, self.log))

        await asyncio.gather(*tasks)

        for i in range(total):
            self.progress["value"] = i+1

        self.status_var.set("✅ 全部异步下载完成")
        messagebox.showinfo("完成", "所有UID已全异步下载完毕！")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()