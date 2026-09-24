"""
统一路径解析模块（修复“路径混乱”）
====================================
修复前的问题：
  • main.py / info_get.py 的所有相对路径（config.ini / inputdata / outputdata /
    test / 价格表 bin / work_dir）都以“启动时的当前工作目录 os.getcwd()”为基准；
    从不同目录启动同一个程序，读写位置就不同 —— 比如从仓库根目录启动时，
    会在根目录另建一整套 config/inputdata/outputdata，而 main/config.ini 里保存的
    相对 work_dir 又随启动目录漂移，出现 main\\main\\test 之类错误拼法；
  • info_get.py 在 import 时就把 work_dir 求值成 BASE_SAVE_DIR，主程序设置页改了
    work_dir 也不生效，必须重启；
  • 打包成 EXE 后 os.getcwd() 可能是任意目录，资源（main.ico）与配置文件找不到。

修复后的策略（唯一基准 = 程序自身所在目录，而不是启动目录）：
  • PROGRAM_DIR   程序目录：打包(EXE) → EXE 所在目录；源码运行 → 脚本所在目录；
  • RESOURCE_DIR  资源目录：打包 → PyInstaller 解包目录(_MEIPASS)；否则同 PROGRAM_DIR；
  • 配置/输入里的相对路径一律按“相对 PROGRAM_DIR”解析；为兼容历史值
    （如 work_dir = main\\test，是当年从上级目录启动时写入的），
    当 PROGRAM_DIR 下的解析结果不存在、而 PROGRAM_DIR 的上级存在时，取上级结果；
  • 只读资源（价格表/对照表/图标）额外优先查找打包资源目录；
  • 需要写回 config.ini 时用 to_config_path()，位于程序目录内的一律写成
    “.\\相对路径”（可迁移），程序目录之外才写绝对路径。
"""
from __future__ import annotations

import os
import sys

__all__ = [
    "PROGRAM_DIR", "RESOURCE_DIR", "program_dir", "resource_path",
    "resolve", "resolve_input", "ensure_dir", "in_program_dir", "to_config_path",
]


def program_dir() -> str:
    """程序目录（绝对路径）：EXE → EXE 所在目录；源码 → 脚本所在目录。"""
    if getattr(sys, "frozen", False):
        exe = getattr(sys, "executable", "") or ""
        if exe:
            return os.path.dirname(os.path.abspath(exe))
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # 极端情况：交互式执行时没有 __file__
        return os.path.abspath(os.getcwd())


PROGRAM_DIR = program_dir()
PROGRAM_PARENT_DIR = os.path.dirname(PROGRAM_DIR)


def _resource_dir() -> str:
    """打包资源目录（PyInstaller --add-data 的解包目录），未打包时同程序目录。"""
    meipass = getattr(sys, "_MEIPASS", None)
    return os.path.abspath(meipass) if meipass else PROGRAM_DIR


RESOURCE_DIR = _resource_dir()


def in_program_dir(*parts: str) -> str:
    """拼出程序目录下的绝对路径，如 in_program_dir('inputdata', 'x.bin')。"""
    return os.path.join(PROGRAM_DIR, *parts)


def _clean(text) -> str:
    """去掉首尾空白与包裹的引号，并展开 %VAR% / ~。"""
    value = str(text).strip().strip('"').strip("'")
    return os.path.expandvars(os.path.expanduser(value))


def resolve(path, default=None, *, prefer_existing: bool = True) -> str | None:
    """把配置里的用户路径解析为绝对路径。

    • 空值            → 使用 default（同样解析；default 也为空则返回 None）
    • 绝对路径        → 规范化后原样返回
    • 相对路径        → 相对 PROGRAM_DIR；若 PROGRAM_DIR 下不存在、而上级目录存在，
                        则取上级目录结果（兼容 main\\test 这类历史写法）
    """
    raw = path if (path is not None and str(path).strip()) else default
    if raw is None:
        return None
    text = _clean(raw)
    if not text:
        return None
    if os.path.isabs(text):
        return os.path.normpath(text)

    primary = os.path.normpath(os.path.join(PROGRAM_DIR, text))
    if prefer_existing and not os.path.exists(primary) and PROGRAM_PARENT_DIR:
        alt = os.path.normpath(os.path.join(PROGRAM_PARENT_DIR, text))
        if alt != primary and os.path.exists(alt):
            return alt
    return primary


def resolve_input(path, default=None) -> str | None:
    """只读资源（价格表 bin / good_items.csv 等）解析为绝对路径。

    相对路径优先找打包资源目录(RESOURCE_DIR)，其次程序目录；
    都不存在时返回“程序目录下的拼法”（便于报错时提示用户配置了什么）。
    """
    raw = path if (path is not None and str(path).strip()) else default
    if raw is None:
        return None
    text = _clean(raw)
    if not text:
        return None
    if os.path.isabs(text):
        return os.path.normpath(text)

    candidates = []
    for base in (RESOURCE_DIR, PROGRAM_DIR):
        cand = os.path.normpath(os.path.join(base, text))
        if cand not in candidates:
            candidates.append(cand)
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return candidates[-1]


def resource_path(relative_path) -> str:
    """资源文件绝对路径：打包解包目录 → 程序目录 → 上级目录 → 当前目录。

    （旧版直接以 os.getcwd() 为基准，从别处启动就找不到 main.ico 等资源。）
    """
    text = str(relative_path)
    if os.path.isabs(text):
        return os.path.normpath(text)
    candidates = []
    for base in (RESOURCE_DIR, PROGRAM_DIR, PROGRAM_PARENT_DIR, os.getcwd()):
        if not base:
            continue
        cand = os.path.normpath(os.path.join(base, text))
        if cand in candidates:
            continue
        candidates.append(cand)
        if os.path.exists(cand):
            return cand
    return candidates[0]


def ensure_dir(path) -> str | None:
    """解析路径并确保目录存在（用于输出目录）。"""
    target = resolve(path)
    if target and not os.path.isdir(target):
        os.makedirs(target, exist_ok=True)
    return target


def to_config_path(path, base=None) -> str:
    """把路径转成适合写进 config.ini 的写法。

    位于“程序目录”（base，默认 PROGRAM_DIR）内部 → 写成 .\\相对路径，保持配置
    可随程序目录整体迁移；程序目录之外 → 保留绝对路径，避免歧义。
    """
    if path is None or not str(path).strip():
        return path
    text = _clean(path)
    if not os.path.isabs(text):
        return text
    normalized = os.path.normpath(text)
    base_dir = base or PROGRAM_DIR
    try:
        rel = os.path.relpath(normalized, base_dir)
    except ValueError:
        return normalized
    if rel == ".":
        return "."
    if rel.startswith(".."):
        return normalized
    return os.path.join(".", rel)
