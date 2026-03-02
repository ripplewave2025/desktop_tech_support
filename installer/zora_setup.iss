; ─────────────────────────────────────────────────────────────
; Zora AI Desktop Companion — Inno Setup Installer Script
; Produces a professional Windows installer with:
;   - Program Files installation
;   - Start Menu + Desktop shortcuts
;   - Add/Remove Programs entry + uninstaller
;   - Optional Ollama auto-install during setup
;   - Optional Windows startup entry
;   - Localhost firewall exception for port 8000
; ─────────────────────────────────────────────────────────────

#define MyAppName "Zora"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Zora Project"
#define MyAppURL "https://github.com/zora-desktop"
#define MyAppExeName "Zora.exe"
#define MyAppDescription "AI Desktop Companion — your personal tech support"

[Setup]
; Basic info
AppId={{A7E3F5B2-9C14-4D8E-B1A6-3F5D7E2C9A84}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Install location
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output
OutputDir=output
OutputBaseFilename=ZoraSetup-{#MyAppVersion}
SetupIconFile=..\assets\zora_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes

; Appearance
WizardStyle=modern
WizardSizePercent=110

; Privileges
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Misc
AllowNoIcons=yes
LicenseFile=..\LICENSE
ChangesEnvironment=yes

; Minimum Windows version (Windows 10 1809+)
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startupentry"; Description: "Start Zora when Windows starts (system tray)"; GroupDescription: "Startup:"; Flags: unchecked
Name: "installollama"; Description: "Download and install Ollama (AI engine, ~150MB)"; GroupDescription: "AI Engine:"; Flags: checkedonce

[Files]
; Main executable (built by PyInstaller)
Source: "..\dist\Zora.exe"; DestDir: "{app}"; Flags: ignoreversion

; Config
Source: "..\config.json"; DestDir: "{app}"; Flags: ignoreversion

; Assets (icon, etc.)
Source: "..\assets\zora_icon.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Diagnostic flows (YAML)
Source: "..\diagnostics\flows\*.yaml"; DestDir: "{app}\diagnostics\flows"; Flags: ignoreversion

; React UI (pre-built)
Source: "..\ui\dist\*"; DestDir: "{app}\ui\dist"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppDescription}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop (optional)
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "{#MyAppDescription}"

[Registry]
; Startup entry (optional)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Zora"; ValueData: """{app}\{#MyAppExeName}"" --tray"; Flags: uninsdeletevalue; Tasks: startupentry

; App settings
Root: HKCU; Subkey: "Software\Zora"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Zora"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

[Run]
; Post-install: add firewall rule for localhost:8000
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""Zora AI Companion"" dir=in action=allow protocol=TCP localport=8000 remoteip=127.0.0.1 program=""{app}\{#MyAppExeName}"""; Flags: runhidden; StatusMsg: "Adding firewall exception..."

; Post-install: optionally install Ollama
Filename: "{tmp}\OllamaSetup.exe"; StatusMsg: "Installing Ollama AI Engine..."; Flags: nowait skipifnotexists; Tasks: installollama

; Launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove firewall rule on uninstall
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""Zora AI Companion"""; Flags: runhidden

[UninstallDelete]
; Clean up local data
Type: filesandordirs; Name: "{localappdata}\Zora"

[Code]
// ── Custom Ollama download during install ──
var
  OllamaDownloadPage: TOutputProgressWizardPage;

procedure DownloadOllama();
var
  ResultCode: Integer;
begin
  if not IsTaskSelected('installollama') then
    Exit;

  OllamaDownloadPage := CreateOutputProgressPage(
    'Installing Ollama',
    'Downloading the AI engine that powers Zora...'
  );
  OllamaDownloadPage.SetProgress(0, 100);
  OllamaDownloadPage.Show;

  try
    OllamaDownloadPage.SetText('Downloading Ollama installer...', '');
    OllamaDownloadPage.SetProgress(20, 100);

    // Use PowerShell to download (more reliable than WinHTTP for large files)
    Exec(
      'powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -Command "' +
        '[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ' +
        'Invoke-WebRequest -Uri ''https://ollama.com/download/OllamaSetup.exe'' ' +
        '-OutFile ''' + ExpandConstant('{tmp}\OllamaSetup.exe') + ''' -UseBasicParsing"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode
    );

    OllamaDownloadPage.SetProgress(80, 100);

    if FileExists(ExpandConstant('{tmp}\OllamaSetup.exe')) then
    begin
      OllamaDownloadPage.SetText('Ollama downloaded successfully!', '');
      OllamaDownloadPage.SetProgress(100, 100);
    end
    else
    begin
      OllamaDownloadPage.SetText('Download failed. You can install Ollama manually from ollama.com', '');
      OllamaDownloadPage.SetProgress(100, 100);
    end;
  finally
    OllamaDownloadPage.Hide;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    // Download Ollama before file installation
    DownloadOllama();
  end;
end;

// ── Check if Ollama is already installed ──
function IsOllamaInstalled(): Boolean;
var
  OllamaPath: String;
begin
  Result := False;
  OllamaPath := ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe');
  if FileExists(OllamaPath) then
    Result := True;

  // Also check PATH
  if not Result then
  begin
    if FileSearch('ollama.exe', GetEnv('PATH')) <> '' then
      Result := True;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard();
begin
  // If Ollama is already installed, uncheck the install task
  if IsOllamaInstalled() then
  begin
    WizardForm.TasksList.Checked[2] := False;
    WizardForm.TasksList.ItemCaption[2] :=
      'Ollama is already installed (uncheck to skip)';
  end;
end;

// ── Show installed components at end ──
procedure CurPageChanged(CurPageID: Integer);
var
  Msg: String;
begin
  if CurPageID = wpFinished then
  begin
    Msg := 'Zora has been installed successfully!' + #13#10#13#10;
    Msg := Msg + 'What''s included:' + #13#10;
    Msg := Msg + '  - 30+ diagnostic checks across 8 categories' + #13#10;
    Msg := Msg + '  - 52 automated Windows fixes' + #13#10;
    Msg := Msg + '  - 5 flow-based diagnostic trees' + #13#10;
    Msg := Msg + '  - Proactive system monitoring' + #13#10;
    Msg := Msg + '  - AI-powered troubleshooting chat' + #13#10;
    Msg := Msg + #13#10 + 'Zora runs at http://localhost:8000';

    WizardForm.FinishedLabel.Caption := Msg;
  end;
end;

// FileExists is built-in to Inno Setup Pascal Script — no need to redefine
