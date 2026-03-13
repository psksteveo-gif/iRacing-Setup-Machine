; Inno Setup Script for iRacing Setup Advisor
; Download Inno Setup 6 from: https://jrsoftware.org/isinfo.php
; Then run: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss

[Setup]
AppId={{B2F4C8E1-7A3D-4E5F-9B1C-6D8E2F0A3B5C}
AppName=iRacing Setup Advisor
AppVersion=2.1.0
AppPublisher=iRacing Setup Machine
AppCopyright=Copyright (c) 2024-2026 iRacing Setup Machine
DefaultDirName={autopf}\iRacing Setup Advisor
DefaultGroupName=iRacing Setup Advisor
OutputDir=dist
OutputBaseFilename=iRacingSetupAdvisor_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
LicenseFile=LICENSE
UninstallDisplayIcon={app}\iRacingSetupAdvisor.exe
SetupIconFile=app.ico
ChangesAssociations=yes
VersionInfoVersion=2.1.0.0
VersionInfoProductName=iRacing Setup Advisor

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startmenuicon"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "associbt"; Description: "Associate .ibt files with iRacing Setup Advisor"; GroupDescription: "File associations:"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Classes\.ibt"; ValueType: string; ValueName: ""; ValueData: "iRacingSetupAdvisor.ibt"; Flags: uninsdeletevalue; Tasks: associbt
Root: HKCU; Subkey: "Software\Classes\iRacingSetupAdvisor.ibt"; ValueType: string; ValueName: ""; ValueData: "iRacing Telemetry File"; Flags: uninsdeletekey; Tasks: associbt
Root: HKCU; Subkey: "Software\Classes\iRacingSetupAdvisor.ibt\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\iRacingSetupAdvisor.exe"" ""%1"""; Tasks: associbt

[Files]
; Include the entire PyInstaller output folder
Source: "dist\iRacingSetupAdvisor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\iRacing Setup Advisor"; Filename: "{app}\iRacingSetupAdvisor.exe"
Name: "{group}\Uninstall iRacing Setup Advisor"; Filename: "{uninstallexe}"
Name: "{autodesktop}\iRacing Setup Advisor"; Filename: "{app}\iRacingSetupAdvisor.exe"; Tasks: desktopicon

[UninstallDelete]
Type: filesandirs; Name: "{userappdata}\iRacing Setup Advisor"
Type: filesandirs; Name: "{userprofile}\.iracing_setup_advisor_logs"
Type: files; Name: "{userprofile}\.iracing_setup_advisor.json"
Type: files; Name: "{userprofile}\.iracing_setup_history.json"

[Run]
Filename: "{app}\iRacingSetupAdvisor.exe"; Description: "Launch iRacing Setup Advisor"; Flags: nowait postinstall skipifsilent
