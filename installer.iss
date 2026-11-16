; Inno Setup 6 script — 外设电量托盘（鼠标 + 耳机）
; 构建：先运行 build.ps1（会生成 dist\MyGearBatteryTray.exe）

#ifndef MyAppVersion
  #define MyAppVersion "1.1.1"
#endif

#define MyAppName "外设电量托盘"
#define MyAppExeName "MyGearBatteryTray.exe"

[Setup]
AppId={{A3F1C2D4-5E6B-4F7A-9C8D-1E2F3A4B5C6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Personal
DefaultDirName={localappdata}\Programs\MyGearBatteryTray
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0
OutputDir=dist
OutputBaseFilename=MyGearBatteryTray-Setup-{#MyAppVersion}
SetupIconFile=build\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
VersionInfoVersion={#MyAppVersion}.0
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "chinesesimp"; MessagesFile: "packaging\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "dist\MyGearBatteryTray.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\退出{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--quit"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--quit"; Flags: runhidden waituntilterminated; RunOnceId: "QuitTray"
Filename: "{app}\{#MyAppExeName}"; Parameters: "--autostart off"; Flags: runhidden waituntilterminated; RunOnceId: "DisableAutostart"

[UninstallDelete]
Type: files; Name: "{app}\my_gear_config.json"
Type: files; Name: "{userstartup}\{#MyAppName}.lnk"
