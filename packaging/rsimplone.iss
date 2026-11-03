; SPDX-License-Identifier: AGPL-3.0-or-later
; Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
; Inno Setup script: per-user install (no admin rights), Start menu entry, optional desktop icon, and a real
; uninstaller that asks whether to also delete your jobs, logs and settings (default: keep them).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B1F6C0E-5A3D-4E57-9D7A-2F0C8B7E41A9}
AppName=rSimpLone
AppVersion={#AppVersion}
AppPublisher=blessedevil | Mehedi Maruf
AppPublisherURL=https://mehedimaruf.com
DefaultDirName={autopf}\rSimpLone
DefaultGroupName=rSimpLone
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=rSimpLone-{#AppVersion}-windows-x64-setup
SetupIconFile=..\rsg\ui\brand\rsimplone.ico
UninstallDisplayIcon={app}\rSimpLone.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\rSimpLone.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\rSimpLone"; Filename: "{app}\rSimpLone.exe"
Name: "{group}\Uninstall rSimpLone"; Filename: "{uninstallexe}"
Name: "{autodesktop}\rSimpLone"; Filename: "{app}\rSimpLone.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\rSimpLone.exe"; Description: "Start rSimpLone"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Data := ExpandConstant('{userappdata}\rSimpLone');
    if DirExists(Data) then
      if MsgBox('Also delete your rSimpLone jobs, logs and settings?' + #13#10 + #13#10 + Data + #13#10 + #13#10 +
                'Choose No to keep them for a later reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Data, True, True, True);
  end;
end;
