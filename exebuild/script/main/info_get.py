import requests
import hashlib
import base64
import zlib
import os
import tkinter as tk
from tkinter import messagebox
import asyncio
import aiohttp
import json
import threading

# ================= 配置区域 =================
DEFAULT_GAME_ID = "100027788"
GAMEID = DEFAULT_GAME_ID
SAVE_DIR = "test"
# ===========================================


class SaveArchiver:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        })

    def take_verify(self, index: str, uid: str, gameid: str, gamekey: str) -> str:
        raw = f"SDALPlsldlnSLWPElsdslSE{index}{gamekey}{uid}{gameid}PKslsO"
        md5 = hashlib.md5(raw.encode()).hexdigest()
        md5 = hashlib.md5(md5.encode()).hexdigest()
        md5 = hashlib.md5(md5.encode()).hexdigest()
        return md5

    async def download_single_slot(self, index, uid, gamekey, uid_folder):
        """异步下载单个存档槽位"""
        data = {
            'uid': uid,
            'gameid': GAMEID,
            'gamekey': gamekey,
            'index': index,
            'verify': self.take_verify(index, uid, GAMEID, gamekey)
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post('https://save.api.4399.com/ranging.php/?ac=get', data=data, timeout=15) as response:
                    resp_text = await response.text()

                    # 保存原始数据
                    raw_path = os.path.join(uid_folder, f"{uid}_{index}_raw.txt")
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(resp_text)

                    # 解析数据
                    try:
                        json_data = json.loads(resp_text)
                    except:
                        return {"index": index, "error": "解析失败"}

                    # 解析字段
                    result = {
                        "index": index,
                        "title": json_data.get("title", ""),
                        "status": json_data.get("status", 0),
                        "create_time": json_data.get("create_time", ""),
                        "update_times": json_data.get("update_times", ""),
                        "datetime": json_data.get("datetime", "")
                    }

                    # 解码并保存XML
                    b64_data = json_data.get("data", "")
                    if b64_data:
                        xml_content = self.process_save_data(b64_data)
                        if xml_content:
                            xml_path = os.path.join(uid_folder, f"{uid}_{index}.xml")
                            with open(xml_path, "w", encoding="utf-8") as f:
                                f.write(xml_content)
                    return result
            except:
                return {"index": index, "error": "请求失败"}

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

    async def batch_download(self, uid):
        """批量并发下载 0-7"""
        gamekey = self.calculate_gamekey()
        uid_folder = os.path.join(SAVE_DIR, uid)
        os.makedirs(uid_folder, exist_ok=True)

        # 并发任务
        tasks = [self.download_single_slot(str(i), uid, gamekey, uid_folder) for i in range(8)]
        results = await asyncio.gather(*tasks)

        # 生成详情文件
        details_path = os.path.join(uid_folder, f"{uid}_details.txt")
        with open(details_path, "w", encoding="utf-8") as f:
            f.write("index;title;status;create_time;update_times;datetime\n")
            for res in results:
                if "error" in res:
                    line = f"{res['index']};{res['error']};;;;;"
                else:
                    line = f"{res['index']};{res['title']};{res['status']};{res['create_time']};{res['update_times']};{res['datetime']}"
                f.write(line + "\n")
        return True, f"下载完成！路径：{uid_folder}"

    def calculate_gamekey(self):
        salt = "LPislKLodlLKKOSNlSDOAADLKADJAOADALAklsd"
        raw_str = DEFAULT_GAME_ID + salt + DEFAULT_GAME_ID
        md5_full = hashlib.md5(hashlib.md5(raw_str.encode()).hexdigest().encode()).hexdigest()
        return md5_full[4:20]

    def check_account_exists(self, username):
        url = "http://ptlogin.4399.com/ptlogin/isExist.do"
        params = {"username": username, "appId": "u4399", "regMode": "reg_normal"}
        try:
            return "已被注册" in self.session.get(url, params=params, timeout=5).text
        except:
            return False

    def get_uid_from_account(self, username):
        url = "http://cz.4399.com/get_role_info.php"
        params = {"ac": "cuid", "uname": username}
        try:
            cleaned = self.session.get(url, params=params, timeout=5).text.strip()
            return cleaned if cleaned.isdigit() else None
        except:
            return None


# ================= GUI =================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("4399 多线程全存档下载器")
        self.root.geometry("420x330")
        self.archiver = SaveArchiver()
        self._build_ui()

    def _build_ui(self):
        tk.Label(self.root, text="🎮 4399 多线程批量下载器", font=("Arial", 16, "bold")).pack(pady=15)
        tk.Label(self.root, text="游戏账号:").pack(anchor="w", padx=30)
        self.account_entry = tk.Entry(self.root, width=35)
        self.account_entry.pack(pady=5)

        tk.Button(self.root, text="🔍 获取UID", command=self.get_uid_thread, bg="#e1e1e1", fg="#333").pack(pady=5)

        tk.Label(self.root, text="UID:").pack(anchor="w", padx=30)
        self.uid_entry = tk.Entry(self.root, width=35)
        self.uid_entry.pack(pady=5)

        tk.Button(
            self.root, text="⬇️ 多线程下载 0~7 全部存档", command=self.start_download_thread,
            bg="#0078d7", fg="white", font=("Arial", 11, "bold")
        ).pack(pady=20)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor="w").pack(side=tk.BOTTOM, fill=tk.X)

    def get_uid_thread(self):
        """使用线程防止卡顿"""
        threading.Thread(target=self.get_uid, daemon=True).start()

    def get_uid(self):
        username = self.account_entry.get().strip()
        if not username:
            messagebox.showwarning("提示", "请输入账号")
            return

        self.status_var.set("检测账号中...")
        if not self.archiver.check_account_exists(username):
            messagebox.showerror("错误", "账号不存在")
            self.status_var.set("检测失败")
            return

        uid = self.archiver.get_uid_from_account(username)
        if uid:
            self.uid_entry.delete(0, tk.END)
            self.uid_entry.insert(0, uid)
            self.status_var.set("UID 获取成功")
            messagebox.showinfo("成功", f"UID: {uid}")
        else:
            self.status_var.set("获取UID失败")
            messagebox.showerror("错误", "获取UID失败")

    def start_download_thread(self):
        """多线程启动下载，不卡界面"""
        uid = self.uid_entry.get().strip()
        if not uid or not uid.isdigit():
            messagebox.showwarning("提示", "请先获取有效UID")
            return
        threading.Thread(target=self.run_download, daemon=True).start()

    def run_download(self):
        uid = self.uid_entry.get().strip()
        self.status_var.set("正在并发下载 0~7 全部存档...")
        try:
            ok, msg = asyncio.run(self.archiver.batch_download(uid))
            self.status_var.set("下载完成" if ok else "下载失败")
            messagebox.showinfo("完成" if ok else "失败", msg)
        except Exception as e:
            self.status_var.set("下载异常")
            messagebox.showerror("错误", f"下载失败：{str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()