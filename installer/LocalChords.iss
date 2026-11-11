; LocalChords-Setup-v<version>.exe: the dist\LocalChords folder, installed for the current user,
; without administrator rights. docs/INSTALLATEUR.md says what it does and never does.
; Build: ISCC /DAppVersion=1.5 installer\LocalChords.iss   (Inno Setup 6, https://jrsoftware.org)

#ifndef AppVersion
  #define AppVersion "dev"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\LocalChords"
#endif
#ifndef OutputDir
  #define OutputDir "..\out"
#endif

[Setup]
; Never change the AppId: it is what makes a new version update the installed one.
AppId={{C21679FE-1659-4CB0-872C-E0A24C7766C0}
AppName=LocalChords
AppVersion={#AppVersion}
AppVerName=LocalChords {#AppVersion}
AppPublisher=LocalChords
AppPublisherURL=https://github.com/tadikwa/LocalChords
AppSupportURL=https://github.com/tadikwa/LocalChords/issues
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\LocalChords
DisableProgramGroupPage=yes
; The welcome page says the user's projects are never touched.
DisableWelcomePage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
SetupIconFile=..\assets\localchords.ico
UninstallDisplayIcon={app}\LocalChords.exe
UninstallDisplayName=LocalChords
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no
Compression=lzma2/max
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename=LocalChords-Setup-v{#AppVersion}
; Windows' display language when the installer has it, else a choice that starts on English
; (docs/LOCALISATION.md). The updater passes /LANG= in the program's own language.
ShowLanguageDialog=auto
UsePreviousLanguage=no

[Languages]
; The first one is the fallback for a Windows in another language.
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
english.WelcomeLabel2=This wizard will install [name/ver] on your computer, for your account only, without administrator rights.%n%nYour projects, your library and your backups (AppData\Local\LocalChords) are never changed or deleted by installing, updating or uninstalling.
french.WelcomeLabel2=Cet assistant va installer [name/ver] sur votre ordinateur, pour votre compte uniquement, sans droits d'administrateur.%n%nVos projets, votre bibliothèque et vos sauvegardes (AppData\Local\LocalChords) ne sont jamais modifiés ni supprimés par l'installation, la mise à jour ou la désinstallation.

[CustomMessages]
english.Association=Open .lchords projects with LocalChords
french.Association=Ouvrir les projets .lchords avec LocalChords
english.FilesGroup=Files:
french.FilesGroup=Fichiers :
english.ProjectType=LocalChords project
french.ProjectType=Projet LocalChords
english.DataFolder=This folder contains your LocalChords projects (%1).%nChoose another folder for the program.
french.DataFolder=Ce dossier contient vos projets LocalChords (%1).%nChoisissez un autre dossier pour le programme.
english.PortableFolder=This folder contains a portable LocalChords (LocalChords.portable file).%nChoose another folder: the installed version keeps its data in %1.
french.PortableFolder=Ce dossier contient un LocalChords portable (fichier LocalChords.portable).%nChoisissez un autre dossier : la version installée garde ses données dans %1.
english.Uninstalled=LocalChords has been uninstalled.%n%nYour projects, your library and your backups are kept in:%n%1%n%nIf you no longer need them, delete this folder yourself.
french.Uninstalled=LocalChords est désinstallé.%n%nVos projets, votre bibliothèque et vos sauvegardes sont conservés dans :%n%1%n%nSi vous n'en avez plus besoin, supprimez ce dossier vous-même.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "association"; Description: "{cm:Association}"; GroupDescription: "{cm:FilesGroup}"

[Files]
; The folder build as the zip carries it, licences included. Never the portable marker: the
; installed program keeps its data in %LOCALAPPDATA%\LocalChords.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "LocalChords.portable,\Data"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\LocalChords"; Filename: "{app}\LocalChords.exe"
Name: "{autodesktop}\LocalChords"; Filename: "{app}\LocalChords.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.lchords"; ValueType: string; ValueName: ""; ValueData: "LocalChords.Project"; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: association
Root: HKA; Subkey: "Software\Classes\.lchords\OpenWithProgids"; ValueType: string; ValueName: "LocalChords.Project"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: association
Root: HKA; Subkey: "Software\Classes\LocalChords.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:ProjectType}"; Flags: uninsdeletekey; Tasks: association
Root: HKA; Subkey: "Software\Classes\LocalChords.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\LocalChords.exe,0"; Tasks: association
Root: HKA; Subkey: "Software\Classes\LocalChords.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\LocalChords.exe"" ""%1"""; Tasks: association

[Run]
Filename: "{app}\LocalChords.exe"; Description: "{cm:LaunchProgram,LocalChords}"; Flags: nowait postinstall skipifsilent

[Code]
function DataDir: String;
begin
  Result := ExpandConstant('{localappdata}\LocalChords');
end;

{ Dir is Parent, or inside it. }
function Within(const Dir, Parent: String): Boolean;
var
  D, P: String;
begin
  D := AddBackslash(Lowercase(ExpandFileName(Dir)));
  P := AddBackslash(Lowercase(ExpandFileName(Parent)));
  Result := Copy(D, 1, Length(P)) = P;
end;

{ Why the program must not go in Dir, or ''. }
function Refusal(const Dir: String): String;
begin
  Result := '';
  if Within(Dir, DataDir) or Within(DataDir, Dir) then
    Result := FmtMessage(CustomMessage('DataFolder'), [DataDir])
  else if FileExists(AddBackslash(Dir) + 'LocalChords.portable') then
    Result := FmtMessage(CustomMessage('PortableFolder'), [DataDir]);
end;

{ In the wizard, the folder page says it and stays open. }
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Why: String;
begin
  Result := True;
  if (CurPageID <> wpSelectDir) or WizardSilent then
    Exit;
  Why := Refusal(WizardDirValue);
  if Why <> '' then
  begin
    MsgBox(Why, mbError, MB_OK);
    Result := False;
  end;
end;

{ Silent (/DIR=...), Setup stops before copying anything. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := Refusal(ExpandConstant('{app}'));
end;

{ An update replaces the program's own folder whole, so no file of the old version lingers. Only
  where LocalChords was installed: the folder holds LocalChords.exe. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Dir: String;
begin
  Dir := ExpandConstant('{app}');
  if (CurStep = ssInstall) and FileExists(Dir + '\LocalChords.exe') and DirExists(Dir + '\_internal') then
    DelTree(Dir + '\_internal', True, True, True);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent and DirExists(DataDir) then
    MsgBox(FmtMessage(CustomMessage('Uninstalled'), [DataDir]), mbInformation, MB_OK);
end;
