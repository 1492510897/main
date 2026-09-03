# main_pyside6.py - 深色背景 #121314 + 蓝色调主题
# 重构版本：4窗口结构（基础窗口 + 左、中、右三个子窗口）

import sys
import os
import json
import configparser
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
import threading
import importlib
import importlib.util
import time
from enum import Enum

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QSplitter, QStatusBar, QMessageBox,
    QFileDialog, QDialog, QLineEdit, QFormLayout, QDialogButtonBox,
    QGroupBox, QFrame, QProgressBar,QGridLayout
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QObject, QThread, QRect, QCoreApplication, QSize
)
from PySide6.QtGui import QFont, QTextCursor, QIcon, QColor, QFontMetrics


# ==========================================
# 颜色常量定义
# ==========================================

COLOR_BG_MAIN = "#121314"      # 主背景色
COLOR_BG_SECONDARY = "#1a1c1e"  # 次要背景色
COLOR_BG_CARD = "#1e2022"       # 卡片背景色
COLOR_BG_INPUT = "#2a2c2e"      # 输入框背景色
COLOR_BG_HOVER = "#2c2e30"      # 悬停背景色

COLOR_BLUE_PRIMARY = "#58a6ff"   # 主蓝色
COLOR_BLUE_HOVER = "#79c0ff"     # 悬停蓝色
COLOR_BLUE_ACTIVE = "#1f6feb"    # 激活蓝色

COLOR_GREEN = "#3fb950"          # 成功绿色
COLOR_RED = "#f85149"            # 错误红色
COLOR_YELLOW = "#d29922"         # 警告黄色
COLOR_GRAY = "#8b949e"           # 灰色
COLOR_WHITE = "#c0c0c0"          # 白色文字

COLOR_BORDER = "#30363d"         # 边框颜色


# ==========================================
# 配置和常量
# ==========================================

CURRENT_DIR = os.getcwd()

# 添加thrift/gen_py到系统路径
THRIFT_GEN_PY_PATH = os.path.join(CURRENT_DIR, "thrift", "gen_py")
if THRIFT_GEN_PY_PATH not in sys.path:
    sys.path.insert(0, THRIFT_GEN_PY_PATH)

GAME_ID = str(100027788)


# ==========================================
# 字体管理器 - 实现字体随窗口大小变动
# ==========================================

# 修改 FontManager 类中的字体基准大小

class FontManager:
    """字体管理器，根据窗口大小自动调整字体"""
    
    # 基准尺寸（窗口宽度为1400时的字体大小）
    BASE_WIDTH = 1400
    # 缩小字体基准大小
    BASE_FONT_SIZES = {
        'huge': 16,      # 大标题 (原来是20)
        'large': 14,     # 标题 (原来是16)
        'medium': 12,    # 中等文字 (原来是14)
        'normal': 11,    # 正文 (原来是12)
        'small': 9,      # 小文字 (原来是10)
        'tiny': 8,       # 极小文字 (原来是9)
    }
    
    # 字体族
    DEFAULT_FONT_FAMILY = "Microsoft YaHei"
    MONO_FONT_FAMILY = "Consolas"
    
    def __init__(self):
        self.current_width = FontManager.BASE_WIDTH
        self._font_cache = {}
        # 添加一个全局缩放系数，可以整体调整字体大小
        self.global_scale = 0.85  # 整体缩小到85%
    
    def update_width(self, width: int):
        """更新当前窗口宽度"""
        self.current_width = max(800, width)
        self._font_cache.clear()
    
    def get_scale_factor(self) -> float:
        """获取缩放因子"""
        # 应用全局缩放系数
        return (self.current_width / FontManager.BASE_WIDTH) * self.global_scale
    
    def get_font_size(self, size_key: str) -> int:
        """获取缩放后的字体大小"""
        base_size = FontManager.BASE_FONT_SIZES.get(size_key, 11)
        scaled_size = int(base_size * self.get_scale_factor())
        # 限制字体大小范围 (降低最大值)
        return max(8, min(scaled_size, 18))
    
    def get_font(self, size_key: str = 'normal', bold: bool = False, 
                 monospace: bool = False) -> QFont:
        """获取缩放后的字体"""
        cache_key = f"{size_key}_{bold}_{monospace}"
        
        if cache_key in self._font_cache:
            return QFont(self._font_cache[cache_key])
        
        family = self.MONO_FONT_FAMILY if monospace else self.DEFAULT_FONT_FAMILY
        size = self.get_font_size(size_key)
        
        font = QFont(family, size)
        font.setBold(bold)
        
        # 缓存字体（保存副本）
        self._font_cache[cache_key] = QFont(font)
        return QFont(font)
    
    def update_widget_font(self, widget: QWidget):
        """递归更新控件及其子控件的字体"""
        if not widget:
            return
            
        # 避免重复更新
        if hasattr(widget, '_font_updated'):
            return
        
        try:
            # 根据控件类型设置默认字体
            if isinstance(widget, QLabel):
                # 判断是否为标题
                text = widget.text()
                if any(keyword in text for keyword in ["👥", "⚡", "🏛️", "功能", "公会", "Cookie", "日志"]):
                    font = self.get_font('medium', bold=True)
                else:
                    font = self.get_font('normal')
                widget.setFont(font)
            elif isinstance(widget, QPushButton):
                font = self.get_font('normal')
                widget.setFont(font)
            elif isinstance(widget, QTextEdit):
                font = self.get_font('normal', monospace=True)
                widget.setFont(font)
            elif isinstance(widget, QLineEdit):
                font = self.get_font('normal')
                widget.setFont(font)
            elif isinstance(widget, QGroupBox):
                font = self.get_font('medium', bold=True)
                widget.setFont(font)
            elif isinstance(widget, QStatusBar):
                font = self.get_font('small')
                widget.setFont(font)
            
            # 标记已更新
            widget._font_updated = True
            
            # 递归处理子控件
            if hasattr(widget, 'children'):
                for child in widget.children():
                    if isinstance(child, QWidget):
                        self.update_widget_font(child)
        except Exception as e:
            # 忽略字体更新错误，不影响主程序运行
            pass
    
    def reset_update_flag(self, widget: QWidget):
        """重置更新标志"""
        if hasattr(widget, '_font_updated'):
            delattr(widget, '_font_updated')
        
        if hasattr(widget, 'children'):
            for child in widget.children():
                if isinstance(child, QWidget):
                    self.reset_update_flag(child)


