import os
import sys
import argparse
import pandas as pd
from pathlib import Path


def merge_csv_files(
    input_path: str,
    output_file: str = "merged_output.csv",
    add_source_column: bool = False,
    encoding: str = "utf-8",
    output_encoding: str = "utf-8-sig"
):
    input_path = Path(input_path)
    all_frames = []
    
    # 获取需要处理的文件列表
    if input_path.is_file() and input_path.suffix.lower() == ".csv":
        csv_files = [input_path]
    elif input_path.is_dir():
        csv_files = sorted(list(input_path.glob("*.csv")))
    else:
        print(f"[错误] 路径不存在或不是有效的 CSV/文件夹: {input_path}")
        return

    if not csv_files:
        print("[警告] 未找到任何 CSV 文件。")
        return

    print(f"🔍 找到 {len(csv_files)} 个 CSV 文件，开始合并...")

    for file in csv_files:
        try:
            df = pd.read_csv(file, encoding=encoding)
            if add_source_column:
                df.insert(0, "source_file", file.name)
            all_frames.append(df)
            print(f"  ✅ 成功读取: {file.name} ({len(df)} 行)")
        except Exception as e:
            print(f"  ❌ 读取失败: {file.name} | 错误: {e}")

    if not all_frames:
        print("[警告] 没有成功读取任何文件，跳过合并。")
        return

    merged_df = pd.concat(all_frames, ignore_index=True)
    
    # 如果输出文件名没有带路径，默认输出到脚本所在的文件夹
    output_path = Path(output_file)
    if not output_path.is_absolute() and str(output_path) == output_file:
        output_path = script_dir / output_file

    merged_df.to_csv(output_path, index=False, encoding=output_encoding)
    print(f"\n🎉 合并完成！")
    print(f"   总行数: {len(merged_df)} | 总列数: {len(merged_df.columns)}")
    print(f"   输出文件: {os.path.abspath(output_path)}")


if __name__ == "__main__":
    # 获取当前脚本所在的绝对路径
    script_dir = Path(sys.argv[0]).resolve().parent

    parser = argparse.ArgumentParser(description="🛠️ Python CSV 文件合并工具")
    # 将 input 改为可选参数，默认值为脚本所在文件夹
    parser.add_argument("input", nargs="?", default=str(script_dir), 
                        help="输入路径（CSV 文件 或 包含 CSV 的文件夹，默认: 脚本所在目录）")
    parser.add_argument("-o", "--output", default="merged_output.csv", help="输出文件名 (默认: merged_output.csv)")
    parser.add_argument("-s", "--source", action="store_true", help="添加 'source_file' 列标记数据来源")
    parser.add_argument("-e", "--encoding", default="utf-8", help="输入文件编码 (默认: utf-8)")
    parser.add_argument("-oe", "--output-encoding", default="utf-8-sig", help="输出文件编码 (默认: utf-8-sig)")

    args = parser.parse_args()
    merge_csv_files(
        input_path=args.input,
        output_file=args.output,
        add_source_column=args.source,
        encoding=args.encoding,
        output_encoding=args.output_encoding
    )


