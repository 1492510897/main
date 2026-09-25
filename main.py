"""
main (γ 合并版) v3.1.0 —— 数据检测工具（军队/公会成员存档批量检测）
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
  7. 🧩 资产差值检测     ★ 重点不是估值，而是找出「持有量 ≠ 应有总量」的差值
                       （差值 > 0 = 来源说不清，疑似异常修改存档，交人工复核）：
                         差值 = 持有量 − 应有总量
                         应有总量 = 付费次数 + 免费额度（活动/掉落/赠送等）
                         稀有零件：应有 = 付费 + 券购 + 塔领 + 活动修正
                       付费载具 / 付费时装与购买记录(pay.obj)双向比对：
                         「未购买但存档内拥有」与「购买了但存档内无」会输出，
                         能正常匹配（购买记录 ≥ 持有量）的不输出
                       免费额度 / 活动修正见 inputdata/free_quota.ini，可自行调整
                       • 节点：equip/equipBag/equipHouse、partsBag、arms/armsBag/armsHouse
                         （含武器镶嵌位 partsSave），以及队友存档 more/moreBag→SAVE
                       • 零件按 objType 分类（权威定义见 partsType.ts 注释），
                         普通零件（loader 等）与特殊零件（腐蚀芯片/猎人技能器）不计入，
                         仅统计稀有零件（objType=rare）

批量导出（按 UID 汇总）：
  • 同一 UID（服务器UID）下多个 uid_index 合并为一份 *_异常详情.txt
    （含「异常一览」逐档摘要、资产汇总、index 异常单列、逐档详细日志）
  • CSV 每行对应一个 UID，含 时装/载具/特殊零件/资产价值/资产异常摘要 列
  • 文件中单独列出“🔢 index 异常单独指出”，标注理论/实际不一致的存档

界面：主页(单文件检测 / 批量检测 / 报告导出 / 打开下载工具) + 设置 + 致谢
运行目录：inputdata/ outputdata/ test/ ；读取 config.ini(Settings)
"""
import os
import hashlib
import configparser
import xml
import base64
import datetime
import re
import sys
import xml.etree.ElementTree as ET
import hmac
from collections import defaultdict
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import io

import app_paths

# ========================================================
# 📦 可选依赖（延迟导入，支持作为模块被其他项目 import）
# ========================================================
# 本文件需要能被其他项目（如 NoneBot 机器人）直接 import，因此：
#   • 导入时不执行任何系统/GUI 调用（不改 DPI、不弹窗、不启动界面）；
#   • tkinter（界面）、pycryptodome（价格表解密）、info_get（下载工具）按需导入，
#     缺失时给出明确提示，而不是让 import 直接失败。
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ImportError:                  # 无显示环境 / 未安装 tkinter
    tk = None
    filedialog = None
    messagebox = None

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:                  # 缺少 pycryptodome：仅金币消费检测降级
    AES = None
    unpad = None

# 缺少 pycryptodome 时的统一提示（价格表 bin 需 AES 解密）
MISSING_CRYPTO_MSG = ("缺少 pycryptodome 依赖（pip install pycryptodome），"
                      "无法解密价格表，金币消费检测不可用")


def has_gui():
    """当前环境是否可用图形界面（tkinter 是否可用）。"""
    return tk is not None


def has_crypto():
    """价格表解密所需的 pycryptodome 是否可用。"""
    return AES is not None


def enable_dpi_awareness():
    """高分屏下让界面清晰；仅在启动 GUI 时调用（导入本模块无副作用）。"""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

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
# 所有路径均以“程序所在目录”为基准（见 app_paths），不再依赖启动时的当前工作目录，
# 因此从任何目录启动本程序，配置/输入/输出/工作目录都落在同一位置。
PROGRAM_DIR = app_paths.PROGRAM_DIR
INPUT_DIR = app_paths.in_program_dir("inputdata")
OUTPUT_DIR = app_paths.in_program_dir("outputdata")
TEST_DIR = app_paths.in_program_dir("test")
CONFIG_FILE = app_paths.in_program_dir("config.ini")
DEFAULT_BIN_PATH = os.path.join(INPUT_DIR, "v36.11_pro.bin")
VERSION = "3.1.0"

# ---- 资产检测（时装 / 载具 / 稀有零件）----
GOODS_CSV = os.path.join(INPUT_DIR, "good_items.csv")   # id/价值对照表
GOODS_CSV_REL = os.path.join("inputdata", "good_items.csv")   # 相对写法（供资源目录优先解析）
ASSET_FASHION = 'fashion'
ASSET_VEHICLE = 'vehicle'
ASSET_PARTS = 'parts'
ASSET_KIND_CN = {ASSET_FASHION: '时装', ASSET_VEHICLE: '载具', ASSET_PARTS: '特殊零件'}
ASSET_SOURCE_MAIN = 'main'      # 主存档
ASSET_SOURCE_TEAM = 'team'      # 队友存档（more / moreBag → SAVE）
# ---- 零件类型（objType）—— 权威定义 ----
# 来源：zzl-Jiang/bqyx-query-initial（游戏前端反编译）
#   src/core/module/parts/define/partsType.ts
#       normalArr  = bullet / shooter / capacity / loader / stabler / sight  → 普通零件
#       special    = 特殊零件（芯片）        skill = 特殊零件（技能器）
#       rare       = 稀有零件（稀零）← 本工具关注的对象
#       NORMAL_PARTS = getPartsName(loader) = "loaderParts"
#   src/core/things/define/thingsDefine.ts
#       isPartsNormalB():  objType == PartsType.NORMAL
#       isPartsSpecialB(): objType == special || objType == skill
#       isPartsRareB():    objType == rare
#   src/core/common/constants/partsConstants.ts（PARTS_MAP 中文名对照）
#       loaderParts=零件  huntParts=猎人技能器  acidicParts=腐蚀芯片
#       hardeningParts=硬化器  shockParts=宽震器  speedParts=加速器  twoShootParts=连发器
#   src/core/module/parts/define/partsConst.ts
#       minLv=3, cLv=3 —— 普通零件等级为 3 的倍数（3,6,…,96），
#       中文名前缀依次为 小/（空）/初级/中级/高级/特级/超级/究级/闪耀·/绝世·/超凡·
# 因此：**普通零件**（6 种）+ **特殊零件**（2 种）以外的零件即为稀有零件。
# 注：早期靠“等级是 3 的倍数 / 名称命中”启发式判定，既会误排稀有零件
#     （如 maxLevel 恰为 3 的倍数时），也会漏掉新零件，故改用 baseLabel 精确判定。
PARTS_NORMAL_NAMES = frozenset({
    "bulletParts",    # 伤害
    "shooterParts",   # 射速
    "capacityParts",  # 弹容
    "loaderParts",    # 装弹速（PartsType.NORMAL）
    "stablerParts",   # 精准度
    "sightParts",     # 射程
})
PARTS_SPECIAL_NAMES = frozenset({
    "acidicParts",    # 腐蚀芯片（objType=special）
    "huntParts",      # 猎人技能器（objType=skill）
})
# ---- 稀有零件升级 / 合成规则（权威定义：AS3 ThingsDefine.getComposeMustNum）----
# 高阶稀有零件**既不能掉落也不能购买**（partsCoinClass.bin 全为一阶；
# thingsDefineGroup.ts 明确「只有 1 级可以掉落」），只能由同族低阶零件升级而来。
# 升级所需份数（以 lv0 阶的同族零件为材料）：
#     lshapedParts（C型枪管）  → 3
#     isElePartsB()（元素球）  → 3      四系元素球，以及四素球
#     lv0 == 1                → 4
#     lv0 >= 2                → 3
#     （默认 100 为非零件物品的哨兵值，不会用于升级）
# 另有一批一阶稀零只走「材料合成」，配方见 xml/58_XMLOut_thingsComposeClass.bin
# 的 giftType="parts" 段落：
#     demCapacityParts_1 修罗弹夹 ← things;demonChest ×18
#     purgoldCpu_1       紫金之芯 ← zodiacCash ×100 + demBall ×700 + demStone ×600
#     poisonParts_1      生化球   ← madheart ×300 + demStone ×300
#     oldBulletCube_1    老弹体   ← oldBulletStamp ×300
#     betrayParts_1      叛变器   ← oldBulletStamp ×400
#     followParts_1      跟踪器   ← deathSilver ×70
# 特例：fourEleParts_2（四素球）= 二阶元素球（电/火/冰/毒）任取 3 种各 1 个
#       → 数据表里恰好列了 4 种组合，与「任取 3 种」一致。
PARTS_COMPOSE_ALWAYS_THREE = frozenset({"lshapedParts"})      # C型枪管：恒为 3
PARTS_ELE_NAMES = frozenset({"electricParts", "fireParts",
                             "frozenParts", "poisonParts"})   # PartsName.eleArr 四系元素球
FOUR_ELE_PARTS = "fourEleParts"                               # 四素球（元素球合成体）


def parts_upgrade_cost(base, level=1):
    """把 level 阶的同族稀有零件升级时所需的份数（getComposeMustNum）。

    与「载具进阶」不同 —— 稀有零件升阶会**消耗**低阶零件，因此
    同一 baseLabel 的多个阶应合并计数：存档中常见 `_2` 多于 `_1`
    （如 xpw 的连发器 Lv1×1 / Lv2×4），正是材料被消耗后的结果。
    """
    base = (base or '').strip()
    if (base in PARTS_COMPOSE_ALWAYS_THREE or base in PARTS_ELE_NAMES
            or base == FOUR_ELE_PARTS):
        return 3
    try:
        lv = int(level)
    except (TypeError, ValueError):
        lv = 1
    return 4 if lv == 1 else 3


def parts_level1_equiv(base, level):
    """把 level 阶零件换算成「一阶当量」（累计升级消耗）。

    高阶既不能掉落也不能购买（零件券商店只有 _1），只能由低阶升上来，
    因此消耗是逐级累乘的：
        Lv1 → 1
        Lv2 → cost(Lv1)                 （一般 4，C型枪管/元素球为 3）
        Lv3 → cost(Lv1) × cost(Lv2)     （一般 4×3 = 12）
    """
    try:
        lv = int(level)
    except (TypeError, ValueError):
        lv = 1
    equiv = 1
    for lv0 in range(1, max(1, lv)):
        equiv *= parts_upgrade_cost(base, lv0)
    return equiv


# 无英文名（老存档）时的中文名兜底：普通零件中文名均以“零件”结尾
RARE_PARTS_EXCLUDE_CN = ("腐蚀芯片", "猎人技能器")
RARE_PARTS_LEVEL_STEP = 3       # 普通零件等级间隔（PartsConst.cLv）
RARE_PARTS_MAX_LEVEL = 96       # 当前零件等级上限
CHIP_MARK = "碎片"              # 碎片为合成材料，不参与计价

# ---- 统一的持有「差值」判定 ★ 本检测的核心，不是估值 ----
# 目的：找出存档里「来源说不清」的物品 —— 持有量与应有总量对不上，
#       通常意味着存档被异常修改。价值只作辅助（多出来多少、大概值多少）：
#
#     差值数量 = max(0, 持有量 − 应有总量)
#     应有总量 = 付费次数 + 免费额度（活动/掉落/赠送等免费渠道，见 free_quota.ini）
#     差值价值 = 单价 × 差值数量    ← 仅用于排序/展示，**不参与「是否异常」的判断**
#
# ★ 未定价物品同样判定：只要差值 > 0 就报（估值缺失不影响差值检测）。
#   仅当 free_quota.ini 的 [default] min_excess_value > 0 时，才用估值做降噪，
#   默认 0 = 只要能算出差值就全部报出，交人工复核。
DEFAULT_FREE_QUOTA = 3          # 未在 free_quota.ini 中登记时的默认免费额度（份）
FREE_QUOTA_FILE = os.path.join(INPUT_DIR, "free_quota.ini")
FREE_QUOTA_FILE_REL = os.path.join("inputdata", "free_quota.ini")   # 相对写法
# 仅用于降噪的差值价值门槛（黄金）。0 = 只要有差值就报（检测优先，推荐）。
# 不设界面参数，可在 free_quota.ini 的 [default] min_excess_value 中调整。
DEFAULT_ABNORMAL_MIN_VALUE = 0

# ---- 购买记录 ↔ 存档数据：匹配策略与输出精简 ----
# 「付费载具 / 付费时装」使用 pay.obj 的购买记录双向比对：
#   • 正常匹配（购买记录 ≥ 持有量）                  → **不输出**
#   • 未购买但存档内拥有（持有量 > 购买记录，含无购买记录）→ 输出（fail）
#   • 购买了但存档内无（购买记录 > 持有量 / 存档内未见）  → 输出（warn）
# 置 False 可回到旧口径（收费载具全部列出、不输出购买缺口）。
MATCH_PURCHASE_RECORDS = True
# 报告精简：明细单行展示，每区块最多 MAX_REPORT_ITEMS 条，超出折叠（旧行为置 False）。
CONCISE_REPORT = True
MAX_REPORT_ITEMS = 5

# 免费额度取「无限」的哨兵值（可无限免费获取 → 不存在差值）。
# free_quota.ini 中可写 unlimited / 无限 / -1 表示。
FREE_QUOTA_UNLIMITED = -1

# ★ 免费额度 = 「零件券商店限购」+「虚天塔一次性掉落」，两者都不花黄金。
#
# 来源① 56_XMLOut_partsCoinClass.bin（零件券商店）
#     <goods defineLabel="xxx_1" price="券价" buyLimitNum="限购数"/>
#     → buyLimitNum 即该零件不花黄金可获取的上限。
#     文件里 <!-- 可提高上限 --> 分组（宽震器/硬化器/加速器/减速器/连发器/
#     元素泡/红武增强器/穿人器）就是限购被提高过的那批。
#     注：商店**只有一阶**（defineLabel 全是 _1），印证高阶只能靠升级。
#
# 来源② TowerDefineCtrl.as（虚天塔，dataAll/_app/tower/）
#     各层 giftStr = "parts;xxxParts_1;1"，每层固定给 1 个一阶零件。
#     **一次性**：奖励绑定在 save.blv（累计通关进度）上，通关即领；
#     newWeek() 只重置 us/usUse（本周技能使用次数），不重置奖励，
#     故同一账号全部塔层奖励合计只能拿一次（见 TowerSave.as）。
#
# 合计即该零件的免费额度；超出部分才需付费解释。
FREE_QUOTA_PARTS_SHOP = {
    # ---- 可提高上限分组 ----
    "宽震器": 20,        # shockParts_1      券价 15
    "硬化器": 20,        # hardeningParts_1  券价 15
    "加速器": 20,        # speedParts_1      券价 15
    "减速器": 20,        # downSpeedParts_1  券价 15
    "连发器": 16,        # twoShootParts_1   券价 30
    "元素泡": 16,        # eleParts_1        券价 30
    "红武增强器": 12,     # redArmsParts_1    券价 30
    "穿人器": 16,        # penbodyParts_1    券价 40
    # ---- 其余商店零件 ----
    "C型枪管": 3,        # lshapedParts_1    券价 40
    "消磁器": 3,         # degaussingParts_1 券价 25
    "AI迫近器": 2,       # aiStopParts_1     券价 60
    "散射角控制器": 2,    # angleCtrlParts_1  券价 40
    "钝化球": 1,         # bluntBall_1       券价 60
    "溅射体": 1,         # spurtingCube_1    券价 60
    "月饼子弹": 1,       # mooncakeParts_1   券价 60
    "挖墙弹": 1,         # digWallParts_1    券价 40
    "火焰球": 1,         # fireParts_1       券价 50
    "电磁球": 1,         # electricParts_1   券价 60
    # ---- 商店中无限购（未写 buyLimitNum）----
    "枪口塞": FREE_QUOTA_UNLIMITED,   # noHurtParts_1   券价 5
    # ---- 暂不设定额度（来源复杂/待核实，先视为不限，避免误报）----
    # 修罗弹夹 demCapacityParts：配方需 demonChest×18（58_XMLOut_thingsComposeClass.bin），
    # 但宝箱可farm性未确认，暂不限额。
    "修罗弹夹": FREE_QUOTA_UNLIMITED,
}
FREE_QUOTA_PARTS_TOWER = {
    # 虚天塔（一次性）：baseLabel -> 全部塔层掉落合计
    "宽震器": 5,          # shockParts      : 第 7/13/28/38/41 层
    "加速器": 5,          # speedParts      : 第 9/14/19/24/33 层
    "连发器": 5,          # twoShootParts   : 第 10/18/29/37/43 层
    "减速器": 4,          # downSpeedParts  : 第 15/20/25/30 层
    "红武增强器": 2,       # redArmsParts    : 第 17/31 层
    "调表器": 2,          # uidpsParts      : 第 22/26 层
    "元素泡": 2,          # eleParts        : 第 35/40 层
    "硬化器": 1,          # hardeningParts  : 第 5 层
    "穿人器": 1,          # penbodyParts    : 第 45 层
    "绞杀体": 1,          # crushCube       : 第 75 层
}


def _merge_free_quota(*tables):
    """合并多份额度表（不限额度优先，其余相加）。"""
    out = {}
    for table in tables:
        for name, quota in table.items():
            if quota == FREE_QUOTA_UNLIMITED or out.get(name) == FREE_QUOTA_UNLIMITED:
                out[name] = FREE_QUOTA_UNLIMITED
            else:
                out[name] = out.get(name, 0) + quota
    return out


FREE_QUOTA_PARTS = _merge_free_quota(FREE_QUOTA_PARTS_SHOP, FREE_QUOTA_PARTS_TOWER)

# 虚天塔各层的零件奖励（TowerDefineCtrl.as 的 giftStr，每层 1 个一阶零件）。
# 用途：结合存档 tower.gO.saveObj 判断哪些层的奖励**已领取**，
#       从而把「商店限购 + 已领塔奖励」作为该账号真正的免费额度。
TOWER_PARTS_DROPS = {
    5: "hardeningParts", 7: "shockParts", 9: "speedParts", 10: "twoShootParts",
    13: "shockParts", 14: "speedParts", 15: "downSpeedParts", 17: "redArmsParts",
    18: "twoShootParts", 19: "speedParts", 20: "downSpeedParts", 22: "uidpsParts",
    24: "speedParts", 25: "downSpeedParts", 26: "uidpsParts", 28: "shockParts",
    29: "twoShootParts", 30: "downSpeedParts", 31: "redArmsParts", 33: "speedParts",
    35: "eleParts", 37: "twoShootParts", 38: "shockParts", 40: "eleParts",
    41: "shockParts", 43: "twoShootParts", 45: "penbodyParts", 75: "crushCube",
}
# baseLabel → 塔层总数（用于把「免费额度」拆成「商店部分」与「塔部分」）
TOWER_PARTS_TOTAL = {}
for _lv, _base in TOWER_PARTS_DROPS.items():
    TOWER_PARTS_TOTAL[_base] = TOWER_PARTS_TOTAL.get(_base, 0) + 1
