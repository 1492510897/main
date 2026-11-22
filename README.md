# 数据检测工具 · γ 合并版 v3.0.0

> 由 **α 版**（`α/main2.1.py` + `α/info_get5.py`，按文件批量导出）
> 与 **β 版**（`β/2.β.py` + `β/info_get_v2.py`，存档封禁 / UID一致性 / 自动报告）
> 合并重构而成。原 α、β 目录保持不变，本目录为全新统一版本。

## 📁 目录结构

```
γ/
├─ main.py            检测主程序（入口，运行它即可；也可作为模块被其他项目调用）
├─ app_paths.py       统一路径解析（以程序目录为基准，不依赖启动目录）
├─ info_get.py        存档下载工具（主程序主页“打开下载工具”会启动它，整账号 1~8 槽）
├─ info_get3.py       逐槽下载工具（α 线升级版：一行 uid,index = 一个槽位 / 申请节流 / 封禁统计 / 每 5 秒进度日志）
├─ info_get_v3.py     已废弃（仅保留占位，run_tool() 转交 info_get3）
├─ info_get_v3_1.py   已废弃（v3 的日志外观变体，能力已并入 info_get3）
├─ config.ini         配置（价格表路径 / 工作目录 / 检测参数）
├─ main.ico           窗口图标
├─ inputdata/         价格表 bin（v36.11_pro.bin / v36.01_pro.bin，已就绪）
├─ outputdata/        检测报告输出目录（CSV 主报告 + 异常详情/）
└─ test/              默认工作目录（存档存放位置）
```

> **路径基准**：所有路径（config.ini / inputdata / outputdata / test / 价格表 / 工作目录）
> 均以**程序所在目录**为基准，而非启动时的当前工作目录 —— 从任何位置启动，
> 读写位置都一致；相对路径写法（如 `work_dir = .\test`）也不会随启动目录漂移。

## 🚀 使用

```bash
python main.py
```

- 主页左侧“📂 批量检测文件夹”选中下载好的存档目录（`test/` 下各 UID 文件夹），
  程序自动递归扫描全部 `.xml` 并加载同目录的 `*_details.csv` 封禁信息。
- 单文件检测：粘贴/浏览存档 XML 路径 → “🚀 立即开始检测”，自动生成报告到 `outputdata/`。
- “📄 打开下载工具”启动 `info_get.py`（独立下载器，支持单 UID 全档 / 导入文件批量 /
  文件夹批量，含停止、分批暂停防封、失败重试）。
- `info_get3.py` 是并存的**逐槽下载器**（α 线）：任务行 `uid,index` = 一个槽位，
  纯 `uid` 自动展开 1~8 槽；同样支持单 UID 全档 / 导入文件 / 文件夹批量，并已整合
  v3.2.0 的路径统一、响应分类（未创建存档 / 申请过快 / 网络异常 / 解析失败）、
  申请节流（每 200 次申请暂停 30 秒）、封禁状态记录与失败槽位定向重试。
- `info_get_v3.py` 已废弃，仅保留占位，`run_tool()` 会转交给 `info_get3.py`。
- `info_get_v3_1.py` 同样已废弃：它是 `info_get_v3` 的日志外观变体（每 5 秒打印总进度、
  导入时显示路径），这些能力已并入 `info_get3.py`（`PROGRESS_LOG_INTERVAL = 5`）。

## 🔌 作为模块调用（无界面）

`main.py` 可被其他项目（如 NoneBot 机器人）直接 `import`，导入时**无副作用**
（不全屏、不建窗口、不改 DPI）；缺少 tkinter / pycryptodome 时自动降级而非报错。

```python
import main as detect

# 单文件检测
r = detect.detect_file(r"test\xxx\1234_0_名字.xml")
r["overall"], r["uid"], r["index_mismatch"], r["total_cost"], r["report_text"]

# 批量检测（递归扫描 .xml，按 UID 汇总）
res = detect.detect_folder(r"test", out_dir=r"outputdata", log=print)
res["total"], res["uid_rows"], res["csv_path"], res["detail_paths"], res["uid_assets"]

detect.has_gui(), detect.has_crypto()   # 运行环境能力探测
```

两个接口均支持 `log=回调(msg, level)`、`config_file=`、以及 `**overrides`
（临时覆盖 `bin_path` / `thread_count` / `asset_min_delta` 等设置）。

## 🧭 与旧版的差异与合并要点

