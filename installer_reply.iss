; 微信自动回复助手 Inno Setup 安装脚本
; 生成独立安装包，支持隐私协议、安装目录选择、桌面快捷方式勾选

#define MyAppName "微信自动回复助手"
#define MyAppVersion "1.0.0"
#define MyAppExeName "微信自动回复助手.exe"
#define MyAppDir "微信自动回复助手"

[Setup]
; 应用信息（AppId 与 UIA 版本不同，避免冲突）
AppId={{C9E4F8B3-5D6E-7F9A-0B1C-2D3E4F5A6B7C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=wxAutoTool
AppPublisherURL=https://github.com/Be-nothing/wxAutoTool
AppSupportURL=https://github.com/Be-nothing/wxAutoTool
VersionInfoVersion=1.0.0.0

; 安装目录（默认 Program Files）
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 强制每次安装都显示目录选择页（不复用上次安装目录，避免升级时跳过目录选择）
UsePreviousAppDir=no

; 输出配置
OutputDir=product
OutputBaseFilename=微信自动回复助手_Setup_v{#MyAppVersion}
; 压缩参数：体积最小 = 安装最快（LZMA 解压速度与压缩级别无关，只看体积）
; 实测 ultra64+solid 体积最小（16.64MB），解压数据量最少，安装最快
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; 隐私协议页面（用户必须接受才能继续安装）
LicenseFile=privacy.txt

; 卸载配置
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

; 界面配置
WizardStyle=modern
ShowLanguageDialog=no

[Languages]
; 中文简体界面（Inno Setup 6 官方自带 ChineseSimplified.isl）
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
; 桌面快捷方式勾选（默认勾选）
Name: "desktopicon"; Description: "在桌面创建快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
; 打包微信自动回复助手完整目录（dist\微信自动回复助手\）
Source: "dist\微信自动回复助手\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单快捷方式
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

; 桌面快捷方式（仅当用户勾选时创建）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 安装完成后可选启动程序
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时清理程序目录（不清理用户数据目录 %LOCALAPPDATA%）
Type: filesandordirs; Name: "{app}"
