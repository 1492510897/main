"""
main (γ 合并版) v3.0.0 —— 数据检测工具（军队/公会成员存档批量检测）
===================================================================
融合 α(main2.1, 按文件批量输出详情) 与 β(2.β, 存档封禁检测 / UID一致性校验 / 自动报告)

检测项（单文件 & 批量）：
  1. 📄 存档封禁检测    SlotBanCache：递归扫描所选目录下所有 *_details.csv（下载工具产物）
                       （兼容“存档/标题/状态/封禁状态”与旧“槽位/名称/状态”两种表头）
  2. 🆔 UID 验证        文件名 UID/Index/Name + 文件内 un2/uu2 + uidMd5 三重校验，返回理论/实际
                       并单独指出 index 不一致（理论UID_Index ≠ 实际UID_Index）
  3. 🚫 作弊检测        isZuobiB 标记 + zuobiReason 原因联动
  4. 👑 VIP权限检测      vip 节点 m 权限越界
  5. 💰 金币消费检测     bin 价格表解密 → 全部消费明细 + 高价/高频预警
  6. 💎 VIP联合检测      按同一 UID 累计消费估算，判断“覆盖存档”与超额度消耗（修复原β计算bug）

批量导出（按 UID 汇总）：
  • 同一 UID（服务器UID）下多个 uid_index 合并为一份 *_异常详情.txt
  • CSV 每行对应一个 UID，“UID_Index”列汇总列出该 UID 下全部 index
  • 文件中单独列出“🔢 index 异常单独指出”，标注理论/实际不一致的存档

界面：主页(单文件检测 / 批量检测 / 报告导出 / 打开下载工具) + 设置 + 致谢
运行目录：inputdata/ outputdata/ test/ ；读取 config.ini(Settings)
"""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import hashlib
import configparser
import xml
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
import info_get

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
DEFAULT_BIN_PATH = os.path.join(".", INPUT_DIR, "v36.11_pro.bin")
VERSION = "3.0.0"

