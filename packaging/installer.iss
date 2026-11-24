; Mybalcony 安装包脚本（Inno Setup 6 + ISPP）
; 编译：ISCC.exe packaging\installer.iss
; 前置：先跑 PyInstaller 生成 ..\dist\Mybalcony\（含 Mybalcony.exe）
;
; 安装向导页序：欢迎 → 许可 → 安装类型（完整/精简/自定义）→ 选择组件 → 选择目录 → 附加任务 → 安装 → 完成
; 「自定义安装」= 类型页选 custom 后，组件勾选与目录都可自己改；也可直接点「浏览」改目录。

#define AppName "Mybalcony"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppPublisher "Nide2003"
#define AppExe "Mybalcony.exe"
#define DistDir "..\dist\Mybalcony"

[Setup]
AppId={{C4B0A0B7-8C6A-4F2B-9C8E-2A1F6E0A3D55}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
UninstallDisplayName={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=yes
AllowNoIcons=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
OutputDir=..\dist\installer
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
CloseApplications=yes
RestartApplications=no
#if FileExists(AddBackslash(SourcePath) + "mybalcony.ico")
SetupIconFile=mybalcony.ico
#endif
; 侧边向导图需要竖版（Inno 6 会自动缩放，但横版 1000x510 会被裁成窄条）；
; 把竖版图命名为 wizard-side.png 放到 packaging\ 后取消下面两行注释即可。
; #if FileExists("wizard-side.png")
; WizardImageFile=wizard-side.png
; #endif
#if FileExists(AddBackslash(SourcePath) + "..\LICENSE")
LicenseFile=..\LICENSE
#endif

[Languages]
#if FileExists(AddBackslash(SourcePath) + "ChineseSimplified.isl")
Name: "chs"; MessagesFile: "ChineseSimplified.isl"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Types]
Name: "full"; Description: "完整安装（主程序 + 说明文档）"
Name: "compact"; Description: "精简安装（仅主程序）"
Name: "custom"; Description: "自定义安装"; Flags: iscustom

[Components]
Name: "main"; Description: "Mybalcony 主程序（必需）"; Types: full compact custom; Flags: fixed
Name: "docs"; Description: "说明文档与许可证"; Types: full

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："
Name: "autostart"; Description: "开机自动启动 {#AppName}"; GroupDescription: "附加任务："

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Components: docs; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Components: docs; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "mybalcony"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent

; 说明：config.json 与 data 属于用户数据，卸载时有意保留，不放进 [UninstallDelete]。
; 卸载只会移除程序目录中的安装文件、快捷方式和上面的自启注册表值。
