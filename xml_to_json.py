#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xml_objects_to_json.py
读取 XML，导出所有 type="Object" 的节点为 JSON（默认最多到第 2 层）。

用法:
    python xml_objects_to_json.py "路径.xml"
    python xml_objects_to_json.py "路径.xml" --depth 3 -o objects.json
    python xml_objects_to_json.py            # 无参数 -> 交互输入
"""

import argparse
import json
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


def collect_objects(elem, depth=0, max_depth=2, path=""):
    """递归收集所有 type='Object' 的节点，超过 max_depth 就停止递归。"""
    rows = []
    name = elem.attrib.get('name', '')
    typ = elem.attrib.get('type', '')

    cur_path = f"{path}/{name}" if (path and name) else (path or name)
    is_obj = (typ == 'Object')

    if is_obj:
        item = {
            "path": cur_path,
            "type": typ,
            "name": name,
            "depth": depth,
        }
        other = {k: v for k, v in elem.attrib.items() if k not in ('type', 'name')}
        if other:
            item["attrs"] = other
        rows.append(item)

    # 到达深度上限就停止往下递归
    if depth >= max_depth:
        return rows

    for child in elem:
        rows.extend(collect_objects(
            child,
            depth=depth + 1,
            max_depth=max_depth,
            path=cur_path if is_obj else path,
        ))

    return rows


def process_file(xml_path: Path, max_depth: int):
    root = ET.parse(xml_path).getroot()
    # 根节点算第 0 层
    return collect_objects(root, depth=0, max_depth=max_depth)


def prompt_path() -> Path:
    print("请输入 XML 文件或文件夹路径（可直接拖拽文件到窗口）：")
    while True:
        raw = input("> ").strip().strip('"').strip("'")
        if not raw:
            print("路径不能为空，请重新输入。")
            continue
        p = Path(raw)
        if p.exists():
            return p
        print(f"路径不存在：{p}\n请重新输入。")


def gather_xml_files(p: Path):
    if p.is_file():
        return [p]
    if p.is_dir():
        files = sorted(p.rglob("*.xml"))
        if not files:
            print(f"目录下没有找到 .xml 文件：{p}")
        return files
    return []


def main():
    ap = argparse.ArgumentParser(description='导出 XML 中所有 Object 节点为 JSON（默认到第 2 层）')
    ap.add_argument('input', nargs='*',
                    help='输入 XML 文件或文件夹路径（省略则进入交互输入）')
    ap.add_argument('-o', '--output', default='objects.json',
                    help='输出 JSON 路径（默认 objects.json）')
    ap.add_argument('--depth', type=int, default=2,
                    help='最大导出深度（根为第 0 层，默认 2）')
    ap.add_argument('--indent', type=int, default=2)
    args = ap.parse_args()

    if args.input:
        raw = ' '.join(args.input).strip().strip('"').strip("'")
        src = Path(raw)
    else:
        src = prompt_path()

    if not src.exists():
        print(f"路径不存在：{src}")
        sys.exit(1)

    xml_files = gather_xml_files(src)
    if not xml_files:
        sys.exit(1)

    if len(xml_files) == 1:
        result = process_file(xml_files[0], args.depth)
    else:
        result = {f.name: process_file(f, args.depth) for f in xml_files}

    text = json.dumps(result, ensure_ascii=False, indent=args.indent)
    out_path = Path(args.output)
    out_path.write_text(text, encoding='utf-8')

    count = len(xml_files) if isinstance(result, dict) else 1
    total = (sum(len(v) for v in result.values())
             if isinstance(result, dict) else len(result))
    print(f'已处理 {count} 个文件，共 {total} 个 Object 节点（深度≤{args.depth}）-> {out_path.resolve()}')


if __name__ == '__main__':
    main()