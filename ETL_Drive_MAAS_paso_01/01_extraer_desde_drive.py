"""MAAS ECOLOGÍA 4 | PASO 01: extracción SOLO LECTURA desde Google Drive.

FUENTES ACTIVAS (estructura 2026):
  - BSC_KPIs_CON_MARGEN_OPERATIVO_GERENCIA.xlsx (BSC manual + hoja PROYECTOS)
  - MAASECOLOGIA_REPORTE_VENTA_20261016102354.xlsx
  - MAAS_Control_Caja_Mensual_SIMULADO_2026.xlsx
  - Todos los Excel numerados de la carpeta «Seguimiento proyectos» (17 iniciales)

Los archivos de proyecto deben comenzar con 01_, 02_, ..., 17_.
El ETL detecta también proyectos nuevos (18_, 19_, ...).
Los archivos se descargan con control de versión SHA256 y se incorporan al
manifiesto datos_fuente/ultima_extraccion.json. No escribe en Drive ni SQL.

PRUEBAS:
  py 01_extraer_desde_drive.py --probar    # no sustituye el manifiesto
  py 01_extraer_desde_drive.py --ejecutar # publica el manifiesto nuevo

IMPORTANTE: Antes de usar --ejecutar con el ETL maestro, actualizar el PASO 02:
el transformador anterior espera una fuente «proyectos» con la hoja
SEGUIMIENTO_PROPUESTA, que ya NO forma parte de estas 20 fuentes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
HISTORICO = ROOT / "datos_fuente" / "versiones"
MANIFEST = ROOT / "datos_fuente" / "ultima_extraccion.json"
CREDENTIALS = CONFIG / "credentials.json"
TOKEN = CONFIG / "token_drive.json"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
MIME_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_XLSM = "application/vnd.ms-excel.sheet.macroenabled.12"
MIMES_EXCEL = frozenset((MIME_EXCEL, MIME_XLSM))
MIME_SHEETS = "application/vnd.google-apps.spreadsheet"
MIME_CARPETA = "application/vnd.google-apps.folder"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

CARPETA_TESIS_ID = "1W0ZeCoRU4MuC7X-zVbA2EWQqq95gTnDg"
CARPETA_PROYECTOS_ID = "1N1nmegwlgQOYXSe3YZ8ZBI9ITWCqrQuT"
PROYECTOS_INICIALES = set(range(1, 18))
PATRON_PROYECTO = re.compile(r"^(\d{2,3})_(.+?)(?:\.(?:xlsx|xlsm))?$", re.IGNORECASE)


@dataclass(frozen=True)
class Fuente:
    codigo: str
    file_id: str
    nombre: str
    hojas_requeridas: frozenset[str]
    tipo: str
    grupo: str = "base"
    numero_proyecto: int | None = None


FUENTES_FIJAS = [
    Fuente(
        codigo="bsc",
        file_id="1uvwp6qW35fw8-Eb8o4O4zp3umNeRFfpt",
        nombre="BSC_KPIs_CON_MARGEN_OPERATIVO_GERENCIA.xlsx",
        hojas_requeridas=frozenset({
            "CONTRATOS", "BSC KPIs", "ADMINISTRACION", "INGENIERIA",
            "OPERACIONES", "BD", "PROYECTOS",
        }),
        tipo="xlsx",
    ),
    Fuente(
        codigo="ventas",
        file_id="1hhUdnuWdiRS6oWCtGzXlo7WYEGUc7-uz",
        nombre="MAASECOLOGIA_REPORTE_VENTA_20261016102354.xlsx",
        hojas_requeridas=frozenset({"DETALLE", "RESUMEN"}),
        tipo="xlsx",
    ),
    Fuente(
        codigo="caja",
        file_id="1zjIEFun7LbAgh5kTqStbZbY209scyLHQ",
        nombre="MAAS_Control_Caja_Mensual_SIMULADO_2026.xlsx",
        hojas_requeridas=frozenset({"CONTROL_CAJA_MENSUAL"}),
        tipo="xlsx",
    ),
]


def autenticar():
    CONFIG.mkdir(parents=True, exist_ok=True)
    creds = None
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except (ValueError, OSError):
            creds = None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            # El refresh token puede haber caducado o sido revocado.
            # En ese caso, solicitar un nuevo consentimiento OAuth en el navegador.
            # El token anterior solo se sustituye si la autorización tiene éxito.
            print('Token de Drive caducado o revocado; se solicitará autorización de Google.')
            creds = None
    if not creds or not creds.valid:
        if not CREDENTIALS.is_file():
            raise FileNotFoundError(
                "Falta config/credentials.json (OAuth de escritorio). "
                "Conserva el que ya utilizabas y NO lo compartas."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def listar_proyectos(service) -> list[Fuente]:
    """Encuentra todos los libros numerados de la carpeta. No modifica Drive."""
    encontrados = []
    pagina = None
    while True:
        respuesta = service.files().list(
            q=f"'{CARPETA_PROYECTOS_ID}' in parents and trashed = false",
            fields="nextPageToken,files(id,name,mimeType)",
            pageSize=1000,
            pageToken=pagina,
        ).execute()
        encontrados.extend(respuesta.get("files", []))
        pagina = respuesta.get("nextPageToken")
        if not pagina:
            break

    por_numero: dict[int, Fuente] = {}
    identificadores: set[str] = set()
    for archivo in encontrados:
        mime = archivo.get("mimeType")
        nombre = archivo.get("name", "")
        if mime == MIME_CARPETA:
            continue  # p. ej., la subcarpeta ANEXOS
        if mime not in (*MIMES_EXCEL, MIME_SHEETS):
            continue
        coincidencia = PATRON_PROYECTO.fullmatch(nombre)
        if not coincidencia:
            raise ValueError(
                f"Archivo Excel sin prefijo numérico en Seguimiento proyectos: {nombre!r}. "
                "Utiliza 18_NOMBRE.xlsx para agregar otro proyecto."
            )
        numero = int(coincidencia.group(1))
        if numero == 0 or numero in por_numero:
            raise ValueError(f"Número de proyecto repetido o inválido: {numero:02d}")
        if not archivo.get("id") or archivo["id"] in identificadores:
            raise ValueError(f"Identificador de archivo inválido o repetido: {nombre}")
        identificadores.add(archivo["id"])
        por_numero[numero] = Fuente(
            codigo=f"proyecto_{numero:02d}",
            file_id=archivo["id"],
            nombre=nombre,
            hojas_requeridas=frozenset({"Carta Gantt", "Tareas", "Recursos"}),
            tipo="google_sheet" if mime == MIME_SHEETS else "xlsx",
            grupo="seguimiento_proyectos",
            numero_proyecto=numero,
        )

    faltantes = sorted(PROYECTOS_INICIALES - set(por_numero))
    if faltantes:
        raise ValueError(
            f"Faltan proyectos iniciales en Drive: {', '.join(f'{n:02d}' for n in faltantes)}. "
            "No se actualizará el manifiesto incompleto."
        )
    return [por_numero[n] for n in sorted(por_numero)]


def descargar(service, fuente: Fuente) -> bytes:
    metadata = service.files().get(
        fileId=fuente.file_id, fields="id,name,mimeType,modifiedTime,trashed"
    ).execute()
    if metadata.get("trashed"):
        raise ValueError(f"{fuente.codigo}: el archivo está en papelera")
    mime_recibido = metadata.get("mimeType")
    admitidos = {MIME_SHEETS} if fuente.tipo == "google_sheet" else MIMES_EXCEL
    if mime_recibido not in admitidos:
        raise ValueError(
            f"{fuente.codigo}: tipo de archivo inesperado; "
            f"se admite Excel .xlsx/.xlsm o Google Sheets según la fuente, "
            f"recibido {mime_recibido}"
        )
    if fuente.tipo == "google_sheet":
        peticion = service.files().export_media(fileId=fuente.file_id, mimeType=MIME_EXCEL)
    else:
        peticion = service.files().get_media(fileId=fuente.file_id)
    stream = BytesIO()
    downloader = MediaIoBaseDownload(stream, peticion, chunksize=1024 * 1024)
    terminado = False
    while not terminado:
        _, terminado = downloader.next_chunk()
    datos = stream.getvalue()
    if not datos:
        raise ValueError(f"{fuente.codigo}: descarga vacía")
    return datos


def validar_hojas(datos: bytes, obligatorias: frozenset[str], codigo: str) -> list[str]:
    """Lee los nombres de las pestañas, sin modificar la planilla."""
    try:
        with ZipFile(BytesIO(datos)) as z:
            libro = ElementTree.fromstring(z.read("xl/workbook.xml"))
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError(f"{codigo}: no es un archivo .xlsx/.xlsm válido") from exc
    hojas = [hoja.get("name", "") for hoja in libro.findall(".//m:sheet", NS)]
    faltantes = obligatorias - set(hojas)
    if faltantes:
        raise ValueError(
            f"{codigo}: faltan hojas: {', '.join(sorted(faltantes))}. "
            f"Encontradas: {', '.join(hojas)}"
        )
    return hojas


def extension_excel(datos: bytes, codigo: str) -> str:
    """Identifica el formato real del ZIP Office sin ejecutar ni modificar macros.

    Usar el Content-Type del libro, no su nombre visible en Drive: renombrar
    un .xlsm a .xlsx no convierte el archivo ni es una validación fiable.
    """
    try:
        with ZipFile(BytesIO(datos)) as z:
            if "xl/workbook.xml" not in z.namelist():
                raise ValueError(f"{codigo}: falta xl/workbook.xml")
            raiz = ElementTree.fromstring(z.read("[Content_Types].xml"))
        tipo = next((elemento.attrib.get("ContentType", "")
                     for elemento in raiz
                     if elemento.attrib.get("PartName") == "/xl/workbook.xml"), "")
        if not tipo:
            # Algunos productores OOXML asignan el tipo por defecto a *.xml.
            tipo = next((elemento.attrib.get("ContentType", "")
                         for elemento in raiz
                         if elemento.attrib.get("Extension") == "xml"), "")
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError(f"{codigo}: falta un archivo Office válido") from exc
    if tipo == "application/vnd.ms-excel.sheet.macroEnabled.main+xml":
        return ".xlsm"
    if tipo == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml":
        return ".xlsx"
    raise ValueError(f"{codigo}: formato de libro Excel no admitido: {tipo!r}")


def guardar_si_nuevo(codigo: str, datos: bytes, sha: str, extension: str = ".xlsx") -> tuple[Path, bool]:
    HISTORICO.mkdir(parents=True, exist_ok=True)
    if extension not in (".xlsx", ".xlsm"):
        raise ValueError("Extensión Excel no admitida")
    ruta = HISTORICO / f"{codigo}_{sha[:16]}{extension}"
    if ruta.exists():
        if hashlib.sha256(ruta.read_bytes()).hexdigest() != sha:
            raise RuntimeError(f"Conflicto de huella con archivo existente: {ruta}")
        return ruta, False
    with tempfile.NamedTemporaryFile(dir=HISTORICO, suffix=".tmp", delete=False) as tmp:
        tmp.write(datos)
        temporal = Path(tmp.name)
    temporal.replace(ruta)
    return ruta, True


def ejecutar(publicar: bool = True) -> dict:
    service = autenticar()
    fuentes = FUENTES_FIJAS + listar_proyectos(service)
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lista = []
    print("ETL MAAS 4 | EXTRACCIÓN DRIVE SOLO LECTURA")
    print(f"Fuentes encontradas: {len(fuentes)} (3 base + {len(fuentes)-3} proyectos)")

    for indice, fuente in enumerate(fuentes, 1):
        datos = descargar(service, fuente)
        hojas = validar_hojas(datos, fuente.hojas_requeridas, fuente.codigo)
        extension = extension_excel(datos, fuente.codigo)
        sha = hashlib.sha256(datos).hexdigest()
        if publicar:
            ruta, nuevo = guardar_si_nuevo(fuente.codigo, datos, sha, extension)
            ruta_local = str(ruta.relative_to(ROOT)).replace("\\", "/")
        else:
            nuevo = None
            ruta_local = None
        estado = "NUEVA VERSIÓN" if nuevo else ("SIN CAMBIOS" if publicar else "VALIDADO")
        print(f"  [{indice:02d}/{len(fuentes)}] {fuente.codigo}: {estado} "
              f"({len(hojas)} hojas, {extension})")
        lista.append({
            "fuente": fuente.codigo,
            "id_drive": fuente.file_id,
            "nombre_drive": fuente.nombre,
            "version_sha256": sha,
            "ruta_local": ruta_local,
            "formato_excel": extension.lstrip("."),
            "tamano_bytes": len(datos),
            "hojas": hojas,
            "nueva_version": nuevo,
            "grupo": fuente.grupo,
            "numero_proyecto": fuente.numero_proyecto,
        })

    manifiesto = {
        "extraido_utc": ahora,
        "bd_destino_futura": "MAAS_ECOLOGIA_4",
        "carpeta_tesis_drive": CARPETA_TESIS_ID,
        "carpeta_seguimiento_drive": CARPETA_PROYECTOS_ID,
        "archivos": lista,
    }
    if publicar:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=MANIFEST.parent,
            suffix=".tmp", delete=False,
        ) as tmp:
            json.dump(manifiesto, tmp, ensure_ascii=False, indent=2)
            temporal = Path(tmp.name)
        temporal.replace(MANIFEST)
        print(f"\nOK: {len(fuentes)} fuentes descargadas y manifiesto actualizado: {MANIFEST}")
    else:
        print(f"\nPRUEBA OK: {len(fuentes)} fuentes verificadas. No se modificó el manifiesto.")
    print("No se enviaron datos a SQL Server.")
    return manifiesto


def main() -> None:
    parser = argparse.ArgumentParser(description="Extracción de fuentes MAAS desde Drive")
    modos = parser.add_mutually_exclusive_group()
    modos.add_argument("--probar", action="store_true", help="Validar descargas sin publicar cambios")
    modos.add_argument("--ejecutar", action="store_true", help="Descargar y publicar manifiesto")
    args = parser.parse_args()
    ejecutar(publicar=not args.probar)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
