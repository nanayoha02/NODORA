# NODORA · Remote System Management

Aplicación de escritorio para **Windows** que monitorea, administra y mantiene de forma remota el mini PC **BOSGAME**
(Windows o Linux) por **SSH/SFTP** en red local. Implementa las 25 acciones del proyecto semestral más dos de tráfico de red (26 y 27); cada operación se
ejecuta de verdad en el equipo remoto, se **comprueba** su estado real y queda registrada en `actividad.csv`.

**Ficha del producto**
- **Público objetivo:** estudiantes y técnicos que administran un equipo remoto en un laboratorio o red doméstica.
- **Beneficios:** una sola interfaz para monitoreo, red/servicios, archivos con integridad SHA-256, respaldos y evidencias.
- **Limitaciones reales:** un solo equipo administrado; requiere OpenSSH en BOSGAME; las acciones 14 y 15 necesitan una cuenta
  administradora; el respaldo en Windows usa `Compress-Archive` (límite de 2 GB por archivo en PowerShell 5.1);
  el panel muestrea CPU/RAM cada pocos segundos, no es un monitor continuo; la captura limita duración (5–60 s) y, en Linux, número de paquetes; en Windows `pktmon` captura solo cabeceras (128 bytes por paquete) y su sintaxis puede variar entre versiones.

## 1. Requisitos
| Lado | Requisito |
|---|---|
| Cliente | Windows 10/11 64 bits, Python 3.10+ (solo para desarrollo), PySide6, paramiko |
| BOSGAME (Windows) | OpenSSH Server activo, PowerShell 5.1+, cuenta administradora; `pktmon` (incluido en Windows 10 1809+/11) para la captura |
| BOSGAME (Linux) | OpenSSH, `systemd`, `sudo` sin contraseña para la cuenta (acciones 14/15/27); `tcpdump` y `ss` instalados |
| Red | Misma red local; sin internet durante la evaluación |

**Versión probada del cliente:** anótela aquí tras la prueba real → `Windows ____ build ____ · Python ____ · PySide6 ____ · paramiko ____`.

