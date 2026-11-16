# 外设电量托盘 — 开发与交接指南

> 适用版本：`v1.1.2`  
> 最后更新：2026-11-16  
> 当前发布物是 `my_gear_tray.py`（罗技 GPW2 + 索尼 WH-1000XM4）。仓库里的
> `my_devices.py`、`app.py`、`tray_app.py` 是早期通用设备版本，不属于当前发布物。

## 1. 项目概览

Windows 通知区域工具，显示两台设备的电量：

| 设备 | 连接方式 | 读取方式 |
|---|---|---|
| 罗技 G PRO X Superlight（GPW2） | Lightspeed 接收器 `046D:C547` | HID++ 2.0，特性 `0x1004` / `0x1000` / `0x1001` |
| 索尼 WH-1000XM4 | 蓝牙 | Windows 蓝牙 HFP 未公开 PnP 电量属性 |

产品形态：

- 纯 Python 标准库 + `ctypes`，运行时零第三方依赖
- 两个托盘图标：鼠标无底板，耳机紫色底板
- 0–99 显示数字；100% 显示满电电池图标；未知状态显示带底板的 `?`
- 右键原生 Win32 菜单：刷新、间隔、开机自启、检查更新、详情、退出
- 安装包按当前用户安装，不需要管理员权限
- 启动时检查 GitHub Release，可下载并静默安装更新

明确不做的事：

- 不做通用外设工具。协议只针对这两台实测设备。
- 不移回宁芝 X87EC(S) 键盘。它的 2.4G dongle 不透传电量。
- 不上传设备信息，不做遥测。只有检查更新/下载安装包时访问 GitHub。

## 2. 当前状态

- 当前版本：`1.1.2`
- 发布仓库：<https://github.com/blkot/2.4G-battery-viewer>
- 最新 Release：<https://github.com/blkot/2.4G-battery-viewer/releases/latest>
- 更新源：<https://github.com/blkot/2.4G-battery-viewer/releases/latest/download/update.json>
- 当前只保留 `v1.1.2`；`v1.1.0`、`v1.1.1` 的 Release 和 tag 已删除
- 安装包未做代码签名，首次运行可能触发 SmartScreen
- 安装目录：`%LOCALAPPDATA%\Programs\MyGearBatteryTray\`
- 配置：安装目录下的 `my_gear_config.json`
- 启动项：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\外设电量托盘.lnk`

### Git 远端

| 远端 | 地址 | 权限 |
|---|---|---|
| `origin` | `https://github.com/yszyszysz233/2.4G-battery-viewer.git` | 上游，当前账号只读 |
| `fork` | `git@github.com:blkot/2.4G-battery-viewer.git` | 自己的 fork，可推送 |

发布走 `fork`。`version.py` 里的 `GITHUB_REPO` 和 Release 工作流都指向
`blkot/2.4G-battery-viewer`。如果以后发布仓库变更，改 `version.py` 的
`GITHUB_REPO` 即可；工作流里的仓库地址使用当前 Actions 仓库，不需要改。

## 3. 快速开始

### 环境要求

- Windows 10 / 11 x64
- Python 3.10 x64（`build.ps1` 默认用 `py -3.10`）
- PyInstaller（`build.ps1` 会自动安装/升级）
- Inno Setup 6（只有构建安装包时需要）
- 可选：GitHub CLI `gh`，用于查看/删除 Release

### 源码运行

```powershell
# 命令行读一次
py -3.10 my_gear.py --once

# 排查 HID / 蓝牙节点
py -3.10 my_gear.py --diagnose

# 托盘前台运行并输出过程
py -3.10 my_gear_tray.py --debug

# 查看状态 / 通知退出
py -3.10 my_gear_tray.py --status
py -3.10 my_gear_tray.py --quit
```

源码模式不会写日志文件；只有 `--debug` 才输出到控制台。

### 开机自启

```powershell
py -3.10 my_gear.py --autostart on
py -3.10 my_gear.py --autostart off
py -3.10 my_gear.py --autostart status
```

`my_gear_tray.py --autostart ...` 也支持同样的参数。

## 4. 代码结构

### 当前产品实际使用的文件