# ==========================================
# 自适应缩放混入类
# ==========================================

class AutoScaleMixin:
    """自动缩放混入类，用于需要响应窗口大小变化的控件"""
    
    def setup_scaling(self, font_manager: FontManager):
        self._font_manager = font_manager
        self._scale_timer = QTimer()
        self._scale_timer.setSingleShot(True)
        self._scale_timer.timeout.connect(self._apply_scaling)
    
    def _apply_scaling(self):
        """应用缩放"""
        if hasattr(self, '_font_manager') and self._font_manager:
            # 重置更新标志
            self._font_manager.reset_update_flag(self)
            self._font_manager.update_widget_font(self)
    
    def resizeEvent(self, event):
        """重写resizeEvent以响应大小变化"""
        super().resizeEvent(event)
        if hasattr(self, '_scale_timer'):
            self._scale_timer.start(100)  # 延迟100ms执行，避免频繁更新


# ==========================================
# 基础窗口类
# ==========================================

class BaseWindow(QMainWindow):
    """基础窗口类，管理三个子窗口和字体缩放"""
    
    def __init__(self):
        super().__init__()
        self.font_manager = FontManager()
        self.left_panel = None
        self.center_panel = None
        self.right_panel = None
        
        self.setup_base_ui()
    
    def setup_base_ui(self):
        """设置基础UI"""
        self.setWindowTitle("爆枪突击军队管理工具")
        self.setMinimumSize(1000, 600)
        self.resize(1400, 800)
        
        # 设置全局暗色主题
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLOR_BG_MAIN};
            }}
            QLabel {{
                color: {COLOR_WHITE};
            }}
            QGroupBox {{
                color: {COLOR_BLUE_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {COLOR_BG_MAIN};
            }}
            QGroupBox::title {{
                color: {COLOR_BLUE_PRIMARY};
                background-color: {COLOR_BG_MAIN};
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }}
            QSplitter::handle {{
                background-color: {COLOR_BORDER};
            }}
            QStatusBar {{
                background-color: {COLOR_BG_SECONDARY};
                color: {COLOR_GRAY};
            }}
            QScrollBar:vertical {{
                background-color: {COLOR_BG_MAIN};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {COLOR_BORDER};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {COLOR_BLUE_PRIMARY};
            }}
            QScrollBar:horizontal {{
                background-color: {COLOR_BG_MAIN};
                height: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {COLOR_BORDER};
                border-radius: 6px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {COLOR_BLUE_PRIMARY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                height: 0px;
                width: 0px;
            }}
            QMessageBox {{
                background-color: {COLOR_BG_SECONDARY};
                color: {COLOR_WHITE};
            }}
        """)
        
        # 创建中央控件和主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建主分割器
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
        
        self.time_label = QLabel()
        self.time_label.setStyleSheet(f"color: {COLOR_BLUE_PRIMARY};")
        self.status_bar.addPermanentWidget(self.time_label)
        self.update_time()
        
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(1000)
    
    def set_panels(self, left_panel: QWidget, center_panel: QWidget, right_panel: QWidget):
        """设置三个子窗口"""
        self.left_panel = left_panel
        self.center_panel = center_panel
        self.right_panel = right_panel
        
        # 添加三个窗口到分割器
        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(center_panel)
        self.main_splitter.addWidget(right_panel)
        
        # 设置左侧窗口比例为334
        self.main_splitter.setSizes([334, 150, 600])
        self.main_splitter.setChildrenCollapsible(False)
    
    def resizeEvent(self, event):
        """重写resizeEvent，更新字体缩放"""
        super().resizeEvent(event)
        # 更新字体管理器的宽度
        if hasattr(self, 'font_manager'):
            self.font_manager.update_width(self.width())
            # 重置更新标志并应用字体缩放
            self.font_manager.reset_update_flag(self)
            self.font_manager.update_widget_font(self)
    
    def update_time(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(now)


# ==========================================
# 日志级别枚举
# ==========================================

class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"
    DEBUG = "DEBUG"


# ==========================================
# 模块导入器
# ==========================================

class ModuleImporter:
    def import_gen_py_modules(self):
        """动态导入gen_py目录下的所有模块"""
        modules = {}
        module_names = ['grow', 'master', 'member', 'role', 'shared', 'visitor']
        
        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
                modules[module_name] = module
                print(f"成功导入模块: {module_name}")
            except ImportError as e:
                print(f"导入模块 {module_name} 失败: {e}")
                modules[module_name] = None
        
        return modules

    def import_api_tools(self):
        """动态导入tools目录下的所有工具模块"""
        tools_dir = os.path.join(CURRENT_DIR, "tools")
        tools = {}
        tools_names = [
            'cookies',
            'VisitorApi',
            'MasterApi',
            'MemberApi',
            'RoleApi',
        ]
        
        for tool_name in tools_names:
            tool_path = os.path.join(tools_dir, f"{tool_name}.py")
            if os.path.exists(tool_path) and os.path.isfile(tool_path):
                try:
                    spec = importlib.util.spec_from_file_location(tool_name, tool_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    tools[tool_name] = module
                    print(f"成功导入工具模块: {tool_name}")
                except Exception as e:
                    print(f"导入工具模块 {tool_name} 失败: {e}")
                    tools[tool_name] = None
            else:
                print(f"工具模块 {tool_name}.py 不存在")
                tools[tool_name] = None
        
        return tools


# 创建实例并导入
importer = ModuleImporter()
GEN_PY_MODULES = importer.import_gen_py_modules()
API_TOOLS = importer.import_api_tools()


# ==========================================
# 业务逻辑类
# ==========================================

class Functions(QObject):
    """核心功能类 - 处理所有业务逻辑"""
    
    log_signal = Signal(str, str)
    
    def __init__(self):
        super().__init__()
        self.config = None
        self.config_file = os.path.join(CURRENT_DIR, "config.ini")
        self.current_cookie_data = None
        self.current_cookie_name = None
        self.cookie_list = []
        
        self.default_config = {
            'paths': {
                'cookies_dir': os.path.join(CURRENT_DIR, 'cookies'),
                'last_cookie': os.path.join(CURRENT_DIR, 'last_cookie.json'),
                'output_dir': os.path.join(CURRENT_DIR, 'outputdata'),
                'tools_dir': os.path.join(CURRENT_DIR, 'tools'),
            },
            'api': {
                'timeout': '30',
                'retry_count': '3',
            }
        }
        
        self.ensure_default_directories()
        self.load_config()
    
    def log(self, message: str, level: str = LogLevel.INFO):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        self.log_signal.emit(log_message, level)
    
    def ensure_default_directories(self):
        default_dirs = [
            os.path.join(CURRENT_DIR, 'cookies'),
            os.path.join(CURRENT_DIR, 'outputdata'),
            os.path.join(CURRENT_DIR, 'tools')
        ]
        for dir_path in default_dirs:
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path)
                except Exception:
                    pass
    
    def load_config(self):
        self.config = configparser.ConfigParser()
        
        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file, encoding='utf-8')
            except Exception:
                self.create_config()
        else:
            self.create_config()
        
        self.ensure_config_sections()
        self.ensure_config_directories()
    
    def create_config(self):
        for section, keys in self.default_config.items():
            if section not in self.config:
                self.config[section] = {}
            for key, value in keys.items():
                if key not in self.config[section]:
                    self.config[section][key] = value
        self.save_config()
    
    def ensure_config_sections(self):
        for section, keys in self.default_config.items():
            if section not in self.config:
                self.config[section] = {}
            for key, value in keys.items():
                if key not in self.config[section] or not self.config[section][key]:
                    self.config[section][key] = value
    
    def ensure_config_directories(self):
        dir_keys = ['cookies_dir', 'output_dir', 'tools_dir']
        for key in dir_keys:
            dir_path = self.get_config_value('paths', key)
            if dir_path and not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path)
                except Exception:
                    pass
    
    def save_config(self) -> bool:
        try:
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
            return True
        except Exception:
            return False
    
    def get_config_value(self, section: str, key: str, default: Any = None) -> Any:
        try:
            value = self.config.get(section, key)
            if key in ['cookies_dir', 'last_cookie', 'output_dir', 'tools_dir']:
                if not os.path.isabs(value):
                    value = os.path.join(CURRENT_DIR, value)
            return value
        except Exception:
            if default is None:
                return self.default_config.get(section, {}).get(key, default)
            return default
    
    def set_config_value(self, section: str, key: str, value: Any) -> bool:
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)
        return self.save_config()
    
    def switch_cookie(self, cookie_path: str) -> Tuple[bool, str]:
        try:
            with open(cookie_path, 'r', encoding='utf-8') as f:
                content = f.read()
                try:
                    cookie_data = json.loads(content)
                    self.current_cookie_data = cookie_data
                except json.JSONDecodeError:
                    self.current_cookie_data = content
            
            self.current_cookie_name = os.path.basename(cookie_path).replace('.json', '')
            return True, f"已切换到Cookie: {self.current_cookie_name}"
        except Exception as e:
            return False, f"切换失败: {str(e)}"
    
    def get_current_cookie_dict(self) -> Any:
        return self.current_cookie_data
    
    def get_current_cookie_name(self) -> Optional[str]:
        return self.current_cookie_name
    
    def get_cookies_dir(self) -> str:
        return self.get_config_value('paths', 'cookies_dir', os.path.join(CURRENT_DIR, 'cookies'))
    
    def get_output_dir(self) -> str:
        return self.get_config_value('paths', 'output_dir', os.path.join(CURRENT_DIR, 'outputdata'))
    
    def get_tools_dir(self) -> str:
        return self.get_config_value('paths', 'tools_dir', os.path.join(CURRENT_DIR, 'tools'))
    
    def _build_cookie_string(self) -> str:
        if isinstance(self.current_cookie_data, dict):
            cookies = self.current_cookie_data.get('cookies', self.current_cookie_data)
            cookie_parts = []
            for key, value in cookies.items():
                if key in ['Pauth', 'Puser']:
                    cookie_parts.append(f"{key}={value}")
            return "; ".join(cookie_parts)
        return ""
    
    def _thrift_to_dict(self, obj: Any) -> Any:
        if obj is None:
            return None
        elif hasattr(obj, "__dict__"):
            result = {}
            for k, v in vars(obj).items():
                if k.startswith('_'):
                    continue
                result[k] = self._thrift_to_dict(v)
            return result
        elif isinstance(obj, list):
            return [self._thrift_to_dict(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._thrift_to_dict(v) for k, v in obj.items()}
        else:
            return obj
    
    def get_union_of_me(self, params: Dict = None) -> Tuple[bool, Any]:
        if not self.current_cookie_data:
            return False, "请先切换一个Cookie"
        
        try:
            from visitor import VisitorApi
            from shared.ttypes import Normal, NormalException
            from thrift.transport import THttpClient
            from thrift.protocol import TBinaryProtocol
            
            arch_index = "0"
            if isinstance(self.current_cookie_data, dict):
                arch_index = str(self.current_cookie_data.get('index', '0'))
            
            cookie_str = self._build_cookie_string()
            
            url = "https://save.api.4399.com/union/VisitorApi"
            transport = THttpClient.THttpClient(url)
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/x-thrift",
                "Referer": "https://web.4399.com/",
                "Cookie": cookie_str
            }
            transport.setCustomHeaders(headers)
            
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = VisitorApi.Client(protocol)
            transport.open()
            
            normal_req = Normal(
                time=str(int(time.time())),
                game_id=GAME_ID,
                arch_index=arch_index
            )
            
            result = client.unionOfMe(normal_req)
            transport.close()
            
            result_dict = self._thrift_to_dict(result)
            return True, result_dict
            
        except Exception as e:
            error_msg = str(e)
            if "20010" in error_msg or "not_in_union" in error_msg.lower():
                return True, {"not_in_union": True, "message": "当前账号未加入任何军队"}
            return False, f"调用失败: {error_msg}"
    
    def parse_member_info_from_union_of_me(self, result_dict: dict) -> dict:
        if not result_dict:
            return None
        
        if result_dict.get('not_in_union'):
            return {"in_union": False, "message": result_dict.get('message', '未加入公会')}
        
        union_title = ''
        
        if 'compose' in result_dict:
            compose = result_dict.get('compose', {})
            member_union = compose.get('member_union', {})
            if member_union:
                union_title = member_union.get('title', '')
        
        if 'member' in result_dict:
            member = result_dict.get('member', {})
            if member:
                return {
                    "in_union": True,
                    "union_id": member.get('union_id', ''),
                    "union_title": union_title,
                    "nickname": member.get('nickname', ''),
                    "role_name": member.get('role_name', ''),
                    "uid": member.get('uid', ''),
                    "username": member.get('username', ''),
                    "money": member.get('money', 0),
                    "extra": member.get('extra', {}),
                    "extra2": member.get('extra2', {}),
                }
        
        if 'compose' in result_dict:
            compose = result_dict.get('compose', {})
            member = compose.get('member', {})
            if member:
                return {
                    "in_union": True,
                    "union_id": member.get('union_id', ''),
                    "union_title": union_title,
                    "nickname": member.get('nickname', ''),
                    "role_name": member.get('role_name', ''),
                    "uid": member.get('uid', ''),
                    "username": member.get('username', ''),
                    "money": member.get('money', 0),
                    "extra": member.get('extra', {}),
                    "extra2": member.get('extra2', {}),
                }
        
        return {"in_union": False, "message": "未能解析成员信息"}


# ==========================================
# 工作线程
# ==========================================

class QueryWorker(QThread):
    finished = Signal(bool, object)
    
    def __init__(self, func_instance: Functions):
        super().__init__()
        self.func = func_instance
    
    def run(self):
        success, result = self.func.get_union_of_me()
        self.finished.emit(success, result)


class CookieLoginWorker(QThread):
    finished = Signal(bool, str, object)
    progress = Signal(str)
    
    def __init__(self, username: str, password: str, index: int):
        super().__init__()
        self.username = username
        self.password = password
        self.index = index
        self.cookies_module = API_TOOLS.get('cookies')
    
    def run(self):
        if self.cookies_module is None:
            self.finished.emit(False, "cookies模块未正确导入", None)
            return
        
        try:
            self.progress.emit("正在登录...")
            cookie_raw = self.cookies_module.login(self.username, self.password)
            
            if cookie_raw:
                self.progress.emit("正在保存Cookie...")
                success, file_path = self.cookies_module.save_cookies(cookie_raw, self.index)
                if success:
                    self.finished.emit(True, "登录成功", {"file_path": file_path, "index": self.index})
                else:
                    self.finished.emit(False, "保存Cookie文件失败", None)
            else:
                self.finished.emit(False, "登录失败，请检查账号密码", None)
        except Exception as e:
            self.finished.emit(False, str(e), None)


# ==========================================
# 成员信息显示卡片
# ==========================================

class MemberInfoCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setup_ui()
        self.clear_info()
    
    def setup_ui(self):
        self.setStyleSheet(f"""
            MemberInfoCard {{
                background-color: {COLOR_BG_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        
        title_label = QLabel("👥 当前公会成员信息")
        title_label.setStyleSheet(f"color: {COLOR_BLUE_PRIMARY}; background-color: transparent;")
        layout.addWidget(title_label)
        
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet(f"background-color: {COLOR_BORDER};")
        layout.addWidget(line)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        label_style = f"color: {COLOR_BLUE_PRIMARY}; font-weight: bold; background-color: transparent;"
        value_style = f"color: {COLOR_WHITE}; background-color: transparent;"
        highlight_style = f"color: {COLOR_BLUE_HOVER}; font-weight: bold; background-color: transparent;"
        
        self.nickname_label = QLabel("--")
        self.nickname_label.setStyleSheet(value_style)
        form_layout.addRow("论坛名称:", self.nickname_label)
        
        self.union_id_label = QLabel("--")
        self.union_id_label.setStyleSheet(value_style)
        form_layout.addRow("公会编码:", self.union_id_label)
        
        self.username_label = QLabel("--")
        self.username_label.setStyleSheet(value_style)
        form_layout.addRow("用户账号:", self.username_label)
        
        self.union_title_label = QLabel("--")
        self.union_title_label.setStyleSheet(highlight_style)
        form_layout.addRow("公会名称:", self.union_title_label)
        
        self.uid_label = QLabel("--")
        self.uid_label.setStyleSheet(value_style)
        form_layout.addRow("账号标识:", self.uid_label)
        
        self.role_name_label = QLabel("--")
        self.role_name_label.setStyleSheet(highlight_style)
        form_layout.addRow("职务权限:", self.role_name_label)
        
        for i in range(form_layout.rowCount()):
            label_item = form_layout.itemAt(i, QFormLayout.LabelRole)
            if label_item and label_item.widget():
                label_item.widget().setStyleSheet(label_style)
        
        layout.addLayout(form_layout)
        layout.addSpacing(5)
    
    def update_info(self, member_info: dict):
        if not member_info or not member_info.get('in_union'):
            self.clear_info()
            return
        
        self.nickname_label.setText(member_info.get('nickname', '--'))
        self.union_id_label.setText(str(member_info.get('union_id', '--')))
        self.username_label.setText(member_info.get('username', '--'))
        self.union_title_label.setText(member_info.get('union_title', '--'))
        self.uid_label.setText(str(member_info.get('uid', '--')))
        self.role_name_label.setText(member_info.get('role_name', '--'))
    
    def clear_info(self):
        self.nickname_label.setText("--")
        self.union_id_label.setText("--")
        self.username_label.setText("--")
        self.union_title_label.setText("--")
        self.uid_label.setText("--")
        self.role_name_label.setText("--")


# ==========================================
# 日志浏览器
# ==========================================

class LogBrowser(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.document().setMaximumBlockCount(1000)
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLOR_BG_MAIN};
                color: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
        """)
    
    def append_log(self, message: str, level: str = LogLevel.INFO):
        color_map = {
            LogLevel.INFO: COLOR_GRAY,
            LogLevel.SUCCESS: COLOR_GREEN,
            LogLevel.WARNING: COLOR_YELLOW,
            LogLevel.ERROR: COLOR_RED,
            LogLevel.DEBUG: COLOR_BLUE_PRIMARY
        }
        color = color_map.get(level, COLOR_GRAY)
        html = f'<span style="color:{color};">{message}</span><br>'
        self.append(html)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
    
    def clear_log(self):
        self.clear()


# ==========================================
# Cookie添加对话框
# ==========================================

class CookieAddDialog(QDialog):
    login_success = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加Cookie")
        self.setModal(True)
        self.setFixedSize(400, 350)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLOR_BG_SECONDARY};
            }}
            QLabel {{
                color: {COLOR_BLUE_PRIMARY};
            }}
            QLineEdit {{
                background-color: {COLOR_BG_INPUT};
                color: {COLOR_WHITE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                padding: 5px;
            }}
            QLineEdit:focus {{
                border-color: {COLOR_BLUE_PRIMARY};
            }}
            QPushButton {{
                background-color: {COLOR_GREEN};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: #2ea043;
            }}
            QPushButton#cancelBtn {{
                background-color: {COLOR_BG_INPUT};
            }}
            QPushButton#cancelBtn:hover {{
                background-color: {COLOR_BG_HOVER};
            }}
        """)
        self.setup_ui()
        self.worker = None
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(10)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入用户名")
        form_layout.addRow("用户名:", self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("请输入密码")
        form_layout.addRow("密码:", self.password_input)
        
        self.index_input = QLineEdit("0")
        self.index_input.setPlaceholderText("0-7")
        form_layout.addRow("索引 (0-7):", self.index_input)
        
        layout.addWidget(form_widget)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                text-align: center;
                color: {COLOR_WHITE};
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_GREEN};
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self.progress_bar)
        
        self.message_label = QLabel("账号密码仅用于获取cookie\n不会被保存或上传")
        self.message_label.setStyleSheet(f"color: {COLOR_GRAY}; font-size: 16px;")
        layout.addWidget(self.message_label)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {COLOR_GREEN};")
        layout.addWidget(self.status_label)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.on_submit)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
    
    def on_submit(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        if not username or not password:
            QMessageBox.warning(self, "错误", "用户名和密码不能为空")
            return
        
        try:
            index = int(self.index_input.text())
            if index < 0 or index > 7:
                QMessageBox.warning(self, "错误", "索引必须是0-7之间的数字")
                return
        except ValueError:
            QMessageBox.warning(self, "错误", "索引必须是数字")
            return
        
        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)
        self.index_input.setEnabled(False)
        self.ok_button.setEnabled(False)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在登录...")
        
        self.worker = CookieLoginWorker(username, password, index)
        self.worker.progress.connect(self.status_label.setText)
        self.worker.finished.connect(self.on_login_finished)
        self.worker.start()
    
    def on_login_finished(self, success: bool, message: str, result_data: dict):
        self.progress_bar.setVisible(False)
        
        if success:
            self.status_label.setText("✓ 登录成功")
            QMessageBox.information(self, "成功", f"Cookie文件已保存\n{result_data.get('file_path', '')}")
            self.login_success.emit(result_data.get('file_path', ''))
            self.accept()
        else:
            self.status_label.setText(f"✗ {message}")
            self.status_label.setStyleSheet(f"color: {COLOR_RED};")
            QMessageBox.critical(self, "错误", message)
            
            self.username_input.setEnabled(True)
            self.password_input.setEnabled(True)
            self.index_input.setEnabled(True)
            self.ok_button.setEnabled(True)


# ==========================================
# Cookie管理区域
# ==========================================

class CookieManagementWidget(QWidget):
    cookie_changed = Signal()
    
    def __init__(self, func_instance: Functions, parent=None):
        super().__init__(parent)
        self.func = func_instance
        self.is_cookie_hidden = False
        self.hidden_cookie_name = None
        self.hidden_cookie_data = None
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        group_box = QGroupBox("🍪 Cookie管理")
        group_box.setStyleSheet(f"""
            QGroupBox {{
                color: {COLOR_BLUE_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                color: {COLOR_BLUE_PRIMARY};
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }}
        """)
        group_layout = QVBoxLayout(group_box)
        
        current_widget = QWidget()
        current_layout = QHBoxLayout(current_widget)
        current_layout.setContentsMargins(0, 0, 0, 0)
        
        current_label = QLabel("当前使用:")
        current_label.setStyleSheet(f"font-weight: bold; color: {COLOR_BLUE_PRIMARY};")
        self.current_cookie_label = QLabel("未选择")
        self.current_cookie_label.setStyleSheet(f"color: {COLOR_BLUE_HOVER}; font-weight: bold;")
        self.current_cookie_label.setWordWrap(True)
        
        current_layout.addWidget(current_label)
        current_layout.addWidget(self.current_cookie_label, 1)
        group_layout.addWidget(current_widget)
        
        # 改为2x2网格布局
        btn_widget = QWidget()
        btn_layout = QGridLayout(btn_widget)  # 使用QGridLayout
        btn_layout.setContentsMargins(0, 5, 0, 5)
        btn_layout.setSpacing(8)
        
        # 创建按钮
        self.toggle_btn = QPushButton("🔐 隐藏Cookie")
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_GREEN};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: #2ea043;
            }}
        """)
        self.toggle_btn.clicked.connect(self.toggle_cookie)

        self.add_btn = QPushButton("➕ 添加Cookie")
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_GREEN};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: #2ea043;
            }}
        """)
        self.add_btn.clicked.connect(self.add_cookie)
        
        self.switch_btn = QPushButton("🔄 切换Cookie")
        self.switch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BLUE_ACTIVE};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_BLUE_PRIMARY};
            }}
        """)
        self.switch_btn.clicked.connect(self.switch_cookie)
        
        self.clear_btn = QPushButton("🗑️ 清除Cookie")
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_RED};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: #da3633;
            }}
        """)
        self.clear_btn.clicked.connect(self.clear_cookie)
        
        # 2x2 布局：第一行放隐藏和添加，第二行放切换和清除
        btn_layout.addWidget(self.toggle_btn, 0, 0)  # 第0行，第0列
        btn_layout.addWidget(self.add_btn, 0, 1)     # 第0行，第1列
        btn_layout.addWidget(self.switch_btn, 1, 0)  # 第1行，第0列
        btn_layout.addWidget(self.clear_btn, 1, 1)   # 第1行，第1列
        
        # 设置列拉伸比例，使按钮等宽
        btn_layout.setColumnStretch(0, 1)
        btn_layout.setColumnStretch(1, 1)
        
        group_layout.addWidget(btn_widget)
        
        layout.addWidget(group_box)
    
    def toggle_cookie(self):
        if self.is_cookie_hidden:
            self.show_cookie()
        else:
            self.hide_cookie()
    
    def hide_cookie(self):
        current_text = self.current_cookie_label.text()
        
        if current_text == "未选择":
            QMessageBox.information(self, "提示", "当前没有Cookie可以隐藏")
            return
        
        if current_text == "已隐藏":
            QMessageBox.information(self, "提示", "Cookie已经是隐藏状态")
            return
        
        self.hidden_cookie_name = current_text
        self.hidden_cookie_data = self.func.current_cookie_data
        
        main_window = self.window()
        if hasattr(main_window, 'left_panel') and hasattr(main_window.left_panel, 'member_info_card'):
            main_window.left_panel.member_info_card.clear_info()
        
        if hasattr(main_window, 'status_bar'):
            main_window.status_bar.showMessage("Cookie已隐藏，点击「显示Cookie」可恢复", 3000)
        
        self.current_cookie_label.setText("已隐藏")
        self.current_cookie_label.setStyleSheet(f"color: {COLOR_GRAY}; font-style: italic;")
        
        self.toggle_btn.setText("👁️ 显示Cookie")
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BLUE_PRIMARY};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_BLUE_HOVER};
            }}
        """)
        
        self.add_btn.setEnabled(False)
        self.switch_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        
        self.is_cookie_hidden = True
    
    def show_cookie(self):
        if not self.is_cookie_hidden:
            QMessageBox.information(self, "提示", "Cookie已经是显示状态")
            return
        
        last_cookie_path = self.func.get_config_value('paths', 'last_cookie', '')
        
        if not last_cookie_path or not os.path.exists(last_cookie_path):
            QMessageBox.information(self, "提示", "没有找到上次使用的Cookie文件，请重新选择")
            self.reset_hidden_state()
            return
        
        try:
            self.func.current_cookie_data = None
            self.func.current_cookie_name = None
            
            success, message = self.func.switch_cookie(last_cookie_path)
            
            if success:
                self.current_cookie_label.setText(self.func.get_current_cookie_name())
                self.current_cookie_label.setStyleSheet(f"color: {COLOR_GREEN}; font-weight: bold;")
                
                self.toggle_btn.setText("🔐 隐藏Cookie")
                self.toggle_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {COLOR_GREEN};
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 6px;
                        min-height: 30px;
                    }}
                    QPushButton:hover {{
                        background-color: #2ea043;
                    }}
                """)
                
                self.add_btn.setEnabled(True)
                self.switch_btn.setEnabled(True)
                self.clear_btn.setEnabled(True)
                
                main_window = self.window()
                if hasattr(main_window, 'query_member_info'):
                    QTimer.singleShot(200, main_window.query_member_info)
                
                if hasattr(main_window, 'status_bar'):
                    main_window.status_bar.showMessage("Cookie已恢复显示", 2000)
                
                self.is_cookie_hidden = False
                self.hidden_cookie_name = None
                self.hidden_cookie_data = None
            else:
                QMessageBox.warning(self, "错误", f"恢复Cookie失败: {message}")
                self.reset_hidden_state()
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"恢复Cookie时发生错误: {str(e)}")
            self.reset_hidden_state()
    
    def add_cookie(self):
        dialog = CookieAddDialog(self.window())
        dialog.login_success.connect(self.on_cookie_added)
        dialog.exec()
    
    def on_cookie_added(self, file_path: str):
        self.switch_to_cookie(file_path)
        self.cookie_changed.emit()
    
    def switch_cookie(self):
        init_dir = self.func.get_cookies_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Cookie文件", init_dir, "JSON文件 (*.json);;所有文件 (*.*)"
        )
        if file_path:
            self.switch_to_cookie(file_path)
    
    def switch_to_cookie(self, file_path: str):
        self.reset_hidden_state()
        self.clear_cookie(emit_signal=False)
        self.func.set_config_value('paths', 'cookies_dir', os.path.dirname(file_path))
        
        success, message = self.func.switch_cookie(file_path)
        if success:
            self.func.set_config_value('paths', 'last_cookie', file_path)
            self.current_cookie_label.setText(self.func.get_current_cookie_name())
            self.current_cookie_label.setStyleSheet(f"color: {COLOR_GREEN}; font-weight: bold;")
            self.cookie_changed.emit()
        else:
            QMessageBox.critical(self, "错误", message)
    
    def clear_cookie(self, emit_signal: bool = True):
        self.reset_hidden_state()
        
        self.func.current_cookie_data = None
        self.func.current_cookie_name = None
        self.func.set_config_value('paths', 'last_cookie', "")
        self.current_cookie_label.setText("未选择")
        self.current_cookie_label.setStyleSheet(f"color: {COLOR_GRAY};")
        
        main_window = self.window()
        if hasattr(main_window, 'left_panel') and hasattr(main_window.left_panel, 'member_info_card'):
            main_window.left_panel.member_info_card.clear_info()
        
        if hasattr(main_window, 'status_bar'):
            main_window.status_bar.showMessage("Cookie已清除")
            QTimer.singleShot(3000, lambda: main_window.status_bar.showMessage("就绪"))
        
        if emit_signal:
            self.cookie_changed.emit()
    
    def reset_hidden_state(self):
        self.is_cookie_hidden = False
        self.hidden_cookie_name = None
        self.hidden_cookie_data = None
        
        self.toggle_btn.setText("🔐 隐藏Cookie")
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_GREEN};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: #2ea043;
            }}
        """)
        
        if self.func.current_cookie_data and self.func.current_cookie_name:
            self.current_cookie_label.setText(self.func.current_cookie_name)
            self.current_cookie_label.setStyleSheet(f"color: {COLOR_GREEN}; font-weight: bold;")
            self.add_btn.setEnabled(True)
            self.switch_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
        else:
            self.current_cookie_label.setText("未选择")
            self.current_cookie_label.setStyleSheet(f"color: {COLOR_GRAY};")
            self.add_btn.setEnabled(True)
            self.switch_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
    
    def get_current_cookie_name(self) -> str:
        if self.is_cookie_hidden:
            return self.hidden_cookie_name or "未选择"
        return self.func.get_current_cookie_name() or "未选择"


# ==========================================
# 公会信息面板
# ==========================================


# ==========================================
# 功能菜单按钮
# ==========================================

class FunctionMenuButton(QPushButton):
    def __init__(self, text: str, icon_text: str = "", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(45)
        self.setMinimumWidth(120)
        if icon_text:
            self.setText(f"{icon_text} {text}")
        
        self.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding-left: 15px;
                background-color: {COLOR_BG_SECONDARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-weight: 500;
                color: {COLOR_BLUE_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_BLUE_PRIMARY};
                color: {COLOR_BLUE_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {COLOR_BG_MAIN};
                border-color: {COLOR_BLUE_ACTIVE};
                color: {COLOR_BLUE_PRIMARY};
            }}
        """)


