import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
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
import csv

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
    return  # 已禁用原单UID导出

# ========================================================
# 🆕 CSV 封禁检测函数（全局递归加载所有CSV）
# ========================================================
class SlotBanCache:
    def __init__(self):
        self.ban_cache = {}  # {uid_index: reason}

    def load_all_csv_from_root(self, root_folder):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🔍 扫描封禁CSV: {root_folder}")
        csv_count = 0
        for dirpath, _, filenames in os.walk(root_folder):
            for f in filenames:
                if f.endswith("_details.csv"):
                    csv_path = os.path.join(dirpath, f)
                    self._load_single_csv(csv_path)
                    csv_count += 1
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ 封禁CSV加载完成: {csv_count} 个")

    def _load_single_csv(self, csv_path):
        try:
            csv_filename = os.path.basename(csv_path)
            uid = csv_filename.replace("_details.csv", "")
            with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    slot = str(row.get("槽位", "")).strip()
                    state = str(row.get("状态", "")).strip()
                    title = str(row.get("标题", "")).strip() or "无名称"
                    if not slot:
                        continue
                    try:
                        idx = str(int(slot))
                    except:
                        continue

                    reason = None
                    if "永久封禁" in state:
                        reason = f"永久封禁 | 槽位{idx} | {title}"
                    elif "临时封禁" in state:
                        reason = f"临时封禁 | 槽位{idx} | {title}"

                    if reason:
                        key = f"{uid}_{idx}"
                        self.ban_cache[key] = reason
        except:
            pass

    def get_ban_reason(self, fname):
        match = re.match(r"^(\d+)_(\d+)\.xml$", fname)
        if not match:
            return None
        uid, idx = match.groups()
        key = f"{uid}_{idx}"
        return self.ban_cache.get(key)

# 全局实例，整个程序共用
SLOT_BAN_CACHE = SlotBanCache()

# ========================================================
# 🔒 检测引擎核心
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
            msg_lines.append(f"🚨作弊原因:基准额度：{limit_amount}实际消耗：{pay_cost}")
        elif ratio < 0.7:
            status = 'warn'
            msg_lines.append(f"⚠️ 警告原因:消耗小于70%，可能出现覆盖存档")
        else:
            msg_lines.append(f"✅ 消耗正常。")
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
            if len(valid_vip_nodes) > 1:
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
                        vip_errors.append(f"权限越界：[{source}] 中 VIP{vip_level} 开启了需 VIP{required_level} 的权限 (m{m_val})")

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
            tag_md5 = re.search(r'<s[^>]*name=["\']uidMd5["\'][^>]*>(.*?)</s>', content, re.IGNORECASE | re.DOTALL)
            tag_un2 = re.search(r'<s[^>]*name=["\']un2["\'][^>]*>(.*?)</s>', content, re.IGNORECASE | re.DOTALL)
            tag_uu2 = re.search(r'<s[^>]*name=["\']uu2["\'][^>]*>(.*?)</s>', content, re.IGNORECASE | re.DOTALL)

            if not tag_md5:
                return {'status': 'warn', 'msg': '⚠️ 未找到 uidMd5 节点', 'uid': None}

            target_md5 = tag_md5.group(1).strip().lower()
            if not target_md5:
                return {'status': 'fail', 'msg': '❌ uidMd5 节点为空', 'uid': None}

            filename_uid = None
            filename_match = re.search(r'(\d+)_(\d+)', os.path.basename(file_path))
            if filename_match:
                filename_uid = filename_match.group(1)

            if filename_uid:
                for index in range(8):
                    test_str = f"{filename_uid}_{index}"
                    calc_md5 = hashlib.md5(test_str.encode('utf-8')).hexdigest().lower()
                    if calc_md5 == target_md5:
                        return {
                            'status': 'pass',
                            'msg': f"✅ UID 检测通过\nUID：{filename_uid}\nIndex：{index}\n来源：正常存档",
                            'uid': f"{filename_uid}_{index}"
                        }

            FALLBACK_MD5_LIST = [
                "5e20663dadd1e483ac628951dd582ea8",
                "174882033225436b1440b7de44686450",
                "8de55a2e5745f73de25402626a4c3d61",
                "856e4980d5eb3351797f528948f684e5",
                "8efc299ca974ee46c0bc622cd51b4dc7",
                "ade82d56fe033105b37cc8ef1783cd93",
                "8868fae7afbf71557a2e4faceeb9d9d6",
                "66bc78dc545e1a7b7ac07302c82067c1"
            ]

            for index, fallback_md5 in enumerate(FALLBACK_MD5_LIST):
                if target_md5 == fallback_md5.lower():
                    final_uid = f"0_{index}"
                    if index == 0:
                        return {
                            'status': 'pass',
                            'msg': f"ℹ️ 保底通过\n",
                            'uid': final_uid
                        }
                    else:
                        return {
                            'status': 'warn',
                            'msg': f"⚠️ 存档MD5匹配：{final_uid}\n",
                            'uid': final_uid
                        }

            uid = None
            if tag_un2 and tag_un2.group(1).strip().isdigit():
                uid = tag_un2.group(1).strip()
            elif tag_uu2 and tag_uu2.group(1).strip().isdigit():
                uid = tag_uu2.group(1).strip()

            error_msg = f"❌ UID 获取失败\n"
            if uid:
                error_msg += f"UID：{uid}\n"
                error_msg += "结论：疑似外挂或严重损坏"

            return {'status': 'fail', 'msg': error_msg, 'uid': None}

        except Exception as e:
            return {'status': 'fail', 'msg': f'❌ 检测异常：{str(e)}', 'uid': None}