# {baseLabel: 中文名}——free_quota.ini 按中文名登记，塔表按 baseLabel，
# 二者需要互查（如 hardeningParts ↔ 硬化器）。
PARTS_BASE_TO_CN = {
    "shockParts": "宽震器", "hardeningParts": "硬化器", "speedParts": "加速器",
    "downSpeedParts": "减速器", "twoShootParts": "连发器", "eleParts": "元素泡",
    "redArmsParts": "红武增强器", "penbodyParts": "穿人器", "lshapedParts": "C型枪管",
    "degaussingParts": "消磁器", "aiStopParts": "AI迫近器",
    "angleCtrlParts": "散射角控制器", "bluntBall": "钝化球", "spurtingCube": "溅射体",
    "mooncakeParts": "月饼子弹", "digWallParts": "挖墙弹", "fireParts": "火焰球",
    "electricParts": "电磁球", "noHurtParts": "枪口塞", "uidpsParts": "调表器",
    "crushCube": "绞杀体", "demCapacityParts": "修罗弹夹", "fourEleParts": "四素球",
    # 材料合成的稀有零件（配方见文件头：58_XMLOut_thingsComposeClass.bin）
    "purgoldCpu": "紫金之芯", "poisonParts": "生化球", "oldBulletCube": "老弹体",
    "betrayParts": "叛变器", "followParts": "跟踪器",
}
PARTS_CN_TO_BASE = {cn: base for base, cn in PARTS_BASE_TO_CN.items()}


def rare_parts_cn_names():
    """全部已知稀有零件的中文名（按对照表顺序，供生成 [parts_adjust] 列表）。"""
    names = list(PARTS_BASE_TO_CN.values())
    names += [cn for cn in FREE_QUOTA_PARTS if cn not in names]
    return names
FREE_QUOTA_FASHION = {}         # 时装默认全部取 DEFAULT_FREE_QUOTA
FREE_QUOTA_VEHICLE = {}         # 载具同上

# ★ 稀有零件的「活动修正」：活动/兑换码/赠送等**存档内查不到记录**的来源，
#   无法从存档自动统计，只能按零件人工登记 —— 即 free_quota.ini 的 [parts_adjust]。
#   差值 = 持有一阶当量 −（付费 + 券购 + 塔领 + 活动修正）
ASSET_PARTS_ADJUST = 'parts_adjust'

# 免费额度表：{kind: {名称: 额度}}，由 free_quota.ini 载入（见 load_free_quota）
FREE_QUOTA_TABLES = {ASSET_FASHION: {}, ASSET_VEHICLE: {},
                     ASSET_PARTS: {}, ASSET_PARTS_ADJUST: {}}
_free_quota_path = None
_free_quota_error = ''


def _default_free_quota_ini():
    """free_quota.ini 的初始内容（首次运行自动生成，便于用户自行调整）。

    每个 section 对应一个资产类别；键=物品中文名（或英文名），值=允许免费获取的份数。
    """
    lines = [
        "; 免费额度配置 —— ★ 本工具的核心是「差值检测」：找出持有量与应有总量对不上的物品",
        ";   差值 = 持有量 − 应有总量；应有总量 = 付费次数 + 免费额度",
        ";   · 时装：应有 = 免费额度（[fashion]/[default]）+ 付费次数",
        ";   · 零件：应有 = 付费 + 券购 + 塔领（存档实际记录）+ 活动修正（[parts_adjust]）",
        ";   · 载具：不参与本差额判定（由 收费/稀有/免费/异常 分类覆盖）",
        "; 差值只与数量有关，与单价/估值无关 —— 未定价物品同样会报",
        "; 值可写 unlimited / 无限 / -1 表示不限（不存在差值）",
        "; 修改后重新检测即可生效；未列出的物品取 default 值",
        "",
        "[parts_adjust]",
        "; ★ 活动修正参数：活动/兑换/赠送等**存档内查不到记录**的来源，按零件登记份数",
        ";   差值 = 持有一阶当量 −（付费 + 券购 + 塔领 + 本值）；不确定就保持 0",
    ]
    for cn in rare_parts_cn_names():
        lines.append(f"{cn} = 0")
    lines += [
        "",
        "[parts]",
        "; 零件理论免费上限 = 零件券商店限购数 + 虚天塔一次性奖励（两者都不花黄金）：",
        ";   ① 56_XMLOut_partsCoinClass.bin 的 buyLimitNum",
        ";   ② TowerDefineCtrl.as 各层 giftStr（每层 1 个一阶，通关即领、仅一次）",
        "; 注：差值判定从存档实际读取券购/塔领（更准），故本表仅作上限参考，不参与求和；",
        ";     若要用「理论上限」替代实际记录（活动无法逐笔登记时），改此表无效，请用 [parts_adjust]",
        "; 特殊零件（同名不同等级共用同一额度）",
    ]
    for cn, q in sorted(FREE_QUOTA_PARTS.items(), key=lambda kv: (kv[1] < 0, -kv[1])):
        lines.append(f"{cn} = {q}" if q >= 0 else f"{cn} = unlimited")
    lines += [
        "",
        "[fashion]",
        "; 时装免费额度 = 活动/赠送等免费渠道允许的份数（差值 = 持有 − 本值 − 付费次数）",
        "; 未列出的取 [default] quota；如需单独指定，取消下行注释并修改",
        "; 示例 = 1",
        "; 注：免费时装（小7/小娜/扶光/望舒/红魔/小卡/小隆/小田时装）不做差值判定；",
        ";     稀有时装（免费与付费之外的时装）单列「稀有时装」区块，持有即列出（含获取时间）",
    ]
    for cn, q in sorted(FREE_QUOTA_FASHION.items()):
        lines.append(f"{cn} = {q}")
    lines += [
        "",
        "[vehicle]",
        "; 载具：合法性由收费/稀有/免费/异常载具分类覆盖（存在性差值），不参与本差额判定",
    ]
    for cn, q in sorted(FREE_QUOTA_VEHICLE.items()):
        lines.append(f"{cn} = {q}")
    lines += [
        "",
        "[default]",
        "; 未在上方登记的物品所使用的默认免费额度（时装用；零件请用 [parts_adjust]）",
        f"quota = {DEFAULT_FREE_QUOTA}",
        "; 仅降噪用：差值价值低于该值时不报异常（0 = 只要有差值就全部报出，推荐）",
        "; 差值判定本身与估值无关，未定价物品同样会报",
        f"min_excess_value = {DEFAULT_ABNORMAL_MIN_VALUE}",
        "",
    ]
    return "\n".join(lines)


def ensure_free_quota_ini(path=None):
    """确保 free_quota.ini 存在（缺失时按内置默认值生成），返回实际路径。"""
    target = path or app_paths.resolve_input(FREE_QUOTA_FILE, FREE_QUOTA_FILE_REL)
    if not target:
        target = FREE_QUOTA_FILE
    if not os.path.exists(target):
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8-sig") as f:
                f.write(_default_free_quota_ini())
        except OSError:
            return target
    return target


def _ensure_parts_adjust_section(target):
    """旧配置若缺少 [parts_adjust]（活动修正参数）→ 自动补一段全 0。

    活动/兑换/赠送等来源在存档内**没有记录**（无 pay、无券购、无塔），
    只能人工登记；为让修正参数开箱可见，缺失时补到文件末尾（不改变既有判定）。
    """
    try:
        with open(target, 'r', encoding='utf-8-sig') as f:
            text = f.read()
    except OSError:
        return False
    if re.search(r'^\s*\[parts_adjust\]', text, re.M | re.IGNORECASE):
        return False
    block = ["", "[parts_adjust]",
             "; ★ 活动修正参数：活动/兑换/赠送等**存档内查不到记录**的来源，按零件登记份数",
             ";   差值 = 持有一阶当量 −（付费 + 券购 + 塔领 + 本值）；不确定就保持 0"]
    block += [f"{cn} = 0" for cn in rare_parts_cn_names()]
    try:
        # 用 utf-8（非 utf-8-sig）追加：避免在文件中间写入 BOM
        with open(target, 'a', encoding='utf-8') as f:
            f.write("\n".join(block) + "\n")
    except OSError:
        return False
    return True


def load_free_quota(path=None, force=False):
    """从 free_quota.ini 载入免费额度表。

    结构（section 名对应资产类别，键=物品中文名/英文名）：
        [parts_adjust] 宽震器 = 1        # ★ 活动/赠送等「存档内无记录」来源的修正份数
        [parts]   宽震器 = 20            # 零件理论免费上限（券商店限购 + 塔），仅参考
                  枪口塞 = unlimited     # 商店未设限购
        [fashion] 示例 = 1               # 免费渠道允许份数（差值 = 持有 − 本值 − 付费）
        [vehicle] （载具不参与差额判定）
        [default] quota = 0            # 未登记物品的默认免费额度
                  min_excess_value = 0  # 仅降噪：差值价值门槛（0 = 有差值就报）

    返回 (tables, error)；tables 为 {kind: {名称: 额度}}。
    同一路径只加载一次（除非 force=True）。
    """
    global _free_quota_path, _free_quota_error, DEFAULT_FREE_QUOTA, DEFAULT_ABNORMAL_MIN_VALUE
    target = ensure_free_quota_ini(path)
    if not force and _free_quota_path == target:
        return FREE_QUOTA_TABLES, _free_quota_error

    parser = configparser.ConfigParser()
    # 保留键名原样（默认会把键名转小写，"C型枪管" 会变成 "c型枪管" 而查不到）
    parser.optionxform = str
    error = ''
    try:
        parser.read(target, encoding="utf-8-sig")
    except Exception as e:
        error = f"读取免费额度配置失败：{e}"

    section_kind = {"parts": ASSET_PARTS, "fashion": ASSET_FASHION,
                    "vehicle": ASSET_VEHICLE, "parts_adjust": ASSET_PARTS_ADJUST}
    for kind in FREE_QUOTA_TABLES:
        FREE_QUOTA_TABLES[kind] = {}
    if not error:
        for section, kind in section_kind.items():
            if not parser.has_section(section):
                continue
            for name, value in parser.items(section):
                txt = str(value).strip().lower()
                if txt in ('unlimited', 'inf', 'infinite', '无限', '不限'):
                    FREE_QUOTA_TABLES[kind][name.strip()] = FREE_QUOTA_UNLIMITED
                    continue
                try:
                    quota = int(float(txt))
                except (TypeError, ValueError):
                    continue        # 非法值忽略，回退默认额度
                # 负数 = 不限（-1 等）；其余按正数处理
                FREE_QUOTA_TABLES[kind][name.strip()] = (
                    FREE_QUOTA_UNLIMITED if quota < 0 else quota)
        # [default]：未登记物品的默认免费额度 + 差值价值降噪门槛
        if parser.has_section("default"):
            try:
                DEFAULT_FREE_QUOTA = max(
                    0, int(float(parser.get("default", "quota",
                                            fallback=str(DEFAULT_FREE_QUOTA)))))
            except (TypeError, ValueError):
                pass
            try:
                DEFAULT_ABNORMAL_MIN_VALUE = max(
                    0, int(float(parser.get("default", "min_excess_value",
                                            fallback=str(DEFAULT_ABNORMAL_MIN_VALUE)))))
            except (TypeError, ValueError):
                pass

    _free_quota_path = target
    _free_quota_error = error
    # 旧配置补齐 [parts_adjust]（活动修正参数），使差值公式的四个来源都可见
    if not error and not FREE_QUOTA_TABLES.get(ASSET_PARTS_ADJUST):
        if _ensure_parts_adjust_section(target):
            for cn in rare_parts_cn_names():
                FREE_QUOTA_TABLES[ASSET_PARTS_ADJUST].setdefault(cn, 0)
    return FREE_QUOTA_TABLES, _free_quota_error


def free_quota_entry(kind, cn, en=''):
    """返回该物品在 free_quota.ini 中**显式登记**的免费额度；未登记返回 None。

    用于区分“用户特别指定的额度”与“default 兜底值”，
    后者不应在每条明细里重复展示。
    """
    table = FREE_QUOTA_TABLES.get(kind) or {}
    cn = (cn or '').strip()
    if cn and cn in table:
        return int(table[cn])
    base = re.sub(r"_\d+$", "", (en or '').strip())
    if base and base in table:
        return int(table[base])
    return None


def free_quota_of(kind, cn, en=''):
    """返回该物品的免费额度（允许免费/活动获取的份数）。

    优先按中文名查表，其次英文名（去 _数字 后缀）；未登记则用 [default] quota。
    """
    explicit = free_quota_entry(kind, cn, en)
    return explicit if explicit is not None else DEFAULT_FREE_QUOTA


# ---- 存档内编码数值解码（权威：AS3 com/common/text/TextWay.as）----
# 游戏把购买数量等数值用 toCode32() 存进存档，规则是**纯进制转换**、完全可逆：
#     toCode32(s):  逐字符取 charCode → 10 进制转 32 进制 → 左补 '0' 到 4 位
#     getText32(s): 每 4 字符一节 → 32 进制转 10 进制 → fromCharCode
# 10 进制字符（'0'..'9'，charCode 48..57）编码后恰为 '001g'..'001p'，
# 故形如 "001h001l001g" = '1' + '5' + '0' = 150。
def decode_text32(text):
    """解码 TextWay.toCode32 产物；失败返回 None。

    与 AS3 getText32 等价（每 4 字符一节，32 进制 → 字符码 → 字符）。
    """
    if not text:
        return None
    s = str(text).strip()
    if len(s) % 4:
        return None
    out = []
    for i in range(0, len(s), 4):
        try:
            code = int(s[i:i + 4], 32)
        except ValueError:
            return None
        out.append(chr(code))
    return ''.join(out)


def decode_text32_number(text, default=None):
    """解码为整数；非数字内容返回 default。"""
    raw = decode_text32(text)
    if raw is None:
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default

# 免费时装：活动/初始赠送获取，对照表无售价记录。
# 存档中确实持有，但既不该计入价值，也不该被当成“对照表覆盖不全”的告警。
FREE_FASHION_NAMES = (
    "小7时装", "小娜时装", "扶光时装", "望舒时装",
    "红魔时装", "小卡时装", "小隆时装", "小田时装",
    "小蚁时装", "工人帽", "狼首"
)
# 归一化后的匹配集合（去掉 _数字 后缀等差异，容错“小7时装/小7”写法）
FREE_FASHION_SET = frozenset(FREE_FASHION_NAMES)
FREE_FASHION_STEMS = frozenset(
    n[:-2] if n.endswith("时装") else n for n in FREE_FASHION_NAMES
)


def is_free_fashion(cn, en=''):
    """判断是否为免费时装（对照表无价，不算“未定价”告警）。

    匹配中文名（含省略“时装”后缀的写法）与英文名（去掉 _数字 后缀）。
    """
    cn = (cn or '').strip()
    if cn:
        if cn in FREE_FASHION_SET:
            return True
        stem = cn[:-2] if cn.endswith("时装") else cn
        if stem in FREE_FASHION_STEMS:
            return True
    base = re.sub(r"_\d+$", "", (en or '').strip())
    if base and (base in FREE_FASHION_SET or base in FREE_FASHION_STEMS):
        return True
    return False


# 稀有时装：既非免费时装、对照表也无直售价的时装（碎片合成 / 活动产出等），
# 报告需标注其获取时间（XML getTime 字段）便于溯源。
# 判定条件（两者同时满足）：
#   ① is_free_fashion() 为假 —— 不属于已知免费时装；
#   ② 对照表（good_items.csv）中查不到该时装的价格 —— 不属于付费时装。
def is_rare_fashion(cn, en='', table=None):
    """是否为稀有时装（免费时装与付费时装之外）。"""
    if is_free_fashion(cn, en):
        return False
    tbl = table or GOODS_TABLE
    if not tbl.loaded:
        return False        # 无对照表时无法判定，交由“未定价”流程处理
    got = tbl.price_of(en, cn, {'时装', '时装(下架)', '时装(升级)'})
    return got is None


# ---- 载具家族（进化链）----
# 权威数据源：zzl-Jiang/bqtj-wiki-tools 仓库 xml/ 下各载具专属文件
#             （__NN_<Name>Class.bin），其 <equip name cnName> 依次为
#             基础形态 → 各阶进化体；聚合载具见 211_XMLOut_vehicleClass.bin。
# 用途：
#   ① 判定“进阶体沿用基础形态价格”（对照表通常只收录基础形态价）
#   ② 图鉴 / 免费 / 收费 分类的名称归一（中文名、英文名双写法）
VEHICLE_FAMILIES = {
    "泰坦": [("泰坦", "Titans"), ("黑暗泰坦", "BlackTitans"), ("盖亚", "Gaia"),
             ("狂怒盖亚", "RedGaia"), ("神圣盖亚", "GoldGaia")],
    "制裁者": [("制裁者", "Punisher"), ("判决者", "Adjudicator"),
               ("惩戒者", "Chastener"), ("处决者", "Executioner")],
    "先知": [("先知", "Prophet"), ("天目", "Temmoku"),
             ("源代码", "SourceCode"), ("时光机", "TimeMachine")],
    "幽鬼": [("幽鬼", "BlueMoto"), ("血魂", "BlueMotoSec"), ("飞魄", "BlueMotoThird")],
    "赤焰": [("赤焰", "RedMoto"), ("烈焰", "RedMotoSec"), ("圣焰", "RedMotoThird")],
    "挖掘者": [("挖掘者", "Diggers"), ("腥红挖掘者", "SecDiggers"),
               ("炙热挖掘者", "ThirdDiggers"), ("血锯挖掘者", "FourDiggers")],
    "破晓": [("破晓", "Daybreak"), ("月蚀", "MoonLack"),
             ("黎明", "Dayspring"), ("曙光", "Daylight")],
    "收割者": [("收割者", "RedReaper"), ("碾压者", "RedCrusher"),
               ("扫荡者", "RedSweeps"), ("剿灭者", "RedWiper")],
    "巨鲸": [("巨鲸", "BlueWhale"), ("雄鹰", "TheEagle"),
             ("大鹏", "TheRoc"), ("鲲", "TheKun")],
    "潜行者": [("潜行者", "SeaShark"), ("潜伏者", "Lurker"),
               ("潜影者", "LurkerThird"), ("潜匿者", "LurkerFour")],
    "沙漠进袭者": [("沙漠进袭者", "DesertTank"), ("丛林狂袭者", "ForestTank"),
                   ("暗夜侵袭者", "DarkTank"), ("大地掠袭者", "FloorTank")],
    "雷鸣": [("雷鸣", "Thunder"), ("雷霆", "Thunderbolt")],
    "异祖龙": [("异祖龙", "FlyDragonAir"), ("冰霜祖龙", "FrozenDragonAir")],
}
# 单形态载具（无进化链）
VEHICLE_STANDALONE = {
    "异齿虎": "SaberTigerCar", "守望之翼": "WatchEagleAir",
    "狩猎者": "AircraftGun", "年兽": "NianCar",
    "切割者": "BoneBreaker", "虚炎狼": "FireWolfCar", "胖哒号": "PandaCar",
}
# 特殊载具 / 聚合（合体召唤体）：仅能在战斗中由技能合体召唤，
# **无法通过任何常规途径获取**，因此不属于可持有载具 → 不计入载具列表，
# 存档中一旦出现即按「异常载具」处理。
VEHICLE_FIT = {"轰天雷": "GaiaFit", "镇山虎": "CivilianFit", "霸空雕": "FlyFit"}