| 功能 | α | β | γ（合并版） |
|---|---|---|---|
| 存档封禁检测（读 `_details.csv`） | ✗ | ✓ | ✓（兼容新旧两种表头） |
| 文件名 UID 与文件内 UID 一致性校验 | 部分 | ✓ | ✓ |
| UID 详情（理论/实际 Index、Name） | ✓ | 简 | ✓（保留 α 丰富字段） |
| 消费明细列出全部物品 | ✓ | 只列预警 | ✓ |
| VIP 联合“覆盖存档”预警 | ✗ | ✓(有 bug) | ✓（并修复 `pay_cost+5` 优先级 bug） |
| 单文件自动生成报告 | ✗ | ✓ | ✓ |
| 恢复上次文件路径 | ✗ | ✓ | ✓ |
| 批量异常详情按文件输出 | ✓ | 按 UID | ✓（α 风格，CSV 含理论/实际uid、Name） |
| 下载器封禁状态列 | ✓ | ✗ | ✓（统一列名存档/标题/状态/封禁状态） |
| 下载器停止 / 分批暂停 / 失败重试 | ✓ | ✗ | ✓ |
| 下载按 work_dir/任务文件分文件夹 | ✗ | ✓ | ✓ |
| 虚天塔 / 幻塔检测（`tower` 节点） | ✗ | ✗ | ✓（点数 / 每周技能 / 加点 / 幻塔进度） |
| 巅峰检测（`peak` 节点） | ✗ | ✗ | ✓（等级 / 经验 / 全体战力 / 加点方案） |
| 零件位卡检测（镶嵌位解锁 + 位卡账目） | ✗ | ✗ | ✓（占未解锁槽位 → fail） |

## ⚙️ 设置项（config.ini）

- `bin_path`：价格表文件（默认 `inputdata/v36.11_pro.bin`）
- `work_dir`：工作/批量检测目录（默认 `test`，兼容旧版 `temp_dir` 键自动迁移）
- `max_export_details`：输出明细最大条数（0 = 无穷）
- `min_money_details` / `min_number_details`：高价/高频预警阈值
- `batch_thread_count`：批量检测线程数
- `auto_restore` / `auto_open_dir` / `auto_uid_from_filename` / `export_full_details` /
  `auto_open_batch_report`：界面勾选项

## � VIP 二重检测（gift.vv ↔ upLevelObj）

游戏在**导入存档时**把 `vip.upLevelObj` 的首次快照写入 `gift.vv`（AMF3 + base64），
此后每次读取都用它自校验（`PlayerSave.getZuobiStr` → `ObjectMethod.samePan`）。
改档者通常只改其中一处，故本工具把它作为独立于「m 权限越界」的第二重判据：

- `gift.vv` 解码结果与当前 `upLevelObj` **不一致** → 判 `fail`，并列出差异键；
- `vv=no`（编码为空时的哨兵）却已有 `VIPn`（n>0） → 判 `fail`；
- **版本门槛**：`versionNumber >= 35.5` 才判定（老版本无此机制）；
- 快照缺失 / 结构无法识别 → **跳过，不判定**（不误报）。

## 💎 资产差值检测（时装 / 载具 / 特殊零件）

★ **重点不是估值，而是找差值** —— 即档内持有量与应有总量对不上（疑似异常修改存档）。

```
差值 = 持有量 − 应有总量
应有总量 = 付费次数(pay.obj) + 免费额度(free_quota.ini)
稀有零件：应有 = 付费 + 券购(goods._p) + 合成(gift.caO) + 塔领(tower)
                + 已领等级礼包(levelGiftObj) + 活动修正([parts_adjust])
```

- 差值只与**数量**有关，与单价/估值无关 → 未定价物品同样会报。
- 单价只在报告里附带展示（多出来多少、差值估值多少），用于排序与参考。
- `min_excess_value` **仅用于降噪**（默认 0 = 只要能算出差值就全部报出）。
- 零件按一阶当量折算（高阶由低阶升级而来），全族合并判定。
- 载具不参与差值判定，由 **收费 / 稀有 / 免费 / 异常** 分类覆盖（存在性差值）。
- `[parts_adjust]` 即**活动修正参数**：活动/兑换/赠送等存档内无记录的来源，
  按零件人工登记份数（不确定就保持 0），登记后差值相应减小。

## 🗼 虚天塔 / 幻塔检测（tower 节点）

数据源：`saveXml/null/tower`。权威源码见 `dataAll/_app/tower/`
（`TowerSave.as` / `UnendData.as` / `UnendAgent.as` / `UnendDataCtrl.as`），
加点定义见 `306_XMLOut_unendProClass.bin`。

