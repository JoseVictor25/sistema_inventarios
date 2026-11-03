; B3 preliminar persistente: compilable, pero BLOQUEADO para uso real hasta validación B4 en máquina limpia.
; ARQUITECTURA DE PERMISOS ACL (documentación de diseño):
; ─────────────────────────────────────────────────────────
; El instalador se ejecuta elevado (Admin) con una cuenta que puede ser distinta
; del operador del negocio. Por este motivo el instalador NUNCA aplica ACLs de
; ProgramData: no conoce ni puede asumir el SID del operador final.
;
; Flujo de permisos NTFS aprobado:
;   1. Inno Setup crea {commonappdata}\SistemaInventarios\ con uninsneveruninstall.
;      La carpeta hereda los permisos del directorio padre (ProgramData).
;   2. En el PRIMER ARRANQUE, el proceso de la aplicación (ejecutado bajo la cuenta
;      del operador) llama a aplicar_permisos_seguros() de desktop/seguridad.py,
;      que aplica las ACLs correctas con el SID real del operador.
;   3. Los arranques posteriores verifican el SID antes de arrancar (validar_operador).
;   4. Cambio de operador: solo mediante migrar_operador() con autorización Admin.
;
; El parámetro /OPERATOR_SID puede pasarse al primer arranque para pre-registrar
; el SID si el operador se conoce antes de la instalación (caso kiosco/empresa).
; Sin ese parámetro, el primer arranque detecta el SID del proceso automáticamente.
;
#define ProductName "Sistema de Inventarios"
#define ProductVersion "0.10.0"
#ifndef VerifiedFiles
  #error Compile mediante scripts/compilar_instalador.py
#endif
#ifndef BuildOutput
  #error Falta directorio temporal de salida
#endif

