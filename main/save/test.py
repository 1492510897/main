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
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")


# ==========================================
# 🌐 4399 登录相关函数 (使用正确API)
# ==========================================

def login_4399(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    执行4399登录操作 - 使用正确的登录流程
    Args:
        username: 账号
        password: 密码
    Returns:
        成功返回cookie_info字典，失败返回None
    """
    session = requests.Session()
    
    # 第一步：访问登录页面获取必要的cookie
    login_page_url = "https://ptlogin.4399.com/ptlogin/login.do?appId=www_home&fromurl=https%3A%2F%2Fwww.4399.com%2F"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        # 访问登录页面获取初始cookie
        resp = session.get(login_page_url, headers=headers)
        print(f"📊 登录页面状态: {resp.status_code}")
        
        # 获取必要的cookie
        session.cookies.set("domain", ".4399.com")
        
        # 第二步：构建登录请求
        login_url = "https://ptlogin.4399.com/ptlogin/login.do"
        
        # 生成必要的参数
        login_data = {
            "loginFrom": "uframe",
            "postLoginHandler": "default",
            "layoutSelfAdapting": "true",
            "externalLogin": "qq",
            "displayMode": "popup",
            "layout": "vertical",
            "appId": "www_home",
            "gameId": "",
            "cssId": "//www.4399.com/css/ptlogin.css",
            "redirectUrl": "https://www.4399.com/",
            "sessionId": "",
            "mainDivId": "ptloginIframe",
            "includeFcmInfo": "false",
            "level": "0",
            "userNameLabel": "4399用户名",
            "userNameTip": "请输入4399用户名",
            "welcomeTip": "欢迎回来",
            "sec": "1",
            "password": password,
            "username": username,
        }
        
        print("正在登录...")
        response = session.post(
            login_url,
            data=login_data,
            headers=headers,
            allow_redirects=False
        )
        
        print(f"📊 登录响应状态: {response.status_code}")
        
        if response.status_code == 302:
            # 登录成功，获取重定向后的cookie
            location = response.headers.get("Location", "")
            print(f"📍 重定向到: {location}")
            
            # 跟随重定向获取最终cookie
            if location:
                session.get(location, headers=headers)
            
            # 获取所有cookie
            raw_cookies = session.cookies.get_dict()
            print(f"🍪 获取到的Cookie: {list(raw_cookies.keys())}")
            
            # 构建标准化的Cookie字典
            all_cookies = {}
            for key, value in raw_cookies.items():
                all_cookies[key] = value
            
            # 检查关键cookie
            if not all_cookies.get("Uauth"):
                print("⚠️ 未获取到 Uauth，尝试登录游戏页面...")
                # 尝试访问游戏页面获取更多cookie
                game_url = "https://www.4399.com/flash/130396.htm"
                game_resp = session.get(game_url, headers=headers)
                raw_cookies.update(session.cookies.get_dict())
                all_cookies.update(raw_cookies)
            
            # 确保关键字段存在
            if not all_cookies.get("Uauth"):
                print("❌ 登录失败：缺少关键Cookie Uauth")
                return None
            
            # 生成新的USESSIONID
            session_uuid = str(uuid.uuid4()).replace("-", "").upper()
            all_cookies["USESSIONID"] = session_uuid
            
            cookie_info = {
                "cookies": all_cookies,
                "username": username
            }
            
            # 从Puser获取UID
            uid = all_cookies.get("Puser", "")
            if not uid:
                # 尝试从其他字段获取
                uid = all_cookies.get("ck_accname", username)
            cookie_info["uid"] = uid
            
            print("✅ 登录成功")
            print(f"  UID: {uid}")
            print(f"  USESSIONID: {session_uuid[:20]}...")
            print(f"  Uauth: {all_cookies.get('Uauth', '')[:20]}...")
            print(f"  Puser: {all_cookies.get('Puser', '')}")
            print(f"  Pauth: {all_cookies.get('Pauth', '')[:20] if all_cookies.get('Pauth') else 'None'}...")
            
            return cookie_info
            
        elif response.status_code == 200:
            # 可能返回了错误页面或验证码
            if "验证码" in response.text or "captcha" in response.text.lower():
                print("⚠️ 需要验证码")
                # 尝试获取验证码图片
                try:
                    captcha_match = re.search(r'captchaId=([\w\d]+)', response.text)
                    if captcha_match:
                        captcha_id = captcha_match.group(1)
                        captcha_url = f"https://ptlogin.4399.com/ptlogin/captcha.do?captchaId={captcha_id}"
                        captcha_resp = session.get(captcha_url)
                        with open("captcha.jpg", "wb") as f:
                            f.write(captcha_resp.content)
                        print("✅ 验证码图片已保存为 captcha.jpg")
                        captcha = input("请输入验证码: ").strip()
                        
                        # 重新提交带验证码的登录
                        login_data["captcha"] = captcha
                        login_data["captchaId"] = captcha_id
                        
                        response = session.post(
                            login_url,
                            data=login_data,
                            headers=headers,
                            allow_redirects=False
                        )
                        
                        if response.status_code == 302:
                            # 重试登录成功
                            location = response.headers.get("Location", "")
                            if location:
                                session.get(location, headers=headers)
                            
                            raw_cookies = session.cookies.get_dict()
                            all_cookies = {}
                            for key, value in raw_cookies.items():
                                all_cookies[key] = value
                            
                            session_uuid = str(uuid.uuid4()).replace("-", "").upper()
                            all_cookies["USESSIONID"] = session_uuid
                            
                            cookie_info = {
                                "cookies": all_cookies,
                                "username": username
                            }
                            uid = all_cookies.get("Puser", username)
                            cookie_info["uid"] = uid
                            
                            print("✅ 登录成功")
                            return cookie_info
                except Exception as e:
                    print(f"处理验证码失败: {e}")
            
            print("❌ 登录失败，请检查账号密码")
            return None
        else:
            print(f"❌ 登录失败，状态码: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ 登录异常: {e}")
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
    debug: bool = False,
) -> Dict[str, Any]:
    """上传单个 xml 文件到服务器。"""
    if gamekey is None:
        gamekey = calculate_gamekey(gameid)

    try:
        b64_data, orig_size = prepare_payload(xml_path)
    except Exception as e:
        LOG.exception("读取或编码文件失败")
        return {"success": False, "error": f"read_encode_error: {e}"}

    # 计算 verify
    verify = take_verify(str(index), uid, gameid, gamekey)
    
    data = {
        "uid": uid,
        "gameid": gameid,
        "gamekey": gamekey,
        "index": str(index),
        "verify": verify,
        "data": b64_data,
        "title": Path(xml_path).stem,
    }

    if debug:
        print(f"\n🔍 调试信息:")
        print(f"  UID: {uid}")
        print(f"  Index: {index}")
        print(f"  GameID: {gameid}")
        print(f"  GameKey: {gamekey}")
        print(f"  Verify: {verify}")
        print(f"  Title: {Path(xml_path).stem}")
        print(f"  Data长度: {len(b64_data)}")
        print(f"  原始大小: {orig_size} bytes")

    own_session = False
    if session is None:
        jar = aiohttp.CookieJar()
        session = aiohttp.ClientSession(cookie_jar=jar)
        own_session = True

    # 注入 Cookie
    if cookies:
        try:
            session.cookie_jar.clear()
            session.cookie_jar.update_cookies(cookies)
            if debug:
                print(f"  Cookies已注入: {list(cookies.keys())}")
        except Exception as e:
            print(f"  Cookie设置失败: {e}")

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.4399.com/",
            "Origin": "https://www.4399.com",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        
        url = "https://save.api.4399.com/ranging.php/?ac=save"
        
        if debug:
            print(f"\n📤 发送请求:")
            print(f"  URL: {url}")
            print(f"  Data keys: {list(data.keys())}")
        
        async with session.post(
            url,
            data=data,
            timeout=timeout,
            headers=headers,
        ) as resp:
            text = await resp.text()
            
            if debug:
                print(f"\n📥 服务器响应:")
                print(f"  Status: {resp.status}")
                print(f"  Body: {text[:500]}")
            
            # 检查响应
            if "multiple_session" in text:
                return {
                    "success": False, 
                    "status": "multiple_session", 
                    "raw": text,
                    "message": "会话冲突 - 请重新登录"
                }
            
            if "action_error" in text:
                return {
                    "success": False, 
                    "status": "action_error", 
                    "raw": text,
                    "message": "认证或参数错误"
                }
            
            # 尝试解析JSON
            try:
                j = json.loads(text)
                status = j.get("status")
                
                if status == 0 or status == "0":
                    return {"success": True, "status": status, "json": j}
                else:
                    return {"success": False, "status": status, "json": j}
            except Exception:
                return {"success": False, "status": "nojson", "raw": text}
                
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
    debug: bool = False,
) -> Dict[str, Any]:
    last_err = None
    for attempt in range(1, retries + 1):
        print(f"\n🔄 尝试 {attempt}/{retries}")
        res = await upload_single(uid, index, xml_path, session=session, debug=debug)
        if res.get("success"):
            return {"attempts": attempt, **res}
        last_err = res
        
        if res.get("status") in ["multiple_session", "action_error"]:
            print(f"❌ {res.get('message', '错误')}")
            return {"attempts": attempt, "success": False, "last": res}
            
        wait = backoff * (2 ** (attempt - 1))
        await asyncio.sleep(wait)
    return {"attempts": retries, "success": False, "last": last_err}


def demo_single(cookies_dict: Optional[Dict[str, str]] = None):
    """单文件上传"""
    print("\n" + "="*50)
    print("单文件上传")
    print("="*50)
    
    uid = None
    cookies = cookies_dict
    
    if not cookies:
        print("请先登录获取cookie")
        username = input("账号: ").strip()
        password = input("密码: ").strip()
        
        if not username or not password:
            print("❌ 账号密码不能为空")
            return
        
        cookie_info = login_4399(username, password)
        if not cookie_info:
            print("❌ 登录失败")
            return
        
        uid = cookie_info.get("uid")
        cookies = cookie_info.get("cookies", {})
        print(f"✅ 登录成功，UID: {uid}")
    else:
        uid = cookies.get("Puser") or cookies.get("uid")
        if not uid:
            uid = input("请输入UID: ").strip()
    
    print(f"\n当前用户: {uid}")
    
    idx = int(input("\n存档索引 (0-7): ").strip())
    xml_path = input("XML文件路径: ").strip()
    
    if not Path(xml_path).exists():
        print(f"❌ 文件不存在: {xml_path}")
        return
    
    debug = input("是否开启调试模式? (y/n): ").strip().lower() == 'y'
    
    async def run():
        async with aiohttp.ClientSession() as session:
            session.cookie_jar.update_cookies(cookies)
            res = await upload_with_retries(uid, idx, xml_path, session=session, debug=debug)
            print("\n📊 上传结果:")
            print(json.dumps(res, ensure_ascii=False, indent=2))
    
    asyncio.run(run())


def demo_folder(cookies_dict: Optional[Dict[str, str]] = None):
    """批量上传"""
    print("\n" + "="*50)
    print("批量上传")
    print("="*50)
    
    uid = None
    cookies = cookies_dict
    
    if not cookies:
        print("请先登录获取cookie")
        username = input("账号: ").strip()
        password = input("密码: ").strip()
        
        if not username or not password:
            print("❌ 账号密码不能为空")
            return
        
        cookie_info = login_4399(username, password)
        if not cookie_info:
            print("❌ 登录失败")
            return
        
        uid = cookie_info.get("uid")
        cookies = cookie_info.get("cookies", {})
        print(f"✅ 登录成功，UID: {uid}")
    else:
        uid = cookies.get("Puser") or cookies.get("uid")
        if not uid:
            uid = input("请输入UID: ").strip()
    
    folder = input("文件夹路径: ").strip()
    
    if not Path(folder).exists():
        print(f"❌ 文件夹不存在: {folder}")
        return
    
    files = find_xml_files(folder)
    if not files:
        print("❌ 未找到XML文件")
        return
    
    print(f"找到 {len(files)} 个XML文件")
    
    tasks = []
    for f in files:
        name = Path(f).stem
        parts = name.split("_")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            tasks.append((parts[0], int(parts[1]), f))
        else:
            print(f"\n文件: {Path(f).name}")
            idx = int(input("  存档索引 (0-7): ").strip())
            tasks.append((uid, idx, f))
    
    print(f"\n准备上传 {len(tasks)} 个文件...")
    
    debug = input("是否开启调试模式? (y/n): ").strip().lower() == 'y'
    
    async def run():
        res = await upload_batch(tasks, cookies=cookies, debug=debug)
        print("\n📊 批量上传结果:")
        print(json.dumps(res, ensure_ascii=False, indent=2))
    
    asyncio.run(run())


async def upload_batch(
    tasks: Iterable[Tuple[str, int, str]],
    concurrency: int = 4,
    retries: int = 3,
    cookies: Optional[Dict[str, str]] = None,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    """并发批量上传"""
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
                LOG.info("开始上传 UID=%s index=%s", uid, index)
                r = await upload_with_retries(uid, index, path, retries=retries, session=session, debug=debug)
                results.append({"uid": uid, "index": index, "path": path, "result": r})

        await asyncio.gather(*[worker(uid, idx, p) for uid, idx, p in tasks])

    return results


def find_xml_files(folder: str) -> List[str]:
    p = Path(folder)
    files = list(p.rglob("*.xml"))
    return [str(x) for x in files]


def load_cookies_and_uid_from_file(cookie_file: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """从cookie文件加载cookies和uid"""
    try:
        j = json.loads(Path(cookie_file).read_text(encoding="utf-8"))
        if isinstance(j, dict) and "cookies" in j:
            cookies = j.get("cookies", {})
            uid = j.get("uid") or cookies.get("Puser")
            return cookies, uid
        if isinstance(j, dict):
            return j, j.get("uid")
    except Exception as e:
        print(f"加载cookie文件失败: {e}")
    return None, None


# ==========================================
# 🚀 主入口
# ==========================================

if __name__ == "__main__":
    cookies_dict = None
    uid = None
    
    # 尝试加载默认cookie
    cookie_dir = Path(__file__).parent.parent / "cookies"
    if cookie_dir.exists():
        cookie_files = list(cookie_dir.glob("*.json"))
        if cookie_files:
            cookies_dict, uid = load_cookies_and_uid_from_file(str(cookie_files[0]))
            if cookies_dict:
                print(f"✅ 已加载cookie")
    
    print("=" * 50)
    print("4399 存档上传工具")
    print("=" * 50)
    if uid:
        print(f"当前登录用户: {uid}")
    else:
        print("未登录")
    print("=" * 50)
    
    print("\n请选择操作:")
    print("1) 单文件上传")
    print("2) 按文件夹批量上传")
    print("3) 重新登录")
    print("4) 退出")
    
    choice = input("\n选择 (1-4): ").strip()
    
    if choice == "1":
        demo_single(cookies_dict)
    elif choice == "2":
        demo_folder(cookies_dict)
    elif choice == "3":
        print("\n重新登录")
        username = input("账号: ").strip()
        password = input("密码: ").strip()
        if username and password:
            cookie_info = login_4399(username, password)
            if cookie_info:
                cookies_dict = cookie_info.get("cookies", {})
                uid = cookie_info.get("uid")
                print(f"✅ 登录成功，UID: {uid}")
                
                save_choice = input("是否保存cookie? (y/n): ").strip().lower()
                if save_choice == 'y':
                    index = input("索引 (0-7): ").strip()
                    cookie_dir = Path(__file__).parent.parent / "cookies"
                    cookie_dir.mkdir(exist_ok=True)
                    cookie_file = cookie_dir / f"{uid}_{index}.json"
                    cookie_data = {
                        "uid": uid,
                        "index": int(index) if index.isdigit() else 0,
                        "cookies": cookies_dict
                    }
                    with open(cookie_file, "w", encoding="utf-8") as f:
                        json.dump(cookie_data, f, indent=2, ensure_ascii=False)
                    print(f"✅ Cookie已保存")
                
                input("\n按回车继续...")
            else:
                print("❌ 登录失败")
    elif choice == "4":
        print("退出")
    else:
        print("无效选择")