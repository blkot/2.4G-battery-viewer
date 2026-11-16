# 我的外设电量（GPW2 + WH-1000XM4）

这是给本机 **罗技 G PRO X Superlight（GPW2）** 和 **索尼 WH-1000XM4** 做的
托盘电量工具。纯 Python + ctypes，零第三方运行时依赖，也可以打包成安装 exe。

> 宁芝 X87EC(S) 键盘已从本工具移除：它的 2.4G dongle 是单向 BLE→USB HID 桥，
> 不转发 BLE 电量，Windows 侧没有可查询的通道。历史分析仍可从 git 记录里找到。

## 实测结果

| 设备 | 连接方式 | 电量 | 读取方式 |
|---|---|---|---|
| 罗技 G PRO X Superlight（GPW2） | Lightspeed 接收器 `046D:C547` | **可读** | HID++ 2.0 `0x1004` |
| 索尼 WH-1000XM4 | 蓝牙 | **可读** | Windows 蓝牙 HFP 电量属性 |

示例：

```
罗技 G PRO X Superlight：67%（PRO X Wireless · HID++ 0x1004 统一电池）
索尼 WH-1000XM4：60%（蓝牙 HFP 电量上报）
```

## 用法

```bash
# 命令行读一次
python my_gear.py --once

# 排查：列出 HID / 蓝牙节点
python my_gear.py --diagnose

# 托盘常驻（静默，无黑窗）
pythonw my_gear_tray.py

# 调试：前台运行并输出过程（默认不写任何日志文件）
python my_gear_tray.py --debug

# 状态 / 退出
python my_gear_tray.py --status
python my_gear_tray.py --quit

# 开机自启（启动文件夹快捷方式，任务管理器「启动」里可见）
python my_gear.py --autostart on
python my_gear.py --autostart off
python my_gear.py --autostart status
```

## 托盘交互

通知区域两个数字图标：罗技鼠标（无底板）、WH-1000XM4（紫色底板）。
数字就是电量，颜色随电量变化（≥60 绿 / 30–59 黄 / <30 红）。

> Windows 11 默认把新图标放进 `^` 溢出区，点一下 `^` 把两个数字图标拖到任务栏即可。

- **左键**：立刻刷新一次
- **悬停**：设备名 + 电量 / 未连接原因
- **右键**：原生 Win32 菜单
  - 两台设备的电量/状态
  - 刷新
  - 刷新间隔（30 秒 ~ 30 分钟）
  - 开机自启（勾选状态直接读系统启动项）
  - 查看详情
  - 退出

## 耳机未连接时的处理

不会显示上一次的旧电量，而是明确区分三种状态：

| 情况 | 图标 | 菜单/详情 |
|---|---|---|
| 耳机没开机/没连 Windows | `?` | **未连接**：请确认 XM4 已开机，并在 Windows 蓝牙设置里连接 |
| 已配对但当前没有连接 | `?` | **未连接**：耳机已配对，但未连接 |
| 已连接但 HFP 还没上报电量 | `?` | **未上报**：稍等几秒或断开重连 |

鼠标休眠时是例外：会保留上一次成功读数，并标注「上次读数 · 设备休眠」，
因为鼠标动一下就能恢复；耳机断连则一律不保留旧值。

## 协议摘要

### 罗技 HID++ 2.0

- 接收器 `046D:C547` 的厂商接口：Usage Page `0xFF00`
  - usage `0x0002`：输入/输出 20 字节，Report ID `0x11`（长报文）
  - usage `0x0001`：输入/输出 7 字节，Report ID `0x10`（短报文）
- 设备索引：鼠标在 **1**（`0xFF` 是接收器本身）。
- 请求：`[0x11, 设备索引, 特性索引, (功能<<4)|0x01, 参数...]`
- 统一电池 `0x1004`：
  - 功能 0 = 能力（byte0 档位位图，byte1 bit1 = 支持百分比）
  - 功能 1 = 状态：`[百分比, 档位(1/2/4/8), 充电状态(0~7), 外部供电]`
  - 示例：`11 01 06 11 43 08 00 00` → 67%、档位 8、放电中
- 旧版 `0x1000`：`[电量, 下一档, 状态]`
- 电压 `0x1001`：大端 16 位 mV + 标志位

### WH-1000XM4

Windows 收到耳机通过 HFP 上报的电量后，会写到 **Hands-Free AG** 节点上的
未公开 PnP 属性：

```
{104EA319-6EE2-4701-BD47-8DDBF425BBE5}, 2   (DEVPROP_TYPE_BYTE)
```

所以要在 `BTHENUM\...{0000111E-...}` 的 Hands-Free 节点上找，而不是主设备节点。
耳机没连上/没上报时属性为 0 或不存在。

## 打包成安装 exe

构建过程只用两个工具：

- **PyInstaller**：把托盘程序打成单文件 `MyGearBatteryTray.exe`（无控制台）
- **Inno Setup**：把 exe 打成安装包（开始菜单/桌面快捷方式、卸载器、可选开机自启）

```powershell
# 在项目目录执行
.\build.ps1
```

输出：

```
dist\MyGearBatteryTray.exe
dist\MyGearBatteryTray-Setup-1.0.0.exe
```

安装包默认装到当前用户目录，不需要管理员权限：

```
%LOCALAPPDATA%\Programs\MyGearBatteryTray\
```

安装/卸载时会调用程序自己的 `--quit` 和 `--autostart off`，退出托盘并清理启动项。
配置 `my_gear_config.json` 保存在安装目录，卸载时一并删除。

## 文件

| 文件 | 说明 |
|---|---|
| `logi_hidpp.py` | 罗技 HID++ 2.0 最小客户端（长/短报文、设备索引、设备名、电量） |
| `my_gear.py` | 鼠标 + 耳机读取层 + 命令行（`--once` / `--diagnose` / `--autostart`） |
| `my_gear_tray.py` | 托盘：2 个数字图标 + 原生右键菜单 + `SetTimer` 刷新 |
| `my_gear_common.py` | 配置、开机自启、单实例/进程间消息、冻结 exe 路径适配 |
| `installer.iss` | Inno Setup 安装包脚本 |
| `build.ps1` | 一键构建 exe + 安装包 |
| `build_assets.py` | 生成安装包图标 |
| `my_gear_config.json` | 运行时配置（刷新间隔 / 自启意愿），已加入 `.gitignore` |

## 已知限制

1. **鼠标休眠时读不到**：Lightspeed 接收器在鼠标深度休眠后不转发 HID++ 请求。
   工具保留上一次成功读数并标注「上次读数」；动一下鼠标再左键刷新即可恢复。
2. **耳机电量是 HFP 上报值**：刚连接时可能还是旧值，等耳机自己上报后更新；
   断开后不显示旧值。
3. **不写日志**：默认不产生任何日志文件；需要排查时用 `--debug`。

## 隐私

- **不联网**：没有任何 http / socket / urllib / 遥测调用，所有读取都在本地完成。
- **不写日志**：默认不产生日志文件；只有 `--debug` 时才往控制台打印。
- **不上传**：设备序列号、地址等信息只在内存里用，不落盘。