| 文件 | 职责 |
|---|---|
| `my_gear_tray.py` | 托盘主程序：窗口、图标、菜单、定时器、更新 UI |
| `my_gear.py` | 读取层：鼠标/耳机 `Reading`、命令行、详情格式化 |
| `my_gear_common.py` | 配置、开机自启、单实例、进程间消息、冻结路径 |
| `logi_hidpp.py` | 罗技 HID++ 2.0 客户端 |
| `hid_win.py` | Windows HID 枚举 / Feature Report / 异步 Input Report |
| `bt_battery.py` | 蓝牙 HFP 电量属性读取 |
| `win_icon.py` | 数字/电池图标生成：RGBA → ICO → HICON |
| `win_shell.py` | 已知文件夹路径、COM 创建 `.lnk` |
| `updater.py` | GitHub Release 检查、下载、SHA-256 校验、静默安装 |
| `version.py` | 唯一版本号 + 发布/更新渠道配置 |
| `build.ps1` | 本地一键构建 |
| `build_assets.py` | 生成 `build/app.ico` |
| `installer.iss` | Inno Setup 安装包脚本 |
| `packaging/make_version_info.py` | 从 `version.py` 生成 exe 文件版本资源 |
| `packaging/make_update_manifest.py` | 生成 `update.json` |
| `.github/workflows/release.yml` | tag 触发的 Release 工作流 |

### 早期通用版本（不是当前发布物）

这些文件仍在仓库里，但当前托盘不依赖它们：

- `my_devices.py`、`app.py`、`tray_app.py`、`tray_common.py`
- `battery.py`、`darkrim_proto.py`、`win_link.py`
- `PROMPT.md` 等上游通用文档

不要在没有确认的情况下删除它们；它们是上游通用工具的产物，也可能是其他用户仍在用的入口。
当前产品的使用说明以 `README.md` 和 `MY_GEAR.md` 为准。

### 运行时结构

```text
my_gear_tray.py
 ├─ my_gear.py
 │   ├─ logi_hidpp.py ── hid_win.py
 │   └─ bt_battery.py
 ├─ my_gear_common.py ── win_shell.py
 ├─ win_icon.py
 ├─ updater.py ── version.py
 └─ version.py
```

### 托盘线程模型

- 主线程：Win32 消息循环、菜单、图标更新、MessageBox
- `WM_TIMER`（ID 1）：按配置间隔触发刷新
- `WM_TIMER`（ID 2）：启动后鼠标补刷，只跑几次
- 后台线程：`my_gear.read_all()` 读取设备
- 读取完成后 `PostMessage(MSG_REFRESH_DONE)` 回主线程更新图标
- 更新检查/下载也在后台线程，通过 `MSG_UPDATE_RESULT` / `MSG_UPDATE_DOWNLOADED` 回主线程

### 数据模型

`my_gear.Reading` 的关键字段：

```python
key: str              # "mouse" / "headset"
title: str
level: Optional[int]  # None = 不可读
status: str
detail: str
error: str
stale: bool           # True = 鼠标休眠，数值来自上次成功读数
updated_at: float
```

状态规则：

- **鼠标休眠**：保留上一次成功读数，标 `stale=True`，tooltip 写「上次读数 · 设备休眠」
- **耳机未连接/未上报**：一律不保留旧值，显示 `?` 并说明原因
- 耳机三种错误状态：
  - 没有蓝牙节点：`耳机未连接`
  - 只有主设备节点、没有 HFP 节点：`耳机已配对，但未连接`
  - HFP 节点存在但没有电量属性/值为 0：`耳机已连接，但未上报电量`

### 图标规则

- `0–99`：数字图标，颜色按电量变化（≥60 绿 / 30–59 黄 / <30 红）
- `100`：满电电池图标，避免三位数在 16px 下被缩小
- 不可读：灰色底板的 `?`，避免看起来像空白
- 耳机图标有紫色底板，鼠标没有底板

## 5. 配置与单实例

默认配置：

```json
{
  "interval": 60,
  "autostart": true,
  "check_updates": true,
  "update_url": ""
}
```

