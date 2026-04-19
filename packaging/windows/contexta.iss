#define MyAppName "Contexta"
#define MyAppVersion "1.6.0"
#define MyAppPublisher "Contexta"
#define MyAppExeName "contexta.exe"
#define MyRepoRoot "..\.."

[Setup]
AppId={{D5F68778-9F6C-4B8D-BE32-379D62B64B63}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Contexta
DefaultGroupName=Contexta
OutputDir={#MyRepoRoot}\dist
OutputBaseFilename=contexta-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#MyRepoRoot}\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:";

[Files]
Source: "{#MyRepoRoot}\dist\contexta.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyRepoRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyRepoRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Contexta"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Contexta"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Contexta"; Flags: nowait postinstall skipifsilent
