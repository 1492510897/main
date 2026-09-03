"""save_uploader.py

完整的上传存档逻辑实现（Python）。

功能：
- 从本地 XML 文件构建上传负载（zlib 压缩 + base64 编码）
- 计算 verify（与项目中下载逻辑对齐）
- 异步上传单个或批量文件，支持并发和重试
- 支持自动登录获取cookie
- 简单 CLI 调试示例

注意：服务器端解压/验签细节可能与实现差异，若上传失败请贴出服务器响应以便调整压缩或 verify 策略。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import uuid
import zlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp
import requests

DEFAULT_GAME_ID = "100027788"

LOG = logging.getLogger("save_uploader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ==========================================
# 🌐 4399 登录相关函数 (从 cookies.py 移植)
# ==========================================

BASE_URL = "https://ptlogin.4399.com"
LOGIN_VERIFY_URL = f"{BASE_URL}/ptlogin/checkLogin.do"
LOGIN_DO_URL = f"{BASE_URL}/ptlogin/login.do"

LOGIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.4399.com/",
    "Referer": "https://www.4399.com/flash/130396.htm",
}


def check_need_captcha(username: str, session: requests.Session) -> Tuple[bool, Optional[str]]:
    """检查是否需要验证码"""
    session_uuid = str(uuid.uuid4()).replace("-", "").upper()
    session.cookies.set("USESSIONID", session_uuid)
    
    url = (f"{LOGIN_VERIFY_URL}?username={username}"
           f"&appId=kid_wdsj&t={uuid.uuid4()}&inputWidth=iptw2&v=1")
    
    try:
        resp = session.get(url)
        match = re.search(r"/ptlogin/captcha\.do\?captchaId=([\w\d]+)", resp.text)
        if match:
            return True, match.group(1)
        return False, None
    except Exception as e:
        print(f"检查验证码时出错: {e}")
        return False, None


def login_4399(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    执行4399登录操作
    Args:
        username: 账号
        password: 密码
    Returns:
        成功返回cookie_info字典，失败返回None
    """
    with requests.Session() as session:
        session.headers.update(LOGIN_HEADERS)
        
        # 1. 设置初始cookies
        session_uuid = str(uuid.uuid4()).replace("-", "").upper()
        session.cookies.set("USESSIONID", session_uuid)
        session.cookies.set("ptusertype", "kid_wdsj.4399_login")
        
        # 2. 检查是否需要验证码
        need_captcha, captcha_session_id = check_need_captcha(username, session)
        
        if need_captcha:
            print("⚠️ 需要验证码")
            captcha_url = f"{BASE_URL}/ptlogin/captcha.do?captchaId={captcha_session_id}"
            print(f"验证码URL: {captcha_url}")
            
            try:
                resp = session.get(captcha_url)
                if resp.status_code == 200:
                    with open("captcha.jpg", "wb") as f:
                        f.write(resp.content)
                    print("✅ 验证码图片已保存为 captcha.jpg")
                    print("📷 请打开 captcha.jpg 查看验证码")
            except Exception as e:
                print(f"获取验证码图片失败: {e}")
            
            captcha = input("请输入验证码: ").strip()
            if not captcha:
                print("❌ 验证码不能为空")
                return None
        else:
            captcha = ""
            captcha_session_id = None
        
        # 3. 准备登录数据
        login_data = {
            "postLoginHandler": "default",
            "externalLogin": "qq",
            "bizId": "2100001792",
            "appId": "kid_wdsj",
            "gameId": "wd",
            "sec": "1",
            "password": password,
            "username": username,
        }
        
        if captcha and captcha_session_id:
            login_data.update({
                "redirectUrl": "",
                "sessionId": captcha_session_id,
                "inputCaptcha": captcha
            })
        
        # 4. 发送登录请求
        print("正在登录...")
        response = session.post(LOGIN_DO_URL, data=login_data, allow_redirects=False)
        
        print(f"📊 HTTP状态码: {response.status_code}")
        
        if response.status_code == 200:
            raw_cookies = session.cookies.get_dict()
            
            # 构建标准化的Cookie字典
            standard_keys = [
                "USESSIONID", "ptusertype", "Uauth", "Pauth", 
                "ck_accname", "Puser", "Xauth", "Pnick", "Qnick"
            ]
            
            standardized_cookies = {}
            for key in standard_keys:
                standardized_cookies[key] = raw_cookies.get(key, "")
            
            if not standardized_cookies.get("ck_accname"):
                standardized_cookies["ck_accname"] = username

            if not standardized_cookies.get("Uauth") or not standardized_cookies.get("Puser"):
                print("❌ 登录失败：缺少关键Cookie (Uauth 或 Puser)")
                return None
            
            cookie_info = {
                "cookies": standardized_cookies,
                "username": username
            }
            
            # 从 Pauth 中提取 UID
            auth_token = standardized_cookies.get("Pauth", "")
            if auth_token:
                parts = auth_token.split("|")
                if len(parts) > 0 and parts[0]:
                    cookie_info["uid"] = parts[0]
                else:
                    cookie_info["uid"] = "unknown"
            else:
                cookie_info["uid"] = "unknown"
            
            print("✅ 登录成功")
            return cookie_info
        else:
            print(f"❌ 登录失败，HTTP状态码: {response.status_code}")
            return None


