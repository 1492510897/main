import requests
import time
import hashlib
import uuid

# ======================== 真实配置（来自你Java代码） ========================
DEFAULT_GAME_ID = "100027788"
LOGIN_URL = "http://ptlogin.4399.com/ptlogin/login.do"
API_URL = "http://save.api.4399.com/"

# ======================== 【你提供的Java原版游戏签名算法】 ========================
def calculate_gamekey():
    # ✅ 完全照搬你Java代码：双层MD5 + 截取 [4:20]
    salt = "LPislKLodlLKKOSNlSDOAADLKADJAOADALAklsd"
    raw_str = DEFAULT_GAME_ID + salt + DEFAULT_GAME_ID
    md5_once = hashlib.md5(raw_str.encode()).hexdigest()
    md5_twice = hashlib.md5(md5_once.encode()).hexdigest()
    return md5_twice[4:20]  # 输出 16 位 gamekey

# ======================== 【verify 签名算法】 ========================
def calculate_verify(uid, gamekey):
    ts = str(int(time.time()))
    plain = f"{gamekey}{uid}{DEFAULT_GAME_ID}{ts}"
    return hashlib.md5(plain.encode()).hexdigest()

# ======================== 登录客户端（自动拿Cookie + UID） ========================
class LoginClient:
    def __init__(self):
        self.session = requests.Session()
        self.uid = ""
        self.cookie = ""

    def login(self, username, password):
        usid = uuid.uuid4().hex.upper()
        headers = {
            "User-Agent": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.2; WOW64; Trident/7.0)",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "username": username,
            "password": password,
            "appId": "kid_wdsj",
            "sec": "2",
            "gameId": "wd"
        }

        self.session.cookies.set("USESSIONID", usid, domain="4399.com")
        self.session.cookies.set("ptusertype", "kid_wdsj.4399_login", domain="4399.com")
        self.session.post(LOGIN_URL, data=data, headers=headers)

        # 自动组装Cookie
        self.cookie = "; ".join([f"{k}={v}" for k, v in self.session.cookies.items()])

        # 提取UID
        pauth = self.session.cookies.get("Pauth", "")
        if pauth:
            self.uid = pauth.split("|")[1] if "|" in pauth else ""

        return self.cookie, self.uid

# ======================== 数据获取 ========================
class GameClient:
    def __init__(self, cookie, uid):
        self.cookie = cookie
        self.uid = uid
        self.gamekey = calculate_gamekey()

    def get_union_and_me(self):
        """获取【个人+联盟】原始数据"""
        verify = calculate_verify(self.uid, self.gamekey)
        data = {
            "ac": "unionOfMe",
            "uid": self.uid,
            "gameid": DEFAULT_GAME_ID,
            "gamekey": self.gamekey,
            "verify": verify,
            "arch_index": "0",
            "time": str(int(time.time()))
        }
        headers = {
            "Cookie": self.cookie,
            "User-Agent": "Mozilla/4.0"
        }
        return requests.post(API_URL, data=data, headers=headers)

# ======================== 主程序 ========================
if __name__ == "__main__":
    print("===== 4399 纯账号密码自动登录工具 =====")
    username = input("请输入4399账号：")
    password = input("请输入4399密码：")

    # 登录
    login = LoginClient()
    cookie, uid = login.login(username, password)

    if not cookie or not uid:
        print("❌ 登录失败")
        exit()

    print(f"✅ 登录成功")
    print(f"UID: {uid}")
    print(f"GameKey: {calculate_gamekey()}\n")

    # 获取数据
    client = GameClient(cookie, uid)
    print("正在拉取 个人+联盟 原始数据...")
    resp = client.get_union_and_me()

    # 保存服务器原始返回
    with open("union_of_me_raw.bin", "wb") as f:
        f.write(resp.content)

    print(f"\n✅ 完成！状态码：{resp.status_code}")
    print(f"✅ 原始数据已保存为：union_of_me_raw.bin")
    print(f"✅ 返回内容：{resp.text[:150]}...")