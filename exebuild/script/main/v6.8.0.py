import tkinter as tk
from tkinter import filedialog, messagebox
import os
import hashlib
import configparser
import base64
import datetime
import re
import sys
import xml.etree.ElementTree as ET
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import hmac
from collections import defaultdict
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========================================================
# 📂 秘钥配置
# ========================================================
SECRET_KEY = b"shizixingzhang_wuxin_producted12"
SIGN_KEY = b"producted_by_shizi"
ITEM_SECRET_KEY = b"used_by_tdfox_dslhsj_producted13"
ITEM_SIGN_KEY = b"producted_by_tdfox"

# ========================================================
# 📂 目录与常量
# ========================================================
CONFIG_FILE = "config.ini"
INPUT_DIR = "inputdata"
OUTPUT_DIR = "outputdata"
TEST_DIR = "test"
DEFAULT_BIN_PATH = "./inputdata/v1.0.bin"

# ========================================================
# 🔒 工具函数
# ========================================================
def smart_load_xml(file_path, gui_logger=None):
    candidate_encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'cp936', 'windows-1252', 'iso-8859-1']
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
    except Exception as e:
        if gui_logger: gui_logger(f"❌ 文件读取失败：{e}")
        return None, "", "File Read Error"

    for enc in candidate_encodings:
        try:
            text_content = raw_data.decode(enc)
            root = ET.fromstring(text_content)
            return root, text_content, enc
        except UnicodeDecodeError:
            continue
        except ET.ParseError:
            continue

    try:
        text_content = raw_data.decode('utf-8', errors='ignore')
        root = ET.fromstring(text_content)
        return root, text_content, "utf-8 (ignored errors)"
    except Exception:
        pass

    if gui_logger: gui_logger("❌ 无法识别文件编码或 XML 格式严重损坏")
    return None, "", "All Failed"

def generate_signature(content: str) -> str:
    mixed = SIGN_KEY + content.encode('utf-8')
    return hashlib.sha256(mixed).hexdigest()

def verify_signature(content: str, signature: str) -> bool:
    return hmac.compare_digest(generate_signature(content), signature)

LOG_CACHE = {}

def save_log_by_uid(uid, result_info):
    if not uid:
        return
    log_dir = "检测日志"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"UID_{uid}.log")

    if uid not in LOG_CACHE:
        LOG_CACHE[uid] = []

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{now}] {result_info}\n"
    LOG_CACHE[uid].append(log_entry)

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"======== UID: {uid} 检测日志 ========\n")
        f.write("".join(LOG_CACHE[uid]))