- `interval`：刷新间隔秒数，菜单可选 30 秒 ~ 30 分钟
- `autostart`：只记录用户意愿；真实状态以启动文件夹快捷方式 + `StartupApproved` 为准
- `check_updates`：启动时是否检查更新
- `update_url`：空 = 使用 `version.UPDATE_URL`；本地测试可填 `file:///...`

单实例：

- Mutex：`Global\MyGearBatteryTray_single_instance`
- 窗口类：`MyGearBatteryTrayWnd`
- 已有实例时，新进程会 `PostMessage(MSG_RELOAD)` 后退出
- `--quit` 会发消息并等待托盘窗口消失，卸载器随后才能删除 exe

## 6. 版本号与发布

### 唯一版本来源

`version.py`：

```python
APP_VERSION = "1.1.2"
GITHUB_REPO = "blkot/2.4G-battery-viewer"
```

版本号只改这里。构建时会自动同步到：

- exe 文件版本：`packaging/make_version_info.py` → `build/version_info.txt`
- 安装包版本：`build.ps1` 通过 `/DMyAppVersion` 传给 Inno Setup
- `update.json.version`：`packaging/make_update_manifest.py`

`packaging/version_info.txt` 已从仓库删除，不要重新手写。`installer.iss` 里的
`#define MyAppVersion` 只是直接运行 ISCC 时的默认值，正常构建会被覆盖；仍建议随手同步，避免误用。

### tag 规则

tag 必须是 `v` + `APP_VERSION`：

```text
version.py = 1.1.2  ->  tag = v1.1.2
```

`.github/workflows/release.yml` 在构建前强制检查，不一致会直接失败，不会发布错误版本。

### 发布步骤

```powershell
# 1. 修改 version.py
#    APP_VERSION = "1.1.3"

# 2. 可选：本地构建验证
.\build.ps1

# 3. 提交
git add -A
git commit -m "release: v1.1.3"

# 4. 推送主分支
git push fork main

# 5. 打 tag 并推送（只有这一步会触发 Release）
git tag v1.1.3
git push fork v1.1.3
```

推送 tag 后工作流会：

1. 校验 `tag == "v" + version.py`
2. 构建 `MyGearBatteryTray.exe`
3. 构建 `MyGearBatteryTray-Setup-<version>.exe`
4. 生成 `update.json`
5. 创建 GitHub Release，上传三个文件

### 发布后验证

```powershell
# 工作流
gh run list --repo blkot/2.4G-battery-viewer --limit 3

# Release 资源
gh release view v1.1.3 --repo blkot/2.4G-battery-viewer --json assets,isDraft,isPrerelease

# 客户端实际读到的 manifest
Invoke-WebRequest `
  -Uri https://github.com/blkot/2.4G-battery-viewer/releases/latest/download/update.json `
  -UseBasicParsing
```

确认：

- `update.json.version` 等于新版本
- `update.json.url` 指向新安装包
- `update.json.sha256` 等于 Release 资源的 SHA-256
- `isDraft` / `isPrerelease` 都是 `false`，否则不会成为 latest
- 安装新包后 `FileVersion` / `ProductVersion` 正确

### 删除旧版本

确认新版本可用后，停止供应旧 tag：

```powershell
gh release delete v1.1.3 --repo blkot/2.4G-battery-viewer --yes --cleanup-tag
git tag -d v1.1.3
```

`--cleanup-tag` 会同时删除远端 tag。本地 tag 需要单独删。
删除后旧下载 URL 应返回 404，`releases/latest` 应指向剩下的最新版本。

### 注意

- 普通文档提交不要打 tag；tag 会触发构建和发布。
- `workflow_dispatch` 虽然写在触发条件里，但 job 有
  `if: startsWith(github.ref, 'refs/tags/')`，手动 dispatch 目前会被跳过。
  如果需要手动发布，要同时调整这个条件。
- `dist/update.json` 是本地构建产物，SHA 和 CI 构建不同是正常的；客户端只读 Release 里的版本。

## 7. 更新机制

### manifest 格式

```json
{
  "version": "1.1.2",
  "url": "https://github.com/.../MyGearBatteryTray-Setup-1.1.2.exe",
  "sha256": "64 位小写十六进制",
  "notes": "更新说明",
  "published_at": "2026-11-16T10:05:36Z"
}
```

### 客户端流程

1. 启动后首次刷新完成时检查（可在菜单关闭）
2. 拉取 `version.UPDATE_URL` 或配置里的 `update_url`
3. 用 `parse_version()` 比较四段数字，`1.1.2` 等价于 `1.1.2.0`
4. 只有 manifest 版本更高才提示
5. 下载安装包到 `%TEMP%\MyGearBatteryTray_update\`
6. 校验 SHA-256
7. 写一个 PowerShell 助手：等当前进程退出 → `/VERYSILENT` 安装 → 重启
8. 安装版重启当前 exe；免安装版回到默认安装目录的 exe

### 网络策略

Windows 上优先使用系统 PowerShell `Invoke-WebRequest`（走系统代理），失败再回退
Python `urllib`。这台机器上 Python urllib 访问 GitHub 曾出现超时，因此不要随意删掉
PowerShell 优先逻辑。

### 本地测试更新

可以不用真的发版：

1. 构造一个假的安装包和一个 `update.json`
2. 把 `update_url` 配成 `file:///C:/.../update.json`
3. 运行 `my_gear_tray.py --debug`
4. 查看是否发现新版本、下载、SHA 校验是否通过