| 字段 | 含义 | 判定 |
| --- | --- | --- |
| `ws` | 幻塔列表「隐藏已通关层」显示开关 | **不参与判定**（仅报告标注）|
| `unendLv` | 天塔通关最高层 | ≤ `UnendAgent.MAX_LV`（150）|
| `uP` | 当前层已获点数 | ≤ `LEVEL_POINT`（2）；实际取用 `min(uP, 2)` |
| `us` | 本周已使用技能次数 | ≤ `getSkillCanUseWeek()`（2）|
| `usUse` | 本周已用技能**下标**串（如 `"4,6"`）| 下标 0~6、无重复、条数 = `us` |
| `blv` | 幻塔累计通关层 | ≤ 75 |
| `dO` | 幻塔各层通关难度 | 层 1~75、难度 1~4 |
| `gO` | 幻塔各层已领奖难度 | 必须 ⊆ `dO`（先通关才可领奖）|
| `p0`/`p1`/`p2` | 三套加点方案 | 各项不超数据表上限；已用点数 ≤ 可用点数 |
| `pNow` | 当前方案编号 | `"0"` / `"1"` / `"2"` |

> ⚠️ **`ws` 不是「能否参加天塔」的资格开关**。源码（`TowerSave.as` / `TowerData.as`）中
> 它仅有两处显示层用途：`getUIArr()`（隐藏已通关满难度且无可领奖励的层）与
> `winShowB()` / `swapWinShow()`（UI 按钮「显示/隐藏已通关层」，
> `TowerListBoard.as` 里 `coverBtn.isChosen = !winShowB()`）。
> 实测 `ws=false` 的存档中 **124 档天塔已通 150 层**，与「无参赛资格」自相矛盾。
> 因此本工具**不用 `ws` 判定任何资格或改动合法性**（早期版本误将其作为判据，
> 导致 625 例误报，现已移除）。

点数规则（`UnendData`）：

```
可用点数 = unendLv × LEVEL_POINT + min(uP, LEVEL_POINT) = unendLv × 2 + min(uP, 2)
已用点数 = Σ(等级 × 每级消耗)      ← PeakProDefine.getMustPointSum(lv) = lv × point
```

加点项与上限（`unendProClass`）：伤害 60 / 技能回速 50 / 怒气回速 60 / 防御力 80
（每级 1 点）；队友生效加点 1（50 点）；倒计时 100（每级 1 点）；
弹药箱 6（4 点）；重生石 10（5 点）；队友重生卡 10（5 点）；首领全出场 1（2 点）。

> `ws=false` 的基准是**全默认 tower 节点**（见 `test/基础账号.xml`）：
> 未开放天塔时，`unendLv`/`uP`/`us`/`usUse`/`blv`/`p0~p2`/`dO`/`gO` 等
> 任何非默认值都意味着存档被改动过。

## 🏔 巅峰检测（peak 节点）

数据源：`saveXml/null/peak`。权威源码见 `dataAll/_app/peak/`
（`PeakSave.as` / `PeakData.as` / `PeakProDefine.as`），
加点表见 `resource/peak/peakPro.json`（≡ `257_XMLOut_peakProClass.bin`）。

| 字段 | 含义 | 判定 |
| --- | --- | --- |
| `lv` | 巅峰等级（默认 1） | 1 ≤ `lv` ≤ `MAX_LV`（120） |
| `exp` | 当前等级经验 | ≥ 0（上限表 `peakExp` 缺本地副本，不做硬判） |
| `dayExp` | 今日已转化经验 | ≤ `MAX_DAY_EXP`（400000000） |
| `dpN` | 「全体战力」累计加点次数 | ≤ `MAX_WHOLE_DPS_NUM`（30） |
| `dpDay` | 「全体战力」今日加点次数 | ≤ `WHOLE_DPS_DAY`（2） |
| `now` | 当前方案编号 | `""` / `"2"` / `"3"`（`PeakSave.labelArr`） |
| `pointObj`/`pointObj2`/`pointObj3` | 三套加点方案 | 各项不超上限；已用点数 ≤ 可用点数 |

点数规则（`PeakData`）：

```
可用点数 = 巅峰等级 lv                    ← PeakData.getAllPoint() = save.lv
已用点数 = Σ(等级 × 每级消耗)              ← PeakProDefine.getMustPointSum(lv) = lv × point
每级消耗：普通属性 1 点 / 技能项 2 点      ← AS3：构造器 point=1，skill 非空时 point=2
```

加点项与上限（`peakPro.json`）：
战斗力 15 / 生命值 15 / 3倍暴击概率 10 / 闪避概率 15 / 技能回复 10 /
近战伤害减免 15 / 移动速度 10 / 防弹值 15 / 载具攻击力 20（均 1 点/级）；
核爆 8 / 注视 8 / 搏命 8（技能项，2 点/级）。