# ==========================================
# 📤 上传相关函数
# ==========================================

def calculate_gamekey(game_id: str = DEFAULT_GAME_ID) -> str:
    salt = "LPislKLodlLKKOSNlSDOAADLKADJAOADALAklsd"
    raw = game_id + salt + game_id
    md5 = hashlib.md5(hashlib.md5(raw.encode()).hexdigest().encode()).hexdigest()
    return md5[4:20]


def take_verify(index: str, uid: str, gameid: str, gamekey: str) -> str:
    raw = f"SDALPlsldlnSLWPElsdslSE{index}{gamekey}{uid}{gameid}PKslsO"
    for _ in range(3):
        raw = hashlib.md5(raw.encode()).hexdigest()
    return raw


def prepare_payload(xml_path: str) -> Tuple[str, int]:
    """读取 xml 文件并返回 (base64_compressed_str, original_size)"""
    b = Path(xml_path).read_bytes()
    compressed = zlib.compress(b)
    b64 = base64.b64encode(compressed).decode("utf-8")
    return b64, len(b)


async def upload_single(
    uid: str,
    index: int,
    xml_path: str,
    gameid: str = DEFAULT_GAME_ID,
    gamekey: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout_s: int = 30,
) -> Dict[str, Any]:
    """上传单个 xml 文件到服务器。"""
    if gamekey is None:
        gamekey = calculate_gamekey(gameid)

    try:
        b64_data, orig_size = prepare_payload(xml_path)
    except Exception as e:
        LOG.exception("读取或编码文件失败")
        return {"success": False, "error": f"read_encode_error: {e}"}

    data = {
        "uid": uid,
        "gameid": gameid,
        "gamekey": gamekey,
        "index": str(index),
        "verify": take_verify(str(index), uid, gameid, gamekey),
        "data": b64_data,
        "title": Path(xml_path).stem,
    }

    own_session = False
    if session is None:
        jar = aiohttp.CookieJar()
        session = aiohttp.ClientSession(cookie_jar=jar)
        own_session = True

    if cookies:
        try:
            session.cookie_jar.update_cookies(cookies)
        except Exception:
            pass

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.4399.com/",
            "Origin": "https://www.4399.com",
        }
        async with session.post(
            "https://save.api.4399.com/ranging.php/?ac=save",
            data=data,
            timeout=timeout,
            headers=headers,
        ) as resp:
            text = await resp.text()
        try:
            j = json.loads(text)
        except Exception:
            LOG.debug("非 JSON 响应: %s", text[:200])
            return {"success": False, "status": "nojson", "raw": text}

        LOG.debug("上传响应 JSON: %s", j)
        status = j.get("status")
        if status == 0 or status == "0":
            return {"success": True, "status": status, "json": j}
        else:
            return {"success": False, "status": status, "json": j}
    except Exception as e:
        LOG.exception("上传异常")
        return {"success": False, "error": str(e)}
    finally:
        if own_session:
            await session.close()