# {中文名/英文名: (家族基础中文名, 家族基础英文名)}
VEHICLE_FAMILY_INDEX = {}
for _fam, _forms in VEHICLE_FAMILIES.items():
    for _cn, _en in _forms:
        VEHICLE_FAMILY_INDEX[_cn] = (_fam, _forms[0][1])
        VEHICLE_FAMILY_INDEX[_en] = (_fam, _forms[0][1])


def vehicle_family_of(cn, en=''):
    """返回载具所属家族 (基础中文名, 基础英文名)；不属于任何家族时返回 (None, None)。

    用于“进阶体沿用基础形态价格/获取方式”与分类归一。
    注：聚合载具（轰天雷/镇山虎/霸空雕）不属于进化家族，直接返回 (None, None)。
    """
    cn = (cn or '').strip()
    en = re.sub(r"_\d+$", "", (en or '').strip())
    if cn in VEHICLE_FIT or en in VEHICLE_FIT.values():
        return None, None
    if cn in VEHICLE_FAMILY_INDEX:
        return VEHICLE_FAMILY_INDEX[cn]
    if en in VEHICLE_FAMILY_INDEX:
        return VEHICLE_FAMILY_INDEX[en]
    # 英文名前缀兜底（如 GoldGaiaXXX → 泰坦家族）
    # 注意：聚合体英文名（GaiaFit/CivilianFit/FlyFit）本身以家族英文名为前缀
    #       （如 GaiaFit 以 Gaia 开头），必须先排除，否则会被当成泰坦家族进化体。
    if any(en == fit or en.startswith(fit) for fit in VEHICLE_FIT.values()):
        return None, None
    best = None
    for alias, info in VEHICLE_FAMILY_INDEX.items():
        if (alias.isascii() and en != alias and en.startswith(alias)
                and (best is None or len(alias) > len(best[0]))):
            best = (alias, info)
    return best[1] if best else (None, None)


# ---- 载具分类别名表（统一供 classify_vehicle 使用）----
def _alias_table(cn_en_pairs):
    """[(中文名, 英文名)] → {中文名/英文名: 中文名}"""
    table = {}
    for cn, en in cn_en_pairs:
        table[cn] = cn
        table[en] = cn
    return table


# 收费/氪金载具：仅通过充值活动获取，出现即需人工复核
PAID_VEHICLE_FAMILIES = ("泰坦", "制裁者", "先知", "幽鬼")
PAID_VEHICLE_ALIASES = _alias_table(
    [(cn, en) for _fam in PAID_VEHICLE_FAMILIES for cn, en in VEHICLE_FAMILIES[_fam]])

# 稀有载具：来源特殊/获取成本高，报告需标注获取时间（XML getTime 字段）
RARE_VEHICLE_NAMES = {"虚炎狼": "FireWolfCar", "切割者": "BoneBreaker", "胖哒号": "PandaCar"}
RARE_VEHICLE_ALIASES = _alias_table(list(RARE_VEHICLE_NAMES.items()))

# 免费载具：可免费获取、无直售价，数量普遍、参考价值低 → 报告不展示明细
FREE_VEHICLE_NAMES = {"异祖龙": "FlyDragonAir", "异齿虎": "SaberTigerCar", "雷鸣": "Thunder"}
FREE_VEHICLE_ALIASES = _alias_table(list(FREE_VEHICLE_NAMES.items()))

# 载具列表（即可正常持有的全部载具，共 54 款）：家族 + 单形态。
# 不含聚合体（见 VEHICLE_FIT）—— 其无法正常获取，出现即属异常。
VEHICLE_CATALOG = {}
for _forms in VEHICLE_FAMILIES.values():
    for _cn, _en in _forms:
        VEHICLE_CATALOG[_cn] = _en
VEHICLE_CATALOG.update(VEHICLE_STANDALONE)
# 列表载具的匹配集合（中文名 + 英文名）
CATALOG_VEHICLE_ALIASES = _alias_table(list(VEHICLE_CATALOG.items()))


def classify_vehicle(cn, en=''):
    """判定载具归属：('paid'|'rare'|'free'|'catalog'|'unknown', 归属家族名)。

    • paid   收费/氪金载具（泰坦/制裁者/先知/幽鬼）家族 → 报告重点复核
    • rare   稀有载具（虚炎狼/切割者/胖哒号）→ 报告标注获取时间
    • free   免费载具（可免费获取、无直售价）→ 报告不展示明细
    • catalog 载具列表内的常规载具 → 属正常，不单独列出
    • unknown 异常载具：不在载具列表内（含无法正常获取的聚合体）→ 报告重点复核

    返回值第二项为“家族基础名”（如 神圣盖亚 → 泰坦），无家族时回退为自身名。
    族内获取方式一致：基础形态收费/免费的，其进阶体同样按收费/免费处理。
    匹配顺序：聚合体排除 → 中文/英文精确 → 家族归一 → 英文前缀兜底。
    """
    cn = (cn or '').strip()
    en = re.sub(r"_\d+$", "", (en or '').strip())
    # 特殊载具/聚合：无法正常获取，出现即视为异常
    # （须先于前缀兜底判断，否则 GaiaFit 会被当成 Gaia 家族的进化体）
    if cn in VEHICLE_FIT or en in VEHICLE_FIT.values():
        return 'unknown', cn or en
    fam_cn, _fam_en = vehicle_family_of(cn, en)
    family = fam_cn or cn or en

    if cn in PAID_VEHICLE_ALIASES:
        return 'paid', family
    if en in PAID_VEHICLE_ALIASES:
        return 'paid', family
    if cn in RARE_VEHICLE_ALIASES or en in RARE_VEHICLE_ALIASES:
        return 'rare', family
    if cn in FREE_VEHICLE_ALIASES or en in FREE_VEHICLE_ALIASES:
        return 'free', family
    # 族内一致：进阶体继承基础形态的获取方式（如 雷霆 → 雷鸣家族 → 免费）
    if fam_cn in FREE_VEHICLE_NAMES:
        return 'free', family
    if fam_cn in RARE_VEHICLE_NAMES:
        return 'rare', family
    if fam_cn in PAID_VEHICLE_FAMILIES:
        return 'paid', family
    # 图鉴内常规载具
    if cn in CATALOG_VEHICLE_ALIASES or en in CATALOG_VEHICLE_ALIASES:
        return 'catalog', family
    # 英文名前缀兜底（如 GoldGaiaXXX）；
    # 聚合体英文名（GaiaFit/CivilianFit/FlyFit）以家族英文名为前缀，须先排除，
    # 否则会被当成家族进化体（如 GaiaFit 被当成泰坦家族）而漏报异常。
    if en and not any(en == fit or en.startswith(fit) for fit in VEHICLE_FIT.values()):
        best = None       # (匹配到的英文前缀, 家族中文名)
        for alias, (fam_cn2, _base_en) in VEHICLE_FAMILY_INDEX.items():
            if (alias.isascii() and en != alias and en.startswith(alias)
                    and (best is None or len(alias) > len(best[0]))):
                best = (alias, fam_cn2)
        if best:
            if best[1] in PAID_VEHICLE_FAMILIES:
                return 'paid', best[1]
            if best[1] in FREE_VEHICLE_NAMES:
                return 'free', best[1]
            if best[1] in RARE_VEHICLE_NAMES:
                return 'rare', best[1]
            return 'catalog', best[1]
    # 未匹配：不在载具列表内 → 异常载具
    if cn or en:
        return 'unknown', cn or en
    return '', ''

