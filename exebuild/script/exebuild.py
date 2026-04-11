import subprocess
import sys
import os
import shutil

# ================= 配置区域 =================
MAIN_FILE = "v6.8.0.py"       # 主程序入口文件
OUTPUT_DIR = "dist_pyinstaller" # 打包输出目录
ICON_FILE = "ENCRYPT_TOOL.ico"  # 图标文件
VERSION_FILE = "version_info.txt" # 版本信息文件
EXE_NAME = "作弊检测工具v1.7.0.0" # 生成的 exe 文件名
# ===========================================

def check_files():
    """检查必要文件是否存在"""
    missing = []
    if not os.path.exists(MAIN_FILE):
        missing.append(f"主程序: {MAIN_FILE}")
    if not os.path.exists(ICON_FILE):
        missing.append(f"图标: {ICON_FILE}")
    if not os.path.exists(VERSION_FILE):
        missing.append(f"版本文件: {VERSION_FILE}")
    
    if missing:
        print("❌ 错误：找不到以下必要文件，无法打包！")
        for f in missing:
            print(f"   - {f}")
        return False
    
    print("✅ 文件检查通过")
    return True

def build():
    print("="*50)
    print("🚀 PyInstaller 自动打包启动 (单文件模式)")
    print("="*50)

    # 1. 环境检查
    if not check_files():
        sys.exit(1)
    
    # 2. 检查 PyInstaller
    try:
        subprocess.run(["pyinstaller", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n⚠️ 未检测到 PyInstaller，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "pillow"], check=True)
        print("✅ PyInstaller 安装完成")

    # 3. 清理旧文件
    for folder in ["build", OUTPUT_DIR]:
        if os.path.exists(folder):
            print(f"🧹 清理旧目录: {folder}...")
            shutil.rmtree(folder)

    # 4. 构建命令
    cmd = [
        "pyinstaller",
        "--name", EXE_NAME,
        "--onefile",             # 【已恢复】单文件模式
        "--noconsole",           # 隐藏控制台窗口
        "--clean",               # 清除缓存
        "--icon", ICON_FILE,     # 设置图标
        "--version-file", VERSION_FILE,
        "--distpath", OUTPUT_DIR,# 指定输出目录
        "--workpath", "build",
        "--specpath", ".",
        
        # === 依赖库配置 ===
        # 修复了 chardet.pipeline 不存在的问题
        # 增加了 pycryptodome 以确保 Crypto 库能被正确识别
        "--hidden-import=pycryptodome",
        "--hidden-import=Crypto",
        "--hidden-import=Crypto.Cipher",
        "--hidden-import=Crypto.Util",
        "--hidden-import=Crypto.Hash",
        
        MAIN_FILE
    ]

    print(f"\n📦 正在打包: {MAIN_FILE}")
    print(f"🖼️  使用图标: {ICON_FILE}")
    print(f"📂 输出目录: {OUTPUT_DIR}")
    print("-" * 50)
    print("⏳ 编译中...")
    print("-" * 50)

    # 5. 执行
    try:
        subprocess.run(cmd, check=True, shell=True)
        
        # 单文件模式下，exe 直接在 OUTPUT_DIR 下
        exe_path = os.path.join(OUTPUT_DIR, f"{EXE_NAME}.exe")
        
        print("\n" + "="*50)
        if os.path.exists(exe_path):
            file_size = os.path.getsize(exe_path) / (1024 * 1024)
            print("✅ ✅ ✅  打包成功！  ✅ ✅ ✅")
            print(f"📂 位置: {os.path.abspath(exe_path)}")
            print(f"📏 大小: {file_size:.2f} MB")
            print("\n💡 分发提示:")
            print(f"   直接分发这个 exe 文件即可")
            print("   确保 v1.0.bin 与 exe 文件在同一目录下！")
        else:
            print("⚠️ 警告: 未找到生成的 exe 文件。")
        print("="*50)
        
    except subprocess.CalledProcessError:
        print("\n❌ 打包失败！请检查上方错误日志。")
        print("💡 常见原因: 代码语法错误 或 缺少库 (pip install <库名>)")
        sys.exit(1)

if __name__ == "__main__":
    build()