async def upload_with_retries(
    uid: str,
    index: int,
    xml_path: str,
    retries: int = 3,
    backoff: float = 1.0,
    session: Optional[aiohttp.ClientSession] = None,
) -> Dict[str, Any]:
    last_err = None
    for attempt in range(1, retries + 1):
        res = await upload_single(uid, index, xml_path, session=session)
        if res.get("success"):
            return {"attempts": attempt, **res}
        last_err = res
        wait = backoff * (2 ** (attempt - 1))
        LOG.info("上传失败，重试 %d/%d，等待 %.1fs", attempt, retries, wait)
        await asyncio.sleep(wait)
    return {"attempts": retries, "success": False, "last": last_err}


async def upload_batch(
    tasks: Iterable[Tuple[str, int, str]],
    concurrency: int = 4,
    retries: int = 3,
    cookies: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """并发批量上传。"""
    sem = asyncio.Semaphore(concurrency)
    results: List[Dict[str, Any]] = []

    async with aiohttp.ClientSession() as session:
        if cookies:
            try:
                session.cookie_jar.update_cookies(cookies)
            except Exception:
                pass

        async def worker(uid: str, index: int, path: str):
            async with sem:
                LOG.info("开始上传 UID=%s index=%s file=%s", uid, index, path)
                r = await upload_with_retries(uid, index, path, retries=retries, session=session)
                LOG.info("上传完成 UID=%s index=%s -> %s", uid, index, r.get("success"))
                results.append({"uid": uid, "index": index, "path": path, "result": r})

        await asyncio.gather(*[worker(uid, idx, p) for uid, idx, p in tasks])

    return results


def find_xml_files(folder: str) -> List[str]:
    p = Path(folder)
    files = list(p.rglob("*.xml"))
    return [str(x) for x in files]


async def login_and_upload_interactive():
    """交互式登录并上传"""
    print("=" * 50)
    print("4399 存档上传工具")
    print("=" * 50)
    
    # 1. 登录
    username = input("请输入账号: ").strip()
    if not username:
        print("❌ 账号不能为空")
        return
    
    password = input("请输入密码: ").strip()
    if not password:
        print("❌ 密码不能为空")
        return
    
    print("\n正在登录...")
    cookie_info = login_4399(username, password)
    if not cookie_info:
        print("❌ 登录失败，请检查账号密码")
        return
    
    uid = cookie_info.get("uid")
    cookies = cookie_info.get("cookies", {})
    
    print(f"✅ 登录成功，UID: {uid}")
    print("-" * 50)
    
    # 2. 选择上传模式
    print("请选择上传模式:")
    print("1) 单文件上传")
    print("2) 批量上传（文件夹）")
    choice = input("选择 (1/2): ").strip()
    
    if choice == "1":
        idx = int(input("存档索引 (0-7): ").strip())
        xml_path = input("XML文件路径: ").strip()
        
        if not Path(xml_path).exists():
            print(f"❌ 文件不存在: {xml_path}")
            return
        
        async def run_single():
            async with aiohttp.ClientSession() as session:
                session.cookie_jar.update_cookies(cookies)
                res = await upload_with_retries(uid, idx, xml_path, session=session)
                print("\n上传结果:")
                print(json.dumps(res, ensure_ascii=False, indent=2))
        
        await run_single()
    
    elif choice == "2":
        folder = input("文件夹路径: ").strip()
        if not Path(folder).exists():
            print(f"❌ 文件夹不存在: {folder}")
            return
        
        files = find_xml_files(folder)
        if not files:
            print("❌ 未找到XML文件")
            return
        
        print(f"找到 {len(files)} 个XML文件")
        
        # 从文件名解析 UID 和 index，或让用户指定
        tasks = []
        for f in files:
            name = Path(f).stem
            parts = name.split("_")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                tasks.append((parts[0], int(parts[1]), f))
            else:
                # 使用登录获取的UID，让用户指定index
                idx = int(input(f"文件 {Path(f).name} 的索引 (0-7): ").strip())
                tasks.append((uid, idx, f))
        
        print(f"\n准备上传 {len(tasks)} 个文件...")
        results = await upload_batch(tasks, cookies=cookies)
        print("\n批量上传结果:")
        print(json.dumps(results, ensure_ascii=False, indent=2))
    
    else:
        print("❌ 无效选择")


# ==========================================
# 🚀 命令行入口
# ==========================================

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="4399存档上传工具")
    parser.add_argument("--login", action="store_true", help="交互式登录并上传")
    parser.add_argument("--uid", help="指定UID（跳过登录）")
    parser.add_argument("--index", type=int, help="存档索引 (0-7)")
    parser.add_argument("--xml", help="XML文件路径")
    parser.add_argument("--folder", help="文件夹路径（批量上传）")
    parser.add_argument("--cookies-file", help="从文件加载cookies")
    parser.add_argument("--try-variants", action="store_true", help="尝试不同压缩变体（诊断用）")
    
    args = parser.parse_args()
    
    # 交互式登录模式
    if args.login:
        asyncio.run(login_and_upload_interactive())
        return
    
    # 从文件加载cookies
    cookies_dict = None
    uid = args.uid
    
    if args.cookies_file:
        try:
            j = json.loads(Path(args.cookies_file).read_text(encoding="utf-8"))
            if isinstance(j, dict) and "cookies" in j:
                cookies_dict = j.get("cookies")
                if not uid:
                    uid = j.get("uid")
            elif isinstance(j, dict):
                cookies_dict = j
        except Exception as e:
            print(f"❌ 加载cookies文件失败: {e}")
            return
    
    # 单文件上传
    if args.xml and uid and args.index is not None:
        if args.try_variants:
            asyncio.run(try_upload_variants_async(uid, args.index, args.xml))
        else:
            async def run_one():
                async with aiohttp.ClientSession() as session:
                    if cookies_dict:
                        session.cookie_jar.update_cookies(cookies_dict)
                    res = await upload_with_retries(uid, args.index, args.xml, session=session)
                    print(json.dumps(res, ensure_ascii=False, indent=2))
            asyncio.run(run_one())
        return
    
    # 批量上传
    if args.folder and uid:
        files = find_xml_files(args.folder)
        tasks = []
        for f in files:
            name = Path(f).stem
            parts = name.split("_")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                tasks.append((parts[0], int(parts[1]), f))
            elif args.index is not None:
                tasks.append((uid, args.index, f))
            else:
                print(f"⚠️ 跳过文件 {Path(f).name}，无法解析索引")
        
        if tasks:
            async def run_batch():
                res = await upload_batch(tasks, cookies=cookies_dict)
                print(json.dumps(res, ensure_ascii=False, indent=2))
            asyncio.run(run_batch())
        return
    
    # 如果没有参数，进入交互模式
    asyncio.run(login_and_upload_interactive())


