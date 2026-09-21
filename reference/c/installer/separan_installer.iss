; Separan native installer
#define MyAppName "Separan Native Core"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Separan"
#define MyAppExeName "separan.exe"

[Setup]
AppId={{EDAFDCD7-2243-4A5F-BC98-09B0F66F2A32}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Separan
DefaultGroupName=Separan
OutputDir=..\dist
OutputBaseFilename=separan-installer
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64

[Files]
Source: "..\separan.exe"; DestDir: "{app}"
Source: "..\separan.cmd"; DestDir: "{app}"

[Icons]
Name: "{group}\Separan"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Separan Help"; Filename: "{app}\{#MyAppExeName}"; Parameters: "-help"

[Environment]
Name: "PATH"; Value: "{app}"; Flags: userenvironpath

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "-help"; Description: "Show Separan help"; Flags: postinstall skipifdoesntexist