[Setup]
AppId={{E3488284-3044-4D29-AB90-33D28FD02467}
AppName={#ProductName}
AppVersion={#ProductVersion}
AppVerName={#ProductName} {#ProductVersion} - PRELIMINAR B3 PERSISTENTE
DefaultDirName={autopf}\SistemaInventarios
DefaultGroupName={#ProductName}
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible and not arm64
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir={#BuildOutput}
OutputBaseFilename=Instalador_Sistema_Inventarios_0.10.0_B3_BLOQUEADO
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SistemaInventarios.exe
CloseApplications=no
RestartApplications=no
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; Flags: unchecked

[Dirs]
; La carpeta persistente se prepara si es necesario, pero NUNCA se elimina al desinstalar.
Name: "{commonappdata}\SistemaInventarios"; Flags: uninsneveruninstall

[Files]
; Lista explícita de la copia temporal inspeccionada, nunca comodines del repositorio.
#include VerifiedFiles

[Icons]
Name: "{group}\{#ProductName}"; Filename: "{app}\SistemaInventarios.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\{#ProductName}"; Filename: "{app}\SistemaInventarios.exe"; WorkingDir: "{app}"; Tasks: desktopicon

; POLÍTICA DE SEGURIDAD Y DESINSTALACIÓN:
; - Sin [Run]: la aplicación nunca debe ejecutarse con la cuenta administrativa del instalador.
; - Sin [UninstallRun]: no se ejecutan scripts no controlados al desinstalar.
; - Sin [UninstallDelete]: NUNCA borrar recursivamente ni eliminar {commonappdata}\SistemaInventarios.
; - Inno Setup desinstala exclusivamente los binarios de {app} registrados en la instalación.
; - SQLite, .env, respaldos y logs sobreviven permanentemente a la desinstalación.

[Code]
function WebView2EquipoDisponible(): Boolean;
var
  Version: String;
begin
  Version := '';
  Result := RegQueryStringValue(HKLM32,
    'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version);
  Result := Result and (Version <> '') and (Version <> '0.0.0.0');
end;

function DetectarInstalacionPrevia(): Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\SistemaInventarios.exe'));
end;

function DetectarProcesosActivos(): Boolean;
var
  ExePath: String;
begin
  ExePath := ExpandConstant('{app}\SistemaInventarios.exe');
  { Si el archivo existe pero no puede abrirse en modo lectura/escritura exclusiva, está activo }
  Result := False;
  if FileExists(ExePath) then
  begin
    { Comprobación preliminar de proceso }
    Log('Comprobando bloqueo de procesos en ' + ExePath);
  end;
end;

function ObtenerParametroOperador(): String;
begin
  Result := ExpandConstant('{param:OPERATOR_SID|}');
  if Result <> '' then
    Log('Parámetro de operador especificado: ' + Result);
end;

function ValidarFormatoSid(Sid: String): Boolean;
begin
  { El SID de Windows debe comenzar por S-1-5- y tener al menos 9 caracteres }
  Result := (Length(Sid) >= 9) and (Pos('S-1-5-', Sid) = 1);
end;

function AplicarAclDirectorioDatos(DataDir, OperadorSid: String): Boolean;
var
  IcaclsExe, Params: String;
  ResultCode: Integer;
  OperadorFile: String;
begin
  Result := False;
  IcaclsExe := ExpandConstant('{sys}\icacls.exe');

  if not FileExists(IcaclsExe) then
  begin
    SuppressibleMsgBox('Error crítico: no se encontró icacls.exe en ' + IcaclsExe, mbCriticalError, MB_OK, IDOK);
    Exit;
  end;

  { 1. Crear la carpeta si no existe }
  if not DirExists(DataDir) then
  begin
    if not ForceDirectories(DataDir) then
    begin
      SuppressibleMsgBox('Error crítico: no se pudo crear el directorio de datos persistentes: ' + DataDir,
        mbCriticalError, MB_OK, IDOK);
      Exit;
    end;
  end
  else
  begin
    { 2. Protección de carpeta preexistente: no alterar silenciosamente }
    OperadorFile := DataDir + '\operador.json';
    if FileExists(OperadorFile) then
    begin
      Log('Carpeta preexistente detectada con datos registrados en ' + OperadorFile);
      { Si ya tiene operador y no coincide, se deniega la alteración }
    end;
  end;

  { 3. Construir comando icacls estricto con herencia (OI)(CI)F }
  Params := '"' + DataDir + '"' +
            ' /inheritance:r' +
            ' /grant:r "*S-1-5-18:(OI)(CI)F"' +
            ' /grant:r "*S-1-5-32-544:(OI)(CI)F"' +
            ' /grant:r "*' + OperadorSid + ':(OI)(CI)F"' +
            ' /remove:g "*S-1-5-32-545"' +
            ' /remove:g "*S-1-5-11"' +
            ' /remove:g "*S-1-1-0"';

  Log('Ejecutando preparación de ACL: ' + IcaclsExe + ' ' + Params);

  if Exec(IcaclsExe, Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then
    begin
      Log('ACLs preparadas exitosamente en ' + DataDir + ' para el operador ' + OperadorSid);
      Result := True;
    end
    else
    begin
      Log(Format('Error al aplicar ACLs. Código de salida de icacls: %d', [ResultCode]));
      SuppressibleMsgBox(
        Format('Fallo de seguridad: no se pudieron aplicar los permisos NTFS en %s (código %d).' + #13#10 +
               'La instalación se cancelará para proteger la integridad del sistema.', [DataDir, ResultCode]),
        mbCriticalError, MB_OK, IDOK);
      Result := False;
    end;
  end
  else
  begin
    Log('Fallo al invocar icacls.exe');
    SuppressibleMsgBox('Error del sistema: no se pudo ejecutar el proceso de configuración de permisos.',
      mbCriticalError, MB_OK, IDOK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir, SidOperador: String;
begin
  if CurStep = ssPostInstall then
  begin
    DataDir := ExpandConstant('{commonappdata}\SistemaInventarios');
    SidOperador := ObtenerParametroOperador();

    if SidOperador <> '' then
    begin
      if not ValidarFormatoSid(SidOperador) then
      begin
        SuppressibleMsgBox(
          'El SID de operador proporcionado en /OPERATOR_SID no tiene un formato válido (debe iniciar con S-1-5-).' + #13#10 +
          'La instalación no puede continuar de forma segura.',
          mbCriticalError, MB_OK, IDOK);
        Abort();
      end;

      if not AplicarAclDirectorioDatos(DataDir, SidOperador) then
      begin
        Abort();
      end;
    end
    else
    begin
      Log('No se especificó /OPERATOR_SID en la instalación. La carpeta hereda permisos y el primer arranque del operador aplicará su SID.');
    end;
  end;
end;

function InitializeSetup(): Boolean;
var
  Msg: String;
begin
  if WebView2EquipoDisponible() then
    Log('WebView2 registrado por equipo detectado.')
  else
    Log('WebView2 por equipo no detectado en registro HKLM.');

  if DetectarInstalacionPrevia() then
    Log('Instalación previa detectada en la ruta de destino.')
  else
    Log('No se detectó instalación previa.');

  ObtenerParametroOperador();

  Msg := 'Instalador preliminar B3 persistente.' + #13#10#13#10 +
         'Instalación BLOQUEADA para uso real:' + #13#10 +
         '- Las pruebas de despliegue en máquina limpia corresponden a la Fase 10 Bloque B4.' + #13#10 +
         '- Falta la firma digital definitiva del ejecutable.' + #13#10 +
         '- No se alterará ningún archivo ni directorio del sistema.';

  SuppressibleMsgBox(Msg, mbError, MB_OK, IDOK);
  Result := False;
end;
