import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import base64
import os
import csv
import json
import threading

# --- 1. 环境检查与配置 ---
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

try:
    from pyamf import amf3
except ImportError:
    amf3 = None

class AMF3Tool:
    def __init__(self, root):
        self.root = root
        self.root.title("爆枪突击AMF解析工具")
        self.root.geometry("950x700")
        self.root.minsize(850, 650)
        self.root.configure(bg="#1e1e2e")
        
        # 如果库缺失，弹窗提示
        if not amf3:
            messagebox.showerror("缺少依赖", "未找到 pyamf 库，请运行:\npip install Py3AMF")
            self.root.destroy()
            return

        self.setup_ui()

    def setup_ui(self):
        # --- 全局样式配置 ---
        style = ttk.Style()
        style.theme_use('clam') 
        
        # 配置颜色变量
        colors = {
            "bg": "#1e1e2e",
            "frame": "#28293b",
            "input_bg": "#313244",
            "text_fg": "#f5e0dc",
            "label_fg": "#bac2de",
            "accent_blue": "#89b4fa",
            "accent_red": "#f38ba8",
            "accent_green": "#a6e3a1",
            "accent_orange": "#fab387",
            "accent_purple": "#cba6f7",
            "log_bg": "#11111b"
        }

        # 自定义按钮样式
        style.configure("TButton", padding=6, font=("微软雅黑", 9))
        style.map("TButton",
            background=[('active', '#4a4b60')],
            foreground=[('active', '#ffffff')]
        )

        # 自定义输入框样式
        style.configure("TEntry", padding=5)
        
        # 自定义标签样式
        style.configure("TLabel", background=colors["frame"], foreground=colors["label_fg"], font=("微软雅黑", 10))
        style.configure("Header.TLabel", font=("微软雅黑", 14, "bold"), foreground="#cba6f7")

        # 创建主区域（不使用滚动条）
        scrollable_frame = tk.Frame(self.root, bg=colors["bg"])
        scrollable_frame.pack(fill="both", expand=True)

        # 设置主容器
        main_container = scrollable_frame
        
        # 设置主容器
        main_container = scrollable_frame

        # 左侧功能区 (固定宽度)
        left_frame = tk.Frame(main_container, bg=colors["frame"], width=380)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(15, 10), pady=15)
        left_frame.pack_propagate(False)

        # 右侧日志区 (自适应宽度)
        right_frame = tk.Frame(main_container, bg=colors["frame"])
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0, 15), pady=15)

        # --- 左侧内容 ---

        # 单文件调试区域
        debug_frame = tk.LabelFrame(left_frame, text="🔍 单文件调试", bg=colors["frame"], fg=colors["accent_blue"], font=("微软雅黑", 10, "bold"), bd=2)
        debug_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(debug_frame, text="粘贴 Base64 字符串:", background=colors["frame"], foreground=colors["label_fg"]).pack(anchor="w", padx=10, pady=(10, 0))
        
        self.input_text = tk.Text(debug_frame, height=4, bg=colors["input_bg"], fg=colors["text_fg"], 
                                  insertbackground=colors["text_fg"], bd=0, relief=tk.FLAT, font=("Consolas", 9))
        self.input_text.pack(fill="x", padx=10, pady=5, ipady=4)

        self.btn_test = tk.Button(debug_frame, text="🚀 测试解码", bg=colors["accent_blue"], fg="#1e1e2e", 
                                  font=("微软雅黑", 9, "bold"), bd=0, cursor="hand2", command=self.test_decode)
        self.btn_test.pack(fill="x", padx=10, pady=(5, 5), ipady=3)
        
        # 编码区域
        encode_frame = tk.LabelFrame(left_frame, text="✏️ 编码回写", bg=colors["frame"], fg=colors["accent_purple"], font=("微软雅黑", 10, "bold"), bd=2)
        encode_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(encode_frame, text="JSON 数据 (可编辑):", background=colors["frame"], foreground=colors["label_fg"]).pack(anchor="w", padx=10, pady=(10, 0))
        
        self.json_edit = tk.Text(encode_frame, height=8, bg=colors["input_bg"], fg=colors["text_fg"], 
                                 insertbackground=colors["text_fg"], bd=0, relief=tk.FLAT, font=("Consolas", 9))
        self.json_edit.pack(fill="x", padx=10, pady=5, ipady=4)
        
        # 按钮组
        btn_frame = tk.Frame(encode_frame, bg=colors["frame"])
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        self.btn_load_json = tk.Button(btn_frame, text="📂 加载JSON文件", bg=colors["accent_purple"], fg="#1e1e2e", 
                                      font=("微软雅黑", 9, "bold"), bd=0, cursor="hand2", command=self.load_json_file)
        self.btn_load_json.pack(side=tk.LEFT, padx=(0, 5), ipady=3, expand=True, fill="x")
        
        self.btn_encode = tk.Button(btn_frame, text="🔐 编码为Base64", bg=colors["accent_orange"], fg="#1e1e2e", 
                                   font=("微软雅黑", 9, "bold"), bd=0, cursor="hand2", command=self.encode_to_base64)
        self.btn_encode.pack(side=tk.LEFT, padx=(5, 0), ipady=3, expand=True, fill="x")
        
        self.btn_save_batch = tk.Button(encode_frame, text="💾 批量编码文件夹", bg=colors["accent_green"], fg="#1e1e2e", 
                                       font=("微软雅黑", 9, "bold"), bd=0, cursor="hand2", command=self.encode_folder)
        self.btn_save_batch.pack(fill="x", padx=10, pady=(0, 10), ipady=3)

        # 分割线
        ttk.Separator(left_frame, orient='horizontal').pack(fill='x', pady=10, padx=20)

        # 批量处理区域
        batch_frame = tk.LabelFrame(left_frame, text="📂 批量解析", bg=colors["frame"], fg=colors["accent_green"], font=("微软雅黑", 10, "bold"), bd=2)
        batch_frame.pack(fill="x", padx=10, pady=10, expand=True)

        info_label = tk.Label(batch_frame, text="选择包含存档文件的文件夹\n程序将自动解析并生成 CSV\n(含贡献值动态提取)", 
                              bg=colors["frame"], fg=colors["label_fg"], justify="left", font=("微软雅黑", 9))
        info_label.pack(anchor="w", padx=10, pady=10)

        self.btn_batch = tk.Button(batch_frame, text="📁 选择文件夹并解析", bg=colors["accent_green"], fg="#1e1e2e", 
                                   font=("微软雅黑", 10, "bold"), bd=0, cursor="hand2", command=self.process_folder)
        self.btn_batch.pack(fill="x", padx=10, pady=10, ipady=5)

        self.progress = ttk.Progressbar(batch_frame, mode='indeterminate')
        self.progress.pack(fill="x", padx=10, pady=(0, 10))

        # --- 右侧内容 (日志) ---
        log_title = ttk.Label(right_frame, text="📝 运行日志", style="Header.TLabel")
        log_title.pack(anchor="w", padx=5)

        log_bg = colors["log_bg"]
        self.log_area = tk.Text(right_frame, bg=log_bg, fg="#a6e3a1", font=("Consolas", 10),
                                bd=0, relief=tk.FLAT, wrap=tk.WORD, state=tk.DISABLED)
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def log(self, message):
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def decode_amf3_data(self, raw_data):
        clean_data = raw_data.replace("\n", "").replace("\r", "").strip()
        if not clean_data:
            raise ValueError("输入为空")
        try:
            binary_data = base64.b64decode(clean_data)
            decoder = amf3.Decoder(stream=bytes(binary_data))
            obj = decoder.readElement()
            return obj
        except Exception as e:
            raise Exception(f"解码失败: {str(e)}")

    def encode_to_amf3(self, data_dict):
        """将字典编码为AMF3格式并返回Base64字符串"""
        try:
            # 创建编码器
            encoder = amf3.Encoder()
            encoder.writeElement(data_dict)
            # 获取二进制数据
            binary_data = encoder.stream.getvalue()
            # 转换为Base64
            base64_str = base64.b64encode(binary_data).decode('utf-8')
            return base64_str
        except Exception as e:
            raise Exception(f"编码失败: {str(e)}")

    def extract_fields(self, data_dict, file_name_no_ext):
        # --- 1. 动态处理 conObj (贡献) ---
        con_obj = data_dict.get('conObj', {})
        con_list = []
        
        if isinstance(con_obj, dict):
            # 按数字大小排序键
            try:
                sorted_keys = sorted(con_obj.keys(), key=lambda x: int(x))
            except ValueError:
                sorted_keys = sorted(con_obj.keys()) # 如果非数字则按字符串排序
                
            for key in sorted_keys:
                con_list.append(str(con_obj[key]))
        
        con_str = ", ".join(con_list)
        print(data_dict)  # 调试输出，查看conObj内容
        # --- 2. 组装行数据 ---
        return [
            file_name_no_ext,             
            data_dict.get('playerName', ''),
            data_dict.get('vip', ''),
            data_dict.get('lv', ''),
            data_dict.get('dps', ''),
            data_dict.get('mdp', ''),
            data_dict.get('life', ''),
            data_dict.get('mp', ''),        
            data_dict.get('lt', ''),        
            con_str,                      
            data_dict.get('money', ''),
            data_dict.get('loginTime', '')
        ]

    def test_decode(self):
        raw_data = self.input_text.get("1.0", tk.END).strip()
        if not raw_data: 
            messagebox.showwarning("警告", "请先粘贴Base64数据")
            return
        try:
            data_obj = self.decode_amf3_data(raw_data)
            print(data_obj)  # 调试输出，查看解码结果
            if isinstance(data_obj, dict):
                # 显示在JSON编辑框中
                json_str = json.dumps(data_obj, ensure_ascii=False, indent=2)
                self.json_edit.delete("1.0", tk.END)
                self.json_edit.insert("1.0", json_str)
                
                self.log("✅ 解码成功，JSON已加载到编辑框")
                messagebox.showinfo("解码成功", "数据已解码并显示在JSON编辑框中，您可以修改后重新编码")
            else:
                messagebox.showwarning("结果", f"解码成功，但不是字典格式: {type(data_obj)}")
        except Exception as e:
            self.log(f"❌ 解码错误: {str(e)}")
            messagebox.showerror("错误", str(e))

    def load_json_file(self):
        """从文件加载JSON数据"""
        file_path = filedialog.askopenfilename(
            title="选择JSON文件",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            self.json_edit.delete("1.0", tk.END)
            self.json_edit.insert("1.0", json_str)
            self.log(f"✅ 已加载JSON文件: {os.path.basename(file_path)}")
        except Exception as e:
            self.log(f"❌ 加载JSON失败: {str(e)}")
            messagebox.showerror("错误", f"无法加载JSON文件: {str(e)}")

    def encode_to_base64(self):
        """将JSON编辑框中的数据编码为Base64"""
        json_str = self.json_edit.get("1.0", tk.END).strip()
        if not json_str:
            messagebox.showwarning("警告", "JSON编辑框为空")
            return
        
        try:
            # 解析JSON
            data_dict = json.loads(json_str)
            
            # 编码为AMF3
            base64_str = self.encode_to_amf3(data_dict)
            
            # 显示结果
            result_window = tk.Toplevel(self.root)
            result_window.title("编码结果")
            result_window.geometry("600x400")
            result_window.configure(bg="#1e1e2e")
            
            # 添加文本区域显示结果
            text_area = tk.Text(result_window, bg="#313244", fg="#f5e0dc", font=("Consolas", 10), wrap=tk.WORD)
            text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text_area.insert("1.0", base64_str)
            
            # 添加按钮
            btn_frame = tk.Frame(result_window, bg="#1e1e2e")
            btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            
            def copy_to_clipboard():
                self.root.clipboard_clear()
                self.root.clipboard_append(base64_str)
                messagebox.showinfo("成功", "已复制到剪贴板")
            
            def save_to_file():
                file_path = filedialog.asksaveasfilename(
                    title="保存Base64数据",
                    defaultextension=".txt",
                    filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
                )
                if file_path:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(base64_str)
                    messagebox.showinfo("成功", f"已保存到: {file_path}")
            
            tk.Button(btn_frame, text="📋 复制到剪贴板", command=copy_to_clipboard,
                     bg="#89b4fa", fg="#1e1e2e", font=("微软雅黑", 9, "bold"), bd=0, cursor="hand2").pack(side=tk.LEFT, padx=5, ipady=3, expand=True, fill=tk.X)
            tk.Button(btn_frame, text="💾 保存到文件", command=save_to_file,
                     bg="#a6e3a1", fg="#1e1e2e", font=("微软雅黑", 9, "bold"), bd=0, cursor="hand2").pack(side=tk.LEFT, padx=5, ipady=3, expand=True, fill=tk.X)
            
            self.log("✅ 编码成功！")
        except json.JSONDecodeError as e:
            self.log(f"❌ JSON格式错误: {str(e)}")
            messagebox.showerror("错误", f"JSON格式无效: {str(e)}")
        except Exception as e:
            self.log(f"❌ 编码失败: {str(e)}")
            messagebox.showerror("错误", str(e))

    def encode_folder(self):
        """批量编码文件夹中的所有JSON文件"""
        folder_path = filedialog.askdirectory(title="选择包含JSON文件的文件夹")
        if not folder_path:
            return
        
        # 启动后台线程处理
        threading.Thread(target=self._run_batch_encode, args=(folder_path,), daemon=True).start()
    
    def _run_batch_encode(self, folder_path):
        self.btn_save_batch.config(state="disabled")
        self.progress.start(10)
        self.log(f"=== 开始批量编码: {folder_path} ===")
        
        success_count = 0
        fail_count = 0
        
        # 创建输出文件夹
        output_folder = os.path.join(folder_path, "encoded_output")
        os.makedirs(output_folder, exist_ok=True)
        
        # 获取所有JSON文件
        files = [f for f in os.listdir(folder_path) 
                if f.endswith('.json') and os.path.isfile(os.path.join(folder_path, f))]
        
        total_files = len(files)
        self.log(f"找到 {total_files} 个JSON文件")
        
        for idx, filename in enumerate(files):
            file_path = os.path.join(folder_path, filename)
            name_no_ext = os.path.splitext(filename)[0]
            
            try:
                # 读取JSON文件
                with open(file_path, 'r', encoding='utf-8') as f:
                    data_dict = json.load(f)
                
                # 编码为AMF3
                base64_str = self.encode_to_amf3(data_dict)
                
                # 保存为同名文件（无扩展名）
                output_path = os.path.join(output_folder, name_no_ext)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(base64_str)
                
                success_count += 1
                self.log(f"✅ 编码成功: {filename} -> {name_no_ext}")
                
            except Exception as e:
                fail_count += 1
                self.log(f"❌ 编码失败 [{filename}]: {str(e)[:50]}")
        
        self.log(f"=== 批量编码完成 ===")
        self.log(f"成功: {success_count}, 失败: {fail_count}")
        self.log(f"输出目录: {output_folder}")
        
        messagebox.showinfo("批量编码完成", 
                           f"处理完成！\n成功: {success_count}\n失败: {fail_count}\n\n输出目录:\n{output_folder}")
        
        self.progress.stop()
        self.btn_save_batch.config(state="normal")

    def process_folder(self):
        folder_path = filedialog.askdirectory(title="选择包含数据文件的文件夹")
        if not folder_path: 
            return

        folder_name = os.path.basename(folder_path)
        output_file = os.path.join(folder_path, f"{folder_name}_解析结果.csv")

        # 启动后台线程处理
        threading.Thread(target=self._run_batch_process, args=(folder_path, output_file), daemon=True).start()

    def _run_batch_process(self, folder_path, output_file):
        self.btn_batch.config(state="disabled")
        self.progress.start(10)
        self.log(f"=== 开始处理文件夹: {folder_path} ===")

        success_count = 0
        fail_count = 0

        try:
            with open(output_file, mode='w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                # 表头
                writer.writerow([
                    "UID_index", "玩家名称", "VIP", "等级", "战斗力",
                    "最大战斗力", "生命值", "地图", "争霸时间", "贡献值", "黄金", "登录时间"
                ])

                files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                total_files = len(files)

                for idx, filename in enumerate(files):
                    # 跳过非数据文件
                    if filename.endswith('.csv') or filename.endswith('.json') or filename.startswith('.') or filename == "encoded_output":
                        continue
                        
                    file_path = os.path.join(folder_path, filename)
                    name_no_ext = os.path.splitext(filename)[0]

                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        data_obj = self.decode_amf3_data(content)
                        if isinstance(data_obj, dict):
                            row_data = self.extract_fields(data_obj, name_no_ext)
                            writer.writerow(row_data)
                            success_count += 1
                            
                            # 同时保存JSON副本到encoded_output文件夹
                            json_output_dir = os.path.join(folder_path, "decoded_json")
                            os.makedirs(json_output_dir, exist_ok=True)
                            json_path = os.path.join(json_output_dir, f"{name_no_ext}.json")
                            with open(json_path, 'w', encoding='utf-8') as jf:
                                json.dump(data_obj, jf, ensure_ascii=False, indent=2)
                            
                        else:
                            fail_count += 1
                            self.log(f"⚠️ 跳过非字典数据: {filename}")
                            
                    except Exception as e:
                        fail_count += 1
                        self.log(f"❌ 处理失败 [{filename}]: {str(e)[:50]}...")

            self.log(f"✅ 处理完成！成功: {success_count}, 失败: {fail_count}")
            self.log(f"📁 CSV文件已保存: {output_file}")
            self.log(f"📁 JSON文件已保存到: {os.path.join(folder_path, 'decoded_json')}")
            messagebox.showinfo("完成", f"批量处理结束！\n成功: {success_count}\n失败: {fail_count}")

        except Exception as e:
            self.log(f"❌ 致命错误: {str(e)}")
            messagebox.showerror("错误", f"无法创建输出文件: {str(e)}")
        
        finally:
            self.progress.stop()
            self.btn_batch.config(state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = AMF3Tool(root)
    root.mainloop()