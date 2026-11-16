param(
    [string]$UpdateUrl = "",
    [string]$Python = "py"
)
# 一键构建外设电量托盘 exe + 安装包 + update.json
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pyArgs = @()
if ($Python -eq 'py') { $pyArgs = @('-3.10') }

Write-Host '== 1/4 安装/检查 PyInstaller =='
& $Python @pyArgs -m pip install --upgrade pyinstaller | Out-Host

$ver = (& $Python @pyArgs -c "import version; print(version.APP_VERSION)").Trim()
if (-not $ver) { throw '无法从 version.py 读取版本号' }
Write-Host "版本：$ver"

Write-Host '== 2/4 生成图标并打包单文件 exe =='
& $Python @pyArgs build_assets.py
$icon = (Resolve-Path 'build\app.ico').Path
$verFile = (Resolve-Path 'packaging\version_info.txt').Path
& $Python @pyArgs -m PyInstaller --noconfirm --clean --onefile --noconsole `
    --name MyGearBatteryTray `
    --icon $icon `
    --version-file $verFile `
    --workpath build\pyinstaller `
    --specpath build `
    my_gear_tray.py

if (-not (Test-Path 'dist\MyGearBatteryTray.exe')) {
    throw 'PyInstaller 没有生成 dist\MyGearBatteryTray.exe'
}

Write-Host '== 3/4 生成安装包 =='
$iscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) { $iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' }
if (-not (Test-Path $iscc)) { $iscc = 'C:\Program Files\Inno Setup 6\ISCC.exe' }
if (-not (Test-Path $iscc)) {
    throw '找不到 Inno Setup 的 ISCC.exe，请先安装 Inno Setup 6'
}
& $iscc "/DMyAppVersion=$ver" installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup 编译失败' }
$setup = "dist\MyGearBatteryTray-Setup-$ver.exe"
if (-not (Test-Path $setup)) { throw "没有生成 $setup" }

Write-Host '== 4/4 生成 update.json =='
$repo = (& $Python @pyArgs -c "import version; print(version.GITHUB_REPO)").Trim()
if (-not $UpdateUrl) {
    $UpdateUrl = "https://github.com/$repo/releases/download/v$ver/MyGearBatteryTray-Setup-$ver.exe"
}
& $Python @pyArgs packaging\make_update_manifest.py `
    --installer $setup `
    --url $UpdateUrl `
    --version $ver `
    --notes "外设电量 v$ver" `
    --output "dist\update.json"

Write-Host ''
Write-Host '完成：'
Write-Host "  dist\MyGearBatteryTray.exe"
Write-Host "  $setup"
Write-Host '  dist\update.json'
Write-Host "  update 源：https://github.com/$repo/releases/latest/download/update.json"
