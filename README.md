# 数据检测工具 · γ 合并版 v3.0.0

> 由 **α 版**（`α/main2.1.py` + `α/info_get5.py`，按文件批量导出）
> 与 **β 版**（`β/2.β.py` + `β/info_get_v2.py`，存档封禁 / UID一致性 / 自动报告）
> 合并重构而成。原 α、β 目录保持不变，本目录为全新统一版本。

## 📁 目录结构

```
γ/
├─ main.py            检测主程序（入口，运行它即可；也可作为模块被其他项目调用）
├─ app_paths.py       统一路径解析（以程序目录为基准，不依赖启动目录）
├─ info_get.py        存档下载工具（主程序主页“打开下载工具”会启动它）
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
稀有零件：应有 = 付费 + 券购(goods._p) + 塔领(tower) + 活动修正([parts_adjust])
```

- 差值只与**数量**有关，与单价/估值无关 → 未定价物品同样会报。
- 单价只在报告里附带展示（多出来多少、差值估值多少），用于排序与参考。
- `min_excess_value` **仅用于降噪**（默认 0 = 只要能算出差值就全部报出）。
- 零件按一阶当量折算（高阶由低阶升级而来），全族合并判定。
- 载具不参与差值判定，由 **收费 / 稀有 / 免费 / 异常** 分类覆盖（存在性差值）。
- `[parts_adjust]` 即**活动修正参数**：活动/兑换/赠送等存档内无记录的来源，
  按零件人工登记份数（不确定就保持 0），登记后差值相应减小。

## 🧪 依赖

```
pycryptodome  requests  aiohttp  (tkinter 为 Python 自带)
```

> 说明：配置文件首次由程序自动创建；如改动设置请用界面“保存设置”，程序会重写签名。
> 作为模块调用时 `pycryptodome` 为可选：缺失则「金币消费检测」降级为提示，其余检测不受影响。

## 📝 批量检测报告格式

`outputdata/批量检测报告_<时间戳>.csv` —— **一行 = 一个存档 index**（便于按槽位筛选）：

`UID_Index | Name | VIP | 状态 | 涉及存档数 | 封禁槽位 | 时装 | 载具 | 特殊零件 | 资产价值 | 资产异常摘要 | 异常摘要`

- `UID_Index` 采用 `<uid>_<index>_<名字>` 形式，每个异常存档独立成行；
- 状态 / 封禁槽位 / 资产各列均为**该槽位自身**口径（不再取同 UID 各档的最大值，
  故同一账号的多行可精确定位到具体档）；
- `涉及存档数` = 该 UID 的异常档总数；
- 未参与检测的封禁槽位（服务器未返回内容、无 XML）各自单独成行（状态 `fail`，
  封禁槽位列写明原因），保证封禁信息不因逐槽位拆分而丢失。

`outputdata/异常详情/<uid>_异常详情.txt` 为该账号全部异常档的完整检测日志（按 UID 汇总）。
