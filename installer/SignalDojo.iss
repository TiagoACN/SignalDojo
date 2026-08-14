; SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
; SPDX-License-Identifier: GPL-3.0-or-later

#define MyAppName "SignalDojo"
#define MyAppVersion "1.2.6"
#define MyAppPublisher "Tiago Alvarez Calderon Newton / SignalDojo Open Source Project"
#define MyAppExeName "SignalDojo.exe"

[Setup]
AppId={{78A1BDA8-7F32-4BDF-87F8-90E796891F9A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://signaldojo.org
AppSupportURL=https://signaldojo.org
AppUpdatesURL=https://signaldojo.org
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=SignalDojo-{#MyAppVersion}-win64-setup
SetupIconFile=..\resources\signaldojo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; GPL acceptance is not required merely to receive or run the program.
; Present an informational open-source notice instead of a conventional EULA page.
InfoBeforeFile=OPEN_SOURCE_NOTICE.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=SignalDojo Open Source Installer
VersionInfoCopyright=Copyright (C) 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\dist\SignalDojo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.sdojo"; ValueType: string; ValueName: ""; ValueData: "SignalDojo.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\SignalDojo.Project"; ValueType: string; ValueName: ""; ValueData: "SignalDojo Project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SignalDojo.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\SignalDojo.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
