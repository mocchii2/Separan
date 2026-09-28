; Separan native installer
#define MyAppName "Separan Core"
#define MyAppVersion "1.1.1"
#define MyAppPublisher "Separan"
#define MyAppExeName "separan.exe"

[Setup]
AppId={{EDAFDCD7-2243-4A5F-BC98-09B0F66F2A32}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Separan
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
Source: "..\..\..\README.md"; DestDir: "{app}"
Source: "..\..\..\docs\README.ja.md"; DestDir: "{app}\docs"
Source: "..\..\..\docs\philosophy.md"; DestDir: "{app}\docs"
Source: "..\..\..\docs\philosophy.ja.md"; DestDir: "{app}\docs"
Source: "..\..\..\docs\ai-integration.md"; DestDir: "{app}\docs"
Source: "..\..\..\docs\ai-integration.ja.md"; DestDir: "{app}\docs"
Source: "..\..\..\spec\*"; DestDir: "{app}\spec"; Flags: recursesubdirs createallsubdirs

[Environment]
Name: "PATH"; Value: "{app}"; Flags: userenvironpath