# ========================================================
# ⚙️ 检测引擎核心
# ========================================================
class DetectionEngine:
    @staticmethod
    def _decode_decrypted_data(decrypted_data):
        encodings_to_try = ['utf-8', 'gbk', 'gb2312']
        for enc in encodings_to_try:
            try:
                content = decrypted_data.decode(enc)
                return content, enc
            except UnicodeDecodeError:
                continue
        return None, None

    @staticmethod
    def load_price_map_from_bin(bin_path, secret_key_bytes, sign_key_bytes):
        price_map = {}
        if not os.path.exists(bin_path): return None
        try:
            with open(bin_path, 'rb') as f:
                file_data = f.read()
            if len(file_data) < 48: return None
            iv = file_data[:16]
            signature = file_data[-32:]
            ciphertext = file_data[16:-32]
            body_to_verify = iv + ciphertext
            expected_signature = hmac.new(sign_key_bytes, body_to_verify, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected_signature): return None
            cipher = AES.new(secret_key_bytes, AES.MODE_CBC, iv)
            try:
                decrypted_padded = cipher.decrypt(ciphertext)
                decrypted_data = unpad(decrypted_padded, AES.block_size)
            except ValueError:
                return None
            csv_content, _ = DetectionEngine._decode_decrypted_data(decrypted_data)
            if csv_content is None: return None
            lines = csv_content.splitlines()
            for i, line in enumerate(lines):
                line = line.strip()
                if not line: continue
                if i == 0 and not line[0].isdigit(): continue
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[0])
                        price = int(float(parts[1]))
                        price_map[pid] = price
                    except ValueError:
                        continue
            return price_map
        except Exception:
            return None

    @staticmethod
    def load_price_map_from_bin_pro(bin_path):
        if not os.path.exists(bin_path): return None
        try:
            with open(bin_path, 'rb') as f:
                file_data = f.read()
            if len(file_data) < 48: return None
            iv = file_data[:16]
            signature = file_data[-32:]
            ciphertext = file_data[16:-32]
            body_to_verify = iv + ciphertext
            expected_signature = hmac.new(ITEM_SIGN_KEY, body_to_verify, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected_signature): return None
            try:
                cipher = AES.new(ITEM_SECRET_KEY, AES.MODE_CBC, iv)
                decrypted_padded = cipher.decrypt(ciphertext)
                decrypted_data = unpad(decrypted_padded, AES.block_size)
            except ValueError:
                return None
            csv_content, _ = DetectionEngine._decode_decrypted_data(decrypted_data)
            if csv_content is None: return None
            price_map = {}
            lines = csv_content.splitlines()
            for i, line in enumerate(lines):
                line = line.strip()
                if not line: continue
                if i == 0:
                    try:
                        int(line.split(',')[0])
                    except ValueError:
                        continue
                parts = line.split(',')
                if len(parts) >= 2:
                    try:
                        pid = int(parts[0])
                        price = int(float(parts[1]))
                        cname = None
                        if len(parts) >= 3:
                            cname = parts[2].strip()
                            if not cname: cname = None
                        price_map[pid] = {'price': price, 'cname': cname}
                    except ValueError:
                        continue
            return price_map
        except Exception:
            return None

    @staticmethod
    def check_pay_xml(file_path, bin_path, max_details=10, min_money_details=500, min_number_details=500, export_full=False):
        price_map = None
        try:
            price_map = DetectionEngine.load_price_map_from_bin(bin_path, SECRET_KEY, SIGN_KEY)
        except Exception:
            price_map = None
        if price_map is None:
            try:
                price_map = DetectionEngine.load_price_map_from_bin_pro(bin_path)
            except Exception:
                price_map = None

        if price_map is None:
            return {'status': 'fail', 'msg': f"❌ 错误：无法读取或解密价格表文件。\n路径：{bin_path}\n(文件不存在或格式错误)", 'total_cost': 0}
        if not price_map:
            return {'status': 'warn', 'msg': "⚠️ 价格表为空，跳过消费计算。", 'total_cost': 0}

        total_cost = 0
        high_value_items = []
        high_freq_items = []

        try:
            root, _, _ = smart_load_xml(file_path)
            if root is None: return {'status': 'fail', 'msg': "❌ XML 文件严重损坏，无法解析支付节点。", 'total_cost': 0}
            pay_node = root.find('.//s[@name="pay"]')
            if pay_node is None: return {'status': 'warn', 'msg': "⚠️ 未找到 <pay> 节点", 'total_cost': 0}
            obj_node = pay_node.find('.//s[@name="obj"]')
            if obj_node is None: return {'status': 'warn', 'msg': "⚠️ <pay> 节点下未找到 <obj> 子节点", 'total_cost': 0}

            for item in obj_node.findall('s'):
                try:
                    prop_id = int(item.get('name'))
                    count = int(item.text.strip())
                    raw_data = price_map.get(prop_id, 0)
                    if isinstance(raw_data, dict):
                        price = raw_data.get('price', 0)
                        cname = raw_data.get('cname')
                    else:
                        price = raw_data
                        cname = None
                    cost = price * count
                    total_cost += cost
                    if count > 0:
                        if price > min_money_details:
                            high_value_items.append(f"- {cname} 单价:{price}, 次数:{count}, 小计:{cost}")
                        if count > min_number_details:
                            high_freq_items.append(f"- {cname} 单价:{price}, 次数:{count}, 小计:{cost}")
                except (ValueError, TypeError):
                    continue

            msg_lines = [f"💰 估算总消费：{total_cost} 黄金"]
            status = 'pass'
            hv_count = len(high_value_items)
            hf_count = len(high_freq_items)

            if export_full:
                hv_limit = hv_count
                hf_limit = hf_count
            else:
                hv_limit = min(hv_count, max_details) if max_details > 0 else hv_count
                hf_limit = min(hf_count, max_details) if max_details > 0 else hf_count

            if high_value_items:
                msg_lines.append(f"\n⚠️ 高价物品 (单价>{min_money_details}) 共{hv_count}项:")
                for line in high_value_items[:hv_limit]:
                    msg_lines.append(f" {line}")
                if not export_full and max_details > 0 and hv_count > max_details:
                    msg_lines.append(f" ... 还有 {hv_count - max_details} 项 (已隐藏)")
                status = 'warn'

            if high_freq_items:
                msg_lines.append(f"\n🚨 高频购买 (次数>{min_number_details}) 共{hf_count}项:")
                for line in high_freq_items[:hf_limit]:
                    msg_lines.append(f" {line}")
                if not export_full and max_details > 0 and hf_count > max_details:
                    msg_lines.append(f" ... 还有 {hf_count - max_details} 项 (已隐藏)")
                status = 'warn'

            return {'status': status, 'msg': "\n".join(msg_lines), 'total_cost': total_cost}
        except Exception as e:
            return {'status': 'fail', 'msg': f"解析错误：{str(e)}", 'total_cost': 0}

    @staticmethod
    def check_vip_pay_union(file_path, pay_cost):
        vip_map2 = {100: 0, 200: 1, 500: 0, 1000: 3, 2000: 4, 5000: 5, 8000: 6, 10000: 7, 20000: 8, 50000: 9, 100000: 10}
        if pay_cost is None or pay_cost <= 0: return {'status': 'pass', 'msg': 'ℹ️ 无有效消费金额，跳过联合检测。'}
        level_to_limit = {v: k for k, v in vip_map2.items()}
        try:
            root, _, _ = smart_load_xml(file_path)
            if root is None: return {'status': 'fail', 'msg': '❌ 无法解析 XML 获取 VIP 信息'}
        except Exception:
            return {'status': 'fail', 'msg': '❌ 无法解析 XML 获取 VIP 信息'}

        vip_level = -1
        vip_node = root.find('.//s[@name="vip"]')
        if vip_node is not None:
            level_elem = vip_node.find('.//s[@name="level"]')
            if level_elem is not None and level_elem.text:
                try:
                    vip_level = int(level_elem.text.strip())
                except ValueError:
                    pass

        if vip_level < 0: return {'status': 'pass', 'msg': 'ℹ️ 未检测到有效 VIP 等级。'}
        limit_amount = level_to_limit.get(vip_level)
        if limit_amount is None or limit_amount == 0: return {'status': 'pass', 'msg': f'ℹ️ VIP 等级 {vip_level} 不在对照表中或额度为 0。'}

        ratio = pay_cost / limit_amount
        msg_lines = [f"🔍 【VIP-Pay 联合检测】", f" - VIP 等级：{vip_level}", f" - 基准额度：{limit_amount}", f" - 实际消耗：{pay_cost}", f" - 消耗占比：{ratio:.2%}"]
        status = 'pass'
        if ratio > 1.0:
            status = 'fail'
            msg_lines.append(f" 🚨 结论：消耗超过 100%，判定为【作弊】！")
        elif ratio > 0.7:
            status = 'warn'
            msg_lines.append(f" ⚠️ 结论：消耗超过 70%，触发【警告】！")
        else:
            msg_lines.append(f" ✅ 结论：消耗正常。")
        return {'status': status, 'msg': '\n'.join(msg_lines)}

    @staticmethod
    def check_vip_xml(file_path):
        try:
            vip_errors = []
            vip_level = -1
            vip_map = {100: 1, 200: 2, 500: 3, 1000: 4, 2000: 5, 5000: 6, 8000: 7, 10000: 8, 20000: 9, 50000: 10}
            valid_m_keys = set(vip_map.keys())
            target_obj_names = ["obj", "nO", "upLevelObj"]

            root, _, _ = smart_load_xml(file_path)
            if root is None:
                return {'status': 'fail', 'msg': "❌ XML 文件严重损坏，无法解析 VIP 节点。"}
            all_vip_nodes = root.findall('.//s[@name="vip"]')
            valid_vip_nodes = [node for node in all_vip_nodes if node.find('.//s[@name="level"]') is not None]
            if len(valid_vip_nodes) == 0:
                return {'status': 'warn', 'msg': "⚠️ 未找到有效的 <vip> 节点"}
            elif len(valid_vip_nodes) > 1:
                return {'status': 'fail', 'msg': f"❌ 异常：存在多个 vip 节点 ({len(valid_vip_nodes)}个)"}

            current_vip_node = valid_vip_nodes[0]
            level_elem = current_vip_node.find('.//s[@name="level"]')
            try:
                vip_level = int(level_elem.text.strip())
            except:
                return {'status': 'fail', 'msg': "❌ 无法读取 level 数值"}

            if vip_level < 0 or vip_level > 10:
                vip_errors.append(f"VIP 等级数值异常：{vip_level}")

            category_counts = {}
            all_enabled_items = []
            for obj_name in target_obj_names:
                obj_node = current_vip_node.find(f'.//s[@name="{obj_name}"]')
                count = 0
                if obj_node is not None:
                    for item in obj_node.findall('s'):
                        name_attr = item.get('name')
                        text_val = item.text
                        if name_attr and name_attr.startswith('m') and text_val and text_val.lower().strip() == 'true':
                            try:
                                m_val = int(name_attr[1:])
                                count += 1
                                all_enabled_items.append((m_val, obj_name))
                            except ValueError:
                                pass
                category_counts[obj_name] = count
                if count > vip_level:
                    vip_errors.append(f"类别 [{obj_name}] 溢出：开启{count}项 > VIP{vip_level}")

            for m_val, source in all_enabled_items:
                if m_val not in valid_m_keys:
                    vip_errors.append(f"非法数值：[{source}] 中发现未定义权限 m{m_val}")
                else:
                    required_level = vip_map[m_val]
                    if required_level > vip_level:
                        vip_errors.append(f"越权：[{source}] 中 VIP{vip_level} 开启了需 VIP{required_level} 的权限 (m{m_val})")

            if vip_errors:
                return {'status': 'fail', 'msg': "❌ 检测到异常:\n" + "\n".join(vip_errors)}
            return {'status': 'pass', 'msg': '✅ VIP 权限配置正常'}
        except Exception as e:
            return {'status': 'fail', 'msg': f"解析异常：{str(e)}"}

    @staticmethod
    def check_cheat_stream(file_path, check_flag=True, check_reason=True):
        try:
            results = []
            cheat_found = False
            flag_node_found = False
            flag_value = None
            reason_content = None
            re_flag = re.compile(r'name=["\']isZuobiB["\'][^>]*>(.*?)<', re.IGNORECASE | re.DOTALL)
            re_reason = re.compile(r'name=["\']zuobiReason["\'][^>]*>(.*?)<', re.IGNORECASE | re.DOTALL)

            _, content, _ = smart_load_xml(file_path)
            if not content:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

            if check_flag:
                match = re_flag.search(content)
                if match:
                    flag_node_found = True
                    flag_value = match.group(1).strip().lower()

            if check_reason:
                match = re_reason.search(content)
                if match:
                    reason_content = match.group(1)

            if check_flag:
                if flag_node_found:
                    if flag_value == "false":
                        results.append({'title': "🚫 IsZuobiB 检测", 'status': 'pass', 'msg': "✅ 正常 (False)"})
                    else:
                        cheat_found = True
                        results.append({'title': "🚫 IsZuobiB 检测", 'status': 'fail', 'msg': f"❌ 发现作弊标记 (值：{flag_value})"})
                else:
                    results.append({'title': "🚫 IsZuobiB 检测", 'status': 'warn', 'msg': "⚠️ 未找到节点"})

            if check_reason:
                if reason_content is not None:
                    clean_reason = reason_content.strip()
                    if clean_reason == "":
                        if not (flag_node_found and flag_value == "false"):
                            results.append({'title': "📝 ZuobiReason 分析", 'status': 'warn', 'msg': "⚠️ 标记作弊但无原因"})
                        else:
                            results.append({'title': "📝 ZuobiReason 分析", 'status': 'pass', 'msg': "✅ 无原因记录"})
                    else:
                        cheat_found = True
                        display = clean_reason.replace('\n', ' ').replace('\r', ' ')[:100] + ("..." if len(clean_reason) > 100 else "")
                        results.append({'title': "📝 ZuobiReason 分析", 'status': 'fail', 'msg': f"❌ 发现记录:\n{display}"})
                else:
                    if flag_node_found and flag_value != "false":
                        results.append({'title': "📝 ZuobiReason 分析", 'status': 'warn', 'msg': "⚠️ 已标记作弊但未找到原因节点"})
                    else:
                        results.append({'title': "📝 ZuobiReason 分析", 'status': 'pass', 'msg': "✅ 未发现原因节点"})
            return {'cheat_found': cheat_found, 'details': results}
        except Exception as e:
            return {'cheat_found': False, 'details': [{'title': "🚫 检测异常", 'status': 'fail', 'msg': str(e)}]}

    @staticmethod
    def check_uid_md5_advanced(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            tag_un2 = re.search(r'<s[^>]*name=["\']un2["\'][^>]*>(.*?)</s>', content, re.IGNORECASE | re.DOTALL)
            tag_uu2 = re.search(r'<s[^>]*name=["\']uu2["\'][^>]*>(.*?)</s>', content, re.IGNORECASE | re.DOTALL)
            tag_md5 = re.search(r'<s[^>]*name=["\']uidMd5["\'][^>]*>(.*?)</s>', content, re.IGNORECASE | re.DOTALL)

            if not tag_md5:
                return {'status': 'warn', 'msg': "⚠️ 未找到 uidMd5 节点，无法进行完整性验证", 'uid': None}

            target_md5 = tag_md5.group(1).strip().lower()
            if not target_md5:
                return {'status': 'fail', 'msg': '❌ uidMd5 节点为空', 'uid': None}

            uid = None
            if tag_un2 and tag_un2.group(1).strip().isdigit():
                uid = tag_un2.group(1).strip()
            elif tag_uu2 and tag_uu2.group(1).strip().isdigit():
                uid = tag_uu2.group(1).strip()

            if not uid:
                return {'status': 'fail', 'msg': '❌ 未找到有效的 UID 数据（un2 / uu2）', 'uid': None}

            found_uid = None
            for i in range(8):
                test_str = f"{uid}_{i}"
                calc_md5 = hashlib.md5(test_str.encode('utf-8')).hexdigest().lower()
                if calc_md5 == target_md5:
                    found_uid = test_str
                    break

            if found_uid:
                return {'status': 'pass', 'msg': f"✅ UID 检测通过\nUID：{uid}\n正确 index：{found_uid.split('_')[1]}\n完整值：{found_uid}", 'uid': found_uid}
            else:
                return {'status': 'fail', 'msg': f"❌ MD5 不匹配\nUID：{uid}\n无法匹配正确 index", 'uid': None}
        except Exception as e:
            return {'status': 'fail', 'msg': f"❌ UID 检测错误：{str(e)}", 'uid': None}

# ========================================================
# 🖥️ GUI 主程序
# ========================================================
class AppDetector:
    def __init__(self, root):
        self.root = root
        self.root.title("数据检测工具 (v7.0 多线程完整版)|BY. 观星者")
        self.WINDOW_W, self.WINDOW_H, self.NAV_H = 1200, 700, 40
        self.root.geometry(f"{self.WINDOW_W}x{self.WINDOW_H}")
        self.root.resizable(False, False)
        self.root.config(bg="#F0F0F0")

        self.COLOR_NAV_BG = "#00575F"
        self.COLOR_NAV_ACTIVE = "#E9A100"
        self.COLOR_PASS_BG, self.COLOR_PASS_FG = "#E8F5E9", "#2E7D32"
        self.COLOR_WARN_BG, self.COLOR_WARN_FG = "#FFF3E0", "#EF6C00"
        self.COLOR_FAIL_BG, self.COLOR_FAIL_FG = "#FFEBEE", "#C62828"

        self.config = configparser.ConfigParser()
        self.pages = {}
        self.nav_buttons = {}
        self.entry_uid = None
        self.entry_file_path = None
        self.result_inner_frame = None
        self.list_canvas = None
        self.settings_modified = False
        self.entry_work_dir = None
        self.entry_bin_path = None

        self.current_results = []
        self.current_file_path = ""
        self.current_uid_info = ""

        self._ensure_dirs()
        self._init_config()
        self._build_ui()

    def _ensure_dirs(self):
        dirs = [INPUT_DIR, OUTPUT_DIR, TEST_DIR]
        for d in dirs:
            if not os.path.exists(d):
                os.makedirs(d)

    def _init_config(self):
        if not os.path.exists(CONFIG_FILE):
            self._create_default_config()
            return

        try:
            self.config.read(CONFIG_FILE, encoding='utf-8')
            if 'Settings' not in self.config:
                self.config.add_section('Settings')
            if 'Security' not in self.config:
                self.config.add_section('Security')
        except Exception as e:
            print(f"警告：读取配置文件异常: {e}")
            if 'Settings' not in self.config:
                self.config.add_section('Settings')

    def _create_default_config(self):
        self.config['Settings'] = {
            'bin_path': DEFAULT_BIN_PATH,
            'work_dir': TEST_DIR,
            'last_file_path': '',
            'auto_restore': 'True',
            'auto_open_dir': 'False',
            'auto_uid_from_filename': 'True',
            'max_export_details': '10',
            'min_money_details': '500',
            'min_number_details': '10',
            'export_full_details': 'False',
            'batch_thread_count': '5',
            'auto_open_batch_report': 'False'
        }
        self._save_config(is_init=True)

    def _save_config(self, is_init=False):
        content_source = str(dict(self.config['Settings']))
        sig = generate_signature(content_source)
        if 'Security' not in self.config:
            self.config['Security'] = {}
        self.config['Security']['signature'] = sig
        self.config['Security']['version'] = '7.0.0'
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            self.config.write(f)
        self.settings_modified = False

    def _get_bool(self, key, default=False):
        try:
            return self.config.getboolean('Settings', key)
        except:
            return default

    def _set_bool(self, key, value):
        self.config.set('Settings', key, str(value))
        self.settings_modified = True

    def _get_str(self, key, default=''):
        try:
            return self.config.get('Settings', key)
        except:
            return default

    def _set_str(self, key, value):
        self.config.set('Settings', key, value)
        self.settings_modified = True

    def _get_int(self, key, default=0):
        try:
            return int(self.config.get('Settings', key))
        except:
            return default

    def _mark_settings_modified(self, *args):
        self.settings_modified = True

    def _build_ui(self):
        nav_frame = tk.Frame(self.root, bg=self.COLOR_NAV_BG, relief="flat")
        nav_frame.place(x=0, y=0, width=self.WINDOW_W, height=self.NAV_H)

        btn_w = 80
        pages_info = [("home", "🏠 主页", self._show_home), ("settings", "⚙️ 设置", self._show_settings), ("thanks", "📜 致谢", self._show_thanks)]

        for i, (key, text, cmd) in enumerate(pages_info):
            btn = tk.Button(nav_frame, text=text, bg=self.COLOR_NAV_ACTIVE if i == 0 else self.COLOR_NAV_BG, fg="white", font=("Microsoft YaHei", 10), bd=0, command=cmd)
            btn.place(x=i * btn_w, y=0, width=btn_w, height=self.NAV_H)
            btn.bind("<Enter>", lambda e, b=btn: self._on_btn_enter(e, b))
            btn.bind("<Leave>", lambda e, b=btn: self._on_btn_leave(e, b))
            self.nav_buttons[key] = btn

        tk.Label(nav_frame, text="数据检测工具 v7.0 多线程版", bg=self.COLOR_NAV_BG, fg="white", font=("Microsoft YaHei", 12, "bold")).place(relx=0.8, y=0)

        self.page_container = tk.Frame(self.root, bg="#F0F0F0")
        self.page_container.place(x=0, y=self.NAV_H, width=self.WINDOW_W, height=self.WINDOW_H - self.NAV_H)

        self._build_home_page()
        self._build_settings_page()
        self._build_thanks_page()
        self._show_home()

    def _on_btn_enter(self, event, btn):
        if btn.cget("bg") != self.COLOR_NAV_ACTIVE:
            btn.config(bg="#55A7F2")

    def _on_btn_leave(self, event, btn):
        if btn.cget("bg") != self.COLOR_NAV_ACTIVE:
            btn.config(bg=self.COLOR_NAV_BG)

    def _switch_page(self, page_name):
        current_page = None
        for name, frame in self.pages.items():
            if frame.winfo_viewable():
                current_page = name
                break

        if current_page == "settings" and self.settings_modified:
            response = messagebox.askyesnocancel("未保存的更改", "⚠️ 您修改了设置但尚未保存。\n\n是否先保存设置再切换页面？")
            if response is None:
                return
            elif response:
                self._save_settings()
            else:
                self.settings_modified = False

        for name, frame in self.pages.items():
            frame.place(x=0, y=0, width=self.WINDOW_W, height=self.WINDOW_H - self.NAV_H) if name == page_name else frame.place_forget()

        for key, btn in self.nav_buttons.items():
            btn.config(bg=self.COLOR_NAV_ACTIVE if key == page_name else self.COLOR_NAV_BG)

    def _show_home(self):
        self._switch_page("home")

    def _show_settings(self):
        self._switch_page("settings")

    def _show_thanks(self):
        self._switch_page("thanks")

    def _build_home_page(self):
        frame = tk.Frame(self.page_container, bg="#F0F0F0")
        self.pages["home"] = frame

        current_bin_path = self._get_str('bin_path', DEFAULT_BIN_PATH)
        if not os.path.exists(current_bin_path):
            tk.Label(frame, text=f"⚠️ 警告：未使用官方.bin 文件 (路径无效)，请注意甄别", font=("Microsoft YaHei", 10), bg="#FFEBEE", fg="#C62828", padx=10, pady=5, justify="left").pack(fill="x", padx=40, pady=(10, 0))

        main_area_x = 20
        main_area_y = 55
        total_width = 1100
        total_height = 550
        left_width = int(total_width * 0.6)
        right_width = int(total_width * 0.4)

        left_frame = tk.Frame(frame, bg="#FFFFFF", relief="solid", borderwidth=1)
        left_frame.place(x=main_area_x, y=main_area_x, width=left_width, height=total_height)

        tk.Label(left_frame, text="🆔 UID 输入", font=("Microsoft YaHei", 12, "bold"), bg="#FFFFFF", fg="#005159").place(x=20, y=15)
        self.entry_uid = tk.Entry(left_frame, width=65, font=("Consolas", 9), bd=1, relief="solid")
        self.entry_uid.place(x=20, y=55, width=left_width - 250, height=50)
        self.entry_uid.insert(0, "请输入 UID 或自动从文件名识别")
        self.entry_uid.config(fg="#999999")
        self.entry_uid.bind("<FocusIn>", lambda e: self._clear_placeholder(e, "请输入 UID 或自动从文件名识别"))
        self.entry_uid.bind("<FocusOut>", lambda e: self._set_placeholder(e, "请输入 UID 或自动从文件名识别"))

        tk.Button(left_frame, text="🔄 检测 uid", command=self._refresh_uid_from_filename, bg="#005159", fg="white", font=("Microsoft YaHei", 10), bd=0).place(x=450, y=55, width=190, height=50)

        tk.Label(left_frame, text="📂 文件路径", font=("Microsoft YaHei", 12, "bold"), bg="#FFFFFF", fg="#005159").place(x=20, y=110)
        self.entry_file_path = tk.Entry(left_frame, width=65, font=("Consolas", 9), bd=1, relief="solid")
        self.entry_file_path.place(x=20, y=160, width=left_width - 190, height=50)

        saved_path = self._get_str('last_file_path', '')
        if saved_path and self._get_bool('auto_restore', True):
            self.entry_file_path.insert(0, saved_path)
            self.entry_file_path.config(fg="black")
            self._try_auto_fill_uid(saved_path)
        else:
            self.entry_file_path.insert(0, "请在此粘贴路径或点击浏览...")
            self.entry_file_path.config(fg="#999999")

        self.entry_file_path.bind("<FocusIn>", lambda e: self._clear_placeholder(e, "请在此粘贴路径或点击浏览..."))
        self.entry_file_path.bind("<FocusOut>", lambda e: self._set_placeholder(e, "请在此粘贴路径或点击浏览..."))

        tk.Button(left_frame, text="🔍 浏览", command=self._browse_file, bg="#005159", fg="white", font=("Microsoft YaHei", 10), bd=0).place(x=left_width - 160, y=160, width=140, height=50)

        tk.Button(left_frame, text="📂 批量检测文件夹（多线程）", command=self._batch_detect_folder, bg="#d32f2f", fg="white", font=("Microsoft YaHei", 11, "bold"), bd=0).place(x=20, y=230, width=left_width - 40, height=50)

        btn_y_start = 300
        btn_h = 60
        btn_gap = 15

        tk.Button(left_frame, text="🚀 立即开始检测", command=self._run_detection, bg="#008984", fg="white", font=("Microsoft YaHei", 12, "bold"), bd=0).place(x=20, y=btn_y_start, width=left_width - 40, height=btn_h)

        btn_y_2 = btn_y_start + btn_h + btn_gap
        tk.Button(left_frame, text="📂 打开输出目录", command=lambda: self._open_dir(OUTPUT_DIR), bg="#E0E0E0", fg="#333333", font=("Microsoft YaHei", 10), bd=1, relief="solid").place(x=20, y=btn_y_2, width=(left_width - 40) // 2 - 5, height=btn_h)
        tk.Button(left_frame, text="📄 输出检测报告", command=self._generate_report, bg="#E0E0E0", fg="#333333", font=("Microsoft YaHei", 10), bd=1, relief="solid").place(x=20 + (left_width - 40) // 2 + 5, y=btn_y_2, width=(left_width - 40) // 2 - 5, height=btn_h)

        right_frame = tk.Frame(frame, bg="#F0F0F0")
        right_frame.place(x=main_area_x + left_width + 10, y=main_area_y, width=right_width + 40, height=total_height)

        list_container = tk.Frame(right_frame, bg="#FFFFFF", relief="solid", borderwidth=1)
        list_container.pack(fill="both", expand=True)

        self.list_canvas = tk.Canvas(list_container, bg="#FFFFFF", highlightthickness=0)
        vsb = tk.Scrollbar(list_container, orient="vertical", command=self.list_canvas.yview)
        vsb.pack(side="right", fill="y")
        self.list_canvas.configure(yscrollcommand=vsb.set)
        self.list_canvas.pack(side="left", fill="both", expand=True)

        self.result_inner_frame = tk.Frame(self.list_canvas, bg="#FFFFFF")
        self.canvas_window = self.list_canvas.create_window((0, 0), window=self.result_inner_frame, anchor="nw")
        self.result_inner_frame.bind("<Configure>", lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))

        def on_canvas_configure(event):
            self.list_canvas.itemconfig(self.canvas_window, width=event.width)

        self.list_canvas.bind("<Configure>", on_canvas_configure)

        def on_mouse_wheel(event):
            self.list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.list_canvas.bind("<MouseWheel>", on_mouse_wheel)

        tk.Label(self.result_inner_frame, text="等待检测...", font=("Microsoft YaHei", 12), bg="#FFFFFF", fg="#999999", justify="center").pack(pady=40, padx=20)

    def _build_settings_page(self):
        frame = tk.Frame(self.page_container, bg="#E0E0E0")
        self.pages["settings"] = frame

        tk.Label(frame, text="⚙️ 安全与检测设置", font=("Microsoft YaHei", 20, "bold"), bg="#E0E0E0", fg="#333333").place(x=40, y=20)

        card = tk.Frame(frame, bg="#FFFFFF", relief="solid", borderwidth=1)
        card.place(x=40, y=70, width=1080, height=520)

        self.cb_restore_var = tk.BooleanVar(value=self._get_bool('auto_restore', True))
        self.cb_open_var = tk.BooleanVar(value=self._get_bool('auto_open_dir', False))
        self.cb_auto_uid_var = tk.BooleanVar(value=self._get_bool('auto_uid_from_filename', True))
        self.cb_export_full_var = tk.BooleanVar(value=self._get_bool('export_full_details', False))
        self.cb_batch_open_var = tk.BooleanVar(value=self._get_bool('auto_open_batch_report', False))

        all_vars = [self.cb_restore_var, self.cb_open_var, self.cb_auto_uid_var, self.cb_export_full_var, self.cb_batch_open_var]
        for var in all_vars:
            var.trace_add("write", self._mark_settings_modified)

        y = 20
        tk.Label(card, text="📂 价格表文件路径:", bg="#FFFFFF", font=("Microsoft YaHei", 12, "bold"), fg="#008984").place(x=30, y=y)
        y += 35
        self.entry_bin_path = tk.Entry(card, font=("Consolas", 10), bd=1, relief="solid")
        self.entry_bin_path.place(x=30, y=y, width=720, height=35)
        current_bin = self._get_str('bin_path', DEFAULT_BIN_PATH)
        self.entry_bin_path.insert(0, current_bin)
        self.entry_bin_path.bind("<KeyRelease>", self._mark_settings_modified)

        def browse_bin():
            fp = filedialog.askopenfilename(title="选择 bin 文件", initialdir=INPUT_DIR, filetypes=[("Bin Files", "*.bin"), ("All Files", "*.*")])
            if fp:
                self.entry_bin_path.delete(0, tk.END)
                self.entry_bin_path.insert(0, fp)
                self._mark_settings_modified()

        tk.Button(card, text="📂 浏览", command=browse_bin, bg="#005159", fg="white", font=("Microsoft YaHei", 10), bd=0).place(x=760, y=y, width=120, height=35)

        y += 50
        tk.Label(card, text="📁 默认工作目录:", bg="#FFFFFF", font=("Microsoft YaHei", 12, "bold"), fg="#00575F").place(x=30, y=y)
        y += 35
        self.entry_work_dir = tk.Entry(card, font=("Consolas", 10), bd=1, relief="solid")
        self.entry_work_dir.place(x=30, y=y, width=720, height=35)
        current_work_dir = self._get_str('work_dir', TEST_DIR)
        self.entry_work_dir.insert(0, current_work_dir)
        self.entry_work_dir.bind("<KeyRelease>", self._mark_settings_modified)

        def browse_work_dir():
            curr_dir = self.entry_work_dir.get().strip()
            if not os.path.isdir(curr_dir):
                curr_dir = os.getcwd()
            fp = filedialog.askdirectory(title="选择默认工作目录", initialdir=curr_dir)
            if fp:
                self.entry_work_dir.delete(0, tk.END)
                self.entry_work_dir.insert(0, fp)
                self._mark_settings_modified()

        tk.Button(card, text="📂 浏览", command=browse_work_dir, bg="#005159", fg="white", font=("Microsoft YaHei", 10), bd=0).place(x=760, y=y, width=120, height=35)

        y += 50
        tk.Label(card, text="🛠️ 功能选项", bg="#FFFFFF", font=("Microsoft YaHei", 11, "bold"), fg="#00575F").place(x=30, y=y)
        y += 30

        tk.Checkbutton(card, text="自动恢复历史路径", variable=self.cb_restore_var, bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=50, y=y)
        tk.Checkbutton(card, text="单文件报告自动打开", variable=self.cb_open_var, bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=280, y=y)
        tk.Checkbutton(card, text="批量报告自动打开", variable=self.cb_batch_open_var, bg="#FFFFFF", font=("Microsoft YaHei", 11), fg="#d32f2f").place(x=510, y=y)
        y += 35

        tk.Checkbutton(card, text="自动从文件名识别UID", variable=self.cb_auto_uid_var, bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=50, y=y)
        tk.Checkbutton(card, text="批量导出完整细节", variable=self.cb_export_full_var, bg="#FFFFFF", font=("Microsoft YaHei", 11), fg="#C62828").place(x=280, y=y)
        y += 50

        tk.Label(card, text="📊 检测参数配置", bg="#FFFFFF", font=("Microsoft YaHei", 11, "bold"), fg="#00575F").place(x=30, y=y)
        y += 35

        tk.Label(card, text="明细最大条数:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=50, y=y)
        current_max_details = self._get_int('max_export_details', 10)
        self.entry_max_details = tk.Entry(card, font=("Consolas", 11), bd=1, relief="solid", justify="center")
        self.entry_max_details.place(x=150, y=y, width=80, height=30)
        self.entry_max_details.insert(0, str(current_max_details))
        self.entry_max_details.bind("<KeyRelease>", self._mark_settings_modified)

        tk.Label(card, text="最小金额明细:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=270, y=y)
        current_min_money = self._get_int('min_money_details', 500)
        self.entry_min_money = tk.Entry(card, font=("Consolas", 11), bd=1, relief="solid", justify="center")
        self.entry_min_money.place(x=370, y=y, width=80, height=30)
        self.entry_min_money.insert(0, str(current_min_money))
        self.entry_min_money.bind("<KeyRelease>", self._mark_settings_modified)

        tk.Label(card, text="最小数量明细:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=490, y=y)
        current_min_number = self._get_int('min_number_details', 10)
        self.entry_min_number = tk.Entry(card, font=("Consolas", 11), bd=1, relief="solid", justify="center")
        self.entry_min_number.place(x=590, y=y, width=80, height=30)
        self.entry_min_number.insert(0, str(current_min_number))
        self.entry_min_number.bind("<KeyRelease>", self._mark_settings_modified)

        tk.Label(card, text="批量线程数:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=710, y=y)
        thread_val = self._get_int('batch_thread_count', 5)
        self.entry_thread_count = tk.Entry(card, font=("Consolas", 11), bd=1, relief="solid", justify="center")
        self.entry_thread_count.place(x=800, y=y, width=80, height=30)
        self.entry_thread_count.insert(0, str(thread_val))
        self.entry_thread_count.bind("<KeyRelease>", self._mark_settings_modified)

        def validate_number(action, value_if_allowed):
            if action == '1':
                try:
                    int(value_if_allowed)
                    return True
                except ValueError:
                    return False
            return True

        vcmd = (self.root.register(validate_number), '%a', '%P')
        self.entry_max_details.config(validate='key', validatecommand=vcmd)
        self.entry_thread_count.config(validate='key', validatecommand=vcmd)
        self.entry_min_money.config(validate='key', validatecommand=vcmd)
        self.entry_min_number.config(validate='key', validatecommand=vcmd)

        btn_width = 160
        btn_x_start = 40
        btn_y = 610
        tk.Button(frame, text="💾 保存设置", command=self._save_settings, bg="#005159", fg="white", font=("Microsoft YaHei", 11, "bold"), bd=0).place(x=btn_x_start, y=btn_y, width=btn_width, height=45)
        tk.Button(frame, text="🔄 恢复默认设置", command=self._reset_settings, bg="#999999", fg="white", font=("Microsoft YaHei", 11), bd=0).place(x=btn_x_start + btn_width + 20, y=btn_y, width=btn_width, height=45)

    def _build_thanks_page(self):
        frame = tk.Frame(self.page_container, bg="#FFFFFF")
        self.pages["thanks"] = frame
        tk.Label(frame, text="📜 版本说明 (v7.0 精简版)", font=("Microsoft YaHei", 24, "bold"), bg="#FFFFFF", fg="#333333").place(x=40, y=50)
        txt = """版本：v7.0 精简优化版
[优化内容]
✅ 已删除冗余的 XOR 路径加密逻辑
✅ 配置文件直接使用明文路径，简洁易懂
✅ 代码体积减小，逻辑清晰
✅ 保留所有核心检测功能
✅ 多线程批量检测 / UID 合并报告
Copyright © 2026 观星者。"""
        tk.Label(frame, text=txt, font=("Microsoft YaHei", 12), bg="#FFFFFF", fg="#555555", justify="left", anchor="nw").place(x=40, y=110, width=870, height=400)

    def _clear_placeholder(self, event, placeholder):
        if event.widget.get() == placeholder:
            event.widget.delete(0, tk.END)
            event.widget.config(fg="black")

    def _set_placeholder(self, event, placeholder):
        if not event.widget.get():
            event.widget.insert(0, placeholder)
            event.widget.config(fg="#999999")

    def _refresh_uid_from_filename(self):
        file_path = self.entry_file_path.get().strip()
        if not file_path or file_path == "请在此粘贴路径或点击浏览...":
            return
        self.entry_uid.delete(0, tk.END)
        self.entry_uid.config(fg="black")
        self._try_auto_fill_uid(file_path)

    def _try_auto_fill_uid(self, file_path):
        if not self._get_bool('auto_uid_from_filename', True):
            return
        filename = os.path.basename(file_path)
        match = re.search(r'(\d+_\d+)', filename)
        if match:
            extracted_uid = match.group(1)
            self.entry_uid.delete(0, tk.END)
            self.entry_uid.insert(0, extracted_uid)
            self.entry_uid.config(fg="black")

    def _browse_file(self):
        work_dir = self._get_str('work_dir', TEST_DIR)
        if not os.path.isdir(work_dir):
            work_dir = TEST_DIR
        fp = filedialog.askopenfilename(title="选择数据文件", initialdir=work_dir, filetypes=[("XML 与 TXT 文件", "*.xml *.txt"), ("所有文件", "*.*")])
        if fp:
            self.entry_file_path.delete(0, tk.END)
            self.entry_file_path.insert(0, fp)
            self.entry_file_path.config(fg="black")
            self._set_str('last_file_path', fp)
            self._save_config()
            self._try_auto_fill_uid(fp)

    def _open_dir(self, path):
        if os.path.exists(path):
            os.startfile(path)
        else:
            try:
                os.makedirs(path)
                os.startfile(path)
            except:
                messagebox.showerror("错误", f"无法打开或创建目录：{path}")

    def _save_settings(self):
        self._set_bool('auto_restore', self.cb_restore_var.get())
        self._set_bool('auto_open_dir', self.cb_open_var.get())
        self._set_bool('auto_uid_from_filename', self.cb_auto_uid_var.get())
        self._set_bool('export_full_details', self.cb_export_full_var.get())
        self._set_bool('auto_open_batch_report', self.cb_batch_open_var.get())

        try:
            v = max(1, min(32, int(self.entry_thread_count.get().strip()) or 5))
            self.config.set('Settings', 'batch_thread_count', str(v))
        except:
            messagebox.showwarning("警告", "线程数必须是数字！")

        try:
            val = max(0, int(self.entry_max_details.get().strip()) if self.entry_max_details.get().strip() else 0)
            self.config.set('Settings', 'max_export_details', str(val))
        except:
            messagebox.showwarning("警告", "明细条数必须是数字！")

        try:
            val = max(0, int(self.entry_min_money.get().strip()) if self.entry_min_money.get().strip() else 0)
            self.config.set('Settings', 'min_money_details', str(val))
        except:
            messagebox.showwarning("警告", "最小金额必须是数字！")

        try:
            val = max(0, int(self.entry_min_number.get().strip()) if self.entry_min_number.get().strip() else 0)
            self.config.set('Settings', 'min_number_details', str(val))
        except:
            messagebox.showwarning("警告", "最小数量必须是数字！")

        self._set_str('bin_path', self.entry_bin_path.get().strip())
        self._set_str('work_dir', self.entry_work_dir.get().strip())

        self._save_config()
        messagebox.showinfo("成功", "✅ 设置已保存！")

    def _reset_settings(self):
        if messagebox.askyesno("确认", "确定要恢复默认设置吗？"):
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            self._init_config()
            self._show_settings()

    def _clear_results(self):
        for w in self.result_inner_frame.winfo_children():
            w.destroy()
        self.current_results = []

    def _add_result_item(self, status, title, detail):
        row = tk.Frame(self.result_inner_frame, relief="solid", borderwidth=1, bg="#FFFFFF")
        row.pack(fill="x", pady=2, padx=5, ipadx=5)
        colors = {'pass': ("#E8F5E9", "#2E7D32", "✅"), 'warn': ("#FFF3E0", "#EF6C00", "⚠️"), 'fail': ("#FFEBEE", "#C62828", "❌")}
        bg, fg, icon = colors.get(status, colors['warn'])
        tk.Label(row, text=f"{icon} {title}", font=("Microsoft YaHei", 10, "bold"), bg=bg, fg=fg, anchor="w").pack(fill="x", padx=5, pady=3)
        if detail:
            tk.Label(row, text=detail, font=("Microsoft YaHei", 9), bg="#FFFFFF", fg="#333333", anchor="nw", justify="left", wraplength=500, padx=5, pady=5).pack(fill="x")
        self.current_results.append((title, status, detail))

    def _run_detection(self):
        f_path = self.entry_file_path.get().strip()
        if not f_path or "浏览" in f_path or "粘贴" in f_path:
            messagebox.showwarning("缺少文件", "请先输入文件路径！")
            return
        if not os.path.exists(f_path):
            messagebox.showerror("文件未找到", f"❌ 系统找不到该文件：\n\n{f_path}")
            return

        bin_path = self._get_str('bin_path', DEFAULT_BIN_PATH)
        self._clear_results()
        self.current_file_path = f_path

        advanced_check_result = DetectionEngine.check_uid_md5_advanced(f_path)
        real_uid = advanced_check_result.get("uid")
        self.current_uid_info = real_uid if real_uid else "未提供"

        if real_uid:
            self.entry_uid.delete(0, tk.END)
            self.entry_uid.insert(0, real_uid)
            self.entry_uid.config(fg="black")

        self._add_result_item(advanced_check_result["status"], "🔐 UID 检测", advanced_check_result["msg"])

        res = DetectionEngine.check_vip_xml(f_path)
        if res:
            self._add_result_item(res['status'], "VIP 权限检测", res['msg'])

        max_det = self._get_int('max_export_details', 10)
        min_money = self._get_int('min_money_details', 500)
        min_number = self._get_int('min_number_details', 10)
        export_full = self._get_bool('export_full_details', False)
        res = DetectionEngine.check_pay_xml(f_path, bin_path, max_details=max_det, min_money_details=min_money, min_number_details=min_number, export_full=export_full)
        self._add_result_item(res['status'], "💰 支付消费分析", res['msg'])

        cheat_res = DetectionEngine.check_cheat_stream(f_path)
        for item in cheat_res['details']:
            self._add_result_item(item['status'], item['title'], item['msg'])

        if cheat_res['cheat_found']:
            messagebox.showwarning("高危警告", "⚠️ 检测发现疑似作弊行为！")

    def _process_one_file(self, file_path, bin_path, max_det, min_money, min_num, export_full):
        try:
            uid_res = DetectionEngine.check_uid_md5_advanced(file_path)
            vip_res = DetectionEngine.check_vip_xml(file_path)
            pay_res = DetectionEngine.check_pay_xml(file_path, bin_path, max_det, min_money, min_num, export_full)
            cheat_res = DetectionEngine.check_cheat_stream(file_path)
            return {
                "file": os.path.basename(file_path),
                "uid": uid_res, "vip": vip_res, "pay": pay_res, "cheat": cheat_res,
                "has_cheat": cheat_res["cheat_found"],
                "has_fail": (vip_res["status"] == "fail" or pay_res["status"] == "fail" or uid_res["status"] == "fail"),
                "total_cost": pay_res.get('total_cost', 0)
            }
        except Exception as e:
            return {"file": os.path.basename(file_path), "error": str(e), "has_fail": True, "total_cost": 0}

    def _batch_detect_folder(self):
        root_dir = filedialog.askdirectory(title="选择要检测的文件夹（支持直接放XML）")
        if not root_dir:
            return

        bin_path = self._get_str('bin_path', DEFAULT_BIN_PATH)
        if not os.path.exists(bin_path):
            messagebox.showerror("错误", "bin 文件不存在，请先配置！")
            return

        self._clear_results()
        max_det = self._get_int('max_export_details', 10)
        min_money = self._get_int('min_money_details', 500)
        min_num = self._get_int('min_number_details', 10)
        thread_count = self._get_int('batch_thread_count', 5)
        export_full = self._get_bool('export_full_details', False)
        auto_open_batch = self._get_bool('auto_open_batch_report', False)

        file_list = []
        for base_path, _, files in os.walk(root_dir):
            for fname in files:
                if not fname.endswith('.xml'):
                    continue
                fpath = os.path.join(base_path, fname)
                match = re.search(r'(\d+_\d+)', fname)
                if match:
                    full_uid = match.group(1)
                    uid = full_uid.split('_')[0]
                else:
                    uid = 'unknown_uid'
                file_list.append((uid, fpath))

        if not file_list:
            messagebox.showwarning("提示", "未找到任何XML文件！")
            return

        self._add_result_item("pass", "🧵 多线程检测开始", f"线程数：{thread_count} | 总文件：{len(file_list)}")
        self.root.update()

        uid_record = defaultdict(list)
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            future_map = {executor.submit(self._process_one_file, fp, bin_path, max_det, min_money, min_num, export_full): uid for uid, fp in file_list}
            for fut in as_completed(future_map):
                uid = future_map[fut]
                res = fut.result()
                uid_record[uid].append(res)
                self._add_result_item("pass", f"✅ 已完成：{uid}", f"文件：{res['file']}")
                self.root.update()

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        total_report = os.path.join(OUTPUT_DIR, f"批量总报告_{timestamp}.txt")

        with open(total_report, "w", encoding="utf-8") as f:
            f.write("="*70 + f"\n  批量检测报告 {timestamp}\n" + "="*70 + "\n\n")
            f.write(f"总文件数：{len(file_list)}\n\n")
            for uid, records in uid_record.items():
                cheat = sum(1 for r in records if r.get("has_cheat"))
                fail = sum(1 for r in records if r.get("has_fail"))
                status = "✅正常" if cheat==0 and fail==0 else "⚠️异常" if fail>0 else "❌作弊"
                f.write(f"【{uid}】{status} | 文件：{len(records)} | 作弊：{cheat} | 异常：{fail}\n")

        for uid, records in uid_record.items():
            uid_report = os.path.join(OUTPUT_DIR, f"UID_{uid}.txt")
            total_cost = sum(r.get("total_cost", 0) for r in records)
            index_map = defaultdict(list)

            for r in records:
                match = re.search(r"_(\d+)\.xml$", r["file"])
                idx = match.group(1) if match else "0"
                index_map[idx].append(r)

            sorted_indices = sorted(index_map.keys(), key=lambda x: int(x))

            with open(uid_report, "w", encoding="utf-8") as f:
                f.write(f"UID：{uid}\n总消费：{total_cost} 黄金\n\n")
                f.write("="*50 + "\n")
                for idx in sorted_indices:
                    group = index_map[idx]
                    best = group[-1]
                    f.write(f"【Index {idx}】文件：{best['file']}\n")
                    if "error" in best:
                        f.write(f"❌ 错误：{best['error']}\n")
                    else:
                        f.write(f"{best['uid']['msg']}\n")
                        f.write(f"{best['vip']['msg']}\n")
                        f.write(f"{best['pay']['msg']}\n")
                    f.write("-"*50 + "\n")

        if auto_open_batch:
            os.startfile(total_report)

        msg = f"✅ 检测完成！\n总文件：{len(file_list)}\n报告已保存至 outputdata"
        self._add_result_item("pass", "完成", msg)
        messagebox.showinfo("完成", msg)

    def _generate_report(self):
        if not self.current_results or not self.current_file_path:
            messagebox.showwarning("提示", "请先进行检测！")
            return
        uid = self.current_uid_info
        if not uid:
            uid = "未知UID"
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filename = f"检测报告_{uid}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"===== 检测报告 =====\n文件：{self.current_file_path}\nUID：{uid}\n\n")
            for title, status, detail in self.current_results:
                f.write(f"[{status}] {title}\n{detail}\n\n")
        messagebox.showinfo("成功", f"报告已保存：\n{path}")
        if self._get_bool('auto_open_dir'):
            os.startfile(path)

if __name__ == "__main__":
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
    root = tk.Tk()
    app = AppDetector(root)
    root.mainloop()