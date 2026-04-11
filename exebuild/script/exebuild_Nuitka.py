import subprocess
import sys
import os
import re

# ================= 配置区域 =================
DEFAULT_MAIN_FILE = "v6.1.0.py" 
OUTPUT_DIR = "dist"
ICON_FILE = "ENCRYPT_TOOL.ico"

# ✅ 修复：显式列出需要打包的非标准文件 (如 .bin, .dat 等)
# 格式：(源文件路径, 打包后在程序内的相对路径)
DATA_FILES = [
    ("inputdata/v1.0.bin", "inputdata/v1.0.bin"),
    # 如果有更多文件，可以在这里继续加，例如：
    # ("config/settings.json", "config/settings.json"),
]
# ===========================================

def get_main_file():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return DEFAULT_MAIN_FILE

def analyze_imports(filename):
    imports = set()
    std_libs = {
        'tkinter', 'os', 'sys', 'hashlib', 'base64', 'datetime', 're', 
        'csv', 'io', 'configparser', 'xml', 'json', 'math', 'time', 
        'threading', 'multiprocessing', 'socket', 'http', 'urllib',
        'functools', 'collections', 'typing', 'pathlib', 'subprocess'
    }
    
    if not os.path.exists(filename):
        print(f"❌ 错误: 找不到文件 '{filename}'")
        sys.exit(1)

    print(f"📄 正在分析文件: {filename}")
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
        
    patterns = [
        r'^import\s+([\w\.]+)',
        r'^from\s+([\w\.]+)\s+import'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content, re.MULTILINE)
        for match in matches:
            top_module = match.split('.')[0]
            if top_module not in std_libs:
                imports.add(top_module)
                
    return list(imports)

def build():
    main_file = get_main_file()
    print(f"🔍 正在分析 {main_file} 的依赖...")
    
    third_party_libs = analyze_imports(main_file)
    
    if third_party_libs:
        print(f"📦 检测到第三方库: {third_party_libs}")
    else:
        print(f"📦 检测到第三方库: 无 (全是标准库)")
    
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone", 
        "--python-flag=-O",
        "--lto=yes",
        "--windows-disable-console",
        "--assume-yes-for-downloads",
        f"--output-dir={OUTPUT_DIR}",
        main_file
    ]
    
    # 图标
    if ICON_FILE and os.path.exists(ICON_FILE):
        cmd.append(f"--windows-icon-from-ico={ICON_FILE}")
        print(f"✅ 已添加图标: {ICON_FILE}")
    elif ICON_FILE:
        print(f"⚠️ 警告: 未找到图标文件 {ICON_FILE}")

    # 第三方库
    for lib in third_party_libs:
        cmd.append(f"--include-package={lib}")
        print(f"🔗 显式包含库: {lib}")

    # ✅ 核心修复：显式包含 .bin 文件
    for src_path, dest_path in DATA_FILES:
        if os.path.exists(src_path):
            cmd.append(f"--include-data-file={src_path}={dest_path}")
            print(f"📄 已包含数据文件: {src_path}")
        else:
            print(f"⚠️ 严重警告: 未找到数据文件 {src_path}，程序运行可能会报错！")

    print("\n🚀 开始编译 (这可能需要几分钟)...")
    print("-" * 30)
    
    try:
        subprocess.run(cmd, check=True)
        
        base_name = os.path.splitext(os.path.basename(main_file))[0]
        output_folder = os.path.join(OUTPUT_DIR, f"{base_name}.dist")
        
        print("\n" + "="*30)
        print("✅ 打包成功！")
        if os.path.exists(output_folder):
            print(f"📂 产物位置: {os.path.abspath(output_folder)}")
            
            # 验证 .bin 文件是否真的进去了
            bin_in_dist = os.path.join(output_folder, "inputdata", "v1.0.bin")
            if os.path.exists(bin_in_dist):
                print(f"✅ 验证通过：v1.0.bin 已成功打包到 dist 目录！")
            else:
                print(f"❌ 验证失败：v1.0.bin 未在 dist 目录找到，请检查代码逻辑。")
                
            print("💡 请将整个文件夹压缩分发给用户。")
        else:
            print(f"⚠️ 未在预期位置找到输出文件夹。")
        print("="*30)
        
    except subprocess.CalledProcessError as e:
        print("\n❌ 打包失败！")
        sys.exit(1)

if __name__ == "__main__":
    build()