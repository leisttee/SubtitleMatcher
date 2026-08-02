#define MyAppName "SubtitleMatcher"
#define MyAppVersion "2.2.0"
#define MyAppPublisher "Teemu Leisto"
#define MyAppExeName "SubtitleMatcher.exe"

[Setup]
AppId={{B19E58D7-8C5B-4E44-B063-1268D668E9F3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=SubtitleMatcher_Setup_v{#MyAppVersion}
SetupIconFile=resources\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\SubtitleMatcher.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SubtitleMatcher"; Filename: "{app}\SubtitleMatcher.exe"
Name: "{autodesktop}\SubtitleMatcher"; Filename: "{app}\SubtitleMatcher.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SubtitleMatcher.exe"; Description: "Launch SubtitleMatcher"; Flags: nowait postinstall skipifsilent