async def try_upload_variants_async(uid: str, index: int, xml_path: str, gameid: str = DEFAULT_GAME_ID):
    """尝试不同的压缩/编码和表单类型，打印服务器原始响应"""
    gamekey = calculate_gamekey(gameid)
    b = Path(xml_path).read_bytes()

    variants = [
        ("zlib", base64.b64encode(zlib.compress(b)).decode()),
    ]
    # raw deflate
    co = zlib.compressobj(wbits=-15)
    raw_def = co.compress(b) + co.flush()
    variants.append(("deflate_raw", base64.b64encode(raw_def).decode()))
    variants.append(("base64_raw", base64.b64encode(b).decode()))

    async with aiohttp.ClientSession() as session:
        for mode, b64 in variants:
            data = {
                "uid": uid,
                "gameid": gameid,
                "gamekey": gamekey,
                "index": str(index),
                "verify": take_verify(str(index), uid, gameid, gamekey),
                "data": b64,
                "title": Path(xml_path).stem,
            }
            try:
                async with session.post("https://save.api.4399.com/ranging.php/?ac=save", data=data, timeout=15) as resp:
                    text = await resp.text()
                    print(f"MODE={mode} / form -> status={resp.status} body={text[:400]}")
            except Exception as e:
                print(f"MODE={mode} / form -> exception: {e}")


if __name__ == "__main__":
    main()