# ========================================================
# 🖥️ GUI 主程序
# ========================================================
class AppDetector:
    def __init__(self, root):
        self.root = root
        self.root.title("数据检测工具 v7.2.2|BY. 观星者")
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
        dirs = [INPUT_DIR, OUTPUT_DIR, TEST_DIR, os.path.join(OUTPUT_DIR, "异常详情")]
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

    def _set_int(self, key, value):
        self.config.set('Settings', key, str(value))
        self.settings_modified = True

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

        tk.Label(nav_frame, text="数据检测工具 v7.2.2", bg=self.COLOR_NAV_BG, fg="white", font=("Microsoft YaHei", 12, "bold")).place(relx=0.7, y=0)

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
        left_frame.place(x=main_area_x, y=main_area_y, width=left_width, height=total_height)

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

        log_container = tk.Frame(right_frame, bg="#FFFFFF", relief="solid", borderwidth=1)
        log_container.pack(fill="both", expand=True, padx=0, pady=0)

        tk.Label(log_container, text="💻 实时运行日志", font=("Microsoft YaHei", 11, "bold"),
                 bg="#FFFFFF", fg=self.COLOR_NAV_BG).pack(anchor="w", padx=10, pady=5)

        log_frame = tk.Frame(log_container, bg="#FFFFFF")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0,10))

        self.log_text = tk.Text(log_frame, font=("Consolas", 9), bg="#1E1E1E", fg="#FFFFFF",
                                wrap="word", state="disabled")
        log_scroll = tk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        self.log_text.tag_config("PASS", foreground=self.COLOR_PASS_FG)
        self.log_text.tag_config("WARN", foreground=self.COLOR_WARN_FG)
        self.log_text.tag_config("FAIL", foreground=self.COLOR_FAIL_FG)
        self.log_text.tag_config("INFO", foreground="#9CDCFE")

    def log(self, msg, level="INFO"):
        self.root.after(0, self._real_log, msg, level)

    def _real_log(self, msg, level="INFO"):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        log_str = f"[{now}] [{level}] {msg}\n"
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, log_str, level)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")


    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

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

        tk.Label(card, text="线程数:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=710, y=y)
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
        frame = tk.Frame(self.page_container, bg="#F0F0F0")
        self.pages["thanks"] = frame

        tk.Label(frame, text="📜 致谢与说明", font=("Microsoft YaHei", 20, "bold"), bg="#F0F0F0").pack(pady=20)

        text = """
本工具用于数据安全检测与异常分析
仅用于合法合规的项目调试与安全审计

核心功能：
• UID 合法性校验
• VIP 权限越权检测
• 消费数据异常分析
• 作弊标记自动识别
• CSV存档封禁状态自动检测
• 结果仅供参考，请自行判断,因此产生不良后果与开发者无关

使用须知：
1. 请确保用于授权场景
2. 请勿用于非法用途
3. 问题反馈请联系开发者qq:2434044637
"""
        tk.Label(frame, text=text, font=("Microsoft YaHei", 12), bg="#F0F0F0", justify=tk.LEFT, anchor="w").pack(anchor="w", padx=30, pady=10)
        tk.Label(frame, text="2026.4.9", font=("Microsoft YaHei", 12), bg="#F0F0F0", justify=tk.RIGHT).pack(side=tk.BOTTOM, anchor=tk.E, padx=30, pady=15)

    def _clear_placeholder(self, event, placeholder):
        widget = event.widget
        if widget.get() == placeholder:
            widget.delete(0, tk.END)
            widget.config(fg="black")

    def _set_placeholder(self, event, placeholder):
        widget = event.widget
        if not widget.get():
            widget.insert(0, placeholder)
            widget.config(fg="#999999")

    def _try_auto_fill_uid(self, file_path):
        if not self._get_bool('auto_uid_from_filename', True):
            return
        if not file_path or not os.path.exists(file_path):
            return
        try:
            res = DetectionEngine.check_uid_md5_advanced(file_path)
            if res and res.get('uid'):
                self.entry_uid.delete(0, tk.END)
                self.entry_uid.insert(0, res.get('uid'))
                self.entry_uid.config(fg="black")
        except:
            pass

    def _browse_file(self):
        last_path = self._get_str('last_file_path', '')
        init_dir = os.path.dirname(last_path) if last_path and os.path.exists(os.path.dirname(last_path)) else TEST_DIR
        file_path = filedialog.askopenfilename(
            title="选择数据文件",
            initialdir=init_dir,
            filetypes=[("XML Files", "*.xml"), ("All Files", "*.*")]
        )
        if file_path:
            self.entry_file_path.delete(0, tk.END)
            self.entry_file_path.insert(0, file_path)
            self.entry_file_path.config(fg="black")
            self._set_str('last_file_path', file_path)
            self._try_auto_fill_uid(file_path)

    def _refresh_uid_from_filename(self):
        file_path = self.entry_file_path.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning("提示", "请先选择有效的文件路径")
            return
        self._try_auto_fill_uid(file_path)
        messagebox.showinfo("完成", "已尝试从文件名自动识别 UID")

    def _open_dir(self, dir_path):
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        try:
            os.startfile(dir_path)
        except:
            messagebox.showwarning("提示", "无法自动打开目录，请手动访问")

    def _run_detection(self):
        file_path = self.entry_file_path.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("错误", "文件路径无效或不存在")
            return

        self._set_str('last_file_path', file_path)
        self._save_config()
        threading.Thread(target=self._do_detect_work, daemon=True).start()

    def _do_detect_work(self):
        self.clear_log()
        file_path = self.entry_file_path.get().strip()
        bin_path = self._get_str('bin_path', DEFAULT_BIN_PATH)
        max_details = self._get_int('max_export_details', 10)
        min_money = self._get_int('min_money_details', 500)
        min_num = self._get_int('min_number_details', 10)
        export_full = self._get_bool('export_full_details', False)
        folder_path = os.path.dirname(file_path)
        fname = os.path.basename(file_path)

        results = []
        uid_info = ""

        # 封禁检测
        ban_reason = SLOT_BAN_CACHE.get_ban_reason(fname)
        ban_result = {"status": "pass", "title": "📄 CSV存档封禁检测", "msg": "✅ 未检测到存档封禁"}
        if ban_reason:
            ban_result = {"status": "fail", "title": "📄 CSV存档封禁检测", "msg": f"🚨 {ban_reason}"}
        results.append(ban_result)
        self.log(f"封禁检测：{ban_result['msg']}", ban_result['status'].upper())

        # UID检测
        uid_res = DetectionEngine.check_uid_md5_advanced(file_path)
        results.append(uid_res)
        if uid_res.get('uid'):
            uid_info = uid_res.get('uid')
            self.current_uid_info = uid_info
        self.log(f"UID检测：{uid_res.get('msg')}", uid_res.get('status').upper())

        # 作弊检测
        self.log("执行作弊流检测...", "INFO")
        cheat_res = DetectionEngine.check_cheat_stream(file_path)
        for d in cheat_res['details']:
            results.append(d)
            self.log(f"{d['title']}：{d['msg']}", d['status'].upper())

        # VIP检测
        vip_res = DetectionEngine.check_vip_xml(file_path)
        results.append(vip_res)
        self.log(f"VIP检测：{vip_res.get('msg')}", vip_res.get('status').upper())

        # 消费检测
        self.log("执行消费数据检测...", "INFO")
        pay_res = DetectionEngine.check_pay_xml(file_path, bin_path, max_details, min_money, min_num, export_full)
        results.append(pay_res)
        self.log(f"消费检测：{pay_res.get('msg')}", pay_res.get('status').upper())
        total_cost = pay_res.get("total_cost", 0)

        # VIP联合检测（使用真实总消费）
        self.log("执行VIP-消费联合检测...", "INFO")
        union_res = DetectionEngine.check_vip_pay_union(file_path, total_cost)
        results.append(union_res)
        self.log(f"VIP联合检测：{union_res.get('msg')}", union_res.get('status').upper())

        self.current_results = results
        self.current_file_path = file_path

    def _generate_report(self):
        if not self.current_results:
            messagebox.showwarning("提示", "暂无检测结果可导出")
            return

        filename = os.path.basename(self.current_file_path)
        name = os.path.splitext(filename)[0]
        report_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_name = f"检测报告_{name}_{report_time}.txt"
        report_path = os.path.join(OUTPUT_DIR, report_name)

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"检测文件：{self.current_file_path}\n")
            f.write(f"检测时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"UID：{self.current_uid_info}\n\n")
            f.write("="*50 + "\n\n")

            for res in self.current_results:
                if isinstance(res, dict):
                    title = res.get('title', '检测项')
                    status = res.get('status', 'pass')
                    msg = res.get('msg', '')
                    f.write(f"【{title}】[{status}]\n")
                    f.write(msg + "\n\n")

        if self._get_bool('auto_open_dir', False):
            self._open_dir(OUTPUT_DIR)
        messagebox.showinfo("完成", f"报告已保存：\n{report_path}")

    def _batch_detect_folder(self):
        folder_path = filedialog.askdirectory(title="选择批量检测文件夹", initialdir=self._get_str('work_dir', TEST_DIR))
        if not folder_path:
            return

        self._set_str('work_dir', folder_path)
        self._save_config()
        threading.Thread(target=self._do_batch_detect, args=(folder_path,), daemon=True).start()

    def _do_batch_detect(self, folder_path):
        self.clear_log()
        self.log(f"📂 开始批量检测：{folder_path}", "INFO")
        SLOT_BAN_CACHE.load_all_csv_from_root(folder_path)
        self.log("✅ 封禁缓存加载完成", "INFO")

        bin_path = self._get_str('bin_path', DEFAULT_BIN_PATH)
        max_details = self._get_int('max_export_details', 10)
        min_money = self._get_int('min_money_details', 500)
        min_num = self._get_int('min_number_details', 10)
        export_full = self._get_bool('export_full_details', False)
        thread_count = self._get_int('batch_thread_count', 5)

        file_list = []
        for root_dir, dirs, files in os.walk(folder_path):
            for f in files:
                if f.lower().endswith('.xml'):
                    file_list.append(os.path.join(root_dir, f))

        total = len(file_list)


        # 全局 UID 消费累加（修复核心）
        uid_total_cost = defaultdict(int)
        success = warn = fail = 0
        report_data = []

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            future_to_file = {}
            for fp in file_list:
                future = executor.submit(self._detect_single_file_batch, fp, bin_path, max_details, min_money, min_num, export_full, uid_total_cost)
                future_to_file[future] = fp

            for future in as_completed(future_to_file):
                fp = future_to_file[future]
                try:
                    res = future.result()
                    report_data.append(res)
                    if res['overall'] == 'fail':
                        fail += 1
                    elif res['overall'] == 'warn':
                        warn += 1
                    else:
                        success += 1

                    # 提取 warn/fail 原因（只取第一条，避免日志过长）
                    reason = '未知原因'
                    for r in res['results']:
                        if isinstance(r, dict) and r.get('status') in ['warn', 'fail']:
                            msg_lines = r.get('msg', '未知原因').split('\n')
                            # 取最后一行（就是「作弊原因/警告原因/消耗正常」那一行）
                            for line in reversed(msg_lines):
                                line = line.strip()
                                if line and not line.startswith(('🔍', '-', '【')):  # 过滤掉标题、参数行
                                    reason = line
                                    break
                            break

                    status = res['overall'].upper()
                    if status == "PASS":
                        self.log(f"✅ 完成：{os.path.basename(fp)} | {res['uid']} | {res['overall']}", status)
                    elif status == "WARN":
                        self.log(f"⚠️ 完成：{os.path.basename(fp)} | {res['uid']} | {res['overall']} | 原因：{reason}", status)
                    elif status == "FAIL":
                        self.log(f"❌ 完成：{os.path.basename(fp)} | {res['uid']} | {res['overall']} | 原因：{reason}", status)
                    else:
                        self.log(f"✅ 完成：{os.path.basename(fp)} | {res['uid']} | {res['overall']}", status)
                except Exception as e:
                    self.log(f"❌ 处理失败：{fp} | {str(e)}", "FAIL")

        self._generate_batch_report(report_data, success, warn, fail, total)


    def _detect_single_file_batch(self, file_path, bin_path, max_details, min_money, min_num, export_full, uid_total_cost):
        fname = os.path.basename(file_path)
        ban_reason = SLOT_BAN_CACHE.get_ban_reason(fname)
        uid_res = DetectionEngine.check_uid_md5_advanced(file_path)
        cheat_res = DetectionEngine.check_cheat_stream(file_path)
        vip_res = DetectionEngine.check_vip_xml(file_path)
        pay_res = DetectionEngine.check_pay_xml(file_path, bin_path, max_details, min_money, min_num, export_full)

        # ========== 【终极修复 split 报错】 ==========
        uid_str = uid_res.get('uid', '') if uid_res is not None else ''
        if uid_str and '_' in str(uid_str):
            real_uid = str(uid_str).split('_')[0]
        else:
            real_uid = 'unknown'

        current_cost = pay_res.get('total_cost', 0)
        uid_total_cost[real_uid] += current_cost
        total_cost = uid_total_cost[real_uid]

        union_res = DetectionEngine.check_vip_pay_union(file_path, total_cost)

        ban_result = {"status": "pass", "title": "CSV封禁", "msg": "正常"}
        if ban_reason:
            ban_result = {"status": "fail", "title": "CSV封禁", "msg": ban_reason}

        uid = uid_str if uid_str else '未知'
        overall = 'pass'
        cheat_found = cheat_res.get('cheat_found', False)
        all_checks = [uid_res, vip_res, pay_res, union_res, ban_result] + cheat_res['details']

        for r in all_checks:
            if isinstance(r, dict) and r.get('status') == 'fail':
                overall = 'fail'
                break
        if overall != 'fail':
            for r in all_checks:
                if isinstance(r, dict) and r.get('status') == 'warn':
                    overall = 'warn'
                    break

        return {
            'file': file_path,
            'uid': uid,
            'overall': overall,
            'cheat': cheat_found,
            'results': [uid_res] + cheat_res['details'] + [vip_res, pay_res, union_res, ban_result]
        }

    def _generate_batch_report(self, report_data, success, warn, fail, total):
        report_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_name = f"批量检测总报告_{report_time}.txt"
        report_path = os.path.join(OUTPUT_DIR, report_name)

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"批量检测总报告\n")
            f.write(f"检测时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总计：{total} | 异常：{fail} | 警告：{warn}\n")
            f.write("=" * 60 + "\n\n")

            for item in report_data:
                if item['overall'] == 'pass':
                    continue
                f.write(f"🚨 文件：{os.path.basename(item['file'])}\nUID：{item['uid']}\n结果：【{item['overall']}】\n")
                f.write("-" * 40 + "\n")
                for res in item['results']:
                    if isinstance(res, dict) and res.get('status') in ('fail', 'warn'):
                        f.write(f"[{res.get('title','检测项')}] [{res.get('status')}]\n{res.get('msg','')}\n\n")
                f.write("="*50 + "\n\n")

        self.log(f"📄 总报告已生成：{report_path}", "INFO")
        if self._get_bool('auto_open_batch_report'):
            self._open_dir(OUTPUT_DIR)

    def _save_settings(self):
        self._set_str('bin_path', self.entry_bin_path.get().strip())
        self._set_str('work_dir', self.entry_work_dir.get().strip())
        self._set_bool('auto_restore', self.cb_restore_var.get())
        self._set_bool('auto_open_dir', self.cb_open_var.get())
        self._set_bool('auto_uid_from_filename', self.cb_auto_uid_var.get())
        self._set_bool('export_full_details', self.cb_export_full_var.get())
        self._set_bool('auto_open_batch_report', self.cb_batch_open_var.get())

        try:
            self._set_int('max_export_details', int(self.entry_max_details.get()))
            self._set_int('min_money_details', int(self.entry_min_money.get()))
            self._set_int('min_number_details', int(self.entry_min_number.get()))
            self._set_int('batch_thread_count', int(self.entry_thread_count.get()))
        except:
            messagebox.showwarning("警告", "参数必须为数字")

        self._save_config()
        messagebox.showinfo("成功", "设置已保存！")

    def _reset_settings(self):
        self._create_default_config()
        self.entry_bin_path.delete(0, tk.END)
        self.entry_bin_path.insert(0, DEFAULT_BIN_PATH)
        self.entry_work_dir.delete(0, tk.END)
        self.entry_work_dir.insert(0, TEST_DIR)
        messagebox.showinfo("完成", "已恢复默认设置")

if __name__ == "__main__":
    root = tk.Tk()
    app = AppDetector(root)
    root.mainloop()