# ========================================================
# 🔒 工具函数
# ========================================================
def resource_path(relative_path):
    """获取资源文件的绝对路径。

    统一交由 app_paths 解析：打包解包目录 → 程序目录 → 上级目录 → 当前目录，
    不再以 os.getcwd() 为唯一基准（否则换个目录启动就找不到 main.ico）。
    """
    return app_paths.resource_path(relative_path)


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
    def render_uid_detail(uid, items, vip_level=None, banned_slots=None, asset=None):
        """渲染单个 UID 的异常详情报告。

        items: [{fname,theory,actual,name,cost,uid_cost,uid_file_count,
                 status,reason,index_mismatch,index_tag,detail_lines,
                 asset_lines,issues}]
        vip_level:   该账号最高 VIP 等级（同UID多档取最高），<0 或 None 表示无。
        banned_slots: 未参与检测的封禁槽位说明（服务器未返回内容）。
        asset:       该账号的资产汇总（批量 CSV 用的精简结构）。
        """
        uid_indexes = sorted({it['theory'] for it in items if it['theory'] != '无'})
        total_cost = sum(it['cost'] for it in items)
        uid_total_cost = max(it.get('uid_cost', it['cost']) for it in items)
        uid_file_count = max(it.get('uid_file_count', 1) for it in items)
        uid_status = 'FAIL' if any(it['status'] == 'fail' for it in items) else 'WARN'
        mismatch_items = [it for it in items if it['index_mismatch']]
        ban_tags = sorted({it['ban_tag'] for it in items if it.get('ban_tag')})

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

        # ---- 一览表：各存档的异常项按检测项汇总，便于快速定位 ----
        lines.append("📊 【异常一览】")
        for it in items:
            issues = it.get('issues') or []
            label = it['name'] or ''
            idx_text = it['theory'] if it['theory'] != '无' else '无'
            lines.append(f"   • [{idx_text}]{(' ' + label) if label else ''} "
                         f"[{it['status'].upper()}]")
            if issues:
                for issue in issues:
                    mark = '❌' if issue['status'] == 'fail' else '⚠️'
                    lines.append(f"       {mark} {issue['title']}：{issue['summary']}")
            else:
                lines.append("       （无明细）")
        lines.append("")

        # ---- 资产汇总（有采集数据即展示）----
        asset_lines = []
        for it in items:
            if it.get('asset_lines'):
                asset_lines = it['asset_lines']
                break
        if asset_lines:
            lines.append("💎 【资产汇总（时装 / 载具 / 特殊零件）】")
            if asset:
                lines.append("   " + "｜".join([
                    f"时装 {asset.get('fashion_text', '无')}",
                    f"载具 {asset.get('vehicle_text', '无')}",
                    f"特殊零件 {asset.get('parts_text', '无')}",
                    f"账号资产总值 {asset.get('value', 0)} 金",
                ]))
            lines.extend(asset_lines)
            lines.append("")

        if ban_tags:
            lines.append("🚨 【封禁槽位】" + "；".join(ban_tags))
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

        # ---- 逐存档详细检测日志 ----
        lines.append("=" * 60)
        lines.append("📋 逐存档详细检测日志")
        lines.append("=" * 60)
        for it in items:
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

        # ---- 未参与检测的封禁槽位说明 ----
        if banned_slots:
            lines.append("-" * 60)
            lines.append("ℹ️ 说明：以下槽位在下载结果中被标记封禁，因服务器不返回内容（无 XML 文件），")
            lines.append("   故未参与本次存档检测，封禁信息仅记录如下：")
            for s in banned_slots:
                lines.append(f"   • {s}")
            lines.append("")

        return "\n".join(lines)

    # ---- 资产报告 ----
    @staticmethod
    def render_asset_result(res, max_details=0):
        """把资产检测结果渲染成报告文本块。

        max_details > 0 时每个分类最多列出该数量的明细行（0 表示不限）。
        """
        if not res:
            return ""
        lines = []
        summary = res.get('kinds') or {}
        for kind in (ASSET_FASHION, ASSET_VEHICLE, ASSET_PARTS):
            data = summary.get(kind)
            if not data:
                continue
            cn = ASSET_KIND_CN[kind]
            ordered = sorted(data['items'].values(),
                             key=lambda x: (-((x.get('price') or 0) * x['count']),
                                            -(x.get('count') or 0),
                                            x['cn'] or x['name']))
            # ---- 明细展示口径：只列「有差值、需人工复核」的行 ----
            #   • 载具：收费(paid) / 稀有(rare)。免费载具与图鉴内常规载具不展示
            #     （异常载具由下方专属区块单独列出）；
            #     收费载具**与购买记录正常匹配（购买记录 ≥ 持有量）的不展示**。
            #   • 时装 / 特殊零件：**持有量 > 应有总量（差值 > 0）** 才展示。
            #     稀有零件按 baseLabel 全族合并判定，差值只落在代表记录上，
            #     故一族的全部阶只输出一行（行内含各阶折算明细）。
            if kind == ASSET_VEHICLE:
                ordered = [r for r in ordered
                           if r.get('tag') == 'rare'
                           or (r.get('tag') == 'paid'
                               and (not MATCH_PURCHASE_RECORDS
                                    or (r.get('pay') or 0) < r['count']))]
                total = sum(r['count'] for r in ordered)
                priced = sum(r['count'] for r in ordered if r.get('price') is not None)
                value = sum((r.get('price') or 0) * r['count'] for r in ordered)
                lines.append(f"  [{cn}] 共 {total} 件"
                             f"（可计价 {priced} 件，参考估值 {value} 金）")
            else:
                n_excess = sum(1 for r in ordered if r.get('excess'))
                lines.append(f"  [{cn}] 共 {data['total']} 件"
                             + (f"｜⚠️差值 {n_excess} 项" if n_excess else "｜✅ 无差值")
                             + f"（估值仅供参考 {data['value']} 金）")
                ordered = [r for r in ordered if r.get('excess')]
                if not ordered:
                    lines.append("      （持有量 ≤ 应有总量，来源说得清）")
                    continue
            limit = max_details if max_details and max_details > 0 else len(ordered)
            for rec in ordered[:limit]:
                lines.append("      " + ReportRenderer._asset_item_line(rec))
            if len(ordered) > limit:
                lines.append(f"      … 其余 {len(ordered) - limit} 项已省略"
                             f"（可在设置中调大“明细最大条数”）")
        if res.get('abnormal'):
            lines.append("  🚨 差值异常（持有量 > 应有总量，疑似异常修改存档，需人工复核）：")
            recs = sorted(res['abnormal'], key=lambda r: -r.get('excess_value', 0))
            shown, omitted = ReportRenderer._capped(recs)
            for rec in shown:
                lv = f" Lv{rec['level']}" if rec.get('level') else ""
                price = rec.get('excess_price', rec.get('price'))
                pay = rec.get('pay') or 0
                should = rec.get('explainable') or 0
                adjust = rec.get('adjust') or 0
                excess = rec.get('excess', 0)
                value = rec.get('excess_value', 0)
                name_cn = rec['cn'] or rec['name']
                # 零件：展示全族折算（各阶 × 升级消耗 = 一阶当量）
                fam = rec.get('family')
                if fam:
                    detail = " + ".join(f"Lv{lv0}×{cnt}"
                                        + (f"×{eq}" if eq > 1 else "")
                                        for _cn, lv0, cnt, eq in fam)
                    held_txt = f"{rec.get('held_equiv', rec['count'])}（{detail}）"
                elif rec.get('level1_equiv', 1) > 1:
                    # 单阶但已升阶：当量 = 数量 × 升阶消耗
                    held_txt = (f"{rec.get('held_equiv', rec['count'])}"
                                f"（{rec['count']}×{rec['level1_equiv']}）")
                else:
                    held_txt = str(rec['count'])
                # 应有总量 = 付费 + 券购 + 塔领 + 活动修正
                parts_of = " + ".join(b for b in (
                    f"付费 {pay}" if pay else "",
                    f"券购 {rec['ticket_buy']}" if rec.get('ticket_buy') else "",
                    f"塔领 {rec['tower_claimed']}" if rec.get('tower_claimed') else "",
                    f"活动 {adjust}" if adjust else "",
                ) if b)
                lines.append(
                    f"      - [{ASSET_KIND_CN[rec['kind']]}] {name_cn}{lv} "
                    + ("折算一阶当量 " if rec['kind'] == ASSET_PARTS else "持有 ")
                    + held_txt
                    + f" > 应有 {should}"
                    + (f"（{parts_of}）" if parts_of
                       else ("（无购买记录）" if not should else ""))
                    + f" = 差值 {excess} 份"
                    + (f"，单价 {price}金，差值估值 {value} 金"
                       if price is not None else "（未定价，仅报数量）"))
            if omitted:
                lines.append(f"      …另 {omitted} 项（详见异常详情文件）")
        unmatched = res.get('unmatched') or []
        if unmatched:
            uniq = sorted(set(unmatched))
            shown = uniq[:10]
        # 稀有时装：免费/付费时装之外，标注获取时间便于溯源
        rare_fash = res.get('rare_fashions') or []
        if rare_fash:
            lines.append("  💠 稀有时装（含获取时间）：")
            shown, omitted = ReportRenderer._capped(rare_fash)
            for rec in shown:
                lines.append("      - " + ReportRenderer._fashion_tag_line(rec))
            if omitted:
                lines.append(f"      …另 {omitted} 项（详见异常详情文件）")
        # 收费载具（含进阶体）：仅能通过充值活动获取，需重点核对
        # （与购买记录正常匹配的已在采集阶段排除，此处只剩未匹配的）
        paid = res.get('paid_vehicles') or []
        if paid:
            lines.append("  💳 收费载具（未匹配购买记录，需人工复核）：")
            shown, omitted = ReportRenderer._capped(paid)
            for rec in shown:
                lines.append("      - " + ReportRenderer._vehicle_tag_line(rec))
            if omitted:
                lines.append(f"      …另 {omitted} 项（详见异常详情文件）")
        # 购买了但存档内无：购买记录有、存档内未见或数量不足
        missing = res.get('missing_purchases') or []
        if missing:
            lines.append("  🔻 购买了但存档内无（购买记录与存档数据对不上，需人工复核）：")
            shown, omitted = ReportRenderer._capped(missing)
            for rec in shown:
                lines.append("      - " + ReportRenderer._missing_purchase_line(rec))
            if omitted:
                lines.append(f"      …另 {omitted} 项（详见异常详情文件）")
        # 稀有载具：标注获取时间便于溯源
        rare = res.get('rare_vehicles') or []
        if rare:
            lines.append("  ⭐ 稀有载具（含获取时间）：")
            shown, omitted = ReportRenderer._capped(rare)
            for rec in shown:
                lines.append("      - " + ReportRenderer._vehicle_tag_line(rec))
            if omitted:
                lines.append(f"      …另 {omitted} 项（详见异常详情文件）")
        # 异常载具：不在载具列表内（含无法正常获取的聚合体），需人工复核
        unknown = res.get('unknown_vehicles') or []
        if unknown:
            lines.append("  🚨 异常载具（不在载具列表内，需人工复核）：")
            shown, omitted = ReportRenderer._capped(unknown)
            for rec in shown:
                lines.append("      - " + ReportRenderer._vehicle_tag_line(rec))
            if omitted:
                lines.append(f"      …另 {omitted} 项（详见异常详情文件）")
        errors = res.get('errors') or []
        lines.extend(f"  {e}" for e in errors)
        return "\n".join(lines)

    # 标记文本（tag → 中文名）。稀有时装虽同为 'rare'，但由 is_fashion 区分，
    # 不会走 VEHICLE_TAG_CN（见 _asset_item_line 中的分支）。
    VEHICLE_TAG_CN = {'paid': '收费载具', 'rare': '稀有载具',
                      'free': '免费载具', 'unknown': '异常载具'}

    @staticmethod
    def _capped(recs):
        """按 CONCISE_REPORT 限制明细条数；返回 (展示列表, 省略条数)。

        简洁模式（默认）下每区块最多 MAX_REPORT_ITEMS 条，避免报告/日志刷屏；
        改为 False 则完整展开（旧行为）。数据本身不受影响，异常详情文件同样受限。
        """
        if CONCISE_REPORT and MAX_REPORT_ITEMS > 0 and len(recs) > MAX_REPORT_ITEMS:
            return recs[:MAX_REPORT_ITEMS], len(recs) - MAX_REPORT_ITEMS
        return recs, 0

    @staticmethod
    def _vehicle_tag_line(rec):
        """收费/稀有载具专用行：名称、所属系列、价格、获取时间、付费对照。"""
        name = rec['cn'] or rec['name']
        bits = [f"{name} ×{rec['count']}"]
        base = rec.get('base')
        if base and base != name:
            bits.append(f"（{base}系列）")
        price = rec.get('price')
        if price is not None:
            # 进阶体价格来自基础载具（进阶不改变售价）
            from_base = rec.get('price_from_base')
            bits.append(f"单价 {price}金" + (f"（按{from_base}计）" if from_base else ""))
        else:
            bits.append("未定价")
        gt = rec.get('get_time')
        if gt:
            bits.append(f"获取时间 {gt}")
        if rec.get('pay') is not None:
            bits.append(f"付费 {rec['pay']}")
        return " | ".join(bits)

    @staticmethod
    def _missing_purchase_line(rec):
        """「购买了但存档内无」专用行：名称、购买记录、存档内持有、缺口与差额。"""
        name = rec['cn'] or rec['name']
        kind = rec.get('kind') or ''
        lv = f" Lv{rec['level']}" if rec.get('level') else ""
        price = rec.get('price')
        bits = [f"[{ASSET_KIND_CN[kind]}] {name}{lv}" if kind else f"{name}{lv}"]
        if rec.get('absent'):
            bits.append(f"存档内未见（购买记录 {rec.get('pay') or 0}）")
        else:
            bits.append(f"持有 {rec.get('count', 0)} < 购买记录 {rec.get('pay') or 0}"
                        f"，缺 {rec.get('missing', 0)} 份")
        if price is not None:
            bits.append(f"单价 {price}金"
                        + (f"，缺值 {rec.get('missing_value', 0)} 金"
                           if rec.get('missing_value') else ""))
        else:
            bits.append("未定价")
        return " | ".join(bits)

    @staticmethod
    def _fashion_tag_line(rec):
        """稀有时装专用行：名称、数量、获取时间。"""
        name = rec['cn'] or rec['name']
        bits = [f"{name} ×{rec['count']}"]
        gt = rec.get('get_time')
        bits.append(f"获取时间 {gt}" if gt else "获取时间 未记录")
        return " | ".join(bits)

    @staticmethod
    def _asset_item_line(rec):
        """单条资产明细文本：名称、标记、等级、数量、单价、小计、免费额度、
        差值情况、来源、获取时间、付费对照。"""
        name = rec['cn'] or rec['name']
        lv = f" Lv{rec['level']}" if rec.get('level') else ""
        price = rec.get('price')
        is_rare_fash = (rec.get('tag') == 'rare' and rec.get('is_fashion'))
        bits = [f"{name}{lv} ×{rec['count']}"]
        if is_rare_fash:
            bits.append("【稀有时装】")
        else:
            tag_cn = ReportRenderer.VEHICLE_TAG_CN.get(rec.get('tag'))
            if tag_cn:
                bits.append(f"【{tag_cn}】")
        if rec.get('free'):
            bits.append("【免费】")
        # 稀有时装：无直售价属预期，不显示「未定价」
        if is_rare_fash:
            bits.append("无直售价")
        else:
            bits.append(f"单价 {price}金" if price is not None else "未定价")
            if price is not None:
                bits.append(f"小计 {price * rec['count']}")
        # 差值信息：**实际持有 > 应有总量**（免费额度+付费+券购+塔领+活动）才标注
        # （稀有时装已单列「稀有时装」区块，不在明细行重复标注）
        if not is_rare_fash and rec.get('excess') and rec['excess'] > 0:
            should = rec.get('explainable')
            if should is None:
                should = (rec.get('quota') or 0) + (rec.get('pay') or 0)
            # 零件：差值是按 baseLabel 全族折算出来的，需标明「全族当量」
            equiv = rec.get('held_equiv')
            if equiv is not None and rec.get('family'):
                detail = " + ".join(f"Lv{lv0}×{cnt}" + (f"×{eq}" if eq > 1 else "")
                                    for _cn, lv0, cnt, eq in rec['family'])
                bits.append(f"⚠️全族折算 {equiv}（{detail}）"
                            f" > 应有 {should}，差值 {rec['excess']} 份"
                            + (f"（{rec.get('excess_value')}金）"
                               if rec.get('excess_value') else "（未定价，仅报数量）"))
            else:
                lv_eq = rec.get('level1_equiv') or 1
                eq_txt = f"（{rec['count']}×{lv_eq}={rec.get('held_equiv', rec['count'])}）" \
                    if lv_eq > 1 else ""
                bits.append(f"⚠️持有 {rec['count']}{eq_txt}"
                            f" > 应有 {should}，差值 {rec['excess']} 份"
                            + (f"（{rec.get('excess_value')}金）"
                               if rec.get('excess_value') else "（未定价，仅报数量）"))
        # 附带展示券购 / 塔领 / 活动修正来源（仅供参考）
        elif not is_rare_fash and (rec.get('ticket_buy') or rec.get('tower_claimed')
                                   or rec.get('adjust')):
            # 显示存档中的**实际**获取记录（券购 / 塔领）与人工登记的活动修正
            got = []
            if rec.get('ticket_buy'):
                got.append(f"券购 {rec['ticket_buy']}")
            if rec.get('tower_claimed'):
                got.append(f"塔领 {rec['tower_claimed']}")
            if rec.get('adjust'):
                got.append(f"活动 {rec['adjust']}")
            bits.append(" + ".join(got))
        # 同族多阶（升级链）：在**每个**阶上都提示全族持有与总差值，
        # 避免只看单阶时误以为「只有 1 个却报差值」
        elif not is_rare_fash and rec.get('family_excess'):
            bits.append(f"⚠️同族共 {rec.get('family_equiv')} 个一阶当量，"
                        f"全族差值 {rec['family_excess']} 份")
        src = []
        if rec.get(ASSET_SOURCE_MAIN):
            src.append(f"主{rec[ASSET_SOURCE_MAIN]}")
        if rec.get(ASSET_SOURCE_TEAM):
            src.append(f"队友{rec[ASSET_SOURCE_TEAM]}")
        if src:
            bits.append("来源 " + "+".join(src))
        # 稀有载具/稀有时装展示获取时间，便于溯源
        if rec.get('tag') == 'rare' and rec.get('get_time'):
            bits.append(f"获取 {rec['get_time']}")
        if rec.get('pay') is not None:
            bits.append(f"付费 {rec['pay']}")
        return " | ".join(bits)

    # ---- 批量 CSV ----
    @staticmethod
    def build_batch_csv_rows(uid_rows):
        """uid_rows: [{uid,indexes,index_display,name,vip_level,status,reason,
                       multi,items,inactive_bans,asset_summary}] → CSV 行列表

        列顺序：UID_Index | Name | VIP | 状态 | 涉及存档数 | 封禁槽位 |
                时装 | 载具 | 稀有零件 | 资产价值 | 资产异常摘要 | 异常摘要
        UID_Index 列采用 uid_index_name 格式（每个存档自带名称，与 Name 列一一对应）。
        """
        rows = [['UID_Index', 'Name', 'VIP', '状态', '涉及存档数', '封禁槽位',
                 '时装', '载具', '特殊零件', '资产价值', '资产异常摘要', '异常摘要']]
        for row in uid_rows:
            detail = (row.get('reason') or '').replace('\n', ' ').replace('\r', ' ').replace(',', '，')
            if len(detail) > 400:
                detail = detail[:400] + "..."
            items = row.get('items') or []
            # 封禁列：本次检测到的封禁存档 + 未参与检测的封禁槽位（服务器未返回内容）
            ban_tags = {it['ban_tag'] for it in items if it.get('ban_tag')}
            ban_tags.update(row.get('inactive_bans') or [])
            asset = row.get('asset') or {}
            asset_detail = (asset.get('reason') or '').replace('\n', ' ').replace('\r', ' ') \
                .replace(',', '，')
            if len(asset_detail) > 400:
                asset_detail = asset_detail[:400] + "..."
            rows.append([
                row.get('index_display') or '无',
                row.get('name') or '无',
                ReportRenderer._vip_text(row.get('vip_level')),
                row.get('status') or 'warn',
                len(items),
                "；".join(sorted(ban_tags)) or '无',
                asset.get('fashion_text') or '无',
                asset.get('vehicle_text') or '无',
                asset.get('parts_text') or '无',
                asset.get('value') if asset.get('value') is not None else '无',
                asset_detail or '无',
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
# 💰 物品价值对照表（good_items.csv）
# ========================================================
class GoodsTable:
    """id/价值对照表（inputdata/good_items.csv，GBK 编码）。

    表头：记录ID(propId),金额(price),物品（cNname）,英文名(name),分类,,备注
    同一物品可能随版本多次上架（价格不同），此处按“最高价”归并，
    避免用早期折扣价低估资产。
    """

    def __init__(self):
        self.by_id = {}       # propId(int) -> {'price', 'cn', 'en', 'cat'}
        self.by_en = {}       # 英文名 -> 同结构
        self.by_cn = {}       # 中文名 -> 同结构
        self.loaded = False
        self.error = ''

    @staticmethod
    def _norm_name(name):
        """去掉 _数字 后缀（如 loaderParts_96 → loaderParts）。"""
        if not name:
            return ''
        return re.sub(r"_\d+$", "", name.strip())

    def _add(self, bucket, key, info):
        if not key:
            return
        prev = bucket.get(key)
        if prev is None or info['price'] > prev['price']:
            bucket[key] = info

    def load(self, csv_path):
        self.by_id.clear()
        self.by_en.clear()
        self.by_cn.clear()
        self.loaded = False
        self.error = ''
        if not csv_path or not os.path.exists(csv_path):
            self.error = f"未找到价值对照表：{csv_path}"
            return None
        raw = None
        for enc in ('gbk', 'utf-8-sig', 'utf-8'):
            try:
                with open(csv_path, 'rb') as f:
                    raw = f.read().decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
            except OSError as e:
                self.error = f"读取价值对照表失败：{e}"
                return None
        if raw is None:
            self.error = "价值对照表编码无法识别（期望 GBK/UTF-8）"
            return None
        try:
            rows = list(csv.reader(io.StringIO(raw)))
        except Exception as e:
            self.error = f"解析价值对照表失败：{e}"
            return None
        for row in rows[1:]:
            if len(row) < 5:
                continue
            pid_text = (row[0] or '').strip()
            try:
                price = int(float((row[1] or '0').strip()))
            except ValueError:
                continue
            cn = (row[2] or '').strip()
            en = (row[3] or '').strip()
            cat = (row[4] or '').strip()
            info = {'price': price, 'cn': cn, 'en': en, 'cat': cat}
            if pid_text.isdigit():
                self._add(self.by_id, int(pid_text), info)
            self._add(self.by_en, en, info)
            base = self._norm_name(en)
            if base and base != en:
                self._add(self.by_en, base, info)
            if cn and cn != '0':
                self._add(self.by_cn, cn, info)
        self.loaded = bool(self.by_en or self.by_cn)
        if not self.loaded:
            self.error = "价值对照表为空或格式不符"
        return self.by_en if self.loaded else None

    @staticmethod
    def is_chip(cn, en=''):
        """碎片类（合成材料）判定：不参与计价。"""
        cn = cn or ''
        if CHIP_MARK in cn:
            return True
        # 无中文名时按英文名兜底（Chip 结尾或含 Cash）
        en = en or ''
        return en.endswith('Chip') or en.endswith('Cash')

    def price_of(self, name, cn='', cat_wanted=None):
        """按英文名/中文名查价；返回 (price, matched_by, cat) 或 None。"""
        if name:
            info = self.by_en.get(name)
            if info is None:
                info = self.by_en.get(self._norm_name(name))
            if info is not None and (cat_wanted is None or info['cat'] in cat_wanted):
                return info['price'], 'en', info['cat']
        if cn:
            info = self.by_cn.get(cn)
            if info is not None and (cat_wanted is None or info['cat'] in cat_wanted):
                return info['price'], 'cn', info['cat']
        return None


# 全局实例，整个程序共用
GOODS_TABLE = GoodsTable()
_goods_table_path = None


def ensure_goods_table(csv_path=None):
    """按需加载价值对照表（同路径只加载一次）。

    路径统一经 app_paths 解析：配置项 → 打包资源目录／程序目录下的 inputdata，
    不再依赖启动时的当前工作目录。
    """
    global _goods_table_path
    path = app_paths.resolve_input(csv_path, GOODS_CSV_REL)
    if GOODS_TABLE.loaded and _goods_table_path == path:
        return GOODS_TABLE
    GOODS_TABLE.load(path)
    _goods_table_path = path
    return GOODS_TABLE


class AssetCollector:
    """采集存档内的时装 / 载具 / 特殊零件，并与 pay 节点购买次数对照。

    节点范围（依据 xpw_objects.jsonc）：
      • 主存档：equip / equipBag / equipHouse（partType=fashion|vehicle）、
                partsBag（零件背包）、arms / armsBag / armsHouse（武器上镶嵌的零件）
      • 队友存档：more / moreBag 内每名队友的 SAVE 子存档（同样结构）

    差值判定（★ 本检测的核心，价值仅作参考）：
        差值 = 持有量 − 应有总量；应有总量 = 免费额度(free_quota.ini) + 付费次数。
        差值 > 0 才判为异常（不存在“差值阈值”这类人工参数）。
        其中：免费时装不存在差值（豁免）；稀有时装单列区块（持有即列出）；
              载具由收费/稀有/免费/异常分类覆盖，不参与本差额判定。

    零件分类（objType，权威定义见文件头 PARTS_NORMAL_NAMES 注释）：
      普通零件（bullet/shooter/capacity/loader/stabler/sight）、
      特殊零件（special=腐蚀芯片 / skill=猎人技能器）不计入统计，
      仅统计稀有零件（rare）—— 与免费额度配置 free_quota.ini 的 [parts] 对应。
    """

    # 主存档内的时装/载具容器
    EQUIP_NODES = ('equip', 'equipBag', 'equipHouse')
    # 武器容器（内含 partsSave.arr 镶嵌零件）
    ARMS_NODES = ('arms', 'armsBag', 'armsHouse')
    # 队友存档节点
    TEAM_NODES = ('more', 'moreBag')

    def __init__(self, table=None, abnormal_min_value=None):
        self.table = table or GOODS_TABLE
        # {kind: {来源: {key: {'name','cn','count','price','source'}}}}
        self.items = defaultdict(lambda: defaultdict(dict))
        self.unmatched = []       # 无法计价的物品
        self.warnings = []        # 异常/提示行
        # 存档内其它数据源（collect() 时填充）
        self.goods_buy = {}       # goods.buyNumObj: {标签: 购买次数}
        self.tower = {}           # tower.gO.saveObj: {层: 通关难度}
        self.tower_claimed = {}    # {baseLabel: 已领取的塔层奖励份数}
        self.pay_totals = {}       # {kind: {名称: 付费次数}}（购买记录，供缺口反查）
        # 判定阈值统一来自 inputdata/free_quota.ini 的免费额度，
        # 不再有“持有vs付费差值阈值”这类人工参数。
        # 差值价值达到该值才判为异常（0 = 只要有差值就报）；
        # 取值来自 free_quota.ini 的 [default] min_excess_value。
        try:
            self.abnormal_min_value = max(
                0, int(abnormal_min_value if abnormal_min_value is not None
                       else DEFAULT_ABNORMAL_MIN_VALUE))
        except (TypeError, ValueError):
            self.abnormal_min_value = DEFAULT_ABNORMAL_MIN_VALUE

    # ---- 基础工具 ----
    @staticmethod
    def _child_text(node, child_name):
        e = node.find(f's[@name="{child_name}"]')
        if e is None or e.text is None:
            return ''
        return e.text.strip()

    @staticmethod
    def _num(text, default=0):
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return default

    @classmethod
    def _iter_items(cls, container):
        """容器节点 → 物品项迭代（优先 arr 数组；无 arr 时取 Object 子项）。"""
        if container is None:
            return
        arr = container.find('s[@name="arr"]')
        if arr is not None:
            for it in arr:
                yield it
            return
        for it in container:
            if it.get('type') == 'Object' and it.get('name') in ('null', 'obj'):
                yield it

    @classmethod
    def _item_meta(cls, node):
        return {
            'name': cls._child_text(node, 'name'),
            'cn': cls._child_text(node, 'cnName'),
            'partType': cls._child_text(node, 'partType'),
            'itemsType': cls._child_text(node, 'itemsType'),
            'level': cls._num(cls._child_text(node, 'itemsLevel'), 0),
            'count': max(1, cls._num(cls._child_text(node, 'nowNum'), 1)),
            # 载具获取时间：优先 getTime，缺失时回退 severTime（两者均为服务器记录、仅差数秒）
            'getTime': (cls._child_text(node, 'getTime')
                        or cls._child_text(node, 'severTime')),
        }

    @staticmethod
    def is_rare_parts(cn, level, en=''):
        """稀有零件判定（objType == 'rare'）。

        权威口径（见文件头 PARTS_NORMAL_NAMES 注释）：
            objType = bullet/shooter/capacity/loader/stabler/sight → 普通零件
            objType = special（腐蚀芯片）/ skill（猎人技能器）     → 特殊零件
            objType = rare                                          → 稀有零件
        存档中的零件 name 即 baseLabel（如 shockParts_3），去 _N 后缀后即可判定，
        不再依赖“等级是不是 3 的倍数”这类不可靠的启发式。
        仅当存档缺少英文名（老版本）时，才回退到中文名 + 等级兜底判定。
        """
        base = GoodsTable._norm_name(en)
        if base:
            return base not in PARTS_NORMAL_NAMES and base not in PARTS_SPECIAL_NAMES
        # ---- 兜底：无英文名 ----
        cn = (cn or '').strip()
        if cn in RARE_PARTS_EXCLUDE_CN or cn.endswith("零件"):
            return False        # 特殊零件 / 普通零件（小零件、高级零件、超凡零件…）
        try:
            lv = int(level)
        except (TypeError, ValueError):
            lv = 0
        # 普通零件等级恒为 3 的倍数，故 3 的倍数视为普通零件
        return not (0 < lv <= RARE_PARTS_MAX_LEVEL and lv % RARE_PARTS_LEVEL_STEP == 0)

    # ---- 采集 ----
    def _add(self, kind, key, name, cn, count, source, level=0, is_chip=False, cat='',
             get_time='', tag=''):
        bucket = self.items[kind][source]
        rec = bucket.get(key)
        if rec is None:
            bucket[key] = {'name': name, 'cn': cn, 'count': count, 'level': level,
                           'source': source, 'is_chip': is_chip, 'cat': cat, 'price': None,
                           'get_time': get_time, 'tag': tag}
            return
        rec['count'] += count
        # 获取时间保留最早的一条（同一物品可能来自多个存档/槽位）
        if get_time and (not rec.get('get_time') or get_time < rec['get_time']):
            rec['get_time'] = get_time
        if tag and not rec.get('tag'):
            rec['tag'] = tag
        # 保留等级最高的一条作为展示/判定依据
        if level > rec.get('level', 0):
            rec['level'] = level
            rec['is_chip'] = is_chip

    def collect_equip_container(self, container, source):
        """采集 equip / equipBag / equipHouse 中的时装与载具。"""
        for it in self._iter_items(container):
            meta = self._item_meta(it)
            pt = meta['partType']
            if pt == ASSET_FASHION:
                kind, key = ASSET_FASHION, meta['name'] or meta['cn']
            elif pt == ASSET_VEHICLE:
                kind, key = ASSET_VEHICLE, meta['name'] or meta['cn']
            else:
                continue
            if not key:
                continue
            tag = ''
            if pt == ASSET_VEHICLE:
                tag, _base = classify_vehicle(meta['cn'], meta['name'])
            self._add(kind, key, meta['name'], meta['cn'], meta['count'], source,
                      level=meta['level'],
                      is_chip=self.table.is_chip(meta['cn'], meta['name']),
                      get_time=meta['getTime'], tag=tag)

    def collect_parts_container(self, container, source):
        """采集零件（零件背包 / 武器镶嵌位）。

        零件按 **基础名 + 等级** 分别统计：同名不同等级是不同物品
        （如 loaderParts_69 与 loaderParts_96），合并会把数量与价值算错。
        """
        for it in self._iter_items(container):
            meta = self._item_meta(it)
            if not meta['name'] and not meta['cn']:
                continue
            if not self.is_rare_parts(meta['cn'], meta['level'], meta['name']):
                continue
            base = self.table._norm_name(meta['name']) or meta['cn']
            key = f"{base}_{meta['level']}" if meta['level'] else base
            self._add(ASSET_PARTS, key, meta['name'], meta['cn'], meta['count'], source,
                      level=meta['level'],
                      is_chip=self.table.is_chip(meta['cn'], meta['name']))

    def collect_arms_container(self, container, source):
        """采集武器上镶嵌的零件（partsSave.arr）。"""
        for it in self._iter_items(container):
            ps = it.find('s[@name="partsSave"]')
            if ps is None:
                continue
            self.collect_parts_container(ps, source)

    def _walk_save(self, save_node, source):
        """采集一份完整存档结构（主存档或队友 SAVE）。"""
        for node in self.EQUIP_NODES:
            self.collect_equip_container(save_node.find(f's[@name="{node}"]'), source)
        self.collect_parts_container(save_node.find('s[@name="partsBag"]'), source)
        for node in self.ARMS_NODES:
            self.collect_arms_container(save_node.find(f's[@name="{node}"]'), source)

    def _load_pay(self, save_node):
        """读取 pay.obj：{propId: 购买次数}。"""
        pay = save_node.find('s[@name="pay"]/s[@name="obj"]')
        bought = {}
        if pay is None:
            return bought
        for c in pay:
            pid = c.get('name')
            if not pid or not pid.isdigit():
                continue
            cnt = self._num((c.text or '').strip(), 0)
            if cnt:
                bought[int(pid)] = cnt
        return bought

    def _load_goods_buy(self, save_node):
        """读取 goods.buyNumObj：{商品标签: 购买数量}。

        存档原文形如 <s type="String" name="shockParts_1_p">001l</s>，
        数值经 TextWay.toCode32 编码，需 decode_text32_number 还原。

        键后缀含义（GoodsSaveGroup.as）：
            _p = 零件券商店（partsCoin）购买次数
            _a = 其它货币（黄金/活动币）购买次数
            _t = 限时商店购买次数
            _d / _arena / _tax = 其它渠道
        本工具关注 `_p`：零件券商店的**实际购买次数**，
        它是免费额度的一部分（券购不花黄金）。
        """
        out = {}
        node = save_node.find('s[@name="goods"]/s[@name="buyNumObj"]')
        if node is None:
            return out
        for c in node:
            name = c.get('name')
            if not name:
                continue
            num = decode_text32_number(c.text, None)
            if num:
                out[name] = num
        return out

    def _load_tower(self, save_node):
        """读取 tower.gO.saveObj：{层号: 该层已通关的最高难度(0~4)}。

        虚天塔各层奖励（零件/材料）在首次通关时发放 —— 奖励绑在累计进度上，
        **一次性、不随周重置**（TowerSave.newWeek 只重置本周技能次数 us/usUse）。
        因此某层 saveObj[层] >= 1 即可认为该层的零件奖励已到手。
        """
        out = {}
        node = save_node.find('s[@name="tower"]/s[@name="gO"]/s[@name="saveObj"]')
        if node is None:
            return out
        for c in node:
            name = (c.get('name') or '').strip()
            if not name.isdigit():
                continue
            lv = self._num((c.text or '').strip(), 0)
            if lv > 0:
                out[int(name)] = lv
        return out

    def _tower_parts_claimed(self, tower):
        """已通关的塔层对应的零件奖励 → {baseLabel: 已领取份数}。

        塔层掉落表见 TOWER_PARTS_DROPS：每层固定给 1 个一阶零件。
        """
        claimed = defaultdict(int)
        for lv, diff in (tower or {}).items():
            base = TOWER_PARTS_DROPS.get(lv)
            if base:
                claimed[base] += 1
        return claimed

    def _pay_totals(self, bought):
        """把 pay 的 propId 归并成 {kind: {key: 数量}}。"""
        totals = {ASSET_FASHION: defaultdict(int),
                  ASSET_VEHICLE: defaultdict(int),
                  ASSET_PARTS: defaultdict(int)}
        cats = (ASSET_FASHION, ASSET_VEHICLE, ASSET_PARTS)
        for pid, cnt in bought.items():
            info = self.table.by_id.get(pid)
            if not info:
                continue
            cat = info['cat'] or ''
            kind = None
            if cat == '载具' or cat == '载具碎片':
                kind = ASSET_VEHICLE
            elif cat.startswith('时装'):
                kind = ASSET_FASHION
            elif cat == '零件':
                kind = ASSET_PARTS
            if kind is None:
                continue
            key = info['en'] or info['cn']
            if self.table.is_chip(info['cn'], info['en']):
                continue    # 碎片/材料不参与对照
            totals[kind][key] += cnt
        return totals

    def collect(self, file_path):
        """采集指定存档；返回自身，结果在 self.items / self.warnings 中。"""
        root, _, _ = smart_load_xml(file_path)
        if root is None:
            self.warnings.append("❌ XML 文件严重损坏，无法解析资产节点")
            return self
        save_node = root
        # 兼容根节点直接就是 null 的情况
        if save_node.get('name') != 'null':
            inner = save_node.find('s[@name="null"]')
            if inner is not None:
                save_node = inner

        # 1) 主存档
        self._walk_save(save_node, ASSET_SOURCE_MAIN)

        # 2) 队友存档（more / moreBag → SAVE）
        for node in self.TEAM_NODES:
            team_root = save_node.find(f's[@name="{node}"]')
            if team_root is None:
                continue
            for tor in self._iter_items(team_root):
                save = tor.find('s[@name="SAVE"]')
                if save is None:
                    continue
                self._walk_save(save, ASSET_SOURCE_TEAM)

        # 3) 计价 + 与「付费/券购」对照
        #    pay.obj        : 黄金购买的 propId 次数（付费）
        #    goods.buyNumObj: 各渠道购买次数（_p = 零件券商店，不花黄金）
        #    tower.gO       : 虚天塔通关进度 → 已领取的塔层零件奖励
        bought = self._load_pay(save_node)
        pay_totals = self._pay_totals(bought)
        self.pay_totals = pay_totals      # 供「购买了但存档内无」反查
        self.goods_buy = self._load_goods_buy(save_node)
        self.tower = self._load_tower(save_node)
        self.tower_claimed = self._tower_parts_claimed(self.tower)
        cats_wanted = {'时装', '时装(下架)', '时装(升级)', '载具', '零件'}

        for kind in (ASSET_FASHION, ASSET_VEHICLE, ASSET_PARTS):
            for source in (ASSET_SOURCE_MAIN, ASSET_SOURCE_TEAM):
                for key, rec in self.items[kind][source].items():
                    # 免费时装：活动/初始赠送，本身可无限免费获取
                    # → 不做限额判定，也不计价值/“未定价”
                    if kind == ASSET_FASHION and is_free_fashion(rec['cn'], rec['name']):
                        rec['free'] = True
                        rec['no_excess'] = True
                        rec['price'] = None
                        rec['pay'] = None
                        continue
                    # 稀有时装：免费时装与付费时装之外（碎片合成/活动产出）。
                    # 额度固定为 0 → 只要持有即返回（并标注获取时间便于溯源）。
                    if kind == ASSET_FASHION and is_rare_fashion(rec['cn'], rec['name'],
                                                                 self.table):
                        rec['tag'] = 'rare'
                        rec['is_fashion'] = True    # 供渲染层与「稀有载具」区分
                        rec['quota_fixed'] = 0
                        rec['price'] = None
                        rec['pay'] = None
                        continue
                    # 载具类别：氪金(paid)/稀有(rare) 需重点展示；
                    # catalog=图鉴内常规载具（免费可得，表内常无价属正常）；unknown=图鉴外载具
                    if kind == ASSET_VEHICLE:
                        tag, base = classify_vehicle(rec['cn'], rec['name'])
                        rec['tag'] = tag
                        rec['base'] = base
                        # 载具合法性由专属区块覆盖（收费/稀有/免费/异常），
                        # 且图鉴内载具本身可免费获得 → 整体豁免差值判定，避免误报
                        rec['no_excess'] = True
                    price = None
                    if not rec['is_chip']:
                        got = self.table.price_of(rec['name'], rec['cn'], cats_wanted)
                        if got:
                            price = got[0]
                            if not rec['cat']:
                                rec['cat'] = got[2]
                    # 载具进阶体：对照表通常只收录基础形态价格，进阶后价格不变
                    # （如 神圣盖亚 → 泰坦家族 → 按泰坦 1500 计；烈焰 → 赤焰家族 → 按赤焰计）
                    if price is None and kind == ASSET_VEHICLE:
                        fam_cn, fam_en = vehicle_family_of(rec['cn'], rec['name'])
                        if fam_cn and fam_cn != (rec['cn'] or '').strip():
                            got_base = (self.table.price_of(fam_en, fam_cn, cats_wanted)
                                        or self.table.price_of(fam_cn, fam_en, cats_wanted))
                            if got_base:
                                price = got_base[0]
                                rec['price_from_base'] = fam_cn
                                if not rec['cat']:
                                    rec['cat'] = got_base[2]
                    rec['price'] = price
                    if price is None:
                        # 未定价提示：载具由专门渠道呈现（收费/稀有/异常），
                        # 列表内常规载具未直售属正常，不再计入“未定价”告警；
                        # 非载具（时装/零件）才需提示对照表覆盖情况。
                        if not rec['is_chip'] and kind != ASSET_VEHICLE:
                            self.unmatched.append(f"{ASSET_KIND_CN[kind]}:"
                                                  f"{rec['cn'] or rec['name']}")
                        rec['pay'] = None
                        continue
                    # 购买记录对照：未购买过（对照表有价但 pay 无记录）的物品，
                    # 会在判定阶段按「持有量 > 应有总量（差值）」处理。
                    pay_cnt = pay_totals[kind].get(key)
                    if pay_cnt is None and rec['name']:
                        pay_cnt = pay_totals[kind].get(self.table._norm_name(rec['name']))
                    # 载具进阶体：购买记录通常落在基础形态（如 神圣盖亚 → 泰坦），
                    # 按家族归一后仍视为已购买，避免正常匹配的被误报。
                    if pay_cnt is None and kind == ASSET_VEHICLE:
                        fam_cn, fam_en = vehicle_family_of(rec['cn'], rec['name'])
                        for token in (rec.get('base'), fam_cn, fam_en):
                            if not token:
                                continue
                            got_pay = (pay_totals[kind].get(token)
                                       or pay_totals[kind].get(self.table._norm_name(token)))
                            if got_pay:
                                pay_cnt = got_pay
                                break
                    rec['pay'] = pay_cnt or None
        return self

    # ---- 汇总 ----
    def summary(self):
        """返回各分类的汇总：总件数、可计价件数、参考估值、以及统一口径的差值异常项。

        ★ 本检测的重点是「差值」，不是估值 —— 找出持有量与应有总量对不上的物品
        （通常意味着存档被异常修改）：
            应有总量 = 免费额度(free_quota.ini) + 付费次数
            差值数量 = max(0, 持有量 − 应有总量)
            差值价值 = 单价 × 差值数量        ← 仅用于排序/展示，不参与判定
        差价 > 0 且（未定价 或 差值价值 ≥ min_excess_value）→ 报为异常。

        稀有零件按 **baseLabel 全族合并** 判定：高阶由低阶升级而来（2 阶吃 4 份一阶），
        而应有总量是「可获取的一阶份数」，故先折算成一阶当量再比较 ——
        既避免高阶被重复计入额度，也与「升级消耗低阶」的机制一致。

        这样只报一次：既说明“多了多少份”，也说明“大概值多少黄金”，
        不再出现同一物品被高价/高频/持有量三条规则重复命中的情况。
        """
        out = {}
        for kind in (ASSET_FASHION, ASSET_VEHICLE, ASSET_PARTS):
            total = priced = value = 0
            abnormal = []
            merged = self.merged_items(kind)
            for rec in merged.values():
                total += rec['count']
                price = rec.get('price')
                if price is not None:
                    priced += rec['count']
                    value += price * rec['count']

            if kind == ASSET_PARTS:
                self._balloon_parts(merged, abnormal)
            else:
                for rec in merged.values():
                    # 稀有时装：已在「稀有时装」区块单列（含获取时间），
                    # 不参与差值判定 —— 否则会被判成「额度 0 → 持有即差值」而重复报告
                    if rec.get('tag') == 'rare' and rec.get('is_fashion'):
                        rec['quota'] = 0
                        continue
                    self._balloon_item(kind, rec, abnormal)
            abnormal.sort(key=lambda r: -r.get('excess_value', 0))
            out[kind] = {'total': total, 'priced': priced, 'value': value,
                         'abnormal': abnormal, 'items': merged}
        return out

    def _balloon_item(self, kind, rec, abnormal):
        """单个物品的「持有量 ↔ 应有总量」差值判定（时装；载具走 no_excess 分支）。

        ★ 差值口径（本检测的核心，不是估值）：
              应有总量 = 免费额度(free_quota.ini) + 付费次数(pay.obj)
              差值     = 持有量 − 应有总量
          • 差值 ≤ 0（来源说得清）→ **不输出**；
          • 差值 > 0（含既无免费额度、也无购买记录）→ 输出，交人工复核。
        价值只随差值附带展示（多出来多少、值多少），不参与是否异常的判断。
        """
        if rec.get('no_excess'):
            # 免费时装 / 免费载具：本身可无限免费获取，不存在差值
            rec['quota'] = 0
            return
        cn, en = rec.get('cn'), rec.get('name')
        quota = free_quota_of(kind, cn, en)
        rec['quota_explicit'] = free_quota_entry(kind, cn, en) is not None
        price = rec.get('price')
        paid_part = rec.get('pay') or 0
        if quota == FREE_QUOTA_UNLIMITED:
            # 配置里登记为「不限」（可无限免费获取）→ 不存在差值
            rec['quota'] = FREE_QUOTA_UNLIMITED
            rec['explainable'] = None
            return
        rec['quota'] = quota
        # 应有总量 = 免费额度 + 付费次数，供报告统一显示
        should_have = quota + paid_part
        rec['explainable'] = should_have
        if not MATCH_PURCHASE_RECORDS and should_have <= 0:
            return              # 旧口径：既无免费额度也无购买记录 → 无参照，不判定
        if rec['count'] <= should_have:
            return              # 来源说得清 → 不输出
        excess = rec['count'] - should_have
        rec['excess'] = excess
        rec['excess_value'] = (price or 0) * excess
        rec['no_record'] = should_have <= 0
        if price is None or rec['excess_value'] >= self.abnormal_min_value:
            abnormal.append(rec)

    def _balloon_parts(self, merged, abnormal):
        """稀有零件差值判定：**把高级折算成低级后统计**，实际当量 > 应有总量即报。

        折算规则（权威：AS3 ThingsDefine.getComposeMustNum / PartsRare）：
            高级零件由低级升级而来（升阶会吃掉 3~4 份低级），
            故把每一阶都换算成「一阶当量」再求和：
                一阶当量 = Σ(该阶持有量 × 升到该阶的累计消耗)
            等价于：把高级零件"拆解"回低级材料后，看总共需要多少低级零件。

        应有总量 = 付费次数(pay) + 券购次数(goods._p) + 已领塔奖励(tower)
                   + 活动修正（free_quota.ini 的 [parts_adjust]：活动/兑换/赠送等
                     存档内查不到记录的来源，按零件人工登记 —— 即“活动”的修正参数）

        判定：`实际一阶当量 > 应有总量` → 差值异常（疑似异常改档）。
        不再报「实际 < 应有」（元素球等被当作合成材料消耗是正常现象）。
        价值只随差值附带展示，不参与判定。
        """
        families = {}
        for key, rec in merged.items():
            base = (self.table._norm_name(rec.get('name')) or '').strip() \
                or (rec.get('cn') or rec.get('name') or key)
            families.setdefault(base, []).append(rec)

        for base, recs in families.items():
            recs.sort(key=lambda r: r.get('level', 0))
            if all(r.get('no_excess') for r in recs):
                for r in recs:
                    r['quota'] = 0
                continue
            # 代表记录：优先一阶，否则取持有量最大者
            rep = next((r for r in recs if r.get('level', 0) == 1), None) \
                or max(recs, key=lambda r: r['count'])
            # 付费次数按 baseLabel 记录，全族只计一次（取最大，避免各阶重复累加）
            paid_part = max((r.get('pay') or 0) for r in recs)
            # 零件券商店实际购买次数（buyNumObj 键为 "<baseLabel>_1_p"）
            ticket_part = self.goods_buy.get(f"{base}_1_p", 0)
            if not ticket_part:
                ticket_part = sum(v for k, v in self.goods_buy.items()
                                  if k.endswith('_p')
                                  and self.table._norm_name(k[:-2]) == base)
            # 虚天塔已领取的该零件奖励（一次性，不随周重置）
            tower_part = (self.tower_claimed or {}).get(base, 0)
            # ★ 活动修正（free_quota.ini 的 [parts_adjust]）：活动/兑换/赠送等
            #   存档内查不到记录的来源，无法自动统计，只能按零件人工登记。
            adjust_part = free_quota_entry(ASSET_PARTS_ADJUST,
                                           PARTS_BASE_TO_CN.get(base, ''), base)
            no_limit = adjust_part == FREE_QUOTA_UNLIMITED
            adjust_part = 0 if (adjust_part is None or no_limit) else adjust_part
            for r in recs:
                r['quota'] = adjust_part
                r['ticket_buy'] = ticket_part
                r['tower_claimed'] = tower_part
                r['adjust'] = adjust_part
                r['pay'] = paid_part or None

            # ★ 把高级折算成低级：各阶 × 升到该阶的累计消耗，求和得"实际一阶当量"
            held_equiv = 0
            for r in recs:
                equiv = parts_level1_equiv(base, r.get('level', 1))
                r['level1_equiv'] = equiv
                held_equiv += r['count'] * equiv
            rep['held_equiv'] = held_equiv
            if len(recs) > 1:
                rep['family'] = [(r.get('cn') or r.get('name'), r.get('level', 0),
                                  r['count'], r['level1_equiv']) for r in recs]

            # 价值按一阶单价折算（差额相当于等量一阶零件）
            lv1 = next((r for r in recs if r.get('level', 0) == 1), None)
            price = (lv1 or rep).get('price')
            if price is None:
                price = rep.get('price')

            # 应有总量 = 付费 + 券购 + 塔领（存档实际记录） + 活动修正（人工登记）
            should_have = paid_part + ticket_part + tower_part + adjust_part
            rep['explainable'] = should_have
            for r in recs:
                r['explainable'] = should_have
            # 登记为「不限」→ 无法判定差值，跳过
            if no_limit:
                for r in recs:
                    r['explainable'] = None
                continue
            # 无任何来源记录 → 无参照，不判定（可在 [parts_adjust] 登记活动所得）
            if should_have <= 0:
                continue
            # ★ 实际（折算后）> 应有 → 报错
            excess = held_equiv - should_have
            if excess > 0:
                rep['excess'] = excess
                rep['excess_value'] = (price or 0) * excess
                rep['excess_price'] = price
                # 全族共享上下文：明细行里每个阶都能看到「同族共多少、差值多少」
                for r in recs:
                    r['family_equiv'] = held_equiv
                    r['family_excess'] = excess
                if price is None or rep['excess_value'] >= self.abnormal_min_value:
                    abnormal.append(rep)

    # ---- 购买记录 ↔ 存档数据：反向缺口（购买了但存档内无）----
    def find_missing_purchases(self, summary):
        """找出**付费载具 / 付费时装**中「购买了但存档内无」的记录。

        与「未购买但存档内拥有」（持有量 > 购买记录）互为反向：
            • 存档内持有但数量不足（持有量 < 购买记录）→ missing = 购买 − 持有
            • 存档内完全未见（购买记录存在但无对应物品）→ absent = True
        返回 [rec]（kind / name / cn / pay / count / missing / missing_value / price），
        供报告与 CSV 的「🔻 购买了但存档内无」区块使用。
        """
        out = []

        # 1) 存档内持有、但少于购买记录（持有 < 购买）
        for kind in (ASSET_FASHION, ASSET_VEHICLE):
            for rec in (summary.get(kind) or {}).get('items', {}).values():
                if kind == ASSET_VEHICLE and rec.get('tag') != 'paid':
                    continue            # 只比对付费载具
                pay_cnt = rec.get('pay') or 0
                if pay_cnt > rec['count']:
                    item = dict(rec)
                    item['kind'] = kind
                    item['missing'] = pay_cnt - rec['count']
                    item['missing_value'] = (rec.get('price') or 0) * item['missing']
                    item['absent'] = False
                    out.append(item)

        # 2) 存档内完全未见（购买记录中的付费载具 / 付费时装）
        present = {ASSET_FASHION: set(), ASSET_VEHICLE: set()}
        for kind in (ASSET_FASHION, ASSET_VEHICLE):
            for rec in (summary.get(kind) or {}).get('items', {}).values():
                for token in (rec.get('name'), self.table._norm_name(rec.get('name')),
                              rec.get('cn'), rec.get('base')):
                    if token:
                        present[kind].add(str(token).strip())
                if kind == ASSET_VEHICLE:
                    # 载具按家族归一：进阶体在档即视为基础形态已在档
                    fam_cn, fam_en = vehicle_family_of(rec.get('cn'), rec.get('name'))
                    for token in (fam_cn, fam_en):
                        if token:
                            present[kind].add(str(token).strip())

        for kind in (ASSET_FASHION, ASSET_VEHICLE):
            for name, cnt in (self.pay_totals.get(kind) or {}).items():
                if not name or cnt <= 0:
                    continue
                if (name in present[kind]
                        or self.table._norm_name(name) in present[kind]):
                    continue
                info = (self.table.by_en.get(name)
                        or self.table.by_en.get(self.table._norm_name(name))
                        or self.table.by_cn.get(name) or {})
                cn = info.get('cn') or ''
                en = info.get('en') or name
                if kind == ASSET_VEHICLE:
                    tag, _base = classify_vehicle(cn, en)
                    if tag != 'paid':
                        continue        # 只标记付费载具
                else:
                    if not (info.get('cat') or '').startswith('时装'):
                        continue        # 只标记时装记录
                    if is_free_fashion(cn, en) or is_rare_fashion(cn, en, self.table):
                        continue        # 免费/稀有时装不参与比对
                price = info.get('price')
                out.append({'kind': kind, 'name': en, 'cn': cn or en, 'count': 0,
                            'level': 0, 'price': price, 'pay': cnt,
                            'explainable': cnt, 'missing': cnt,
                            'missing_value': (price or 0) * cnt,
                            'absent': True, 'is_chip': False, 'tag': '', 'base': ''})

        out.sort(key=lambda r: (-r.get('missing_value', 0), -r.get('missing', 0)))
        return out

    def merged_items(self, kind):
        """把主存档与队友存档的同名物品合并，来源分别记录。

        价格与付费对照取两边“已解析”的值（未定价/无对照为 None）。
        稀有零件额外按 baseLabel 合并同族多阶（见 _merge_parts_families）。
        """
        merged = {}
        for source in (ASSET_SOURCE_MAIN, ASSET_SOURCE_TEAM):
            for key, rec in self.items[kind][source].items():
                target = merged.get(key)
                if target is None:
                    target = dict(rec)
                    target[ASSET_SOURCE_MAIN] = 0
                    target[ASSET_SOURCE_TEAM] = 0
                    merged[key] = target
                else:
                    target['count'] += rec['count']
                    if target.get('price') is None and rec.get('price') is not None:
                        target['price'] = rec['price']
                    if target.get('pay') is None and rec.get('pay') is not None:
                        target['pay'] = rec['pay']
                    if rec['level'] > target.get('level', 0):
                        target['level'] = rec['level']
                    if rec['is_chip']:
                        target['is_chip'] = True
                    # 免费标记：任一侧识别为免费时装即继承（主/队友存档可能只有一方持有）
                    if rec.get('free') or is_free_fashion(rec['cn'], rec['name']):
                        target['free'] = True
                    # 豁免差值：免费时装 / 免费载具（任一来源识别即继承）
                    if rec.get('no_excess'):
                        target['no_excess'] = True
                    # 固定额度（稀有时装 = 0）同样需继承
                    if rec.get('quota_fixed') is not None:
                        target['quota_fixed'] = rec['quota_fixed']
                    # 稀有时装：任一侧识别即继承（额度固定 0 → 持有即报）
                    if (kind == ASSET_FASHION and not target.get('tag')
                            and (rec.get('tag') == 'rare'
                                 or is_rare_fashion(rec['cn'], rec['name'], self.table))):
                        target['tag'] = 'rare'
                        target['is_fashion'] = True
                        target['quota_fixed'] = 0
                    # 载具类别 / 基础名 / 获取时间：主、队友存档可能只有一方持有。
                    # 仅在载具类别下分类 —— 零件/时装不能走载具判定
                    # （否则零件会被标成 unknown 而误入「异常载具」）。
                    if kind == ASSET_VEHICLE and not target.get('tag'):
                        tag, base = classify_vehicle(rec['cn'], rec['name'])
                        if tag or rec.get('tag'):
                            target['tag'] = rec.get('tag') or tag
                            target['base'] = rec.get('base') or base
                    gt = rec.get('get_time')
                    if gt and (not target.get('get_time') or gt < target['get_time']):
                        target['get_time'] = gt
                target[source] = target.get(source, 0) + rec['count']
        return merged


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
        if AES is None:            # 缺少 pycryptodome：交由调用方给出明确提示
            return None
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
        if AES is None:            # 缺少 pycryptodome：交由调用方给出明确提示
            return None
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
            hint = MISSING_CRYPTO_MSG if AES is None else "文件不存在或格式错误"
            return {'title': '金币消费检测', 'status': 'fail',
                    'msg': f"❌ 错误：无法读取或解密价格表文件。\n路径：{bin_path}\n({hint})",
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

            # 结构化摘要：供报告一览表/异常摘要列直接引用，
            # 避免下游再去解析 msg 文本（易受内容中的分隔符干扰）。
            summary_bits = [f"消费 {total_cost} 黄金"]
            if hv_count:
                summary_bits.append(f"高价 {hv_count} 项")
            if hf_count:
                summary_bits.append(f"高频 {hf_count} 项")
            if not has_warning:
                summary_bits.append("无预警")

            return {'title': '金币消费检测', 'status': status,
                    'msg': "\n".join(msg_lines), 'total_cost': total_cost,
                    'summary': "｜".join(summary_bits),
                    'warning_kinds': ('高价' if hv_count else '') + ('/高频' if hf_count else '')}

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
    def check_asset_nodes(file_path, goods_csv=None, max_details=0,
                          abnormal_min_value=None):
        """资产检测：时装 / 载具 / 特殊零件 的**差值检测**（重点非估值）。

        差值 = 持有量 − 应有总量（免费额度 + 付费 + 券购 + 塔领 + 活动修正）；
        差值 > 0 即报异常（疑似异常修改存档）；估值仅作附带参考。
        max_details 控制明细输出条数（0 = 不限），复用界面“明细最大条数”设置。
        返回 dict: {title,status,msg,summary,kinds,abnormal,unmatched,asset_dict}
          • summary 为单行文本摘要（供 CSV/日志）
          • kinds 为分类明细（供渲染层）
        """
        table = ensure_goods_table(goods_csv)
        load_free_quota()       # 载入 free_quota.ini（缺失时按内置默认生成）
        collector = AssetCollector(table, abnormal_min_value=abnormal_min_value)
        try:
            collector.collect(file_path)
        except Exception as e:
            return {'title': '💎 时装/载具/零件检测', 'status': 'warn',
                    'msg': f"⚠️ 资产节点解析异常：{e}", 'summary': f"解析异常：{e}",
                    'kinds': {}, 'abnormal': [], 'unmatched': [],
                    'asset_dict': {}}

        if not table.loaded:
            note = table.error or '价值对照表未加载'
            return {'title': '💎 时装/载具/零件检测', 'status': 'warn',
                    'msg': f"⚠️ {note}\n（已采集节点数量，但无法计价）",
                    'summary': note, 'kinds': {}, 'abnormal': [],
                    'unmatched': [], 'asset_dict': {}}

        summary = collector.summary()
        over = []
        unmatched = []
        for kind in (ASSET_FASHION, ASSET_VEHICLE, ASSET_PARTS):
            data = summary[kind]
            for rec in data['abnormal']:
                # 稀有时装已在「稀有时装」区块单列（含获取时间），避免重复报告
                if rec.get('is_fashion') and rec.get('tag') == 'rare':
                    continue
                over.append(dict(rec, kind=kind))
        unmatched = collector.unmatched

        # 收费载具（含进阶体）/ 稀有载具 / 异常载具：从载具明细中挑出供报告标注。
        # 注：载具列表内的常规载具（tag='catalog'）可正常获取，属正常，不单独列出。
        # ★ 收费载具与购买记录**正常匹配的（购买记录 ≥ 持有量）不输出**，
        #   仅保留未匹配的（持有量 > 购买记录，含无购买记录）供人工复核。
        veh_items = summary[ASSET_VEHICLE]['items']
        if MATCH_PURCHASE_RECORDS:
            paid_vehicles = sorted((r for r in veh_items.values()
                                    if r.get('tag') == 'paid'
                                    and (r.get('pay') or 0) < r['count']),
                                   key=lambda r: (-r['count'], r['cn'] or r['name']))
        else:
            paid_vehicles = sorted((r for r in veh_items.values() if r.get('tag') == 'paid'),
                                   key=lambda r: (-r['count'], r['cn'] or r['name']))
        rare_vehicles = sorted((r for r in veh_items.values() if r.get('tag') == 'rare'),
                               key=lambda r: (r.get('get_time') or '~', r['cn'] or r['name']))
        unknown_vehicles = sorted((r for r in veh_items.values() if r.get('tag') == 'unknown'),
                                  key=lambda r: (-r['count'], r['cn'] or r['name']))
        # 稀有时装：免费时装与付费时装之外（碎片合成/活动产出）→ 标注获取时间
        fash_items = summary[ASSET_FASHION]['items']
        rare_fashions = sorted((r for r in fash_items.values() if r.get('tag') == 'rare'),
                               key=lambda r: (r.get('get_time') or '~', r['cn'] or r['name']))

        # 购买了但存档内无（付费载具 / 付费时装反向缺口）
        missing_purchases = (collector.find_missing_purchases(summary)
                             if MATCH_PURCHASE_RECORDS else [])

        # 状态判定：出现「差值 > 0」（over / 未匹配收费载具）或异常载具
        # （不在载具列表内）时判 fail；仅有「购买了但存档内无」判 warn。
        if over or paid_vehicles or unknown_vehicles:
            status = 'fail'
        elif missing_purchases:
            status = 'warn'
        else:
            status = 'pass'

        # 展示口径：载具只计「收费 / 稀有」；且收费载具里**与购买记录正常匹配
        # 的不计入**（它们不输出，若仍计入会导致头部数字与下方明细对不上）。
        shown_vehicles = [r for r in summary[ASSET_VEHICLE]['items'].values()
                          if r.get('tag') == 'rare'
                          or (r.get('tag') == 'paid'
                              and (not MATCH_PURCHASE_RECORDS
                                   or (r.get('pay') or 0) < r['count']))]
        veh_count = sum(r['count'] for r in shown_vehicles)
        veh_value = sum((r.get('price') or 0) * r['count'] for r in shown_vehicles)

        total_value = (summary[ASSET_FASHION]['value']
                       + summary[ASSET_PARTS]['value'] + veh_value)
        total_count = (summary[ASSET_FASHION]['total']
                       + summary[ASSET_PARTS]['total'] + veh_count)
        parts_kinds = len(summary[ASSET_PARTS]['items'])
        msg_head = (f"△ 差值异常 {len(over)} 项 | 参考估值 {total_value} 黄金 | 共 {total_count} 件"
                    f"（时装 {summary[ASSET_FASHION]['total']}、"
                    f"载具 {veh_count}、"
                    f"特殊零件 {summary[ASSET_PARTS]['total']}/{parts_kinds}种）")
        # 结构化摘要（供报告一览表 / CSV 摘要列直接使用，无需再解析 msg 文本）
        brief_bits = [f"{ASSET_KIND_CN[k]} {summary[k]['total']}件"
                      for k in (ASSET_FASHION, ASSET_PARTS)
                      if summary[k]['total']]
        if veh_count:
            brief_bits.append(f"载具 {veh_count}件")
        brief_bits.append(f"估值 {total_value} 金")
        if over:
            brief_bits.append(f"差值 {len(over)} 项")
        if paid_vehicles:
            brief_bits.append(f"收费载具未匹配 {len(paid_vehicles)} 种")
        if missing_purchases:
            brief_bits.append(f"购买了但存档内无 {len(missing_purchases)} 项")
        if rare_vehicles:
            brief_bits.append(f"稀有载具 {len(rare_vehicles)} 种")
        if unknown_vehicles:
            brief_bits.append(f"异常载具 {len(unknown_vehicles)} 种")
        if rare_fashions:
            brief_bits.append(f"稀有时装 {len(rare_fashions)} 种")
        if unmatched:
            brief_bits.append(f"未定价 {len(unmatched)} 种")

        res = {'title': '💎 时装/载具/零件检测', 'status': status, 'msg': msg_head,
               'kinds': summary,          # 分类明细（供渲染层使用）
               'summary': "｜".join(brief_bits),   # 单行文本摘要
               'abnormal': over,
               'missing_purchases': [dict(r) for r in missing_purchases],  # 购买了但存档内无
               'paid_vehicles': [dict(r) for r in paid_vehicles],
               'rare_vehicles': [dict(r) for r in rare_vehicles],
               'unknown_vehicles': [dict(r) for r in unknown_vehicles],
               'rare_fashions': [dict(r) for r in rare_fashions],
               'unmatched': unmatched, 'errors': collector.warnings}
        res['msg'] = msg_head + "\n" + ReportRenderer.render_asset_result(res, max_details)

        def _text(kind):
            """分类文本：载具只统计「稀有 + 未匹配的收费」（与明细展示口径一致）。"""
            if kind == ASSET_VEHICLE:
                shown = [r for r in summary[kind]['items'].values()
                         if r.get('tag') == 'rare'
                         or (r.get('tag') == 'paid'
                             and (not MATCH_PURCHASE_RECORDS
                                  or (r.get('pay') or 0) < r['count']))]
                cnt = sum(r['count'] for r in shown)
                val = sum((r.get('price') or 0) * r['count'] for r in shown)
                return f"{cnt}件/{val}金"
            return f"{summary[kind]['total']}件/{summary[kind]['value']}金"

        res['asset_dict'] = {
            'fashion_text': _text(ASSET_FASHION),
            'vehicle_text': _text(ASSET_VEHICLE),
            'parts_text': _text(ASSET_PARTS),
            'value': total_value,
            'paid_vehicles': [f"{r['cn'] or r['name']}×{r['count']}" for r in paid_vehicles],
            'rare_vehicles': [f"{r['cn'] or r['name']}×{r['count']}"
                              + (f"（{r['get_time']}）" if r.get('get_time') else "")
                              for r in rare_vehicles],
            'unknown_vehicles': [f"{r['cn'] or r['name']}×{r['count']}"
                                 for r in unknown_vehicles],
            'rare_fashions': [f"{r['cn'] or r['name']}×{r['count']}"
                              + (f"（{r['get_time']}）" if r.get('get_time') else "")
                              for r in rare_fashions],
            'reason': "；".join(
                [f"[{ASSET_KIND_CN[r['kind']]}] {r['cn'] or r['name']} "
                 + (f"折算{r.get('held_equiv', r['count'])}"
                    if r['kind'] == ASSET_PARTS else f"持有{r['count']}")
                 + f" > 应有{r.get('explainable') or 0}"
                 f"（免费{r.get('quota') or 0}+付费{r.get('pay') or 0}"
                 + (f"+券购{r['ticket_buy']}" if r.get('ticket_buy') else "")
                 + (f"+塔领{r['tower_claimed']}" if r.get('tower_claimed') else "")
                 + (f"+活动{r['adjust']}" if r.get('adjust') else "")
                 + f"）差值{r.get('excess', 0)}份"
                 + (f"，差值估值{r.get('excess_value', 0)}金"
                    if r.get('excess_value') else "，未定价")
                 for r in over[:6]]
                + ([f"收费载具未匹配 {len(paid_vehicles)} 种（{('、'.join(r['cn'] or r['name'] for r in paid_vehicles[:4]))}）"]
                   if paid_vehicles else [])
                + ([f"购买了但存档内无 {len(missing_purchases)} 项（{('、'.join(r['cn'] or r['name'] for r in missing_purchases[:4]))}）"]
                   if missing_purchases else [])
                + ([f"异常载具 {len(unknown_vehicles)} 种（{('、'.join(r['cn'] or r['name'] for r in unknown_vehicles[:4]))}）"]
                   if unknown_vehicles else [])
                + ([f"稀有时装 {len(rare_fashions)} 种（{('、'.join(r['cn'] or r['name'] for r in rare_fashions[:4]))}）"]
                   if rare_fashions else [])
                + ([f"未定价 {len(unmatched)} 种"] if unmatched else [])
            ) or '正常',
        }
        return res

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
        self.root.title("数据检测工具 γ合并版 v3.1 | BY. 观星者")
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
            # 旧版「资产差值阈值」已被 free_quota.ini 的免费额度与差值口径取代，去掉残留键
            self.config['Settings'].pop('asset_min_delta', None)
        except Exception as e:
            print(f"警告：读取配置文件异常: {e}")
            if 'Settings' not in self.config:
                self.config.add_section('Settings')

    def _create_default_config(self):
        self.config['Settings'] = {
            'bin_path': app_paths.to_config_path(DEFAULT_BIN_PATH),
            'work_dir': app_paths.to_config_path(TEST_DIR),
            'last_file_path': '',
            'auto_restore': 'True',
            'auto_open_dir': 'False',
            'auto_uid_from_filename': 'True',
            'max_export_details': '10',
            'min_money_details': '500',
            'min_number_details': '10',
            'export_full_details': 'False',
            'batch_thread_count': '5',
            'auto_open_batch_report': 'False',
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

    def _get_bin_path(self):
        """价格表路径（配置值 → 绝对路径，相对路径按程序目录解析）。"""
        return app_paths.resolve_input(self._get_str('bin_path', DEFAULT_BIN_PATH),
                                       DEFAULT_BIN_PATH)

    def _save_settings(self):
        # 先解析为绝对路径，再压回“程序目录内→相对写法 / 目录外→绝对路径”：
        # 避免把 .\test 这类相对值原样存下后又在别的启动目录下漂移。
        # 输入框为空时回退到默认值，避免把 None 写进配置。
        bin_text = app_paths.resolve(self.entry_bin_path.get().strip()) \
            or app_paths.resolve(DEFAULT_BIN_PATH)
        work_text = app_paths.resolve(self.entry_work_dir.get().strip()) \
            or app_paths.resolve(TEST_DIR)
        self._set_str('bin_path', app_paths.to_config_path(bin_text))
        self._set_str('work_dir', app_paths.to_config_path(work_text))
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

        current_bin_path = self._get_bin_path()
        if not current_bin_path or not os.path.exists(current_bin_path):
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

        # 历史路径按程序目录解析后恢复（相对写法也不会随启动目录漂移）
        saved_path = app_paths.resolve(self._get_str('last_file_path', ''))
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
        # 显示解析后的绝对路径，避免相对写法随启动目录漂移（保存时自动压回相对写法）
        self.entry_bin_path.insert(0, self._get_bin_path())
        self.entry_bin_path.bind("<KeyRelease>", self._mark_settings_modified)

        def browse_bin():
            fp = filedialog.askopenfilename(title="选择 bin 文件",
                                            initialdir=app_paths.resolve_input(INPUT_DIR),
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
        # 同上：显示绝对路径，保存时自动压回可迁移的相对写法（位于程序目录内时）
        self.entry_work_dir.insert(0, app_paths.resolve(self._get_str('work_dir', TEST_DIR),
                                                        TEST_DIR))
        self.entry_work_dir.bind("<KeyRelease>", self._mark_settings_modified)

        def browse_work_dir():
            curr_dir = app_paths.resolve(self.entry_work_dir.get().strip())
            if not curr_dir or not os.path.isdir(curr_dir):
                curr_dir = app_paths.resolve(TEST_DIR)
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

        # 第三行：免费额度 / 活动修正配置（差值判定的应有总量来自该文件）
        y += 35
        tk.Label(card, text="免费额度配置:", bg="#FFFFFF", font=("Microsoft YaHei", 11)).place(x=50, y=y)
        tk.Button(card, text="📝 打开 free_quota.ini", command=self._open_free_quota_ini,
                  bg="#005159", fg="white", font=("Microsoft YaHei", 10), bd=0
                  ).place(x=200, y=y + 2, width=200, height=30)
        tk.Label(card, text="（★ 差值判定：持有量 − 应有总量，超过即异常；与估值无关）",
                 bg="#FFFFFF", font=("Microsoft YaHei", 10), fg="#666666").place(x=415, y=y + 10)

        # 第四行：提示
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
• 时装 / 载具 / 特殊零件 资产检测（对照 good_items.csv，含与付费次数比对）
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
        target = app_paths.resolve(file_path) if file_path else None
        if not target or not os.path.exists(target):
            return
        try:
            res = DetectionEngine.check_uid_md5_advanced(target)
            if res and res.get('file_uid'):
                self.entry_uid.delete(0, tk.END)
                self.entry_uid.insert(0, res.get('file_uid'))
                self.entry_uid.config(fg="black")
        except Exception:
            pass

    def _browse_file(self):
        last_path = app_paths.resolve(self._get_str('last_file_path', ''))
        last_dir = os.path.dirname(last_path) if last_path else ''
        if last_dir and os.path.exists(last_dir):
            init_dir = last_dir
        else:
            init_dir = app_paths.resolve(self._get_str('work_dir', TEST_DIR), TEST_DIR)
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
        file_path = app_paths.resolve(self.entry_file_path.get().strip())
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning("提示", "请先选择有效的文件路径")
            return
        self.entry_file_path.delete(0, tk.END)
        self.entry_file_path.insert(0, file_path)
        self.entry_file_path.config(fg="black")
        self._try_auto_fill_uid(file_path)
        messagebox.showinfo("完成", "已尝试从文件名自动识别 UID")

    def _open_dir(self, dir_path):
        target = app_paths.resolve(dir_path) or dir_path
        if not os.path.exists(target):
            os.makedirs(target)
        try:
            os.startfile(target)
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
        raw_input = self.entry_file_path.get().strip()
        # 相对路径按程序目录解析（可直接输入 test\xxx.xml 这类写法）
        file_path = app_paths.resolve(raw_input)
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("错误", "文件路径无效或不存在")
            return
        self.entry_file_path.delete(0, tk.END)
        self.entry_file_path.insert(0, file_path)
        self.entry_file_path.config(fg="black")
        self._set_str('last_file_path', file_path)
        self._save_config()
        threading.Thread(target=self._do_detect_work, daemon=True).start()

    @staticmethod
    def _detect_common_checks(file_path, bin_path, max_details, min_money, min_num,
                              export_full, total_cost_for_union=0, fname_for_ban=None):
        """单文件执行全部检测，返回 (results, 附加信息 dict)
        results: list of {title,status,msg,...}；附带 uid_res 供外部取字段

        纯计算，不依赖 GUI 状态，可被 detect_file() 等模块级接口直接调用。
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

        # 6. 资产检测（时装 / 载具 / 特殊零件）★ 重点：差值（持有量 vs 应有总量）
        #    应有总量与活动修正参数均来自 free_quota.ini
        asset_res = DetectionEngine.check_asset_nodes(file_path, max_details=max_details)
        results.append(asset_res)
        extra['asset_res'] = asset_res
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
        file_path = app_paths.resolve(self.entry_file_path.get().strip()) or ""
        self._start_log_session('单文件检测', 检测文件=file_path)
        bin_path = self._get_bin_path()
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
    def _short_of(title, msg, summary=None):
        """取单条检测项的简短摘要（供 CSV 摘要列/日志用）。

        优先使用检测项自带的结构化 summary；否则从 msg 首个有效行提取。
        对于含多行内容的检测项（如作弊原因可能跨行），只取真正有意义的一行。
        """
        text = str(summary).strip() if summary else ""
        if not text:
            for line in (msg or '').split('\n'):
                ls = line.strip()
                # 跳过空行/装饰行/明细行/续行
                if not ls or ls.startswith('-') or ls.startswith('=') or ls.startswith('…'):
                    continue
                text = ls
                break
        text = " ".join(text.split())        # 折叠换行与重复空白
        if not text:
            text = f"[{title}] 检测异常（详见详情文件）"
        elif len(text) > 120:
            text = text[:120] + "..."
        return text

    @classmethod
    def _collect_file_issues(cls, res):
        """收集单个文件的详情日志与异常摘要。

        返回 (detail_lines, fail_msgs, warn_msgs, issues)
        issues: [{title,status,summary}] 结构化异常项列表
        """
        detail_lines, fail_msgs, warn_msgs = [], [], []
        issues = []
        for item in res.get('results', []):
            if not isinstance(item, dict):
                continue
            title = item.get('title', '检测项')
            status = item.get('status', 'pass')
            msg = item.get('msg', '')
            if status not in ('fail', 'warn'):
                continue

            short_msg = cls._short_of(title, msg, item.get('summary'))
            detail_lines.append(f"--- [{title}] ---")
            detail_lines.append(msg)
            detail_lines.append("")
            issues.append({'title': title, 'status': status, 'summary': short_msg})
            if status == 'fail':
                fail_msgs.append(f"{short_msg}")
            elif status == 'warn':
                warn_msgs.append(f"{short_msg}")
        return detail_lines, fail_msgs, warn_msgs, issues

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

    @classmethod
    def _build_uid_groups(cls, file_result_map, uid_max_vip, uid_assets, max_details):
        """把逐文件检测结果按 UID 聚合成结构化报表数据。

        返回 uid_rows: [{
            uid, indexes, index_display, name, vip_level, status, reason,
            items: [{fname,name,theory,actual,cost,uid_cost,uid_file_count,
                     status,reason,index_mismatch,index_tag,ban_tag,
                     detail_lines,asset_lines,issues}],
            inactive_bans, asset, has_asset_issue,
        }]

        设计要点：所有下游出口（CSV / 详情文件 / 日志）都只消费这份结构，
        不再各自解析文本；同一 UID 的异常项也在这一步合并去重。
        纯计算，不依赖 GUI 状态，可被 detect_folder() 等模块级接口直接调用。
        """
        uid_group = {}
        for file_path, res in file_result_map.items():
            fname = os.path.basename(file_path)
            if res['overall'] not in ('fail', 'warn'):
                continue
            file_name = res.get('file_name', '')
            file_uid_index = res.get('file_uid_index', '')
            inner_uid_index = res.get('inner_uid_index', '')
            group_uid = res.get('uid') or res.get('file_uid') or res.get('inner_uid') or 'unknown'

            detail_lines, fail_msgs, warn_msgs, issues = cls._collect_file_issues(res)
            if fail_msgs:
                file_reason = "；".join(fail_msgs)
                file_status = 'fail'
            elif warn_msgs:
                file_reason = "；".join(warn_msgs)
                file_status = 'warn'
            else:
                continue

            index_mismatch, index_tag = cls._index_tag(file_uid_index, inner_uid_index)

            # 资产明细：只要采集到资产就输出（含 pass），供详情文件展示资产清单
            asset_res = res.get('asset_res') or {}
            asset_lines = []
            if asset_res.get('kinds'):
                asset_lines = ReportRenderer.render_asset_result(
                    asset_res, max_details
                ).split('\n')

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
                'asset_lines': asset_lines,
                'issues': issues,
            })

        uid_rows = []
        for uid, items in uid_group.items():
            indexed_items = sorted(items, key=lambda x: cls._index_sort_key(x['theory']))
            display_parts = [cls._uid_index_name(it['theory'], it.get('name'))
                             for it in indexed_items if it['theory'] != '无']
            display_indexes = ", ".join(p for p in display_parts if p != '无') or '无'
            multi = len(items) > 1

            reason_parts = []
            mismatch_parts = [f"{it['theory']}≠{it['actual']}"
                              for it in items if it['index_mismatch']]
            if mismatch_parts:
                reason_parts.append("🔢 index异常：" + "；".join(mismatch_parts))
            elif multi:
                reason_parts.append("🔢 各存档index均正常")

            for it in indexed_items:
                prefix = f"[{it['theory']}] " if multi else ""
                reason_parts.append(f"{prefix}{it['reason']}")

            banned_slots = sorted({it['ban_tag'] for it in items if it['ban_tag']})
            inactive_bans = SLOT_BAN_CACHE.get_inactive_bans(uid)
            if inactive_bans:
                reason_parts.append("🚨 未参与检测的封禁槽位：" + "；".join(
                    s for s in inactive_bans if s not in banned_slots))

            uid_reason = "；".join(reason_parts).replace('\n', ' ').replace('\r', ' ').strip()
            if len(uid_reason) > 400:
                uid_reason = uid_reason[:400] + "..."

            uid_rows.append({
                'uid': uid,
                'indexes': sorted({it['theory'] for it in items if it['theory'] != '无'}),
                'index_display': display_indexes,
                'name': indexed_items[0]['name'] or '无',
                'vip_level': uid_max_vip.get(uid),
                'status': 'fail' if any(it['status'] == 'fail' for it in items) else 'warn',
                'reason': uid_reason,
                'multi': multi,
                'items': indexed_items,
                'inactive_bans': inactive_bans,
                'asset': uid_assets.get(uid),
                'has_asset_issue': any(it.get('asset_lines') and
                                       any('🚨' in ln or '🔻' in ln or '💳' in ln
                                           for ln in it['asset_lines'])
                                       for it in items),
            })
        return uid_rows

    @staticmethod
    def _write_uid_detail_file(uid, items, banned_slots=None, vip_level=None,
                               asset=None, out_dir=None):
        """将同一 UID 下所有异常存档汇总为一份详情文件（渲染交 ReportRenderer）。

        out_dir 默认 outputdata/异常详情，也可由外部项目指定自己的输出目录。
        """
        detail_dir = out_dir or os.path.join(OUTPUT_DIR, "异常详情")
        os.makedirs(detail_dir, exist_ok=True)
        for it in items:
            it.setdefault('ban_tag', '')
        text = ReportRenderer.render_uid_detail(uid, items, vip_level=vip_level,
                                                banned_slots=banned_slots, asset=asset)
        safe_uid = re.sub(r'[<>:"/\\|?*]', '_', str(uid))
        detail_path = os.path.join(detail_dir, f"{safe_uid}_异常详情.txt")
        with open(detail_path, "w", encoding="utf-8") as f:
            f.write(text)
        return detail_path

    # ---------- 批量检测 ----------
    def _batch_detect_folder(self):
        folder_path = filedialog.askdirectory(
            title="选择批量检测文件夹",
            initialdir=app_paths.resolve(self._get_str('work_dir', TEST_DIR), TEST_DIR))
        if not folder_path:
            return
        self._set_str('work_dir', app_paths.to_config_path(folder_path))
        threading.Thread(target=self._do_batch_detect, args=(folder_path,), daemon=True).start()

    def _do_batch_detect(self, folder_path):
        self._start_log_session('批量检测', 目标目录=folder_path)
        self.log(f"📂 开始批量检测：{folder_path}", "INFO")
        self.log("需要半分钟左右时间，请耐心等待", "INFO")

        # 加载封禁缓存（递归扫描所选目录下所有 _details.csv）
        SLOT_BAN_CACHE.ban_cache.clear()
        SLOT_BAN_CACHE.load_all_csv_from_root(folder_path)
        self.log("✅ 封禁缓存加载完成", "INFO")

        bin_path = self._get_bin_path()
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

        # 资产（时装/载具/特殊零件）按 UID 合并：同一账号多存档内同名物品计数相加
        uid_assets = self._finalize_asset_results(file_result_map)
        self.log(f"💎 资产按UID合并统计完成：{len(uid_assets)} 个账号", "INFO")

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
        # 统一聚合：逐文件结果 → 按 UID 结构化报表数据
        # （所有下游出口都只消费这份结构，不再各自解析文本）
        uid_rows = self._build_uid_groups(file_result_map, uid_max_vip, uid_assets,
                                          max_details)

        # 资产差值单独汇总一行，便于在运行日志里快速看到「谁持有量对不上」
        asset_issue_uids = [r['uid'] for r in uid_rows if r.get('has_asset_issue')]
        if asset_issue_uids:
            self.log(f"💎 资产差值异常账号 {len(asset_issue_uids)} 个："
                     + "、".join(asset_issue_uids[:10])
                     + ("…" if len(asset_issue_uids) > 10 else ""), "FAIL")

        for row in uid_rows:
            self._write_uid_detail_file(row['uid'], row['items'], row['inactive_bans'],
                                        vip_level=row.get('vip_level'),
                                        asset=row.get('asset'))

        self.log(f"📝 已按UID汇总生成 {len(uid_rows)} 份异常详情文件", "INFO")
        self._generate_batch_report(uid_rows, success, warn, fail, total)
        self._finish_log_session(
            f"批量检测结束\n✅ 通过:{success} ⚠️ 警告:{warn} ❌ 异常:{fail} | 总计:{total}")

    @staticmethod
    def _finalize_asset_results(file_result_map):
        """按 UID 汇总各存档的资产统计（时装/载具/特殊零件），用于批量 CSV。

        口径说明：`pay.obj` 是**单个存档内**的累计购买记录，因此“持有 vs 付费”
        的判定始终在单存档粒度完成（见 AssetCollector.collect）。此处按 UID 汇总
        只为报告展示：
          • 数量/价值取该账号各存档的**最大值**（同一账号多个存档是同一份资产的不同
            时间快照，相加会重复计数）；
          • 差值项按 (类别, 物品) 去重，保留差值（当量）最大的一条。

        返回 {uid: {fashion_text, vehicle_text, parts_text, value, reason,
                    abnormal, paid_vehicles, rare_vehicles, rare_fashions}}。
        """
        merged = {}
        for res in file_result_map.values():
            uid = res.get('uid')
            asset = res.get('asset_res')
            if not uid or not asset:
                continue
            summary = asset.get('kinds') or {}
            entry = merged.setdefault(uid, {
                'value': 0,
                'kinds': {k: {'count': 0, 'value': 0} for k in
                          (ASSET_FASHION, ASSET_VEHICLE, ASSET_PARTS)},
                'unmatched': set(),
                'over': {},      # (kind, key) -> rec（差值 > 0，需人工复核）
                'missing': {},   # (kind, key) -> rec（购买了但存档内无）
                'paid': {},      # 名称 -> rec（收费载具）
                'rare': {},      # 名称 -> rec（稀有载具）
                'rare_fash': {},  # 名称 -> rec（稀有时装）
            })
            snapshot_value = 0
            snapshot_count = 0
            for kind in (ASSET_FASHION, ASSET_VEHICLE, ASSET_PARTS):
                data = summary.get(kind) or {}
                slot = entry['kinds'][kind]
                if kind == ASSET_VEHICLE:
                    # 与报告口径一致：载具只计「稀有 + 未匹配的收费」
                    shown = [r for r in (data.get('items') or {}).values()
                             if r.get('tag') == 'rare'
                             or (r.get('tag') == 'paid'
                                 and (not MATCH_PURCHASE_RECORDS
                                      or (r.get('pay') or 0) < r['count']))]
                    cnt = sum(r['count'] for r in shown)
                    val = sum((r.get('price') or 0) * r['count'] for r in shown)
                else:
                    cnt = data.get('total', 0)
                    val = data.get('value', 0)
                slot['value'] = max(slot['value'], val)
                slot['count'] = max(slot['count'], cnt)
                snapshot_value += val
                snapshot_count += cnt
            entry['value'] = max(entry['value'], snapshot_value)
            entry['unmatched'].update(asset.get('unmatched') or [])
            for rec in (asset.get('abnormal') or []):
                key = (rec.get('kind'), rec.get('name') or rec.get('cn'))
                prev = entry['over'].get(key)
                # 同一物品在不同存档中取差值最大的快照（价值为 0 时比数量）
                if prev is None or ((rec.get('excess_value', 0), rec.get('excess', 0))
                                    > (prev.get('excess_value', 0), prev.get('excess', 0))):
                    entry['over'][key] = rec
            # 购买缺口：同一物品取缺口最大的一次快照（购买了但存档内无）
            for rec in (asset.get('missing_purchases') or []):
                key = (rec.get('kind'), rec.get('name') or rec.get('cn'))
                prev = entry['missing'].get(key)
                if prev is None or ((rec.get('missing', 0), rec.get('missing_value', 0))
                                    > (prev.get('missing', 0), prev.get('missing_value', 0))):
                    entry['missing'][key] = rec
            # 收费/稀有载具、稀有时装：取持有量最多的快照，并保留最早的获取时间
            for field, bucket in (('paid_vehicles', 'paid'), ('rare_vehicles', 'rare'),
                                  ('rare_fashions', 'rare_fash')):
                for rec in (asset.get(field) or []):
                    name = rec.get('cn') or rec.get('name')
                    if not name:
                        continue
                    prev = entry[bucket].get(name)
                    if prev is None:
                        entry[bucket][name] = dict(rec)
                        continue
                    merged_rec = prev if prev.get('count', 0) >= rec.get('count', 0) else dict(rec)
                    gt = rec.get('get_time')
                    if gt and (not merged_rec.get('get_time') or gt < merged_rec['get_time']):
                        merged_rec['get_time'] = gt
                    entry[bucket][name] = merged_rec

        out = {}
        for uid, entry in merged.items():
            kinds = entry['kinds']

            def _text(kind):
                return f"{kinds[kind]['count']}件/{kinds[kind]['value']}金"

            over_list = sorted(entry['over'].values(),
                               key=lambda r: (-r.get('excess_value', 0),
                                              -r.get('excess', 0)))
            # 差值摘要：零件与单件时装展示口径不同（零件按全族当量）
            def _over_txt(r):
                head = f"[{ASSET_KIND_CN[r['kind']]}] {r['cn'] or r['name']} "
                if r['kind'] == ASSET_PARTS:
                    head += (f"折算当量{r.get('held_equiv', r['count'])}"
                             f"−应有{r.get('explainable') or 0}")
                    detail = " + ".join(b for b in (
                        f"付费{r.get('pay') or 0}" if r.get('pay') else "",
                        f"券购{r['ticket_buy']}" if r.get('ticket_buy') else "",
                        f"塔领{r['tower_claimed']}" if r.get('tower_claimed') else "",
                        f"活动{r['adjust']}" if r.get('adjust') else "",
                    ) if b)
                    if detail:
                        head += f"（{detail}）"
                else:
                    head += (f"持有{r['count']}−免费{r.get('quota') or 0}"
                             f"−付费{r.get('pay') or 0}")
                return (head + f"=差值{r.get('excess', 0)}份"
                        + (f"（{r.get('excess_value')}金）"
                           if r.get('excess_value') else "（未定价）"))
            over_txt = "；".join(_over_txt(r) for r in over_list[:6])
            paid_list = sorted(entry['paid'].values(),
                               key=lambda r: (-r.get('count', 0), r.get('cn') or ''))
            missing_list = sorted(entry['missing'].values(),
                                  key=lambda r: (-r.get('missing', 0),
                                                 -r.get('missing_value', 0)))
            rare_list = sorted(entry['rare'].values(),
                               key=lambda r: (r.get('get_time') or '~', r.get('cn') or ''))
            rare_fash_list = sorted(entry['rare_fash'].values(),
                                    key=lambda r: (r.get('get_time') or '~', r.get('cn') or ''))
            reason_bits = []
            if over_txt:
                reason_bits.append(over_txt)
            if paid_list:
                reason_bits.append(
                    "收费载具 " + "、".join(f"{r.get('cn') or r.get('name')}×{r.get('count', 0)}"
                                            for r in paid_list[:4]))
            if missing_list:
                reason_bits.append(
                    "购买了但存档内无 " + "、".join(
                        f"{r.get('cn') or r.get('name')}"
                        + ("（未见）" if r.get('absent')
                           else f"缺{r.get('missing', 0)}份")
                        for r in missing_list[:4]))
            if rare_list:
                reason_bits.append(
                    "稀有载具 " + "、".join(
                        f"{r.get('cn') or r.get('name')}×{r.get('count', 0)}"
                        + (f"({r['get_time']})" if r.get('get_time') else "")
                        for r in rare_list[:4]))
            if rare_fash_list:
                reason_bits.append(
                    "稀有时装 " + "、".join(
                        f"{r.get('cn') or r.get('name')}×{r.get('count', 0)}"
                        + (f"({r['get_time']})" if r.get('get_time') else "")
                        for r in rare_fash_list[:4]))
            if entry['unmatched']:
                reason_bits.append(f"未定价 {len(entry['unmatched'])} 种")
            out[uid] = {
                'fashion_text': _text(ASSET_FASHION),
                'vehicle_text': _text(ASSET_VEHICLE),
                'parts_text': _text(ASSET_PARTS),
                'value': entry['value'],
                'reason': "；".join(reason_bits) or '正常',
                'abnormal': over_list,
                'missing_purchases': missing_list,
                'paid_vehicles': paid_list,
                'rare_vehicles': rare_list,
                'rare_fashions': rare_fash_list,
            }
        return out

    @staticmethod
    def _finalize_batch_results(file_result_map, uid_max_vip=None):
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

    @staticmethod
    def _detect_single_file_batch(file_path, bin_path, max_details, min_money, min_num,
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
        asset_res = DetectionEngine.check_asset_nodes(file_path, max_details=max_details)

        results = [ban_result] + [uid_res_checked] + cheat_res['details'] + [vip_res, pay_res,
                                                                            asset_res]
        overall = AppDetector._overall_of(results)

        return {
            'file': file_path,
            'cost_key': cost_key,
            'uid': server_uid or inner_uid or '',
            'overall': overall,
            'results': results,
            'asset_res': asset_res,
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
        self.entry_bin_path.insert(0, self._get_bin_path())
        self.entry_work_dir.delete(0, tk.END)
        self.entry_work_dir.insert(0, app_paths.resolve(TEST_DIR))
        messagebox.showinfo("完成", "已恢复默认设置")

    def _open_free_quota_ini(self):
        """打开配置 free_quota.ini（缺失时按内置默认值生成）。

        差值判定口径即本文件：差值 = 持有量 −（应有总量）；
        时装：免费额度 + 付费；零件：付费 + 券购 + 塔领 + 活动修正 [parts_adjust]。
        """
        path = ensure_free_quota_ini()
        try:
            os.startfile(path)
            self.log(f"📝 已打开免费额度配置：{path}", "INFO")
        except Exception:
            messagebox.showwarning("提示", f"无法自动打开，请手动编辑：\n{path}")


# ========================================================
# 🔌 模块级 API（无界面检测入口）
# ========================================================
# 供其他项目（如 NoneBot 机器人）以模块方式调用，无需 GUI：
#     import main as detect
#     result = detect.detect_file(r"test\2296141867\...xml")
#     report = detect.detect_folder(r"test")          # 批量，按 UID 汇总
# 所有函数不触碰界面；日志通过可选 log 回调输出（签名 log(msg, level='INFO')）。

def _read_settings(config_file=None, overrides=None):
    """读取 config.ini 的 Settings（缺失/损坏时回退到内置默认值）。

    overrides 中的非 None 项优先（便于调用方覆盖 bin_path / work_dir 等）。
    """
    config = configparser.ConfigParser()
    path = config_file or CONFIG_FILE
    if os.path.exists(path):
        try:
            config.read(path, encoding='utf-8-sig')
        except Exception:
            pass
    if 'Settings' not in config:
        config.add_section('Settings')

    def _get(key, default):
        try:
            return config.get('Settings', key)
        except Exception:
            return default

    def _int(key, default):
        try:
            return int(float(_get(key, default)))
        except (TypeError, ValueError):
            return default

    def _bool(key, default):
        try:
            return config.getboolean('Settings', key)
        except Exception:
            return default

    settings = {
        'bin_path': app_paths.resolve_input(_get('bin_path', DEFAULT_BIN_PATH),
                                            DEFAULT_BIN_PATH),
        'work_dir': app_paths.resolve(_get('work_dir', TEST_DIR), TEST_DIR),
        'max_export_details': _int('max_export_details', 10),
        'min_money_details': _int('min_money_details', 500),
        'min_number_details': _int('min_number_details', 10),
        'export_full_details': _bool('export_full_details', False),
        'batch_thread_count': _int('batch_thread_count', 5),
    }
    for key, value in (overrides or {}).items():
        if value is not None:
            settings[key] = value
    return settings


def detect_file(file_path, config_file=None, log=None, **overrides):
    """无界面单文件检测。

    返回 dict：{file, uid, overall, results, theory_uid_index,
                actual_uid_index, index_mismatch, ban_reason, total_cost,
                asset_res, report_text}
    """
    target = app_paths.resolve(file_path)
    if not target or not os.path.exists(target):
        raise FileNotFoundError(f"存档文件不存在：{file_path}")

    settings = _read_settings(config_file, overrides)
    fname = os.path.basename(target)

    # 单文件检测前，若所在目录有 _details.csv，则加载封禁信息
    folder = os.path.dirname(target)
    if folder and not SLOT_BAN_CACHE.ban_cache:
        SLOT_BAN_CACHE.load_all_csv_from_root(folder)

    results, extra = AppDetector._detect_common_checks(
        target, settings['bin_path'], settings['max_export_details'],
        settings['min_money_details'], settings['min_number_details'],
        settings['export_full_details'], fname_for_ban=fname)

    if log:
        for res in results:
            if isinstance(res, dict):
                log(f"{res.get('title', '检测项')}：{res.get('msg')}",
                    (res.get('status') or 'pass').upper())

    uid_res = extra.get('uid_res') or {}
    meta = {
        'file_path': target,
        'uid': uid_res.get('file_uid') or uid_res.get('inner_uid') or '',
        'theory_uid_index': extra.get('theory_uid_index') or '无',
        'actual_uid_index': extra.get('actual_uid_index') or '无',
        'index_mismatch': bool(extra.get('index_mismatch')),
    }
    return {
        'file': target,
        'uid': meta['uid'],
        'overall': AppDetector._overall_of(results),
        'results': results,
        'theory_uid_index': meta['theory_uid_index'],
        'actual_uid_index': meta['actual_uid_index'],
        'index_mismatch': meta['index_mismatch'],
        'ban_reason': extra.get('ban_reason'),
        'total_cost': extra.get('total_cost', 0),
        'asset_res': extra.get('asset_res'),
        'report_text': ReportRenderer.render_single_report(meta, results),
    }


def detect_folder(folder_path, config_file=None, log=None, out_dir=None,
                  thread_count=None, write_detail_files=True, **overrides):
    """无界面批量检测（按 UID 汇总）。

    folder_path        : 存档目录（递归扫描 .xml）
    out_dir            : 报告输出目录；默认 outputdata（异常详情写在 <out_dir>/异常详情）
    thread_count       : 覆盖配置里的批量线程数
    write_detail_files : 是否写 <uid>_异常详情.txt
    log                : 可选回调 log(msg, level)

    返回 dict：{folder, total, success, warn, fail, uid_rows, csv_path,
                detail_paths, uid_total_cost, uid_assets}
    """
    folder = app_paths.resolve(folder_path)
    if not folder or not os.path.isdir(folder):
        raise NotADirectoryError(f"存档目录不存在：{folder_path}")

    settings = _read_settings(config_file, overrides)
    workers = thread_count or settings['batch_thread_count']
    out_root = out_dir or OUTPUT_DIR

    # 加载封禁缓存（递归扫描所选目录下所有 _details.csv）
    SLOT_BAN_CACHE.ban_cache.clear()
    SLOT_BAN_CACHE.load_all_csv_from_root(folder)
    if log:
        log("✅ 封禁缓存加载完成")

    file_list = []
    for root_dir, _, files in os.walk(folder):
        for f in files:
            if f.lower().endswith('.xml'):
                file_list.append(os.path.join(root_dir, f))
    total = len(file_list)
    if total == 0:
        if log:
            log("❌ 未找到任何 XML 文件", "FAIL")
        return {'folder': folder, 'total': 0, 'success': 0, 'warn': 0, 'fail': 0,
                'uid_rows': [], 'csv_path': None, 'detail_paths': [],
                'uid_total_cost': {}, 'uid_assets': {}}

    # 预扫描：同 UID 多档取最高 VIP，作为联合消费判断基准
    uid_max_vip = {}
    for fp in file_list:
        m = re.match(r"^(\d+)_\d+(?:_|\.)", os.path.basename(fp), re.IGNORECASE)
        if not m:
            continue
        uid = m.group(1)
        vip = DetectionEngine.extract_vip_level(fp)
        if vip >= 0 and vip > uid_max_vip.get(uid, -1):
            uid_max_vip[uid] = vip

    file_result_map = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_file = {
            executor.submit(AppDetector._detect_single_file_batch, fp,
                            settings['bin_path'], settings['max_export_details'],
                            settings['min_money_details'], settings['min_number_details'],
                            settings['export_full_details']): fp
            for fp in file_list
        }
        for future in as_completed(future_to_file):
            fp = future_to_file[future]
            try:
                file_result_map[fp] = future.result()
            except Exception as e:
                if log:
                    log(f"❌ 处理失败：{fp} | {e}", "FAIL")

    uid_total_cost = AppDetector._finalize_batch_results(file_result_map, uid_max_vip)
    uid_assets = AppDetector._finalize_asset_results(file_result_map)

    success = warn = fail = 0
    for fp in file_list:
        res = file_result_map.get(fp)
        if not res or res['overall'] == 'fail':
            fail += 1
        elif res['overall'] == 'warn':
            warn += 1
        else:
            success += 1

    uid_rows = AppDetector._build_uid_groups(file_result_map, uid_max_vip, uid_assets,
                                             settings['max_export_details'])

    detail_paths = []
    if write_detail_files:
        detail_dir = os.path.join(out_root, "异常详情")
        for row in uid_rows:
            detail_paths.append(AppDetector._write_uid_detail_file(
                row['uid'], row['items'], row['inactive_bans'],
                vip_level=row.get('vip_level'), asset=row.get('asset'),
                out_dir=detail_dir))

    csv_path = None
    if uid_rows:
        os.makedirs(out_root, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(out_root, f"批量检测报告_{stamp}.csv")
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            csv.writer(f).writerows(ReportRenderer.build_batch_csv_rows(uid_rows))

    if log:
        log(f"批量检测结束 | ✅ 通过:{success} ⚠️ 警告:{warn} ❌ 异常:{fail} | 总计:{total}")
    return {'folder': folder, 'total': total, 'success': success, 'warn': warn,
            'fail': fail, 'uid_rows': uid_rows, 'csv_path': csv_path,
            'detail_paths': detail_paths, 'uid_total_cost': uid_total_cost,
            'uid_assets': uid_assets}


def run_tool():
    """启动图形界面（仅在需要界面时调用；导入本模块不会触发）。"""
    if not has_gui():
        raise RuntimeError("当前环境不可用 tkinter，无法启动图形界面；"
                           "如需无界面检测请调用 detect_file() / detect_folder()")
    enable_dpi_awareness()
    root = tk.Tk()
    app = AppDetector(root)
    set_app_icon(root)
    root.mainloop()


if __name__ == "__main__":
    run_tool()
