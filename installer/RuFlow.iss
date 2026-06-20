#define AppName "RuFlow"
#define AppVersion "0.1.0"
#define AppPublisher "RuFlow"

[Setup]
AppId={{2F825D7E-5E13-47B1-9F75-508C37903039}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\RuFlow
DefaultGroupName=RuFlow
DisableProgramGroupPage=yes
OutputDir=..\dist\windows
OutputBaseFilename=RuFlowSetup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\RuFlow.exe
SetupIconFile=assets\ruflow.ico
WizardImageFile=assets\wizard-side.bmp
WizardSmallImageFile=assets\wizard-small.bmp
SetupLogging=yes
CloseApplications=force
CloseApplicationsFilter=RuFlow.exe
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "..\dist\windows\RuFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\RuFlow"; Filename: "{app}\RuFlow.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\Настройки RuFlow"; Filename: "{app}\RuFlow.exe"; Parameters: "--settings"; WorkingDir: "{app}"
Name: "{autodesktop}\RuFlow"; Filename: "{app}\RuFlow.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\RuFlow.exe"; Parameters: "--first-run"; Description: "Открыть настройку RuFlow"; Flags: nowait postinstall skipifsilent

[Messages]
FinishedHeadingLabel=Установка RuFlow завершена
FinishedLabelNoIcons=RuFlow установлен. Локальная модель распознавания уже включена в установщик.
FinishedLabel=RuFlow установлен. Локальная модель распознавания уже включена в установщик. Ярлыки созданы в меню «Пуск» и на рабочем столе.

[CustomMessages]
BundledModelInfo=Локальная модель распознавания уже включена в установщик. Интернет после установки не требуется.