# ========================================================
# 🔒 工具函数
# ========================================================
def resource_path(relative_path):
    """获取资源文件的绝对路径，支持PyInstaller打包"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def set_app_icon(root):
    """安全设置窗口图标"""
    try:
        ico_path = resource_path("main.ico")
        if os.path.exists(ico_path):
            root.iconbitmap(ico_path)
            return True
    except Exception as e:
        print(f"设置图标失败（忽略）: {e}")
    return False


def smart_load_xml(file_path, gui_logger=None):
    candidate_encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'cp936', 'windows-1252', 'iso-8859-1']
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
    except Exception as e:
        if gui_logger:
            gui_logger(f"❌ 文件读取失败：{e}")
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

    if gui_logger:
        gui_logger("❌ 无法识别文件编码或 XML 格式严重损坏")
    return None, "", "All Failed"


def generate_signature(content: str) -> str:
    mixed = SIGN_KEY + content.encode('utf-8')
    return hashlib.sha256(mixed).hexdigest()


def verify_signature(content: str, signature: str) -> bool:
    return hmac.compare_digest(generate_signature(content), signature)


class RunLogger:
    """线程安全运行日志：内存缓冲 + UI 回调 + 实时落盘 + 可导出。

    取代原先直接向 tkinter Text 写日志的做法（原 clear_log 会被子线程直接调用，
    属线程不安全操作；且日志只存在于界面上，无法导出留档）。

    file_path 设置后每条日志会同步追加到文件：即使程序异常退出/窗口关闭，
    运行日志也已落盘，不会随界面一起丢失。
    """

    def __init__(self, on_emit=None, file_path=None):
        self._lock = threading.Lock()
        self._records = []          # [(时间str, 级别, 文本)]
        self.on_emit = on_emit      # 回调(时间, 级别, 文本)，用于刷新 UI
        self.session = None         # 当前会话信息 dict（用于导出抬头）
        self.file_path = None       # 实时落盘文件
        self._file = None
        if file_path:
            self.open_file(file_path)

    # ---- 实时落盘 ----
    def open_file(self, path):
        """开启实时落盘（写入会话抬头）。"""
        self.close_file()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._file = open(path, "w", encoding="utf-8")
        self.file_path = path
        self._file.write(self._header_text())
        self._file.flush()
        return path

    def close_file(self):
        if self._file:
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                pass
            self._file = None

    def _header_text(self):
        lines = ["=" * 60, "📝 运行日志", "=" * 60]
        for key, value in (self.session or {}).items():
            lines.append(f"{key}：{value}")
        lines.append("")
        return "\n".join(lines) + "\n"

    def log(self, msg, level="INFO"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        text = str(msg)
        with self._lock:
            self._records.append((ts, level, text))
            if self._file:
                try:
                    self._file.write(f"[{ts}] [{level}] {text}\n")
                    self._file.flush()
                except Exception:
                    pass    # 落盘失败不影响检测主流程
        if self.on_emit:
            self.on_emit(ts, level, text)

    def clear(self):
        with self._lock:
            self._records.clear()

    def snapshot(self):
        with self._lock:
            return list(self._records)

    def __len__(self):
        with self._lock:
            return len(self._records)

    def to_text(self, extra_header=None):
        """导出为纯文本（含会话抬头与统计）。"""
        lines = []
        if self.session:
            lines.append("=" * 60)
            lines.append(f"📝 运行日志 · {self.session.get('mode', '检测')}")
            lines.append("=" * 60)
            for key, value in self.session.items():
                if key != 'mode':
                    lines.append(f"{key}：{value}")
            lines.append("")
        if extra_header:
            lines.append(extra_header)
            lines.append("")
        lines.extend(f"[{ts}] [{level}] {msg}" for ts, level, msg in self.snapshot())
        return "\n".join(lines) + "\n"

    def export(self, path, extra_header=None):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_text(extra_header))
        return path

    @staticmethod
    def new_session_path(mode):
        """生成 outputdata/运行日志/运行日志_<模式>_<时间>.txt。"""
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(OUTPUT_DIR, "运行日志", f"运行日志_{mode}_{stamp}.txt")


class ReportRenderer:
    """结构化检测数据 → 文本/CSV 的统一渲染层。

    所有报告出口（单文件报告、UID 异常详情、批量 CSV）都集中在此，
    避免各处手工拼字符串、再由下游 split 反解（结构信息在拼接中丢失）。
    """

    @staticmethod
    def _status_tag(status):
        return (status or 'pass').upper()

    @staticmethod
    def _vip_text(vip_level):
        """VIP 展示文本：有效等级 → 'VIPn'（项目内既有风格），未知/缺失 → '无'。"""
        try:
            level = int(vip_level)
        except (TypeError, ValueError):
            return '无'
        return f"VIP{level}" if level >= 0 else '无'

    # ---- 单文件检测报告 ----
    @staticmethod
    def render_single_report(meta, results):
        lines = [
            f"检测文件：{meta.get('file_path', '')}",
            f"检测时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"UID：{meta.get('uid', '')}",
            f"🔢 理论UID_Index：{meta.get('theory_uid_index', '无')}",
            f"🔢 实际UID_Index：{meta.get('actual_uid_index', '无')}",
        ]
        if meta.get('index_mismatch'):
            lines.append(f"⚠️ index 异常：理论 {meta.get('theory_uid_index')} / "
                         f"实际 {meta.get('actual_uid_index')} 不一致")
        lines.extend(["", "=" * 50, ""])
        for res in results:
            if isinstance(res, dict):
                lines.append(f"【{res.get('title', '检测项')}】"
                             f"[{ReportRenderer._status_tag(res.get('status'))}]")
                lines.append(str(res.get('msg', '')))
                lines.append("")
        return "\n".join(lines)

    # ---- 单个存档条目文本（UID 详情文件用） ----
    @staticmethod
    def render_uid_detail(uid, items, vip_level=None):
        """items: [{fname,theory,actual,name,cost,uid_cost,uid_file_count,
                   status,reason,index_mismatch,index_tag,detail_lines}]
        vip_level: 该账号最高 VIP 等级（同UID多档取最高），<0 或 None 表示无。
        """
        uid_indexes = sorted({it['theory'] for it in items if it['theory'] != '无'})
        total_cost = sum(it['cost'] for it in items)
        # 账号合并消费：同一 UID 下全部存档（含未异常存档）消费之和
        uid_total_cost = max(it.get('uid_cost', it['cost']) for it in items)
        uid_file_count = max(it.get('uid_file_count', 1) for it in items)
        uid_status = 'FAIL' if any(it['status'] == 'fail' for it in items) else 'WARN'
        mismatch_items = [it for it in items if it['index_mismatch']]
        banned_slots = sorted({it['ban_tag'] for it in items if it.get('ban_tag')})

        lines = ["=" * 60,
                 "📄 存档异常详情报告（同一UID汇总）",
                 "=" * 60,
                 "",
                 f"🆔 UID：{uid}",
                 f"👑 VIP：{ReportRenderer._vip_text(vip_level)}",
                 f"📁 UID_Index：{', '.join(uid_indexes) if uid_indexes else '无'}",
                 f"📂 异常存档数：{len(items)} 个",
                 f"🔍 检测结果：{uid_status}",
                 f"💰 账号合并消费(该UID全部 {uid_file_count} 个存档)：{uid_total_cost}",
                 f"💰 异常存档消费合计：{total_cost}",
                 "📄 涉及文件：" + "、".join(it['fname'] for it in items),
                 ""]
        if banned_slots:
            lines.append("🚨 【封禁槽位】" + "；".join(banned_slots))
            lines.append("")

        # index 异常单独指出
        if mismatch_items:
            lines.append("🔢 【index 异常单独指出】")
            for it in mismatch_items:
                extra_name = f" | Name：{it['name']}" if it['name'] else ""
                lines.append(f"   • {it['fname']} | {it['index_tag']}{extra_name}")
        else:
            lines.append("🔢 【index 异常单独指出】：未发现 index 不一致")
        lines.append("")

        for it in sorted(items, key=lambda x: x['theory']):
            lines.append("-" * 60)
            lines.append(f"📄 原始文件：{it['fname']}")
            lines.append(f"📁 理论UID_Index：{it['theory']}")
            lines.append(f"📄 实际UID_Index：{it['actual']}")
            if it['name']:
                lines.append(f"📛 Name：{it['name']}")
            lines.append(f"💰 本存档消费：{it['cost']}（该UID账号合并消费：{uid_total_cost}）")
            lines.append(f"🔍 检测结果：{it['status'].upper()}")
            if it.get('ban_tag'):
                lines.append(f"🚨 封禁情况：{it['ban_tag']}")
            if it['index_mismatch']:
                lines.append(f"🔢 index 异常：{it['index_tag']}")
            lines.append(f"📝 异常摘要：{it['reason']}")
            lines.append("")
            lines.append("📋 详细检测日志:")
            lines.append("")
            lines.append("\n".join(it['detail_lines']) if it['detail_lines'] else "（无详细日志）")
            lines.append("")

        return "\n".join(lines)

    # ---- 批量 CSV ----
    @staticmethod
    def build_batch_csv_rows(uid_rows):
        """uid_rows: [{uid,indexes,index_display,name,vip_level,status,reason,
                       multi,items,inactive_bans}] → CSV 行列表

        列顺序：UID_Index | Name | VIP | 状态 | 涉及存档数 | 封禁槽位 | 异常摘要
        UID_Index 列采用 uid_index_name 格式（每个存档自带名称，与 Name 列一一对应）。
        """
        rows = [['UID_Index', 'Name', 'VIP', '状态', '涉及存档数', '封禁槽位', '异常摘要']]
        for row in uid_rows:
            detail = (row.get('reason') or '').replace('\n', ' ').replace('\r', ' ').replace(',', '，')
            if len(detail) > 500:
                detail = detail[:500] + "..."
            items = row.get('items') or []
            # 封禁列：本次检测到的封禁存档 + 未参与检测的封禁槽位（服务器未返回内容）
            ban_tags = {it['ban_tag'] for it in items if it.get('ban_tag')}
            ban_tags.update(row.get('inactive_bans') or [])
            rows.append([
                row.get('index_display') or '无',
                row.get('name') or '无',
                ReportRenderer._vip_text(row.get('vip_level')),
                row.get('status') or 'warn',
                len(items),
                "；".join(sorted(ban_tags)) or '无',
                detail,
            ])
        return rows


# ========================================================
# 🆕 CSV 封禁检测函数（全局递归加载所有CSV）
# ========================================================
class SlotBanCache:
    """从下载工具产物 *_details.csv 加载永久/临时封禁信息。
    兼容表头：新版(存档/标题/状态/封禁状态) 与 旧版(槽位/名称/状态)

    封禁是**槽位级**的（如账号仅存档1被封），因此缓存按 {uid: {槽位: 原因}} 保存：
    否则按 UID 匹配会把整账号每个存档都标成封禁，导致同一封禁被重复写入日志/报告。
    """

    def __init__(self):
        self.ban_cache = defaultdict(dict)  # {uid: {slot_index: reason}}

    def load_all_csv_from_root(self, root_folder):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🔍 扫描CSV: {root_folder}")
        csv_count = 0
        for dirpath, _, filenames in os.walk(root_folder):
            for f in filenames:
                if f.lower().endswith("_details.csv"):
                    self._load_single_csv(os.path.join(dirpath, f))
                    csv_count += 1
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ CSV加载完成: {csv_count} 个")

    def _load_single_csv(self, csv_path):
        try:
            csv_filename = os.path.basename(csv_path)
            uid = csv_filename.replace("_details.csv", "").replace("_DETAILS.CSV", "")
            with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 兼容列名
                    slot = str(row.get("存档") or row.get("槽位") or "").strip()
                    state = str(row.get("状态") or "").strip()
                    title = str(row.get("标题") or row.get("名称") or "").strip() or "无名称"
                    ban_state = str(row.get("封禁状态") or "").strip()
                    if not slot:
                        continue
                    try:
                        idx = str(int(float(slot)))
                    except Exception:
                        continue

                    reason = None
                    combined_state = state + ban_state
                    if "永久封禁" in combined_state:
                        reason = f"永久封禁 | 存档{idx} | {title}"
                    elif "临时封禁" in combined_state:
                        reason = f"临时封禁 | 存档{idx} | {title}"

                    if reason:
                        # 同一槽位重复出现时覆盖，避免重复 CSV 累积同一封禁
                        self.ban_cache[uid][idx] = reason
        except Exception:
            pass

    @staticmethod
    def _uid_and_slot(fname):
        """从文件名解析 (uid, slot)，如 1360683320_1_xxx.xml → ('1360683320', '1')。"""
        match = re.match(r"^(\d+)_(\d+)(?:_|\.)", str(fname))
        if not match:
            return None, None
        return match.group(1), str(int(match.group(2)))

    def get_account_ban_reason(self, uid):
        """账号级封禁信息（该账号全部被封槽位，按槽位排序，已去重）。"""
        slots = self.ban_cache.get(str(uid))
        if not slots:
            return None
        ordered = sorted(slots, key=lambda x: int(x))
        return "；".join(dict.fromkeys(slots[k] for k in ordered))

    def get_slot_ban_reason(self, fname):
        """槽位级封禁：仅当该文件**自身槽位**被封禁时返回，否则 None。

        批量检测用。旧逻辑按 UID 匹配会把同账号其它正常存档也标成封禁，
        造成同一封禁被重复写入日志与报告。
        """
        uid, slot = self._uid_and_slot(fname)
        if uid is None:
            return None
        slots = self.ban_cache.get(uid)
        if not slots:
            return None
        return slots.get(slot)

    def get_ban_reason(self, fname):
        """账号级封禁信息（单文件检测用：一次检测只输出一次，不会重复）。"""
        uid, _ = self._uid_and_slot(fname)
        if uid is None:
            return None
        return self.get_account_ban_reason(uid)

    def get_inactive_bans(self, uid, fnames=None):
        """该账号被封但**没有对应 XML 文件**的槽位（服务器不返回内容，无法参与检测）。

        返回文本列表；已包含在 fnames 中的槽位不会重复列出。
        """
        slots = self.ban_cache.get(str(uid))
        if not slots:
            return []
        present = set()
        for fn in (fnames or []):
            _, slot = self._uid_and_slot(fn)
            if slot is not None:
                present.add(slot)
        return [f"存档{slot} - {slots[slot]}"
                for slot in sorted(slots, key=lambda x: int(x)) if slot not in present]


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
        if not os.path.exists(bin_path):
            return None
        try:
            with open(bin_path, 'rb') as f:
                file_data = f.read()
            if len(file_data) < 48:
                return None
            iv = file_data[:16]
            signature = file_data[-32:]
            ciphertext = file_data[16:-32]
            body_to_verify = iv + ciphertext
            expected_signature = hmac.new(sign_key_bytes, body_to_verify, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected_signature):
                return None
            cipher = AES.new(secret_key_bytes, AES.MODE_CBC, iv)
            try:
                decrypted_padded = cipher.decrypt(ciphertext)
                decrypted_data = unpad(decrypted_padded, AES.block_size)
            except ValueError:
                return None
            csv_content, _ = DetectionEngine._decode_decrypted_data(decrypted_data)
            if csv_content is None:
                return None
            lines = csv_content.splitlines()
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                if i == 0 and not line[0].isdigit():
                    continue
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
        if not os.path.exists(bin_path):
            return None
        try:
            with open(bin_path, 'rb') as f:
                file_data = f.read()
            if len(file_data) < 48:
                return None
            iv = file_data[:16]
            signature = file_data[-32:]
            ciphertext = file_data[16:-32]
            body_to_verify = iv + ciphertext
            expected_signature = hmac.new(ITEM_SIGN_KEY, body_to_verify, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected_signature):
                return None
            try:
                cipher = AES.new(ITEM_SECRET_KEY, AES.MODE_CBC, iv)
                decrypted_padded = cipher.decrypt(ciphertext)
                decrypted_data = unpad(decrypted_padded, AES.block_size)
            except ValueError:
                return None
            csv_content, _ = DetectionEngine._decode_decrypted_data(decrypted_data)
            if csv_content is None:
                return None
            price_map = {}
            lines = csv_content.splitlines()
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
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
                            if not cname:
                                cname = None
                        price_map[pid] = {'price': price, 'cname': cname}
                    except ValueError:
                        continue
            return price_map
        except Exception:
            return None

    @staticmethod
    def check_pay_xml(file_path, bin_path, max_details=10, min_money_details=500,
                      min_number_details=500, export_full=False):
        """金币消费检测：列出全部消费明细，并对单价/次数超阈值项预警。
        返回 dict: {title,status,msg,total_cost}"""
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
            return {'title': '金币消费检测', 'status': 'fail',
                    'msg': f"❌ 错误：无法读取或解密价格表文件。\n路径：{bin_path}\n(文件不存在或格式错误)",
                    'total_cost': 0}
        if not price_map:
            return {'title': '金币消费检测', 'status': 'warn',
                    'msg': "⚠️ 价格表为空，跳过消费计算。", 'total_cost': 0}

        total_cost = 0
        pay_items = []
        high_value_items = []
        high_freq_items = []
        has_warning = False

        try:
            root, _, _ = smart_load_xml(file_path)
            if root is None:
                return {'title': '金币消费检测', 'status': 'fail',
                        'msg': "❌ XML 文件严重损坏，无法解析支付节点。", 'total_cost': 0}

            pay_node = root.find('.//s[@name="pay"]')
            if pay_node is None:
                return {'title': '金币消费检测', 'status': 'warn',
                        'msg': "⚠️ 未找到 <pay> 节点", 'total_cost': 0}

            obj_node = pay_node.find('.//s[@name="obj"]')
            if obj_node is None:
                return {'title': '金币消费检测', 'status': 'warn',
                        'msg': "⚠️ <pay> 节点下未找到 <obj> 子节点", 'total_cost': 0}

            for item in obj_node.findall('s'):
                try:
                    prop_id = int(item.get('name'))
                    count = int(item.text.strip())
                    raw_data = price_map.get(prop_id, 0)

                    if isinstance(raw_data, dict):
                        price = raw_data.get('price', 0)
                        cname = raw_data.get('cname') or f"物品ID:{prop_id}"
                    else:
                        price = raw_data
                        cname = f"物品ID:{prop_id}"

                    cost = price * count
                    total_cost += cost
                    pay_items.append(f"- {cname} 单价:{price}, 次数:{count}, 小计:{cost}")

                    if price > min_money_details:
                        high_value_items.append(f"- {cname} 单价:{price}, 次数:{count}, 小计:{cost}")
                        has_warning = True

                    if count > min_number_details:
                        high_freq_items.append(f"- {cname} 单价:{price}, 次数:{count}, 小计:{cost}")
                        has_warning = True

                except (ValueError, TypeError):
                    continue

            # 构建返回消息
            msg_lines = []
            status = 'pass' if not has_warning else 'warn'

            if not has_warning:
                msg_lines.append("✅ 未发现高价值或高频购买行为")
            msg_lines.append(f"💰 估算存档消费：{total_cost} 黄金")

            pay_count = len(pay_items)
            hv_count = len(high_value_items)
            hf_count = len(high_freq_items)

            if export_full:
                hv_limit, hf_limit = hv_count, hf_count
            else:
                hv_limit = min(hv_count, max_details) if max_details > 0 else hv_count
                hf_limit = min(hf_count, max_details) if max_details > 0 else hf_count

            if pay_items:
                msg_lines.append("")
                for line in pay_items:
                    msg_lines.append(f" {line}")

            if high_value_items:
                msg_lines.append(f"\n⚠️ 高价物品 (单价>{min_money_details}) 共{hv_count}项:")
                for line in high_value_items[:hv_limit]:
                    msg_lines.append(f" {line}")
                if not export_full and max_details > 0 and hv_count > max_details:
                    msg_lines.append(f" ... 还有 {hv_count - max_details} 项 (已隐藏)")

            if high_freq_items:
                msg_lines.append(f"\n🚨 高频购买 (次数>{min_number_details}) 共{hf_count}项:")
                for line in high_freq_items[:hf_limit]:
                    msg_lines.append(f" {line}")
                if not export_full and max_details > 0 and hf_count > max_details:
                    msg_lines.append(f" ... 还有 {hf_count - max_details} 项 (已隐藏)")

            return {'title': '金币消费检测', 'status': status,
                    'msg': "\n".join(msg_lines), 'total_cost': total_cost}

        except (ValueError, AttributeError, TypeError, xml.etree.ElementTree.ParseError) as e:
            return {'title': '金币消费检测', 'status': 'fail',
                    'msg': f"解析错误：{str(e)}", 'total_cost': 0}

    @staticmethod
    def extract_vip_level(file_path):
        """读取存档内 VIP 等级。解析失败或缺失返回 -1。"""
        try:
            root, _, _ = smart_load_xml(file_path)
            if root is None:
                return -1
        except Exception:
            return -1
        vip_node = root.find('.//s[@name="vip"]')
        if vip_node is None:
            return -1
        level_elem = vip_node.find('.//s[@name="level"]')
        if level_elem is None or not level_elem.text:
            return -1
        try:
            return int(level_elem.text.strip())
        except ValueError:
            return -1

    @staticmethod
    def check_vip_pay_union(file_path, pay_cost, vip_level_override=None):
        """VIP 联合消费检测：以该账号累计消费估算判断。
        修复 β 中 pay_cost+5 优先级 bug；保留“可能出现覆盖存档”预警。
        若 vip_level_override 提供（同UID多档取最高VIP），则用之代替当前文件自身 VIP。
        返回 dict: {title,status,msg}"""
        vip_map = {10: 0, 100: 1, 200: 2, 500: 3, 1000: 4, 2000: 5, 5000: 6,
                   8000: 7, 10000: 8, 20000: 9, 50000: 10}
        vip_map2 = {100: 0, 200: 1, 500: 2, 1000: 3, 2000: 4, 5000: 5, 8000: 6,
                    10000: 7, 20000: 8, 50000: 9, 100000: 10}
        if pay_cost is None or pay_cost <= 0:
            return {'title': 'VIP金币消费', 'status': 'pass',
                    'msg': 'ℹ️ 无有效消费金额，跳过联合检测。'}
        level_to_limit1 = {v: k for k, v in vip_map.items()}
        level_to_limit2 = {v: k for k, v in vip_map2.items()}

        # 优先使用外部传入的同UID最高VIP；否则解析当前文件自身 VIP
        if vip_level_override is not None and vip_level_override >= 0:
            vip_level = vip_level_override
        else:
            vip_level = DetectionEngine.extract_vip_level(file_path)

        if vip_level < 0:
            return {'title': 'VIP金币消费', 'status': 'pass',
                    'msg': 'ℹ️ 未检测到有效 VIP 等级。'}
        limit_amount1 = level_to_limit1.get(vip_level)
        limit_amount2 = level_to_limit2.get(vip_level)

        if limit_amount2 is None or limit_amount2 == 0:
            return {'title': 'VIP金币消费', 'status': 'pass',
                    'msg': f'ℹ️ VIP 等级 {vip_level} 不在对照表中或额度为 0。'}

        # 修复：原β中 pay_cost+5/limit_amount1 因运算符优先级被解析为 pay_cost+(5/limit)
        ratio1 = (pay_cost + 5) / limit_amount1
        ratio2 = pay_cost / limit_amount2

        msg_lines = []
        status = 'pass'
        if ratio2 > 1.0 and vip_level < 10:
            status = 'fail'
            msg_lines.append(f"VIP{vip_level}实际消耗：{pay_cost} 黄金，已超该等级额度上限")
        elif ratio2 > 1.0 and vip_level == 10:
            status = 'warn'
            msg_lines.append(f"VIP{vip_level}实际消耗：{pay_cost} 黄金，已超通常统计上限")
        elif limit_amount1 and ratio1 < 0.3:
            status = 'warn'
            msg_lines.append(f"VIP{vip_level}消耗：{pay_cost} 黄金 (参考额度 {limit_amount1})\n可能出现覆盖存档")
        else:
            msg_lines.append(f"✅ VIP{vip_level} 消耗：{pay_cost} 黄金，消耗正常。")
        return {'title': 'VIP金币消费', 'status': status, 'msg': '\n'.join(msg_lines)}

    @staticmethod
    def check_vip_xml(file_path):
        """VIP 权限越界检测。返回 {title,status,msg}"""
        try:
            vip_errors = []
            vip_level = -1
            vip_map = {100: 1, 200: 2, 500: 3, 1000: 4, 2000: 5, 5000: 6,
                       8000: 7, 10000: 8, 20000: 9, 50000: 10}
            valid_m_keys = set(vip_map.keys())
            target_obj_names = ["obj", "nO", "upLevelObj"]

            root, _, _ = smart_load_xml(file_path)
            if root is None:
                return {'title': 'VIP权限检测', 'status': 'fail',
                        'msg': "❌ XML 文件严重损坏，无法解析 VIP 节点。"}
            all_vip_nodes = root.findall('.//s[@name="vip"]')
            valid_vip_nodes = [node for node in all_vip_nodes
                               if node.find('.//s[@name="level"]') is not None]
            if len(valid_vip_nodes) > 1:
                return {'title': 'VIP权限检测', 'status': 'fail',
                        'msg': f"❌ 异常：存在多个 vip 节点 ({len(valid_vip_nodes)}个)"}
            if not valid_vip_nodes:
                return {'title': 'VIP权限检测', 'status': 'warn',
                        'msg': "⚠️ 未找到有效 VIP 节点"}

            current_vip_node = valid_vip_nodes[0]
            level_elem = current_vip_node.find('.//s[@name="level"]')
            try:
                vip_level = int(level_elem.text.strip())
            except Exception:
                return {'title': 'VIP权限检测', 'status': 'fail',
                        'msg': "❌ 无法读取 level 数值"}

            if vip_level < 0 or vip_level > 10:
                vip_errors.append(f"VIP 等级数值异常：{vip_level}")

            all_enabled_items = []
            for obj_name in target_obj_names:
                obj_node = current_vip_node.find(f'.//s[@name="{obj_name}"]')
                count = 0
                if obj_node is not None:
                    for item in obj_node.findall('s'):
                        name_attr = item.get('name')
                        text_val = item.text
                        if name_attr and name_attr.startswith('m') and text_val \
                                and text_val.lower().strip() == 'true':
                            try:
                                m_val = int(name_attr[1:])
                                count += 1
                                all_enabled_items.append((m_val, obj_name))
                            except ValueError:
                                pass
                if count > vip_level:
                    vip_errors.append(f"类别 [{obj_name}] 溢出：开启{count}项 > VIP{vip_level}")

            for m_val, source in all_enabled_items:
                if m_val not in valid_m_keys:
                    vip_errors.append(f"非法数值：[{source}] 中发现未定义权限 m{m_val}")
                else:
                    required_level = vip_map[m_val]
                    if required_level > vip_level:
                        vip_errors.append(f"权限越界：[{source}]  VIP{vip_level} 开启了 (m{m_val})")

            if vip_errors:
                return {'title': 'VIP权限检测', 'status': 'fail',
                        'msg': "❌ VIP权限越界\n" + ''.join(vip_errors)}
            return {'title': 'VIP权限检测', 'status': 'pass',
                    'msg': f'VIP:{vip_level}\n无权限异常'}
        except Exception as e:
            return {'title': 'VIP权限检测', 'status': 'fail',
                    'msg': f"解析异常：{str(e)}"}

    @staticmethod
    def check_cheat_stream(file_path, check_flag=True, check_reason=True):
        """作弊标记/原因检测（α 智能联动逻辑）。
        返回 {cheat_found, details:[{title,status,msg},...]}"""
        try:
            cheat_found = False
            flag_node_found = False
            flag_value = None
            reason_content = None
            re_flag = re.compile(r'name=["\']isZuobiB["\'][^>]*>(.*?)</[^>]+>', re.IGNORECASE | re.DOTALL)
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

            def _title(flag=True):
                return "作弊标记检测" if flag else "作弊原因检测"

            if check_flag and check_reason:
                has_reason = bool(reason_content and reason_content.strip())
                is_flag_true = flag_node_found and flag_value != "false"

                if is_flag_true:
                    cheat_found = True
                    if has_reason:
                        display = reason_content.strip().replace('\n', ' ').replace('\r', ' ')[:200]
                        return {'cheat_found': True, 'details': [{
                            'title': "作弊检测", 'status': 'fail',
                            'msg': f"❌ 发现作弊标记，作弊原因：{display}"}]}
                    return {'cheat_found': True, 'details': [{
                        'title': "作弊检测", 'status': 'fail',
                        'msg': f"❌ 发现作弊标记 (值：{flag_value})，但无作弊原因"}]}

                if has_reason and not is_flag_true:
                    display = reason_content.strip().replace('\n', ' ').replace('\r', ' ')[:200]
                    return {'cheat_found': False, 'details': [{
                        'title': "作弊检测", 'status': 'warn',
                        'msg': f"⚠️ 发现作弊原因:{display}"}]}

                if flag_node_found and flag_value == "false":
                    return {'cheat_found': False, 'details': [{
                        'title': "作弊检测", 'status': 'pass', 'msg': "✅ 无作弊标记"}]}

                if not flag_node_found and not has_reason:
                    return {'cheat_found': False, 'details': [{
                        'title': "作弊检测", 'status': 'warn',
                        'msg': "⚠️ 未找到作弊标记节点"}]}

                if not flag_node_found and has_reason:
                    display = reason_content.strip().replace('\n', ' ').replace('\r', ' ')[:200]
                    return {'cheat_found': False, 'details': [{
                        'title': "作弊检测", 'status': 'warn',
                        'msg': f"⚠️ 发现作弊原因但未找到作弊标记节点，请人工复核：{display}"}]}

                return {'cheat_found': False,
                        'details': [{'title': "作弊检测", 'status': 'pass', 'msg': "检测完成"}]}

            elif check_flag and not check_reason:
                if flag_node_found:
                    if flag_value == "false":
                        return {'cheat_found': False, 'details': [
                            {'title': _title(), 'status': 'pass', 'msg': "✅ 正常"}]}
                    return {'cheat_found': True, 'details': [
                        {'title': _title(), 'status': 'fail',
                         'msg': f"❌ 发现作弊标记 (值：{flag_value})"}]}
                return {'cheat_found': False, 'details': [
                    {'title': _title(), 'status': 'warn', 'msg': "⚠️ 未找到节点"}]}

            elif not check_flag and check_reason:
                if reason_content and reason_content.strip():
                    display = reason_content.strip().replace('\n', ' ').replace('\r', ' ')[:200]
                    return {'cheat_found': True, 'details': [
                        {'title': _title(False), 'status': 'fail',
                         'msg': f"❌ 发现作弊原因:\n{display}"}]}
                return {'cheat_found': False, 'details': [
                    {'title': _title(False), 'status': 'pass', 'msg': "无作弊原因"}]}

            return {'cheat_found': False,
                    'details': [{'title': "作弊检测", 'status': 'pass', 'msg': "检测完成"}]}

        except Exception as e:
            return {'cheat_found': False,
                    'details': [{'title': "作弊检测", 'status': 'fail', 'msg': str(e)}]}

    @staticmethod
    def check_uid_md5_advanced(file_path):
        """UID 深度验证：文件名 UID/Index/Name 与文件内 un2/uu2/uidMd5 交叉匹配。
        返回：{title,status,msg,file_uid,file_index,file_name,file_uid_index,
               inner_uid,inner_index,inner_uid_index,md5_verified,match_status,target_md5}"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            tag_md5 = re.search(r'<s[^>]*name=["\']uidMd5["\'][^>]*>([^<]+)</s>',
                                content, re.IGNORECASE | re.DOTALL)
            tag_un2 = re.search(r'<s[^>]*name=["\']un2["\'][^>]*>([^<]+)</s>',
                                content, re.IGNORECASE | re.DOTALL)
            tag_uu2 = re.search(r'<s[^>]*name=["\']uu2["\'][^>]*>([^<]+)</s>',
                                content, re.IGNORECASE | re.DOTALL)

            target_md5 = None
            if tag_md5:
                target_md5 = tag_md5.group(1).strip().lower()
                if not target_md5:
                    target_md5 = None

            inner_uid = None
            if tag_un2 and tag_un2.group(1).strip().isdigit():
                inner_uid = tag_un2.group(1).strip()
            elif tag_uu2 and tag_uu2.group(1).strip().isdigit():
                inner_uid = tag_uu2.group(1).strip()

            fname = os.path.basename(file_path)
            fname_without_ext = fname.replace('.xml', '').replace('.XML', '')
            file_uid = file_index = file_name = None

            match_full = re.match(r"^(\d+)_(\d+)_(.+)$", fname_without_ext)
            if match_full:
                file_uid, file_index, file_name = match_full.groups()
            else:
                match_simple = re.match(r"^(\d+)_(\d+)$", fname_without_ext)
                if match_simple:
                    file_uid, file_index = match_simple.groups()

            FALLBACK_MD5_LIST = [
                "5e20663dadd1e483ac628951dd582ea8",
                "174882033225436b1440b7de44686450",
                "8de55a2e5745f73de25402626a4c3d61",
                "856e4980d5eb3351797f528948f684e5",
                "8efc299ca974ee46c0bc622cd51b4dc7",
                "ade82d56fe033105b37cc8ef1783cd93",
                "8868fae7afbf71557a2e4faceeb9d9d6",
                "66bc78dc545e1a7b7ac07302c82067f1"
            ]

            inner_index = None
            md5_verified = False
            match_status = 'none'

            # 保底 MD5 匹配
            if target_md5:
                for idx, fallback_md5 in enumerate(FALLBACK_MD5_LIST):
                    if target_md5 == fallback_md5.lower():
                        inner_index = str(idx)
                        md5_verified = True
                        match_status = 'fallback'
                        break

            # 用 inner_uid 验证 index
            if not md5_verified and inner_uid and target_md5:
                for idx in range(8):
                    test_str = f"{inner_uid}_{idx}"
                    calc_md5 = hashlib.md5(test_str.encode('utf-8')).hexdigest().lower()
                    if calc_md5 == target_md5:
                        inner_index = str(idx)
                        md5_verified = True
                        match_status = 'matched'
                        break

            # 用文件名 uid 验证
            if not md5_verified and file_uid and target_md5:
                for idx in range(8):
                    test_str = f"{file_uid}_{idx}"
                    calc_md5 = hashlib.md5(test_str.encode('utf-8')).hexdigest().lower()
                    if calc_md5 == target_md5:
                        inner_index = str(idx)
                        md5_verified = True
                        match_status = 'file_uid_match'
                        break

            # 构造文件内 UID_INDEX
            if inner_uid and inner_index is not None:
                inner_uid_index = f"{inner_uid}_{inner_index}"
            elif inner_uid:
                inner_uid_index = inner_uid
            elif file_uid and file_index:
                inner_uid_index = f"{file_uid}_{file_index}"
            else:
                inner_uid_index = None

            # 构造文件名 UID_INDEX
            file_uid_index = f"{file_uid}_{file_index}" if file_uid and file_index else None

            # 判断匹配状态
            if file_uid and inner_uid:
                if file_uid == inner_uid:
                    match_status = 'matched' if match_status not in ('fallback', 'file_uid_match') else match_status
                else:
                    match_status = 'mismatch'
            elif file_uid and not inner_uid:
                match_status = 'partial'
            elif not file_uid and inner_uid:
                match_status = 'partial'
            else:
                match_status = 'none'

            msg_lines = []
            status = 'pass'

            if match_status == 'matched':
                msg_lines.append("✅ UID 验证通过（文件名与文件内UID一致）")
                msg_lines.append(f"📁 文件名UID：{file_uid}")
                msg_lines.append(f"📄 文件内UID：{inner_uid}")
                msg_lines.append(f"🔢 Index：{inner_index if inner_index else file_index}")
            elif match_status == 'fallback':
                msg_lines.append("⚠️ 使用保底签名匹配")
                msg_lines.append(f"📁 文件名UID：{file_uid}")
                msg_lines.append(f"📄 文件内UID：{inner_uid}")
                msg_lines.append(f"🔢 Index：{inner_index}")
                status = 'warn'
            elif match_status == 'file_uid_match':
                msg_lines.append("✅ 使用文件名UID验证通过")
                msg_lines.append(f"📁 文件名UID：{file_uid}")
                msg_lines.append(f"📄 文件内UID：{inner_uid if inner_uid else '无'}")
                msg_lines.append(f"🔢 Index：{inner_index}")
                status = 'warn'
            elif match_status == 'mismatch':
                msg_lines.append("❌ 文件名UID与文件内UID不一致")
                msg_lines.append(f"📁 文件名UID：{file_uid}")
                msg_lines.append(f"📄 文件内UID：{inner_uid}")
                msg_lines.append(f"🔢 期望MD5：{target_md5 if target_md5 else '无'}")
                status = 'fail'
            elif match_status == 'partial':
                msg_lines.append("⚠️ 只有部分UID信息")
                if file_uid and not inner_uid:
                    msg_lines.append(f"📁 文件名UID：{file_uid} (文件内无un2/uu2)")
                    msg_lines.append(f"🔢 Index：{file_index}")
                elif not file_uid and inner_uid:
                    msg_lines.append(f"📄 文件内UID：{inner_uid} (文件名无法解析)")
                    msg_lines.append(f"🔢 期望MD5：{target_md5 if target_md5 else '无'}")
                status = 'warn'
            else:  # none
                msg_lines.append("❌ 无法获取任何UID信息")
                msg_lines.append(f"📁 文件名：{fname}")
                status = 'fail'

            return {
                'title': 'UID 验证',
                'status': status,
                'msg': '\n'.join(msg_lines),
                'file_uid': file_uid, 'file_index': file_index, 'file_name': file_name,
                'file_uid_index': file_uid_index,
                'inner_uid': inner_uid, 'inner_index': inner_index,
                'inner_uid_index': inner_uid_index,
                'md5_verified': md5_verified,
                'match_status': match_status,
                'target_md5': target_md5,
            }

        except Exception as e:
            return {
                'title': 'UID 验证', 'status': 'fail',
                'msg': f'❌ 检测异常：{str(e)}',
                'file_uid': None, 'file_index': None, 'file_name': None,
                'file_uid_index': None,
                'inner_uid': None, 'inner_index': None, 'inner_uid_index': None,
                'md5_verified': False, 'match_status': 'error', 'target_md5': None,
            }


