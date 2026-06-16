[Setup]
AppName=Relay
AppVersion=1.0
; MUDANÇA CRÍTICA: Instalar em LocalAppData para ter permissão de escrita/deleção (Logout e Save)
DefaultDirName={localappdata}\Relay
DefaultGroupName=Relay
; Define onde o instalador final será salvo (caminho relativo à pasta do projeto)
OutputDir=.\Build_Final
OutputBaseFilename=Relay_Installer
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
; Ícones da instalação (caminhos relativos)
SetupIconFile=.\src\relay_ico.ico
UninstallDisplayIcon={app}\relay_ico.ico

[Dirs]
; Garante que as pastas vitais são criadas mesmo que estejam vazias
Name: "{app}\config"
Name: "{app}\ambiente_teste"
Name: "{app}\dependencias\versoes"

[Files]
; Copia o executável principal gerado pelo PyInstaller
Source: ".\Relay.exe"; DestDir: "{app}"; Flags: ignoreversion
; Ícones
Source: ".\src\relay_ico.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: ".\src\relay_ico.png"; DestDir: "{app}"; Flags: ignoreversion

; BLINDAGEM: Copia a pasta config, mas exclui credenciais locais e sessões ativas!
Source: ".\config\*"; DestDir: "{app}\config"; Excludes: "session.json, rclone*.conf, .env"; Flags: ignoreversion recursesubdirs createallsubdirs

; Copia as dependências externas (Tailscale, Motores, etc)
Source: ".\dependencias\*"; DestDir: "{app}\dependencias"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Relay"; Filename: "{app}\Relay.exe"; IconFilename: "{app}\relay_ico.ico"
Name: "{group}\Relay"; Filename: "{app}\Relay.exe"; IconFilename: "{app}\relay_ico.ico"

[Run]
; Instala o Tailscale de forma silenciosa
Filename: "{app}\dependencias\Tailscale-Setup.exe"; Parameters: "/quiet"; StatusMsg: "Configurando rede Mesh P2P..."; Flags: waituntilterminated
; Abre o Relay ao final da instalação
Filename: "{app}\Relay.exe"; Description: "Abrir o Relay"; Flags: nowait postinstall skipifsilent