额外一致性判定：`dpN > 0` 时 `lv` 必须 ≥ `WHOLE_DPS_LV`（100）——
该功能按等级解锁，低等级却加过点必为改档。

## 🎫 零件位卡检测（partsGridCard / godGridCard）

数据源：武器/装备的 `partsSave`（镶嵌）与背包类容器的 `lockLen` / `lockObj`。
权威源码：`ItemsSaveGroup.as`（槽位语义）、`MustDefineGroup.as`（解锁成本）。

**槽位解锁规则**（★ 用户口径）：零件的武器镶嵌位**基础解锁为 0~9**，
其余位置均需解锁后才能放零件。

```
getUnlockBySite(site) = (site <= lockLen - 1) or (lockObj[site] == 1)
getCanFillLen()       = lockLen + count(lockObj[n] == 1 && n >= lockLen)
```

> ★ 各位置**互相独立、无高低之分**：UI 点击任一未解锁格位都会单独调用
> `unlockSite(nowSite)`（`ItemsGripUnlockCtrl.as`），按该 site 对应道具扣费并把
> 该 site 写进 `lockObj` —— **不需要先解锁前面的位置**（未解锁 10 号也能直接
> 解锁 17 号）。故校验时逐位置独立比对成本。

解锁各位置的成本（`MustDefineGroup.as`，site 为存档 0-based）：

| site | 解锁所需 |
| --- | --- |
| 10 | 50 万硬币（≈ 免费） |
| 11 | 黄金位卡 ×1 |
| 12 | 零件位卡 ×1 |
| 13 | 黄金位卡 ×1 |
| 14 | 黄金位卡 ×1 |
| 15 | 零件位卡 ×1 |
| 16 | 黄金位卡 ×1 |

位卡获取渠道（存档可查部分）：

| 位卡 | propId | 渠道 |
| --- | --- | --- |
| 零件位卡 `partsGridCard` | 4486 | 零件券兑换（`goods.buyNumObj` 的 `partsGridCard_p`；`pay.obj` 亦可见）|
| 黄金位卡 `godGridCard` | 4579（旧版 4462「零件格子」）| 商店购买（`pay.obj`）|

判定：

- **占用了未解锁槽位** → `fail`（游戏内放不进去，必为改档）；
- 位卡账目差额 → `warn`（黄金位卡另有活动/签到等无记录来源，仅提示复核）。

## 🧪 依赖

```
pycryptodome  requests  aiohttp  (tkinter 为 Python 自带)
```

> 说明：配置文件首次由程序自动创建；如改动设置请用界面“保存设置”，程序会重写签名。
> 作为模块调用时 `pycryptodome` 为可选：缺失则「金币消费检测」降级为提示，其余检测不受影响。

## 📝 批量检测报告格式

`outputdata/批量检测报告_<时间戳>.csv` —— **一行 = 一个存档 index**（便于按槽位筛选）：

`UID_Index | Name | VIP | 状态 | 涉及存档数 | 封禁槽位 | 时装 | 载具 | 特殊零件 | 资产价值 | 塔数据 | 巅峰 | 位卡 | 资产异常摘要 | 异常摘要`

- `UID_Index` 采用 `<uid>_<index>_<名字>` 形式，每个异常存档独立成行；
- 状态 / 封禁槽位 / 资产 / 塔数据 / 巅峰 / 位卡各列均为**该槽位自身**口径
  （不再取同 UID 各档的最大值，故同一账号的多行可精确定位到具体档）；
- `塔数据` 形如 `天塔 145/150 层｜点数 286/290｜每周技能 0/2｜幻塔 45/75 层`，
  异常时前置 `⛔` / `⚠️`；
- `巅峰` 形如 `巅峰 120/120 级｜点数 120/120｜全体战力 30/30（今日 0/2）｜今日经验 0`，
  异常时同样前置 `⛔` / `⚠️`；
- `位卡` 形如 `镶嵌位最高 site 14｜零件背包 55/144 位｜位卡 零件位卡 28`，
  异常时同样前置 `⛔` / `⚠️`；
- `涉及存档数` = 该 UID 的异常档总数；
- 未参与检测的封禁槽位（服务器未返回内容、无 XML）各自单独成行（状态 `fail`，
  封禁槽位列写明原因），保证封禁信息不因逐槽位拆分而丢失。

`outputdata/异常详情/<uid>_异常详情.txt` 为该账号全部异常档的完整检测日志（按 UID 汇总）。