# ========================================================
# 🖥️ GUI 主程序
# ========================================================
class AppDetector:
    def __init__(self, root):
        self.root = root
        self.root.title("数据检测工具 γ合并版 v3.0 | BY. 观星者")
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
        self.current_theory_uid_index = "无"
        self.current_actual_uid_index = "无"
        self.current_index_mismatch = False

        # 运行日志（线程安全缓冲；界面刷新经回调调度到主线程）
        self.logger = RunLogger(on_emit=self._on_log_emit)
        self._log_file = None        # 当前会话实时落盘文件（可选）

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._ensure_dirs()
        self._init_config()
        self._build_ui()

    # ---------- 基础 ----------
    def _on_closing(self):
        try:
            if hasattr(self, 'after_id'):
                self.root.after_cancel(self.after_id)
        except Exception:
            pass
        try:
            if self.logger:
                self.logger.close_file()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _start_log_session(self, mode, **info):
        """开启一次检测会话的运行日志（实时落盘，避免异常退出丢失）。"""
        session = {'mode': mode,
                   '开始时间': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        session.update(info)
        self.logger.clear()
        self.logger.session = session
        try:
            path = RunLogger.new_session_path(mode)
            self.logger.open_file(path)
            self._log_file = path
        except Exception as e:
            self._log_file = None
            self.log(f"⚠️ 运行日志落盘失败（不影响检测）：{e}", "WARN")
        return self._log_file

    def _finish_log_session(self, summary):
        """结束会话：把汇总写入日志并关闭文件。"""
        self.log(summary, "PASS")
        self.log(f"📝 本次运行日志：{self._log_file}", "INFO" if self._log_file else "WARN")
        self.logger.close_file()

    def _ensure_dirs(self):
        dirs = [INPUT_DIR, OUTPUT_DIR, TEST_DIR,
                os.path.join(OUTPUT_DIR, "异常详情"),
                os.path.join(OUTPUT_DIR, "运行日志")]
        for d in dirs:
            if not os.path.exists(d):
                os.makedirs(d)

    def _init_config(self):
        if not os.path.exists(CONFIG_FILE):
            self._create_default_config()
            return
        try:
            self.config.read(CONFIG_FILE, encoding='utf-8-sig')
            if 'Settings' not in self.config:
                self.config.add_section('Settings')
            if 'Security' not in self.config:
                self.config.add_section('Security')
            # 兼容旧版 temp_dir → work_dir
            if 'work_dir' not in self.config['Settings'] and 'temp_dir' in self.config['Settings']:
                self.config['Settings']['work_dir'] = self.config['Settings'].get('temp_dir', TEST_DIR)
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
        self.config['Security']['version'] = VERSION
        with open(CONFIG_FILE, 'w', encoding='utf-8-sig') as f:
            self.config.write(f)
        self.settings_modified = False
        if is_init:
            messagebox.showinfo("成功", "基础设置文件创建成功！\n程序即将自动重启以生效")
            self.root.destroy()
            run_tool()

    def _save_settings(self):
        self._set_str('bin_path', self.entry_bin_path.get().strip().replace('/', '\\'))
        self._set_str('work_dir', self.entry_work_dir.get().strip().replace('/', '\\'))
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
        except Exception:
            messagebox.showwarning("警告", "参数必须为数字")
        self._save_config()
        messagebox.showinfo("成功", "设置已保存！")

    def _get_bool(self, key, default=False):
        try:
            return self.config.getboolean('Settings', key)
        except Exception:
            return default

    def _set_bool(self, key, value):
        self.config.set('Settings', key, str(value))
        self.settings_modified = True

    def _get_str(self, key, default=''):
        try:
            return self.config.get('Settings', key)
        except Exception:
            return default

    def _set_str(self, key, value):
        self.config.set('Settings', key, value)
        self.settings_modified = True

    def _get_int(self, key, default=0):
        try:
            return int(self.config.get('Settings', key))
        except Exception:
            return default

    def _set_int(self, key, value):
        self.config.set('Settings', key, str(value))
        self.settings_modified = True

    def _mark_settings_modified(self, *args):
        self.settings_modified = True

    # ---------- 导航 UI ----------
    def _build_ui(self):
        nav_frame = tk.Frame(self.root, bg=self.COLOR_NAV_BG, relief="flat")
        nav_frame.place(x=0, y=0, width=self.WINDOW_W, height=self.NAV_H)

        btn_w = 80
        pages_info = [("home", "🏠 主页", self._show_home),
                      ("settings", "⚙️ 设置", self._show_settings),
                      ("thanks", "📜 致谢", self._show_thanks)]

        for i, (key, text, cmd) in enumerate(pages_info):
            btn = tk.Button(nav_frame, text=text,
                            bg=self.COLOR_NAV_ACTIVE if i == 0 else self.COLOR_NAV_BG,
                            fg="white", font=("Microsoft YaHei", 10), bd=0, command=cmd)
            btn.place(x=i * btn_w, y=0, width=btn_w, height=self.NAV_H)
            btn.bind("<Enter>", lambda e, b=btn: self._on_btn_enter(e, b))
            btn.bind("<Leave>", lambda e, b=btn: self._on_btn_leave(e, b))
            self.nav_buttons[key] = btn

        tk.Label(nav_frame, text=f"数据检测工具 {VERSION}", bg=self.COLOR_NAV_BG, fg="white",
                 font=("Microsoft YaHei", 12, "bold")).place(relx=0.8, y=0)

        self.page_container = tk.Frame(self.root, bg="#F0F0F0")
        self.page_container.place(x=0, y=self.NAV_H, width=self.WINDOW_W,
                                  height=self.WINDOW_H - self.NAV_H)
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
            response = messagebox.askyesnocancel("未保存的更改",
                                                 "⚠️ 您修改了设置但尚未保存。\n\n是否先保存设置再切换页面？")
            if response is None:
                return
            elif response:
                self._save_settings()
            else:
                self.settings_modified = False

        for name, frame in self.pages.items():
            if name == page_name:
                frame.place(x=0, y=0, width=self.WINDOW_W, height=self.WINDOW_H - self.NAV_H)
            else:
                frame.place_forget()

        for key, btn in self.nav_buttons.items():
            btn.config(bg=self.COLOR_NAV_ACTIVE if key == page_name else self.COLOR_NAV_BG)

    def _show_home(self):
        self._switch_page("home")

    def _show_settings(self):
        self._switch_page("settings")

    def _show_thanks(self):
        self._switch_page("thanks")

    # ---------- 主页 ----------
    def _build_home_page(self):
        frame = tk.Frame(self.page_container, bg="#F0F0F0")
        self.pages["home"] = frame

        current_bin_path = self._get_str('bin_path', DEFAULT_BIN_PATH)
        if not os.path.exists(current_bin_path):
            tk.Label(frame, text=f"⚠️ 警告：价格表 bin 文件路径无效，请注意甄别：{current_bin_path}",
                     font=("Microsoft YaHei", 10), bg="#FFEBEE", fg="#C62828",
                     padx=10, pady=5, justify="left").pack(fill="x", padx=40, pady=(10, 0))

        main_area_x, main_area_y = 20, 55
        total_width, total_height = 1100, 550
        left_width = int(total_width * 0.6)
        right_width = int(total_width * 0.4)

        left_frame = tk.Frame(frame, bg="#FFFFFF", relief="solid", borderwidth=1)
        left_frame.place(x=main_area_x, y=main_area_y, width=left_width, height=total_height)

        tk.Label(left_frame, text="🆔 UID 输入", font=("Microsoft YaHei", 12, "bold"),
                 bg="#FFFFFF", fg="#005159").place(x=20, y=15)
        self.entry_uid = tk.Entry(left_frame, width=65, font=("Consolas", 9), bd=1, relief="solid")
        self.entry_uid.place(x=20, y=55, width=left_width - 250, height=50)
        self.entry_uid.insert(0, "请输入 UID 或自动从文件名识别")
        self.entry_uid.config(fg="#999999")
        self.entry_uid.bind("<FocusIn>", lambda e: self._clear_placeholder(e, "请输入 UID 或自动从文件名识别"))
        self.entry_uid.bind("<FocusOut>", lambda e: self._set_placeholder(e, "请输入 UID 或自动从文件名识别"))
        tk.Button(left_frame, text="🔄 检测 uid", command=self._refresh_uid_from_filename,
                  bg="#005159", fg="white", font=("Microsoft YaHei", 10), bd=0
                  ).place(x=450, y=55, width=190, height=50)

        tk.Label(left_frame, text="📂 文件路径", font=("Microsoft YaHei", 12, "bold"),
                 bg="#FFFFFF", fg="#005159").place(x=20, y=110)
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
        tk.Button(left_frame, text="🔍 浏览", command=self._browse_file,
                  bg="#005159", fg="white", font=("Microsoft YaHei", 10), bd=0
                  ).place(x=left_width - 160, y=160, width=140, height=50)
        tk.Button(left_frame, text="🚀 立即开始检测", command=self._run_detection,
                  bg="#008984", fg="white", font=("Microsoft YaHei", 12, "bold"), bd=0
                  ).place(x=20, y=230, width=left_width - 40, height=50)

        btn_y_start, btn_h, btn_gap = 300, 60, 15
        tk.Button(left_frame, text="📂 批量检测文件夹（多线程）", command=self._batch_detect_folder,
                  bg="#d32f2f", fg="white", font=("Microsoft YaHei", 11, "bold"), bd=0
                  ).place(x=20, y=btn_y_start, width=left_width - 40, height=btn_h)

        btn_y_2 = btn_y_start + btn_h + btn_gap
        tk.Button(left_frame, text="📂 打开输出目录",
                  command=lambda: self._open_dir(OUTPUT_DIR), bg="#E0E0E0", fg="#333333",
                  font=("Microsoft YaHei", 10), bd=1, relief="solid"
                  ).place(x=20, y=btn_y_2, width=(left_width - 40) // 2 - 5, height=btn_h)
        tk.Button(left_frame, text="📄 输出检测报告", command=self._generate_report,
                  bg="#E0E0E0", fg="#333333", font=("Microsoft YaHei", 10), bd=1, relief="solid"
                  ).place(x=20 + (left_width - 40) // 2 + 5, y=btn_y_2,
                          width=(left_width - 40) // 2 - 5, height=btn_h)

        btn_y_3 = btn_y_2 + btn_h + btn_gap
        tk.Button(left_frame, text="📄 打开下载工具", command=self._run_info_get,
                  bg="#E0E0E0", fg="#EE0B0B", font=("Microsoft YaHei", 10), bd=1, relief="solid"
                  ).place(x=20, y=btn_y_3, width=(left_width - 40) // 2 - 5, height=btn_h)
        tk.Button(left_frame, text="📝 导出运行日志", command=self._export_run_log,
                  bg="#E0E0E0", fg="#333333", font=("Microsoft YaHei", 10), bd=1, relief="solid"
                  ).place(x=20 + (left_width - 40) // 2 + 5, y=btn_y_3,
                          width=(left_width - 40) // 2 - 5, height=btn_h)

        right_frame = tk.Frame(frame, bg="#F0F0F0")
        right_frame.place(x=main_area_x + left_width + 10, y=main_area_y,
                          width=right_width + 40, height=total_height)
        log_container = tk.Frame(right_frame, bg="#FFFFFF", relief="solid", borderwidth=1)
        log_container.pack(fill="both", expand=True, padx=0, pady=0)
        tk.Label(log_container, text="💻 实时运行日志", font=("Microsoft YaHei", 11, "bold"),
                 bg="#FFFFFF", fg=self.COLOR_NAV_BG).pack(anchor="w", padx=10, pady=5)
        log_frame = tk.Frame(log_container, bg="#FFFFFF")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

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
        """线程安全日志入口：任意线程可调用，内部转交 RunLogger。"""
        self.logger.log(msg, level)

    def _on_log_emit(self, ts, level, text):
        """RunLogger 回调（可能来自子线程）→ 调度到 Tk 主线程刷新界面。"""
        try:
            self.root.after(0, self._append_log_line, ts, level, text)
        except Exception:
            # 窗口已销毁（如程序退出中）时忽略，保证子线程不因此崩溃
            pass

    def _append_log_line(self, ts, level, text):
        log_str = f"[{ts}] [{level}] {text}\n"
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, log_str, level)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def clear_log(self):
        """清空界面与缓冲（线程安全：界面操作始终走主线程）。"""
        self.logger.clear()
        try:
            self.root.after(0, self._clear_log_widget)
        except Exception:
            pass

    def _clear_log_widget(self):
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

    def _export_run_log(self):
        """导出当前运行日志（含会话抬头）供留档。

        任务进行中日志文件已在实时落盘；此处于用户指定位置另存一份完整副本。
        """
        if len(self.logger) == 0:
            messagebox.showwarning("提示", "暂无运行日志可导出")
            return
        mode = (self.logger.session or {}).get('mode', '检测')
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"运行日志_{mode}_{stamp}.txt"
        path = filedialog.asksaveasfilename(
            title="导出运行日志", defaultextension=".txt",
            initialfile=default_name, filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self.logger.export(path)
        except Exception as e:
            messagebox.showerror("错误", f"导出失败：{e}")
            return
        self.log(f"📝 运行日志已导出：{path}", "INFO")
        messagebox.showinfo("完成", f"运行日志已导出：\n{path}")

    # ---------- 设置页 ----------
    def _build_settings_page(self):
        frame = tk.Frame(self.page_container, bg="#E0E0E0")
        self.pages["settings"] = frame

        tk.Label(frame, text="⚙️ 安全与检测设置", font=("Microsoft YaHei", 15, "bold"),
                 bg="#E0E0E0", fg="#333333").place(x=40, y=20)
        card = tk.Frame(frame, bg="#FFFFFF", relief="solid", borderwidth=1)
        card.place(x=40, y=70, width=1080, height=520)

        self.cb_restore_var = tk.BooleanVar(value=self._get_bool('auto_restore', True))
        self.cb_open_var = tk.BooleanVar(value=self._get_bool('auto_open_dir', False))
        self.cb_auto_uid_var = tk.BooleanVar(value=self._get_bool('auto_uid_from_filename', True))
        self.cb_export_full_var = tk.BooleanVar(value=self._get_bool('export_full_details', False))
        self.cb_batch_open_var = tk.BooleanVar(value=self._get_bool('auto_open_batch_report', False))
        all_vars = [self.cb_restore_var, self.cb_open_var, self.cb_auto_uid_var,
                    self.cb_export_full_var, self.cb_batch_open_var]
        for var in all_vars:
            var.trace_add("write", self._mark_settings_modified)

        y = 20
        tk.Label(card, text="📂 价格表文件路径:", bg="#FFFFFF", font=("Microsoft YaHei", 12, "bold"),
                 fg="#008984").place(x=30, y=y)
        y += 35
        self.entry_bin_path = tk.Entry(card, font=("Consolas", 10), bd=1, relief="solid")
        self.entry_bin_path.place(x=30, y=y, width=720, height=35)
        self.entry_bin_path.insert(0, self._get_str('bin_path', DEFAULT_BIN_PATH))
        self.entry_bin_path.bind("<KeyRelease>", self._mark_settings_modified)

        def browse_bin():
            fp = filedialog.askopenfilename(title="选择 bin 文件", initialdir=INPUT_DIR,
                                            filetypes=[("Bin Files", "*.bin"), ("All Files", "*.*")])
            if fp:
                self.entry_bin_path.delete(0, tk.END)
                self.entry_bin_path.insert(0, fp)
                self._mark_settings_modified()

        tk.Button(card, text="📂 浏览", command=browse_bin, bg="#005159", fg="white",
                  font=("Microsoft YaHei", 10), bd=0).place(x=760, y=y, width=120, height=35)

        y += 50
        tk.Label(card, text="📁 默认工作目录:", bg="#FFFFFF", font=("Microsoft YaHei", 12, "bold"),
                 fg="#00575F").place(x=30, y=y)
        y += 35
        self.entry_work_dir = tk.Entry(card, font=("Consolas", 10), bd=1, relief="solid")
        self.entry_work_dir.place(x=30, y=y, width=720, height=35)
        self.entry_work_dir.insert(0, self._get_str('work_dir', TEST_DIR))
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

        tk.Button(card, text="📂 浏览", command=browse_work_dir, bg="#005159", fg="white",
                  font=("Microsoft YaHei", 10), bd=0).place(x=760, y=y, width=120, height=35)

        y += 50
        tk.Label(card, text="🛠️ 功能选项", bg="#FFFFFF", font=("Microsoft YaHei", 11, "bold"),
                 fg="#00575F").place(x=30, y=y)
        y += 30
        tk.Checkbutton(card, text="自动恢复历史路径", variable=self.cb_restore_var,
                       bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=50, y=y)
        tk.Checkbutton(card, text="单文件报告自动打开", variable=self.cb_open_var,
                       bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=280, y=y)
        tk.Checkbutton(card, text="批量报告自动打开", variable=self.cb_batch_open_var,
                       bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=510, y=y)
        y += 35
        tk.Checkbutton(card, text="自动从文件名识别UID", variable=self.cb_auto_uid_var,
                       bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=50, y=y)
        tk.Checkbutton(card, text="批量导出完整细节", variable=self.cb_export_full_var,
                       bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=300, y=y)
        y += 50

        tk.Label(card, text="📊 检测参数配置", bg="#FFFFFF", font=("Microsoft YaHei", 11, "bold"),
                 fg="#00575F").place(x=30, y=y)
        y += 35

        def make_param_entry(x, ypos, key, default):
            """创建参数输入框(带数字校验)并返回"""
            ent = tk.Entry(card, font=("Consolas", 11), bd=1, relief="solid", justify="center")
            ent.place(x=x, y=ypos + 5, width=80, height=30)
            ent.insert(0, str(self._get_int(key, default)))
            ent.bind("<KeyRelease>", self._mark_settings_modified)
            return ent

        def validate_number(action, value_if_allowed):
            if action == '1':
                try:
                    int(value_if_allowed)
                    return True
                except ValueError:
                    return False
            return True

        vcmd = (self.root.register(validate_number), '%a', '%P')

        # 第一行：明细最大条数 | 最小金额明细
        tk.Label(card, text="明细最大条数:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=50, y=y)
        self.entry_max_details = make_param_entry(200, y, 'max_export_details', 10)
        tk.Label(card, text="最小金额明细:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=350, y=y)
        self.entry_min_money = make_param_entry(500, y, 'min_money_details', 500)

        # 第二行：最小数量明细 | 批量检测线程
        y += 35
        tk.Label(card, text="最小数量明细:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=50, y=y)
        self.entry_min_number = make_param_entry(200, y, 'min_number_details', 10)
        tk.Label(card, text="批量检测线程:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=350, y=y)
        self.entry_thread_count = make_param_entry(500, y, 'batch_thread_count', 5)

        # 第三行：提示
        y += 35
        tk.Label(card, text="输出条数0为无穷", bg="#FFFFFF", font=("Microsoft YaHei", 11, "bold")
                 ).place(x=50, y=y)

        for ent in (self.entry_max_details, self.entry_min_money,
                    self.entry_min_number, self.entry_thread_count):
            ent.config(validate='key', validatecommand=vcmd)

        btn_width, btn_x_start, btn_y = 160, 40, 610
        tk.Button(frame, text="💾 保存设置", command=self._save_settings, bg="#005159", fg="white",
                  font=("Microsoft YaHei", 11, "bold"), bd=0).place(x=btn_x_start, y=btn_y,
                                                                    width=btn_width, height=45)
        tk.Button(frame, text="🔄 恢复默认设置", command=self._reset_settings, bg="#999999",
                  fg="white", font=("Microsoft YaHei", 11), bd=0).place(x=btn_x_start + btn_width + 20,
                                                                        y=btn_y, width=btn_width + 20,
                                                                        height=45)

    # ---------- 致谢页 ----------
    def _build_thanks_page(self):
        frame = tk.Frame(self.page_container, bg="#F0F0F0")
        self.pages["thanks"] = frame
        text = f"""
本工具用于数据安全检测与异常分析
仅用于合法合规的项目调试与安全审计

γ合并版 v{VERSION} 说明：
• 合并 α 版（按文件批量导出明细）与 β 版（存档封禁 / UID一致性）
• VIP 权限越界检测
• 消费数据异常分析（含累计消费覆盖存档预警）
• 作弊标记自动识别
• 存档封禁状态自动检测
• 结果仅供参考，请自行判断\n因此产生不良后果与开发者无关

使用须知：
1. 请确保用于授权场景
2. 请勿用于非法用途
3. 问题反馈请联系开发者QQ:2434044637
"""
        tk.Label(frame, text=text, font=("Microsoft YaHei", 12), bg="#F0F0F0",
                 justify=tk.LEFT, anchor="w").pack(anchor="w", padx=30, pady=10)
        tk.Label(frame, text="2026.09", font=("Microsoft YaHei", 12), bg="#F0F0F0",
                 justify=tk.RIGHT).pack(side=tk.BOTTOM, anchor=tk.E, padx=30, pady=15)

    # ---------- 输入辅助 ----------
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
            if res and res.get('file_uid'):
                self.entry_uid.delete(0, tk.END)
                self.entry_uid.insert(0, res.get('file_uid'))
                self.entry_uid.config(fg="black")
        except Exception:
            pass

    def _browse_file(self):
        last_path = self._get_str('last_file_path', '')
        init_dir = os.path.dirname(last_path) if last_path and os.path.exists(os.path.dirname(last_path)) \
            else self._get_str('work_dir', TEST_DIR)
        file_path = filedialog.askopenfilename(
            title="选择数据文件", initialdir=init_dir,
            filetypes=[("XML/TXT Files", "*.xml *.txt"), ("All Files", "*.*")])
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
        except Exception:
            messagebox.showwarning("提示", "无法自动打开目录，请手动访问")

    # ---------- 下载工具 ----------
    def _run_info_get(self):
        try:
            import info_get
            t = threading.Thread(target=info_get.run_tool, daemon=True)
            t.start()
            self.log("下载工具已启动", "INFO")
        except ImportError:
            self.log("错误：找不到 info_get 模块，请确认已打包", "FAIL")
        except Exception as e:
            self.log(f"运行下载工具失败: {str(e)}", "FAIL")

    # ---------- 单文件检测 ----------
    def _run_detection(self):
        file_path = self.entry_file_path.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("错误", "文件路径无效或不存在")
            return
        self._set_str('last_file_path', file_path)
        self._save_config()
        threading.Thread(target=self._do_detect_work, daemon=True).start()

    def _detect_common_checks(self, file_path, bin_path, max_details, min_money, min_num,
                              export_full, total_cost_for_union=0, fname_for_ban=None):
        """单文件执行全部检测，返回 (results, 附加信息 dict)
        results: list of {title,status,msg,...}；附带 uid_res 供外部取字段
        """
        results = []
        extra = {}

        # 0. 存档封禁检测（若有 fname 且封禁缓存已加载）
        if fname_for_ban is not None:
            ban_reason = SLOT_BAN_CACHE.get_ban_reason(fname_for_ban)
            if ban_reason:
                results.append({"status": "fail", "title": "📄 存档封禁检测",
                                "msg": f"🚨 {ban_reason}"})
            else:
                results.append({"status": "pass", "title": "📄 存档封禁检测",
                                "msg": "✅ 未检测到存档封禁"})
            extra['ban_reason'] = ban_reason

        # 1. UID 验证（附带“理论/实际 index 是否一致”的单点异常提示）
        uid_res = DetectionEngine.check_uid_md5_advanced(file_path)
        theory_uid_index = uid_res.get('file_uid_index') or '无'
        actual_uid_index = uid_res.get('inner_uid_index') or '无'
        index_mismatch = (theory_uid_index != '无' and actual_uid_index != '无'
                          and theory_uid_index != actual_uid_index)
        if index_mismatch:
            uid_res = dict(uid_res)
            uid_res['msg'] = (uid_res.get('msg') or '') + \
                f"\n🔢 【index 异常】理论 {theory_uid_index} / 实际 {actual_uid_index} 不一致"
            if uid_res.get('status') == 'pass':
                uid_res['status'] = 'fail'
        results.append(uid_res)
        extra['uid_res'] = uid_res
        extra['theory_uid_index'] = theory_uid_index
        extra['actual_uid_index'] = actual_uid_index
        extra['index_mismatch'] = index_mismatch

        # 2. 作弊检测
        cheat_res = DetectionEngine.check_cheat_stream(file_path)
        results.extend(cheat_res['details'])
        extra['cheat_found'] = cheat_res.get('cheat_found', False)

        # 3. VIP 检测
        vip_res = DetectionEngine.check_vip_xml(file_path)
        results.append(vip_res)

        # 4. 消费检测
        pay_res = DetectionEngine.check_pay_xml(file_path, bin_path, max_details,
                                                min_money, min_num, export_full)
        results.append(pay_res)
        total_cost = pay_res.get("total_cost", 0)
        extra['total_cost'] = total_cost

        # 5. VIP 联合检测（若给定了累计消费则用累计，否则单文件自身消费）
        cost_for_union = total_cost_for_union if total_cost_for_union > 0 else total_cost
        union_res = DetectionEngine.check_vip_pay_union(file_path, cost_for_union)
        results.append(union_res)
        return results, extra

    @staticmethod
    def _overall_of(results):
        overall = 'pass'
        for r in results:
            if isinstance(r, dict) and r.get('status') == 'fail':
                return 'fail'
        for r in results:
            if isinstance(r, dict) and r.get('status') == 'warn':
                overall = 'warn'
        return overall

    def _do_detect_work(self):
        file_path = self.entry_file_path.get().strip()
        self._start_log_session('单文件检测', 检测文件=file_path)
        bin_path = self._get_str('bin_path', DEFAULT_BIN_PATH)
        max_details = self._get_int('max_export_details', 10)
        min_money = self._get_int('min_money_details', 500)
        min_num = self._get_int('min_number_details', 10)
        export_full = self._get_bool('export_full_details', False)
        fname = os.path.basename(file_path)

        # 单文件检测前，若所在目录有 _details.csv，则加载封禁（兼容β）
        folder = os.path.dirname(file_path)
        if not SLOT_BAN_CACHE.ban_cache:
            SLOT_BAN_CACHE.load_all_csv_from_root(folder)

        results, extra = self._detect_common_checks(file_path, bin_path, max_details,
                                                    min_money, min_num, export_full,
                                                    fname_for_ban=fname)
        uid_res = extra['uid_res']
        if uid_res.get('file_uid'):
            self.current_uid_info = uid_res.get('file_uid')
        else:
            self.current_uid_info = uid_res.get('inner_uid') or ""
        self.current_theory_uid_index = extra.get('theory_uid_index') or '无'
        self.current_actual_uid_index = extra.get('actual_uid_index') or '无'
        self.current_index_mismatch = bool(extra.get('index_mismatch'))

        for res in results:
            if isinstance(res, dict):
                title = res.get('title', '检测项')
                self.log(f"{title}：{res.get('msg')}", (res.get('status') or 'pass').upper())

        self.current_results = results
        self.current_file_path = file_path
        self._generate_report(auto_ok=True)
        overall = self._overall_of(results)
        self._finish_log_session(f"检测结束 | 状态:{overall.upper()} | 文件:{os.path.basename(file_path)}")

    # ---------- 报告 ----------
    def _generate_report(self, auto_ok=False):
        if not self.current_results:
            messagebox.showwarning("提示", "暂无检测结果可导出")
            return
        filename = os.path.basename(self.current_file_path)
        name = os.path.splitext(filename)[0]
        report_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(OUTPUT_DIR, f"检测报告_{name}_{report_time}.txt")

        meta = {
            'file_path': self.current_file_path,
            'uid': self.current_uid_info,
            'theory_uid_index': self.current_theory_uid_index,
            'actual_uid_index': self.current_actual_uid_index,
            'index_mismatch': self.current_index_mismatch,
        }
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(ReportRenderer.render_single_report(meta, self.current_results))

        if self._get_bool('auto_open_dir', False):
            self._open_dir(OUTPUT_DIR)
        if auto_ok:
            self.log(f"📄 检测报告已生成：{report_path}", "INFO")
        else:
            messagebox.showinfo("完成", f"报告已保存：\n{report_path}")

    # ---------- 异常详情汇总辅助 ----------
    @staticmethod
    def _collect_file_issues(res):
        """收集单个文件的详情日志与异常摘要。
        返回 (detail_lines, fail_msgs, warn_msgs)。"""
        detail_lines, fail_msgs, warn_msgs = [], [], []
        for item in res.get('results', []):
            if not isinstance(item, dict):
                continue
            title = item.get('title', '检测项')
            status = item.get('status', 'pass')
            msg = item.get('msg', '')
            if status not in ('fail', 'warn'):
                continue

            # 智能摘要
            short_msg = ""
            if title == '金币消费检测':
                for line in msg.split('\n'):
                    ls = line.strip()
                    if not ls:
                        continue
                    if (any(k in ls for k in ['✅', '⚠️', '🚨', '未发现', '高价物品', '高频购买', '💰'])
                            and not ls.startswith('-') and not ls.startswith(' ')):
                        short_msg = ls
                        break
                if not short_msg:
                    for line in msg.split('\n'):
                        ls = line.strip()
                        if ls and not ls.startswith('-') and not ls.startswith('='):
                            short_msg = ls
                            break
                if not short_msg:
                    short_msg = "消费检测发现高价值或高频购买行为" if ('⚠️' in msg or '🚨' in msg) \
                        else "消费检测完成"
            else:
                for line in msg.split('\n'):
                    ls = line.strip()
                    if ls:
                        short_msg = ls
                        break

            if not short_msg:
                short_msg = f"[{title}] 检测异常（详细请查看详情文件）"
            elif len(short_msg) > 150:
                short_msg = short_msg[:150] + "..."

            detail_lines.append(f"--- [{title}] ---")
            detail_lines.append(msg)
            detail_lines.append("")
            if status == 'fail':
                fail_msgs.append(short_msg)
            elif status == 'warn':
                warn_msgs.append(short_msg)
        return detail_lines, fail_msgs, warn_msgs

    @staticmethod
    def _index_tag(file_uid_index, inner_uid_index):
        """判断单个存档 index 是否异常，返回 (是否异常, 描述文本)。"""
        theory = file_uid_index or '无'
        actual = inner_uid_index or '无'
        if theory != '无' and actual != '无' and theory != actual:
            return True, f"理论 {theory} ≠ 实际 {actual}"
        return False, ""

    @staticmethod
    def _index_sort_key(uid_index):
        """按 uid_index（如 '1234567_10'）排序：先 UID 再 Index 数值，避免 '10' < '2' 的字典序问题。"""
        text = str(uid_index or '')
        m = re.match(r"^(\d+)_(\d+)$", text)
        if m:
            return (0, int(m.group(1)), int(m.group(2)))
        return (1, 0, 0)

    @staticmethod
    def _uid_index_name(uid_index, name):
        """拼装 uid_index_name 展示形式（无 name 时回退到纯 uid_index）。"""
        if not uid_index or uid_index == '无':
            return '无'
        return f"{uid_index}_{name}" if name else str(uid_index)

    @staticmethod
    def _write_uid_detail_file(uid, items, banned_slots=None, vip_level=None):
        """将同一 UID 下所有异常存档汇总为一份详情文件（渲染交 ReportRenderer）。"""
        detail_dir = os.path.join(OUTPUT_DIR, "异常详情")
        os.makedirs(detail_dir, exist_ok=True)
        for it in items:
            it.setdefault('ban_tag', '')
        text = ReportRenderer.render_uid_detail(uid, items, vip_level=vip_level)
        if banned_slots:
            note = ("\n" + "-" * 60 + "\n"
                    "ℹ️ 说明：以下槽位在下载结果中被标记封禁，因服务器不返回内容（无 XML 文件），\n"
                    "   故未参与本次存档检测，封禁信息仅记录如下：\n"
                    + "\n".join(f"   • {s}" for s in banned_slots) + "\n")
            text += note
        safe_uid = re.sub(r'[<>:"/\\|?*]', '_', str(uid))
        detail_path = os.path.join(detail_dir, f"{safe_uid}_异常详情.txt")
        with open(detail_path, "w", encoding="utf-8") as f:
            f.write(text)
        return detail_path

    # ---------- 批量检测 ----------
    def _batch_detect_folder(self):
        folder_path = filedialog.askdirectory(title="选择批量检测文件夹",
                                              initialdir=self._get_str('work_dir', TEST_DIR))
        if not folder_path:
            return
        self._set_str('work_dir', folder_path)
        threading.Thread(target=self._do_batch_detect, args=(folder_path,), daemon=True).start()

    def _do_batch_detect(self, folder_path):
        self._start_log_session('批量检测', 目标目录=folder_path)
        self.log(f"📂 开始批量检测：{folder_path}", "INFO")
        self.log("需要半分钟左右时间，请耐心等待", "INFO")

        # 加载封禁缓存（递归扫描所选目录下所有 _details.csv）
        SLOT_BAN_CACHE.ban_cache.clear()
        SLOT_BAN_CACHE.load_all_csv_from_root(folder_path)
        self.log("✅ 封禁缓存加载完成", "INFO")

        bin_path = self._get_str('bin_path', DEFAULT_BIN_PATH)
        max_details = self._get_int('max_export_details', 10)
        min_money = self._get_int('min_money_details', 500)
        min_num = self._get_int('min_number_details', 10)
        export_full = self._get_bool('export_full_details', False)
        thread_count = self._get_int('batch_thread_count', 5)

        file_list = []
        for root_dir, _, files in os.walk(folder_path):
            for f in files:
                if f.lower().endswith('.xml'):
                    file_list.append(os.path.join(root_dir, f))
        total = len(file_list)
        if total == 0:
            self.log("❌ 未找到任何 XML 文件", "FAIL")
            return

        # 预扫描：同一文件名UID（服务器UID）下多个存档若 VIP 不同，取最高 VIP
        # 作为该账号 VIP 联合消费判断的基准（避免用低档存档误判累计消费）
        uid_max_vip = {}
        for fp in file_list:
            m = re.match(r"^(\d+)_\d+(?:_|\.)", os.path.basename(fp), re.IGNORECASE)
            if not m:
                continue
            uid = m.group(1)
            vip = DetectionEngine.extract_vip_level(fp)
            if vip >= 0:
                prev = uid_max_vip.get(uid, -1)
                if vip > prev:
                    uid_max_vip[uid] = vip
        if uid_max_vip:
            self.log(f"👑 账号最高VIP预扫描完成：{len(uid_max_vip)} 个 UID", "INFO")

        file_result_map = {}

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            future_to_file = {}
            for fp in file_list:
                future = executor.submit(self._detect_single_file_batch, fp, bin_path,
                                         max_details, min_money, min_num, export_full)
                future_to_file[future] = fp

            for future in as_completed(future_to_file):
                fp = future_to_file[future]
                try:
                    file_result_map[fp] = future.result()
                except Exception as e:
                    self.log(f"❌ 处理失败：{fp} | {str(e)}", "FAIL")

        # 全部存档解析完成后，再按账号（同一 UID）合并各存档消费统计，
        # 并用合并值统一做 VIP 联合检测。
        # 注意：不能在线程内累加 —— 线程只处理单个存档，读到的是“部分累计值”，
        # 会把同一账号的消费拆散，且结果随线程调度变化。
        uid_total_cost = self._finalize_batch_results(file_result_map, uid_max_vip)
        self.log(f"💰 消费按UID合并统计完成：{len(uid_total_cost)} 个账号", "INFO")

        # 联合检测可能改变 overall，按最终结果统计并输出逐文件日志
        success = warn = fail = 0
        for fp in file_list:
            res = file_result_map.get(fp)
            if not res:
                fail += 1
                continue
            if res['overall'] == 'fail':
                fail += 1
            elif res['overall'] == 'warn':
                warn += 1
            else:
                success += 1
            # 日志以 uid_index_name 标识存档（index 与存档名一一对应）
            label = self._uid_index_name(res.get('file_uid_index') or '无', res.get('file_name'))
            self.log(f"文件:{label} | UID:{res.get('uid','')} | 状态:{res['overall'].upper()}",
                     res['overall'].upper())

        self.log("📝 开始生成异常详情文件...", "INFO")
        uid_group = {}                # {uid: [每个存档的异常信息]} 同一UID汇总

        # α 风格：按 UID 汇总输出详情（同一 UID 下多个 uid_index 合并为一份文件）
        for file_path, res in file_result_map.items():
            fname = os.path.basename(file_path)
            if res['overall'] not in ('fail', 'warn'):
                continue

            file_name = res.get('file_name', '')
            file_uid_index = res.get('file_uid_index', '')
            inner_uid_index = res.get('inner_uid_index', '')
            # 汇总 UID：优先服务器UID（文件名首段），其次文件内UID
            group_uid = res.get('uid') or res.get('file_uid') or res.get('inner_uid') or 'unknown'

            detail_lines, fail_msgs, warn_msgs = self._collect_file_issues(res)

            if fail_msgs:
                file_reason = "；".join(fail_msgs)
                file_status = 'fail'
            elif warn_msgs:
                file_reason = "；".join(warn_msgs)
                file_status = 'warn'
            else:
                continue

            index_mismatch, index_tag = self._index_tag(file_uid_index, inner_uid_index)

            uid_group.setdefault(group_uid, []).append({
                'fname': fname,
                'name': file_name or '',
                'theory': file_uid_index or '无',
                'actual': inner_uid_index or '无',
                'cost': res.get('total_cost', 0),
                'uid_cost': res.get('uid_total_cost', res.get('total_cost', 0)),
                'uid_file_count': res.get('uid_file_count', 1),
                'status': file_status,
                'reason': file_reason,
                'index_mismatch': index_mismatch,
                'index_tag': index_tag,
                'ban_tag': res.get('ban_tag', ''),
                'detail_lines': detail_lines,
            })

        # 逐 UID 输出：一份汇总详情文件 + 一行结构化 CSV 数据
        uid_rows = []
        for uid, items in uid_group.items():
            uid_fail = any(it['status'] == 'fail' for it in items)
            uid_indexes = sorted({it['theory'] for it in items if it['theory'] != '无'})
            # uid_index_name：按理论 index 排序，每项带上该存档名称（与 Name 列一一对应）
            indexed_items = sorted(items, key=lambda x: self._index_sort_key(x['theory']))
            display_parts = [self._uid_index_name(it['theory'], it.get('name'))
                             for it in indexed_items if it['theory'] != '无']
            display_parts = [p for p in display_parts if p != '无']
            display_indexes = ", ".join(display_parts) if display_parts else '无'
            multi = len(items) > 1

            # 异常 index 单独指出（理论UID_Index 与实际UID_Index 不一致的存档）
            reason_parts = []
            mismatch_parts = [f"{it['theory']}≠{it['actual']}"
                              for it in items if it['index_mismatch']]
            if mismatch_parts:
                reason_parts.append("🔢 index异常：" + "；".join(mismatch_parts))
            elif multi:
                reason_parts.append("🔢 各存档index均正常")

            for it in items:
                prefix = f"[{it['theory']}] " if multi else ""
                reason_parts.append(f"{prefix}{it['reason']}")

            # 未参与检测的封禁槽位（无 XML 文件）：只在汇总处输出一次，避免逐档重复
            banned_slots = sorted({it['ban_tag'] for it in items if it['ban_tag']})
            inactive_bans = SLOT_BAN_CACHE.get_inactive_bans(uid)
            if inactive_bans:
                reason_parts.append("🚨 未参与检测的封禁槽位：" + "；".join(
                    s for s in inactive_bans if s not in banned_slots))

            uid_reason = "；".join(reason_parts).replace('\n', ' ').replace('\r', ' ').strip()
            if len(uid_reason) > 500:
                uid_reason = uid_reason[:500] + "..."

            uid_rows.append({
                'uid': uid,
                'indexes': uid_indexes,
                'index_display': display_indexes,
                'name': items[0]['name'] or '无',
                'vip_level': uid_max_vip.get(uid),
                'status': 'fail' if uid_fail else 'warn',
                'reason': uid_reason,
                'multi': multi,
                'items': items,
                'inactive_bans': inactive_bans,
            })

        for row in uid_rows:
            self._write_uid_detail_file(row['uid'], row['items'], row['inactive_bans'],
                                        vip_level=row.get('vip_level'))

        self.log(f"📝 已按UID汇总生成 {len(uid_rows)} 份异常详情文件", "INFO")
        self._generate_batch_report(uid_rows, success, warn, fail, total)
        self._finish_log_session(
            f"批量检测结束\n✅ 通过:{success} ⚠️ 警告:{warn} ❌ 异常:{fail} | 总计:{total}")

    def _finalize_batch_results(self, file_result_map, uid_max_vip=None):
        """按账号（同一 UID）合并消费统计并完成 VIP 联合检测。

        必须在全部存档并行检测结束后、汇总报告前调用：同一账号下所有存档的消费
        累加为账号总消费，该账号的每个存档都用同一个合并值做联合判断，
        保证结果与文件处理顺序/线程调度无关。

        返回 {cost_key: 账号合并消费}。
        """
        uid_total_cost = defaultdict(int)
        uid_file_count = defaultdict(int)
        for res in file_result_map.values():
            key = res.get('cost_key')
            if not key:
                continue
            uid_total_cost[key] += res.get('total_cost', 0) or 0
            uid_file_count[key] += 1

        for res in file_result_map.values():
            key = res.get('cost_key')
            if not key:
                continue
            merged_cost = uid_total_cost[key]
            # 联合判断使用该账号下最高 VIP（预扫描未命中则回退当前文件自身 VIP）
            best_vip = (uid_max_vip or {}).get(key)
            union_res = DetectionEngine.check_vip_pay_union(file_path=res['file'],
                                                            pay_cost=merged_cost,
                                                            vip_level_override=best_vip)

            # 联合结果插回消费检测之后
            results = []
            inserted = False
            for item in res['results']:
                results.append(item)
                if isinstance(item, dict) and item.get('title') == '金币消费检测':
                    results.append(union_res)
                    inserted = True
            if not inserted:
                results.append(union_res)

            res['results'] = results
            res['overall'] = AppDetector._overall_of(results)
            res['union_res'] = union_res
            res['uid_total_cost'] = merged_cost
            res['uid_file_count'] = uid_file_count[key]
        return dict(uid_total_cost)

    def _detect_single_file_batch(self, file_path, bin_path, max_details, min_money, min_num,
                                  export_full):
        """批量单文件检测（线程内执行）：只检测该存档自身。

        消费不在此处累计、也不做 VIP 联合检测 —— 同一 UID 的消费必须等全部存档
        解析完成后由 _finalize_batch_results 合并统计。
        """
        fname = os.path.basename(file_path)

        uid_res = DetectionEngine.check_uid_md5_advanced(file_path)
        file_uid = uid_res.get('file_uid', '')
        file_index = uid_res.get('file_index', '')
        file_name = uid_res.get('file_name', '')
        file_uid_index = uid_res.get('file_uid_index', '')
        inner_uid = uid_res.get('inner_uid', '')
        inner_index = uid_res.get('inner_index', '')
        inner_uid_index = uid_res.get('inner_uid_index', '')

        # 服务器 UID（文件名首段）
        match = re.match(r"^(\d+)_(\d+)(?:_|\.)", fname, re.IGNORECASE)
        if match:
            server_uid = match.group(1)
        else:
            server_uid = None

        # 封禁检测：只取**本文件自身槽位**的封禁，避免同账号其它存档被重复标记
        # （账号级封禁信息在按 UID 汇总处只输出一次）
        ban_reason = SLOT_BAN_CACHE.get_slot_ban_reason(fname)
        ban_result = {"status": "pass", "title": "📄 存档封禁检测", "msg": "✅ 未检测到存档封禁"}
        ban_tag = ""
        if ban_reason:
            ban_tag = ban_reason
            ban_result = {"status": "fail", "title": "📄 存档封禁检测", "msg": f"🚨 {ban_reason}"}

        # UID 一致性校验（文件名 vs 文件内）
        uid_res_checked = uid_res
        local_uid_full = inner_uid_index or (f"{inner_uid}" if inner_uid else "")
        if not local_uid_full and file_uid_index:
            local_uid_full = file_uid_index
        if server_uid and inner_uid and str(inner_uid) != str(server_uid):
            uid_res_checked = dict(uid_res)
            uid_res_checked['status'] = 'fail'
            uid_res_checked['msg'] = (f"❌ 【异常：UID 不匹配】\n文件名UID:{server_uid}\n数据UID:{inner_uid}\n"
                                      + (uid_res.get('msg') or ''))

        # 消费累计 key：优先用文件名 uid（服务器uid），其次文件内 uid
        # 兜底用文件路径而不是固定字符串，避免把不同账号混成同一个
        cost_key = str(server_uid or inner_uid or file_path)
        pay_res = DetectionEngine.check_pay_xml(file_path, bin_path, max_details,
                                                min_money, min_num, export_full)
        current_cost = pay_res.get('total_cost', 0)

        cheat_res = DetectionEngine.check_cheat_stream(file_path)
        vip_res = DetectionEngine.check_vip_xml(file_path)

        results = [ban_result] + [uid_res_checked] + cheat_res['details'] + [vip_res, pay_res]
        overall = AppDetector._overall_of(results)

        return {
            'file': file_path,
            'cost_key': cost_key,
            'uid': server_uid or inner_uid or '',
            'overall': overall,
            'results': results,
            'ban_tag': ban_tag,
            'file_uid': file_uid,
            'file_index': file_index,
            'file_name': file_name,
            'file_uid_index': file_uid_index,
            'inner_uid': inner_uid,
            'inner_index': inner_index,
            'inner_uid_index': inner_uid_index,
            'total_cost': current_cost,
        }

    def _generate_batch_report(self, uid_rows, success, warn, fail, total):
        """生成批量检测 CSV 报告（按 UID 汇总）。

        uid_rows 为结构化数据，直接交给 ReportRenderer 渲染 —— 不再把数据先拼成
        字符串行、再 split('|') 反解（旧做法在标题/摘要含分隔符时会错列，且丢字段）。
        """
        report_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_report_path = os.path.join(OUTPUT_DIR, f"批量检测报告_{report_time}.csv")

        if not uid_rows:
            self.log("📊 未发现异常或警告，不生成CSV报告", "INFO")
            return

        csv_rows = ReportRenderer.build_batch_csv_rows(uid_rows)
        with open(csv_report_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(csv_rows)
        self.log(f"📊 CSV报告已生成：{csv_report_path} (共{len(uid_rows)}条异常/警告记录)", "INFO")
        if self._get_bool('auto_open_batch_report', False):
            self._open_dir(OUTPUT_DIR)

    # ---------- 设置动作 ----------
    def _reset_settings(self):
        self._create_default_config()
        self.entry_bin_path.delete(0, tk.END)
        self.entry_bin_path.insert(0, DEFAULT_BIN_PATH)
        self.entry_work_dir.delete(0, tk.END)
        self.entry_work_dir.insert(0, TEST_DIR)
        messagebox.showinfo("完成", "已恢复默认设置")


def run_tool():
    root = tk.Tk()
    app = AppDetector(root)
    set_app_icon(root)
    root.mainloop()


if __name__ == "__main__":
    run_tool()