### Preparar BOSGAME (Windows), una sola vez, en PowerShell como administrador
```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name sshd -DisplayName "OpenSSH Server" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

## 2. Instalación
**Opción A · ejecutable:** ejecute `build_exe.bat` (necesita internet una vez). Resultado: `dist\NODORA\NODORA.exe`.
**Opción B · desarrollo:** `run_dev.bat` (crea el entorno, instala dependencias y abre la app).
Las pruebas automáticas (85) usan `sh` y herramientas Linux: ejecútelas en Linux o WSL con `python -m pytest tests -q`; no forman parte del build de Windows.

## 3. Primeros pasos
1. **Conexión SSH** → IP de BOSGAME, puerto, usuario y contraseña (se mantiene solo en memoria) → *Guardar* → *Conectar*.
   La primera vez se pide confirmar la **huella** del equipo y se fija en `known_hosts`.
2. En el mismo panel, **Identificación** → nombre, grupo e identificador (sin `/`, `\` ni `..`) → *Preparar carpeta personal*.
3. En **Configuración › Parámetros del laboratorio** escriba lo que entregue el docente: rango TCP, servicios, servicio de práctica
   y (el día de la evaluación) la ruta revelada. No hay que tocar el código.

## 4. Mapa de funciones
| Sección | Acciones |
|---|---|
| Conexión SSH | 1 configurar · 2 identificar · 3 conectar/desconectar · 4 carpeta personal |
| Monitoreo | 5 sistema · 6 CPU · 7 RAM · 8 almacenamiento · 9 procesos |
| Red y servicios | 10 red · 11 conectividad · 12 puertos · 13 servicios · 14 servicio de práctica · 15 diagnóstico de puerto |
| Tráfico de red | 26 gráfica en vivo (bytes/s por interfaz) y conexiones TCP · 27 captura de paquetes con tabla, resumen y descarga del `.pcap` para Wireshark |
| Archivos y mantenimiento | 16 explorar · 17 subcarpeta · 18 enviar · 19 descargar · 20 copiar · 21 respaldo · 22 restauración · 23 temporales · 25 ruta revelada |
| Historial e informes | 24 historial e informe (local + BOSGAME, sincroniza pendientes sin duplicar) |

Estructura creada en BOSGAME: `<carpeta base>\<identificador>\{Archivos, Respaldos, Restaurados, Evidencias, Informes, Temporales}`
más `identificacion.txt` y `actividad.csv`.

## 5. Cómo se garantiza que "ejecutada" ≠ "verificada"
| Operación | Comprobación real |
|---|---|
| Crear carpeta / identidad | se lista o se relee el archivo desde BOSGAME |
| Enviar / descargar | SHA-256 local frente a SHA-256 calculado **en BOSGAME**; archivo `.part` hasta verificar |
| Copiar | SHA-256 origen = destino y el original sigue existiendo |
| Servicio de práctica | se consulta el estado después de cada orden |
| Cierre del puerto (15) | el puerto desaparece de la lista de escucha **y** la conexión TCP es *rechazada*; un timeout solo no basta |
| Respaldo / restauración | manifiesto con SHA-256 por archivo; restauración comparada contra el manifiesto |
| Limpieza de temporales | tamaño de `Temporales` medido antes y después |
| Tráfico en vivo (26) | tasas = diferencia de contadores ÷ tiempo real entre lecturas; si un contador baja (reinicio) se descarta ese intervalo |
| Captura (27) | el archivo se descarga con SHA-256 verificado contra BOSGAME y se analiza localmente; si no hubo paquetes se informa tal cual |

## 6. Seguridad
- Contraseñas nunca se guardan ni se registran (`settings.json` no las contiene; el registro las enmascara).
- Rutas validadas: no se puede salir de la carpeta personal (`..`, rutas absolutas, prefijos engañosos); la acción 25 es la única excepción.
- Comandos remotos solo con plantillas controladas y parámetros validados; PowerShell se envía codificado (`-EncodedCommand`).
- Huella del servidor SSH confirmada y fijada; cambio de huella ⇒ conexión cancelada.

## 7. Solución de problemas
| Síntoma | Causa probable / solución |
|---|---|
| "Sin respuesta de IP:22" | equipo apagado, IP incorrecta o firewall; pruebe *Probar conexión* y `ping` |
| "rechazó la conexión" | `sshd` no está activo: `Start-Service sshd` |
| "Autenticación rechazada" | usuario/contraseña; en dominios use `usuario@dominio` |
| Acción 14/15 "permisos insuficientes" | use una cuenta administradora (Windows) o `sudo` sin contraseña (Linux) |
| "Falta la biblioteca paramiko" | `pip install -r requirements.txt` |
| Acción 27 «se necesitan privilegios» | ejecute con cuenta administradora (Windows) o con `sudo` sin contraseña (Linux) |
| Acción 27 «herramienta no instalada» | Linux: `sudo apt install tcpdump`; Windows: actualice a Windows 10 1809+ para tener `pktmon` |
| Respaldo muy lento | tamaño grande; el cálculo de sumas SHA-256 recorre todos los archivos |

## 8. Uso de IA y defensa
Este proyecto se desarrolló con ayuda de Claude (IA). **Documente en su informe qué partes usó**, verifíquelas y prepárese para
explicar y modificar el código en la defensa. Archivos clave: `nodora/core/profiles.py` (comandos por SO), `nodora/ops/lab.py`
(acciones), `nodora/ops/transfer.py` (integridad), `nodora/ops/portdrill.py` (acción 15), `nodora/core/validators.py` (seguridad).
Temas a dominar: cliente vs. equipo remoto, conectividad vs. autenticación, puerto vs. servicio, PID vs. proceso, respaldo vs.
restauración, permisos y elevación en Windows, integridad por hash y diferencia entre operación solicitada y comprobada.

## 9. Entregables y matriz
`docs/matriz_acciones.csv` (ábrala en Excel) trae las 25 acciones, las 2 de tráfico y las pruebas de aceptación; complete *Resultado obtenido*,
*Evidencia* y *Estado* tras probar contra BOSGAME. Las capturas complementan los archivos conservados en `Evidencias`.

## 10. Estilo visual
Tema **Ciruela** (predeterminado): fondo ciruela sobre lavanda, tarjetas pastel con muesca superior, botones en píldora y barra lateral de iconos (el nombre de cada sección aparece al pasar el cursor). Se cambia en Configuración › Apariencia (Ciruela, Claro, Oscuro, Sistema); reinicie NODORA para aplicar la barra lateral. La tipografía usa Unbounded, Syne o Space Grotesk si están instaladas y, si no, Segoe UI.

## 11. Créditos y licencias
Qt for Python / PySide6 (LGPL-3.0) · paramiko (LGPL-2.1) · Inter (SIL OFL 1.1, opcional). Logo e icono: logo oficial de NODORA (`assets/nodora_logo_full.png`; los derivados se generan con `tools/make_assets.py`, que requiere Pillow y numpy).