注意 `file://` 只用于本地测试；正式 manifest 的 URL 必须是 HTTPS。

## 8. 构建细节

### 本地构建

```powershell
.\build.ps1
```

流程：

1. 安装/升级 PyInstaller
2. 生成 `build/app.ico`
3. 从 `version.py` 生成 `build/version_info.txt`
4. PyInstaller 打包 `dist/MyGearBatteryTray.exe`（onefile / noconsole）
5. Inno Setup 生成 `dist/MyGearBatteryTray-Setup-<version>.exe`
6. 生成 `dist/update.json`

产物：

```text
dist\MyGearBatteryTray.exe
dist\MyGearBatteryTray-Setup-<version>.exe
dist\update.json
```

### 为什么 exe 约 7 MB

体积主要不是业务代码，而是 PyInstaller 自带的 Python 运行时：

- `python310.dll`：约 4.25 MB
- `libcrypto` / `libssl`：约 3.9 MB（HTTPS 和 SHA-256）
- `unicodedata`、标准库 PYZ、基础库：约 2.9 MB
- `_ctypes` + `libffi`：约 0.15 MB
- 业务 `.py` 代码：约 40 KB

安装包约 8.7 MB，因为还要包含已压缩的主程序、Inno Setup stub 和卸载器。
这不是 ctypes 的问题；如果以后要压到 5 MB 左右，可以把网络和哈希全部改成 PowerShell，
再排除 `ssl` / `hashlib` / `urllib` / `unicodedata`。如果要求 1 MB 以内，只能改原生语言重写。

### 构建注意事项

- `build.ps1` 必须保持 **UTF-8 BOM**。Windows PowerShell 5.1 读取中文注释/字符串时需要它。
- `build.ps1` 每次都会 `pip install --upgrade pyinstaller`，需要网络。
- CI 用 `-Python python`；本地默认 `-Python py`，走 `py -3.10`。
- PyInstaller onefile 运行时会出现父/子两个 `MyGearBatteryTray.exe` 进程，这是正常的。
- `build/`、`dist/`、`*.spec` 已在 `.gitignore`。
- `official_firmware/` 是未跟踪的用户数据，不要提交。
- 安装包的 `AppId` 不要改，否则会被当成另一个产品，影响升级和卸载。

## 9. 测试清单

发布前至少检查：

- [ ] `py -3.10 my_gear.py --once` 能读到鼠标和耳机
- [ ] `py -3.10 my_gear.py --diagnose` 能看到 HID / 蓝牙节点
- [ ] `py -3.10 my_gear_tray.py --debug` 启动后出现两个图标
- [ ] 鼠标动一下后电量能恢复；休眠时显示上次读数
- [ ] 耳机断开后不显示旧电量，三种未连接状态提示正确
- [ ] 100% 显示电池图标，不是缩小的 `100`
- [ ] 左键刷新、右键菜单、刷新间隔生效
- [ ] 开机自启开关能创建/删除启动快捷方式
- [ ] 详情对话框和 tooltip 文案正确
- [ ] 本地 `update.json` 能触发更新提示
- [ ] 安装包能覆盖升级，`FileVersion` 正确
- [ ] 卸载后托盘退出、启动项和配置被清理

