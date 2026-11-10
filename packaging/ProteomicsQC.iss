#ifndef PortableDir
  #define PortableDir "..\dist\ProteomicsQC_0.4.0"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\dist"
#endif

[Setup]
AppId={{CC02B685-1FC6-4E47-9E6F-04CF7FCD388D}
AppName=ProteomicsQC
AppVersion=0.4.0
AppPublisher=ProteomicsQC GUI
DefaultDirName={localappdata}\Programs\ProteomicsQC
DefaultGroupName=ProteomicsQC
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=ProteomicsQC_Setup_0.4.0
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\proteomicsqc\assets\logo.ico
UninstallDisplayIcon={app}\ProteomicsQC.exe
SetupLogging=yes

[Files]
Source: "{#PortableDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Icons]
Name: "{group}\ProteomicsQC"; Filename: "{app}\ProteomicsQC.exe"
Name: "{autodesktop}\ProteomicsQC"; Filename: "{app}\ProteomicsQC.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ProteomicsQC.exe"; Description: "Open ProteomicsQC"; Flags: nowait postinstall skipifsilent unchecked
