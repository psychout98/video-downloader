; Media Downloader - Inno Setup Script
; Installs the WPF app (with in-process Kestrel server) and sets up the environment.

#define MyAppName "Media Downloader"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Media Downloader"
#define MyAppExeName "MediaDownloader.exe"

[Setup]
AppId={{B8E2F4A1-3C5D-4E6F-8A9B-0C1D2E3F4A5B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=MediaDownloader-Setup
SetupIconFile=assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupentry"; Description: "Start on Windows login"; GroupDescription: "System integration:"

[Files]
; WPF Application
Source: "..\build\publish\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Static web assets (frontend)
Source: "..\server\static\*"; DestDir: "{app}\server\static"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\logs"
Name: "{app}\data"
Name: "{app}\data\posters"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Startup entry (only if task selected)
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MediaDownloader"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupentry

[Run]
; Add firewall rule
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""MediaDownloader"" dir=in action=allow protocol=TCP localport=8000"; StatusMsg: "Adding firewall rule..."; Flags: runhidden waituntilterminated

; Launch app after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove firewall rule
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""MediaDownloader"""; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: files; Name: "{app}\.env"
Type: files; Name: "{app}\.version"
Type: files; Name: "{app}\media_downloader.db"