# ==========================================
# 左侧面板 - 包含Cookie管理、成员信息、日志
# ==========================================

class LeftPanel(QWidget):
    """左侧面板 - Cookie管理 + 成员信息 + 日志"""
    
    def __init__(self, func_instance: Functions, parent=None):
        super().__init__(parent)
        self.func = func_instance
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Cookie管理区域
        self.cookie_manager = CookieManagementWidget(self.func)
        layout.addWidget(self.cookie_manager)
        
        # 成员信息显示区域
        self.member_info_card = MemberInfoCard()
        layout.addWidget(self.member_info_card)
        
        # 日志浏览器
        log_group = QGroupBox("📋 运行日志")
        log_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLOR_BLUE_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {COLOR_BG_MAIN};
            }}
            QGroupBox::title {{
                color: {COLOR_BLUE_PRIMARY};
                background-color: {COLOR_BG_MAIN};
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }}
        """)
        log_layout = QVBoxLayout(log_group)
        
        self.log_browser = LogBrowser()
        log_layout.addWidget(self.log_browser)
        
        clear_btn = QPushButton("清空日志")
        clear_btn.setFixedHeight(30)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BG_SECONDARY};
                color: {COLOR_BLUE_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_BLUE_PRIMARY};
            }}
        """)
        clear_btn.clicked.connect(self.log_browser.clear_log)
        log_layout.addWidget(clear_btn)
        
        layout.addWidget(log_group)
    
    def get_cookie_manager(self):
        return self.cookie_manager


