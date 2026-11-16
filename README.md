# 外设电量托盘（GPW2 + WH-1000XM4）

Windows 10 / 11 通知区域电量工具，只针对这两台设备：

- **罗技 G PRO X Superlight（GPW2）**
- **索尼 WH-1000XM4**

纯 Python 标准库 + `ctypes`，运行时零第三方依赖；提供按用户安装的安装包和
GitHub Release 自动更新。当前版本 **v1.1.2**。

> **上游项目**：[yszyszysz233/2.4G-battery-viewer](https://github.com/yszyszysz233/2.4G-battery-viewer)
>
> 上游是一个 Windows 上读取 2.4G 无线外设电量的小工具（纯 ctypes，零第三方依赖），
> 主要面向 ATK / VXE 鼠标、DARKRIM 耳机等通用设备，并提供调试面板和可复用的抓包/逆向
> prompt。
>
> 本仓库是在上游基础上面向 **罗技 GPW2 + 索尼 WH-1000XM4** 的独立实现和发布分支。
> 当前 Release、安装包和自动更新由 [blkot/2.4G-battery-viewer](https://github.com/blkot/2.4G-battery-viewer)
> 提供，不读取上游的 Release。

## 支持设备

| 设备 | 连接方式 | 读取方式 |
|---|---|---|
| 罗技 G PRO X Superlight（GPW2） | Lightspeed 接收器 `046D:C547` | HID++ 2.0，特性 `0x1004` / `0x1000` / `0x1001` |
| 索尼 WH-1000XM4 | 蓝牙 | Windows 蓝牙 HFP 未公开 PnP 电量属性 |

> **这不是通用工具。** 协议是针对上述设备实测得到的。换成别的鼠标或耳机，
> 大概率读不出来。需要通用方案请看[上游项目](https://github.com/yszyszysz233/2.4G-battery-viewer)。

宁芝 X87EC(S) 键盘已移除：它的 2.4G dongle 是单向 BLE→USB HID 桥，
不转发 BLE 电量，Windows 侧没有可查询的通道。

## 功能

- 通知区域两个图标：鼠标无底板，WH-1000XM4 紫色底板
- `0–99` 显示数字，颜色随电量变化（≥60 绿 / 30–59 黄 / <30 红）
- `100%` 显示满电电池图标，避免三位数字在 16px 下被缩小
- 不可读状态显示带灰色底板的 `?`，不会看起来像空白
- 耳机未连接 / 已配对未连接 / 已连接未上报，三种状态分别提示，不显示旧电量
- 鼠标休眠时保留上一次读数，并标注「上次读数 · 设备休眠」
- 启动时立即刷新；鼠标没读到会自动短间隔重试
- 右键菜单可刷新、改刷新间隔、开关开机自启、查看详情、检查更新
- 支持 GitHub Release 自动更新：下载后校验 SHA-256，静默安装并重启
- 安装包按当前用户安装，不需要管理员权限
- 默认不写日志、不做遥测

## 安装

从最新 Release 下载安装包：

<https://github.com/blkot/2.4G-battery-viewer/releases/latest>

文件名形如：

```text
MyGearBatteryTray-Setup-1.1.2.exe
```

安装特点：

- 安装到 `%LOCALAPPDATA%\Programs\MyGearBatteryTray\`
- 不需要管理员权限
- 创建开始菜单快捷方式；桌面快捷方式可选
- 开机自启可选，底层是「启动」文件夹里的 `.lnk`，任务管理器里可见、可禁用
- 卸载时会退出托盘并清理启动项和配置文件

> 安装包没有代码签名，首次运行可能提示「Windows 已保护你的电脑」。
> 选择「更多信息 → 仍要运行」即可。

> Windows 11 默认把新图标放进 `^` 溢出区。点开 `^` 把两个图标拖到任务栏即可。

## 使用

- **左键**托盘图标：立刻刷新一次
- **悬停**：设备名 + 电量 / 未连接原因
- **右键**：打开原生 Win32 菜单

右键菜单包含：

- 两台设备的电量/状态
- 刷新
- 刷新间隔（30 秒 ~ 30 分钟）
- 开机自启
- 启动时检查更新
- 检查更新 / 更新到 vX.Y.Z…
- 查看详情
- 退出

安装版命令行参数：

```powershell
MyGearBatteryTray.exe --status
MyGearBatteryTray.exe --quit
MyGearBatteryTray.exe --autostart on
MyGearBatteryTray.exe --autostart off
MyGearBatteryTray.exe --autostart status
```

配置保存在安装目录的 `my_gear_config.json`：

```json
{
  "interval": 60,
  "autostart": true,
  "check_updates": true,
  "update_url": ""
}
```

## 自动更新

- 启动后首次刷新完成时检查一次；可在右键菜单关闭「启动时检查更新」
- 也可以手动点「检查更新…」
- 发现新版本后：下载安装包 → 校验 `update.json` 里的 SHA-256 → 退出 → 静默安装 → 自动重启
- 网络请求优先使用系统 PowerShell（走系统代理），失败再回退 Python `urllib`

更新源：

```text
https://github.com/blkot/2.4G-battery-viewer/releases/latest/download/update.json
```

当前只供应 **v1.1.2**；`v1.1.0`、`v1.1.1` 的 Release 和 tag 已删除。

## 从源码运行

环境要求：

- Windows 10 / 11 x64
- Python 3.10 x64

```powershell
# 命令行读一次
py -3.10 my_gear.py --once

# 排查 HID / 蓝牙节点
py -3.10 my_gear.py --diagnose

# 托盘前台运行并输出过程
py -3.10 my_gear_tray.py --debug

# 状态 / 退出
py -3.10 my_gear_tray.py --status
py -3.10 my_gear_tray.py --quit
```

源码模式默认不写日志文件；只有 `--debug` 才输出到控制台。

## 构建安装包

需要额外安装 Inno Setup 6。PyInstaller 会由脚本自动安装/升级。

```powershell
.\build.ps1
```

产物：

```text
dist\MyGearBatteryTray.exe
dist\MyGearBatteryTray-Setup-<version>.exe
dist\update.json
```

版本号唯一来源是 `version.py` 的 `APP_VERSION`。exe 文件版本由
`packaging/make_version_info.py` 在构建时生成，安装包和 `update.json`
使用同一个版本号。

发布流程、tag 校验、测试清单和已知坑见 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 项目结构

当前产品实际使用的文件：

| 文件 | 说明 |
|---|---|
| `my_gear_tray.py` | 托盘主程序：窗口、图标、菜单、更新 UI |
| `my_gear.py` | 鼠标/耳机读取层 + 命令行 |
| `my_gear_common.py` | 配置、开机自启、单实例、进程间消息 |
| `logi_hidpp.py` | 罗技 HID++ 2.0 客户端 |
| `hid_win.py` | Windows HID 枚举 / 读写 |
| `bt_battery.py` | 蓝牙 HFP 电量属性读取 |
| `win_icon.py` | 数字/电池图标生成 |
| `win_shell.py` | 已知文件夹路径、创建 `.lnk` |
| `updater.py` | Release 检查、下载、SHA-256 校验、静默安装 |
| `version.py` | 唯一版本号与发布渠道配置 |
| `build.ps1` | 一键构建 exe + 安装包 + `update.json` |
| `installer.iss` | Inno Setup 安装包脚本 |
| `packaging/make_version_info.py` | 生成 exe 文件版本信息 |
| `packaging/make_update_manifest.py` | 生成 Release 用的 `update.json` |

早期通用设备实现（`my_devices.py`、`app.py`、`tray_app.py`、`battery.py`、
`darkrim_proto.py`、`PROMPT.md` 等）仍保留在仓库里，但不属于当前发布物。
当前产品的协议细节和实测结论见 [MY_GEAR.md](MY_GEAR.md)。

## 已知限制

1. **鼠标休眠时读不到**：Lightspeed 接收器在鼠标深度休眠后不转发 HID++ 请求。
   工具会保留上一次成功读数并标注「上次读数」，动一下鼠标再刷新即可恢复。
2. **耳机电量是 HFP 上报值**：刚连接时可能还是旧值，等耳机自己上报后更新；
   断开后不显示旧值。
3. **只支持这两台设备**：不是通用外设电量工具。
4. **安装包未签名**：SmartScreen 可能提示未知发布者。
5. **Windows 11 图标在溢出区**：需要手动拖到任务栏。

## 隐私

- **只为更新联网**：只有检查更新/下载安装包时访问 GitHub，可在菜单关闭自动检查。
- **不写日志**：默认不产生日志文件；只有 `--debug` 时才输出到控制台。
- **不上传**：设备序列号、地址等信息只在内存里使用，不落盘。

## 上游与关系

- 上游项目：<https://github.com/yszyszysz233/2.4G-battery-viewer>
- 上游说明：Windows 上读取 2.4G 无线外设电量的小工具，纯 ctypes、零第三方依赖，
  主要面向 ATK / VXE 鼠标、DARKRIM 耳机等设备，包含通用读取、调试面板和逆向 prompt。
- 本仓库：在上游基础上加入罗技 GPW2 + WH-1000XM4 的独立托盘实现、安装包和
  GitHub Release 自动更新；当前发布渠道是 `blkot/2.4G-battery-viewer`。
- 上游的通用实现和文档仍保留，便于参考和复用到其他设备。

## 开发与交接

- [DEVELOPMENT.md](DEVELOPMENT.md)：环境、架构、构建、发布、测试、交接检查表
- [MY_GEAR.md](MY_GEAR.md)：GPW2 / WH-1000XM4 的协议细节、实测结论和使用说明
- [PROMPT.md](PROMPT.md)：上游的通用设备逆向方法，可作为换设备时的参考