## 10. 已知坑与约束

1. **tag 与版本号不一致**：工作流会拦，但本地构建不会；本地构建前自己确认 `version.py`。
2. **不要手写 `version_info.txt`**：已改为构建时生成。
3. **`build.ps1` 的 BOM 不能丢**：否则 Windows PowerShell 5.1 可能乱码或解析失败。
4. **退出必须走 `PostQuitMessage`**：只销毁窗口会留下僵尸进程，占着单实例锁。
5. **`--quit` 要等窗口消失**：否则卸载器可能删不掉正在运行的 exe。
6. **耳机不能沿用旧值**：只有鼠标休眠才允许 `stale=True`。
7. **100% 必须用电池图标**：数字 `100` 在 16px 下会被压缩到不可读。
8. **更新检查优先 PowerShell**：不要为了“纯标准库”删掉它，否则部分网络环境会超时。
9. **当前是 per-user 安装**：不要改成 `Program Files`，会引入管理员权限和升级路径问题。
10. **README 与 DEVELOPMENT 要保持同步**：README 面向用户，DEVELOPMENT 面向开发者；改发布流程或版本规则时两边一起更新。
11. **`my_gear_common.py` 顶部 docstring 仍写着“三台外设”**：历史文案，实际只有两台；可顺手清理。
12. **不要提交 `official_firmware/`**：这是本机抓包/固件资料，不属于发布物。

## 11. 代码签名现状

当前发布物**没有签名**：

- 用户首次运行可能看到 SmartScreen “未知发布者”
- 更新包只靠 `update.json` 里的 SHA-256 校验
- SHA-256 能防传输损坏，但不能防 GitHub 仓库被完全控制后的恶意替换

常见方案：

| 方案 | 成本 | 说明 |
|---|---|---|
| 不签名 + SHA-256 | 免费 | 当前做法，小型开源项目常见 |
| SignPath Foundation | 免费（需申请） | 面向开源项目的公共信任签名，最匹配本项目 |
| Azure Artifact Signing（原 Trusted Signing） | Basic $9.99/月，5,000 次签名 | 微软托管证书，接入 GitHub Actions 方便 |
| 传统 OV / EV 证书 | 较贵，通常需要硬件令牌 | 个人开源项目一般没必要 |
| 自签名 | 免费 | 只适合自己机器/内部测试，其他用户仍会警告 |

如果以后接签名，顺序是：先签 `MyGearBatteryTray.exe`，再签 Setup；CI 中通过
SignPath 或 Azure 的 GitHub Actions 集成完成，不要把私钥放进仓库。

## 12. 交接检查表

接手时确认：

- [ ] 有 `blkot/2.4G-battery-viewer` 的写权限，或能通过 SSH 推送 `fork`
- [ ] `gh auth status` 正常；能查看/删除 Release
- [ ] 本机有 Python 3.10 x64、PyInstaller、Inno Setup 6
- [ ] 能运行 `my_gear.py --once` 和 `my_gear_tray.py --debug`
- [ ] 知道当前版本是 `1.1.2`，Release 只保留 `v1.1.2`
- [ ] 知道普通提交不要打 tag
- [ ] 知道 `version.py` 是唯一版本源
- [ ] 知道 `README.md` 面向用户、`MY_GEAR.md` 讲协议、`DEVELOPMENT.md` 讲开发/发布
- [ ] 知道 `official_firmware/` 不提交

## 13. 可选后续工作

- 接 SignPath Foundation 或 Azure Artifact Signing
- 把更新网络改成纯 PowerShell，缩减 exe 体积
- 给 `update.json` 增加 minisign/公钥验签，降低仓库被控风险
- 增加 `parse_version()`、耳机状态机、manifest 校验的单元测试
- 清理早期通用文件前先确认没有其他用户依赖
- 让 `workflow_dispatch` 支持手动发布（需要调整 job 的 `if`）
- 持续维护 `README.md` / `MY_GEAR.md` / `DEVELOPMENT.md` 的分工，避免文档过期