# ==========================================
# 中间面板 - 功能菜单
# ==========================================

class CenterPanel(QWidget):
    """中间面板 - 功能菜单"""
    
    function_selected = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(10, 15, 10, 15)
        
        # 功能菜单标题
        title_label = QLabel("⚡ 功能菜单")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_BLUE_PRIMARY};
                padding: 5px;
                background-color: {COLOR_BG_SECONDARY};
                border-radius: 4px;
            }}
        """)
        layout.addWidget(title_label)
        
        layout.addSpacing(20)
        
        # 功能按钮 - 文字居中显示
        self.union_info_btn = FunctionMenuButton("公会信息", "🏛️")
        self.union_info_btn.setStyleSheet(f"""
            QPushButton {{
                text-align: center;
                padding-left: 0px;
                background-color: {COLOR_BG_SECONDARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-weight: 500;
                color: {COLOR_BLUE_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_BLUE_PRIMARY};
                color: {COLOR_BLUE_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {COLOR_BG_MAIN};
                border-color: {COLOR_BLUE_ACTIVE};
                color: {COLOR_BLUE_PRIMARY};
            }}
        """)
        self.union_info_btn.clicked.connect(lambda: self.function_selected.emit("公会信息"))
        layout.addWidget(self.union_info_btn)
        
        self.member_list_btn = FunctionMenuButton("成员列表", "👥")
        self.member_list_btn.setStyleSheet(f"""
            QPushButton {{
                text-align: center;
                padding-left: 0px;
                background-color: {COLOR_BG_SECONDARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-weight: 500;
                color: {COLOR_BLUE_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_BLUE_PRIMARY};
                color: {COLOR_BLUE_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {COLOR_BG_MAIN};
                border-color: {COLOR_BLUE_ACTIVE};
                color: {COLOR_BLUE_PRIMARY};
            }}
        """)
        self.member_list_btn.clicked.connect(lambda: self.function_selected.emit("成员列表"))
        layout.addWidget(self.member_list_btn)

        self.admin_tools_btn = FunctionMenuButton("管理操作", "🛠️")
        self.admin_tools_btn.setStyleSheet(f"""
            QPushButton {{
                text-align: center;
                padding-left: 0px;
                background-color: {COLOR_BG_SECONDARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-weight: 500;
                color: {COLOR_BLUE_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_BLUE_PRIMARY};
                color: {COLOR_BLUE_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {COLOR_BG_MAIN};
                border-color: {COLOR_BLUE_ACTIVE};
                color: {COLOR_BLUE_PRIMARY};
            }}
        """)
        self.admin_tools_btn.clicked.connect(lambda: self.function_selected.emit("管理操作"))
        layout.addWidget(self.admin_tools_btn)

        self.dangerous_ops_btn = FunctionMenuButton("危险操作", "⚠️")
        self.dangerous_ops_btn.setStyleSheet(f"""
            QPushButton {{
                text-align: center;
                padding-left: 0px;
                background-color: {COLOR_BG_SECONDARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-weight: 500;
                color: {COLOR_BLUE_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: {COLOR_BG_HOVER};
                border-color: {COLOR_BLUE_PRIMARY};
                color: {COLOR_BLUE_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {COLOR_BG_MAIN};
                border-color: {COLOR_BLUE_ACTIVE};
                color: {COLOR_BLUE_PRIMARY};
            }}
        """)
        self.dangerous_ops_btn.clicked.connect(lambda: self.function_selected.emit("危险操作"))
        layout.addWidget(self.dangerous_ops_btn)

        layout.addSpacing(10)
        
        layout.addStretch()
# ==========================================
# 右侧面板 - 功能内容显示区
# ==========================================

class RightPanel(QWidget):
    """右侧面板 - 功能内容显示区"""
    
    def __init__(self, func_instance: Functions, parent=None):
        super().__init__(parent)
        self.func = func_instance
        self.setup_ui()
        self.current_panel = None
    
    def setup_ui(self):
        pass


# ==========================================
# 主窗口（继承自BaseWindow）
# ==========================================

class MainWindow(BaseWindow):
    """主窗口 - 继承自BaseWindow，整合三个子窗口"""
    
    def __init__(self):
        super().__init__()
        
        self.func = Functions()
        self.worker = None  # 添加 worker 属性
        self.setup_connections()
        self.create_panels()
        self.load_initial_data()
    
    def create_panels(self):
        """创建三个子窗口"""
        # 创建左侧面板
        self.left_panel = LeftPanel(self.func)
        self.left_panel.cookie_manager.cookie_changed.connect(self.on_cookie_changed)
        
        # 创建中间面板
        self.center_panel = CenterPanel()
        self.center_panel.function_selected.connect(self.on_function_selected)
        
        # 创建右侧面板
        self.right_panel = RightPanel(self.func)
        
        # 设置三个子窗口到基础窗口
        self.set_panels(self.left_panel, self.center_panel, self.right_panel)
        
        # 连接日志信号
        self.func.log_signal.connect(self.on_log_received)
    
    def setup_connections(self):
        """设置信号连接"""
        pass
    
    def load_initial_data(self):
        """加载初始数据"""
        last_cookie_path = self.func.get_config_value('paths', 'last_cookie', '')
        
        if last_cookie_path and os.path.exists(last_cookie_path):
            success, message = self.func.switch_cookie(last_cookie_path)
            if success:
                self.left_panel.cookie_manager.current_cookie_label.setText(self.func.get_current_cookie_name())
                self.left_panel.cookie_manager.current_cookie_label.setStyleSheet(f"color: {COLOR_GREEN}; font-weight: bold;")
                self.log(f"已自动加载上次使用的Cookie: {message}", LogLevel.INFO)
                self.query_member_info()
            else:
                self.log(f"自动加载上次Cookie失败: {message}", LogLevel.WARNING)
        else:
            self.log("未找到上次使用的Cookie，请手动选择", LogLevel.INFO)
    
    def on_cookie_changed(self):
        """Cookie变更时的处理"""
        cookie_name = self.left_panel.cookie_manager.get_current_cookie_name()
        self.log(f"Cookie已切换: {cookie_name}", LogLevel.SUCCESS)
        self.query_member_info()
        
        # 如果右侧面板当前显示的是公会信息，自动刷新
        if hasattr(self.right_panel, 'current_panel') and self.right_panel.current_panel:
            if isinstance(self.right_panel.current_panel, UnionInfoPanel):
                self.right_panel.current_panel.refresh_info()
    
    def on_function_selected(self, function_name: str):
        """功能菜单选择处理"""
        self.right_panel.switch_panel(function_name)
        
        # 如果选中的是公会信息且当前有Cookie，自动刷新
        if function_name == "公会信息" and self.func.current_cookie_data:
            current_panel = self.right_panel.get_current_panel()
            if current_panel and hasattr(current_panel, 'refresh_info'):
                current_panel.refresh_info()
    
    def query_member_info(self):
        """查询成员信息"""
        if not self.func.current_cookie_data:
            self.left_panel.member_info_card.clear_info()
            self.status_bar.showMessage("请先选择Cookie")
            return
        
        self.status_bar.showMessage("正在获取公会成员信息...")
        
        # 清理旧的worker
        if hasattr(self, 'worker') and self.worker:
            try:
                self.worker.finished.disconnect()
            except:
                pass
            if self.worker.isRunning():
                self.worker.quit()
                self.worker.wait(1000)
        
        self.worker = QueryWorker(self.func)
        self.worker.finished.connect(self.on_member_info_result)
        self.worker.start()
    
    def on_member_info_result(self, success: bool, result):
        """成员信息查询结果处理"""
        if success:
            member_info = self.func.parse_member_info_from_union_of_me(result)
            self.left_panel.member_info_card.update_info(member_info)
            
            if member_info and member_info.get('in_union'):
                self.status_bar.showMessage(f"已加载成员信息: {member_info.get('nickname')}")
                self.log(f"成功获取成员信息: {member_info.get('nickname')}", LogLevel.SUCCESS)
            else:
                msg = member_info.get('message', '未加入公会') if member_info else "未获取到成员信息"
                self.status_bar.showMessage(msg)
                self.log(msg, LogLevel.WARNING)
        else:
            self.log(f"获取成员信息失败: {result}", LogLevel.ERROR)
            self.left_panel.member_info_card.clear_info()
            self.status_bar.showMessage("获取成员信息失败")
    
    def on_log_received(self, message: str, level: str):
        """日志接收处理"""
        self.left_panel.log_browser.append_log(message, level)
    
    def log(self, message: str, level: str = LogLevel.INFO):
        """记录日志"""
        self.func.log(message, level)
    
    def closeEvent(self, event):
        """窗口关闭时的处理"""
        # 清理worker线程
        if hasattr(self, 'worker') and self.worker:
            if self.worker.isRunning():
                self.worker.quit()
                self.worker.wait(1000)
            self.worker.deleteLater()
        
        # 清理右侧面板的worker
        if hasattr(self.right_panel, 'current_panel') and self.right_panel.current_panel:
            if hasattr(self.right_panel.current_panel, 'cleanup_worker'):
                self.right_panel.current_panel.cleanup_worker()
        
        event.accept()


# ==========================================
# 应用程序入口
# ==========================================

def main():
    # 强制禁用Qt自动DPI缩放
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    os.environ["QT_SCALE_FACTOR"] = "1"
    os.environ["QT_SCREEN_SCALE_FACTORS"] = "1"
    
    app = QApplication(sys.argv)
    
    icon_path = os.path.join(CURRENT_DIR, "union.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()