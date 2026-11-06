# -*- coding: utf-8 -*-
"""MAAS ECOLOGIA 4 | Extractor independiente Gmail -> archivos locales.

SOLO LECTURA de mensajes con etiqueta Gmail "MAAS-ETL".
NO modifica Drive, SQL Server, Streamlit ni el ETL de los 20 Excel.
NO extrae tareas, recursos ni Gantt de Gmail; esos datos vienen de Excel.

Instalar una sola vez:
  py -m pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 pypdf

Requisitos: habilitar Gmail API en Google Cloud, utilizar OAuth escritorio
config/credentials.json (el mismo cliente OAuth de Drive, si es compatible).
El permiso Gmail se concede por separado y su token se guarda aparte.

Ejemplos:
  py .\01_extraer_desde_gmail.py --demo
  py .\01_extraer_desde_gmail.py --probar
  py .\01_extraer_desde_gmail.py --ejecutar

Para seleccionar mensajes: crear etiqueta de Gmail MAAS-ETL y aplicarla
SOLAMENTE a cierres mensuales y contratos ficticios que deseamos procesar.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import io
import json
import re
import sys
import tempfile
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
OUT = ROOT / "datos_fuente" / "gmail"
CREDENTIALS = CONFIG / "credentials.json"
TOKEN = CONFIG / "token_gmail_maas.json"   # NUNCA modificar token_drive.json
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CONSULTA = "label:MAAS-ETL"                 # NO busca todo el historial
MAX_MENSAJES = 500
MAX_PDF_BYTES = 15 * 1024 * 1024

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def clave_proyecto(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalizar(nombre)).strip("_")


def fecha_iso(valor: str) -> str:
    v = (valor or "").strip().strip(".,;")
    formatos = (r"\d{4}-\d{2}-\d{2}", r"\d{1,2}[/-]\d{1,2}[/-]\d{4}")
    m = re.search("|".join(f"({fmt})" for fmt in formatos), v)
    if m:
        v = m.group(0)
        if re.fullmatch(formatos[0], v):
            return date.fromisoformat(v).isoformat()
        a, b, c = re.split(r"[/-]", v)
        return date(int(c), int(b), int(a)).isoformat()
    n = normalizar(v)
    m = re.search(r"\b(\d{1,2})\s+de\s+([a-z]+)\s+(?:de\s+)?(\d{4})\b", n)
    if m and m.group(2) in MESES:
        return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1))).isoformat()
    raise ValueError("Fecha no reconocida: " + repr(valor))


def dinero_clp(valor: str) -> int:
    """Acepta $1.234.567, CLP 1234567, 1.234.567 pesos; nunca UF/USD."""
    if re.search(r"\b(?:usd|us\$|uf|d[o\u00f3]lares?)\b", normalizar(valor)):
        raise ValueError("Moneda no CLP; requiere revisi\u00f3n")
    s = re.sub(r"(?i)\b(clp|pesos|chilenos|netos|brutos|iva\s+incluido)\b", "", valor)
    s = s.replace("$", "").replace(" ", "").strip()
    m = re.match(r"^(-?\d[\d.,]*)", s)
    if not m:
        raise ValueError("Monto vac\u00edo/no num\u00e9rico: " + repr(valor))
    s = m.group(1)
    if re.fullmatch(r"-?\d{1,3}(?:[.,]\d{3})+", s):
        s = re.sub(r"[.,]", "", s)
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        n = Decimal(s)
    except InvalidOperation as e:
        raise ValueError("Monto inv\u00e1lido: " + repr(valor)) from e
    if not n.is_finite() or n != n.to_integral_value() or n < 0:
        raise ValueError("Monto CLP debe ser entero no negativo: " + repr(valor))
    return int(n)


def campo(texto: str, patrones: tuple[str, ...]) -> str:
    """Campos de una l\u00ednea; tolera valor en la l\u00ednea siguiente."""
    lineas = [x.strip() for x in texto.replace("\r", "\n").split("\n")]
    for linea_i, linea in enumerate(lineas):
        ln = normalizar(linea)
        for p in patrones:
            m = re.match(r"^\s*(?:" + p + r")\s*[:\-\u2013]?\s*(.*?)\s*$", ln, re.I)
            if m:
                # Usar el texto ORIGINAL para preservar nombres y n\u00fameros.
                tail = linea[len(linea) - len(m.group(1)):].strip() if m.group(1) else ""
                if tail:
                    return tail
                if linea_i + 1 < len(lineas):
                    return lineas[linea_i + 1]
    return ""


def periodo_mes(texto: str) -> str:
    raw = campo(texto, (
        r"periodo(?:\s+de\s+facturacion)?", r"mes\s+de\s+cierre", r"mes\s+facturado",
        r"mes\s+de\s+facturacion", r"mes", r"cierre\s+correspondiente\s+a",
    ))
    if not raw:
        raise ValueError("Falta per\u00edodo/mes expl\u00edcito")
    m = re.search(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    v = normalizar(raw)
    m = re.search(r"\b(" + "|".join(MESES) + r")\s+(?:de\s+)?(20\d{2})\b", v)
    if not m:
        raise ValueError("Per\u00edodo no reconocido: " + raw)
    return f"{m.group(2)}-{MESES[m.group(1)]:02d}"


def parsear_facturacion(asunto: str, cuerpo: str) -> dict:
    texto = f"{asunto}\n{cuerpo}"
    mes = periodo_mes(texto)
    fact = campo(texto, (
        r"facturacion\s+total(?:\s+(?:neta|del\s+mes|mensual))?",
        r"total\s+facturado(?:\s+(?:neto|del\s+mes))?",
        r"monto\s+total\s+facturado",
    ))
    pend = campo(texto, (
        r"pendiente(?:\s+de\s+facturar|\s+de\s+facturacion)?",
        r"facturacion\s+pendiente", r"monto\s+pendiente", r"saldo\s+pendiente",
    ))
    if not fact:
        raise ValueError("Falta facturaci\u00f3n total del cierre")
    facturado = dinero_clp(fact)
    if not pend and re.search(r"\bsin\s+pendientes\b|\bsin\s+facturacion\s+pendiente\b", normalizar(texto)):
        pend = "$0"
    if not pend:
        raise ValueError("Falta monto pendiente; no se presume cero")
    pendiente = dinero_clp(pend)
    return {
        "periodo": mes, "facturado_clp": facturado, "pendiente_clp": pendiente,
        "criterio_facturacion": "POR_VALIDAR_NETO_O_BRUTO",
    }


def parsear_contrato(texto: str) -> dict:
    nombre = campo(texto, (r"nombre\s+del\s+proyecto", r"proyecto(?:\s+correspondiente)?"))
    ini = campo(texto, (r"fecha\s+de\s+inicio(?:\s+contractual)?", r"inicio\s+del\s+contrato", r"inicio\s+contractual"))
    fin = campo(texto, (r"fecha\s+de\s+(?:termino|fin)(?:\s+contractual)?", r"termino\s+del\s+contrato", r"termino\s+contractual", r"fin\s+del\s+contrato"))
    total = campo(texto, (r"monto\s+total\s+(?:del\s+)?(?:proyecto|contrato)", r"monto\s+contractual", r"valor\s+total\s+del\s+contrato", r"monto\s+total"))
    if not all((nombre, ini, fin, total)):
        faltan = [x for x, v in (("proyecto", nombre), ("fecha inicio", ini), ("fecha t\u00e9rmino", fin), ("monto total", total)) if not v]
        raise ValueError("Contrato incompleto: " + ", ".join(faltan))
    fi, ff = fecha_iso(ini), fecha_iso(fin)
    if ff < fi:
        raise ValueError("Fecha de t\u00e9rmino anterior a fecha de inicio")
    return {
        "nombre_proyecto": nombre,
        "proyecto_normalizado": clave_proyecto(nombre),
        "fecha_inicio": fi, "fecha_termino": ff,
        "monto_contractual_clp": dinero_clp(total),
    }


def texto_pdf(datos: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Falta pypdf. Ejecuta: py -m pip install pypdf") from exc
    lector = PdfReader(io.BytesIO(datos), strict=False)
    if lector.is_encrypted:
        raise ValueError("PDF protegido con contrase\u00f1a: requiere revisi\u00f3n")
    if len(lector.pages) > 70:
        raise ValueError("PDF demasiado extenso para extracci\u00f3n autom\u00e1tica")
    texto = "\n".join(page.extract_text(extraction_mode="layout") or "" for page in lector.pages)
    if len(texto.strip()) < 30:
        raise ValueError("PDF sin texto extra\u00edble (posible escaneo): requiere revisi\u00f3n")
    return texto


def decodificar_b64url(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes: list[str] = []
    def handle_data(self, data):
        self.partes.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li"):
            self.partes.append("\n")


def partes_mensaje(payload: dict) -> list[dict]:
    ret = []
    def caminar(parte):
        ret.append(parte)
        for x in parte.get("parts", []):
            caminar(x)
    caminar(payload or {})
    return ret


def cuerpo_mensaje(payload: dict) -> str:
    partes = partes_mensaje(payload)
    cuerpos = []
    for tipo in ("text/plain", "text/html"):
        for p in partes:
            if p.get("mimeType") != tipo or p.get("filename"):
                continue
            b = p.get("body", {}).get("data")
            if not b:
                continue
            txt = decodificar_b64url(b).decode("utf-8", errors="replace")
            if tipo == "text/html":
                parser = _HTMLText(); parser.feed(txt)
                txt = html.unescape("".join(parser.partes))
            cuerpos.append(txt)
        if cuerpos:
            return "\n".join(cuerpos)
    return ""


def autenticar_gmail():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Instala Gmail API: py -m pip install google-api-python-client google-auth-oauthlib google-auth-httplib2") from exc
    CONFIG.mkdir(parents=True, exist_ok=True)
    creds = None
    if TOKEN.is_file():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except (ValueError, OSError):
            creds = None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not CREDENTIALS.is_file():
            raise FileNotFoundError("Falta config/credentials.json. Nunca lo compartas.")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def buscar_ids(service, consulta: str) -> list[str]:
    ids, token = [], None
    while True:
        args = {"userId": "me", "q": consulta, "maxResults": 100}
        if token:
            args["pageToken"] = token
        result = service.users().messages().list(**args).execute()
        ids.extend(x["id"] for x in result.get("messages", []))
        if len(ids) > MAX_MENSAJES:
            raise ValueError(f"Hay m\u00e1s de {MAX_MENSAJES} correos etiquetados; acota la etiqueta antes de ejecutar")
        token = result.get("nextPageToken")
        if not token:
            break
    return list(dict.fromkeys(ids))


def adjuntos_pdf(service, msg: dict):
    for p in partes_mensaje(msg.get("payload", {})):
        nombre = p.get("filename") or ""
        if not nombre.lower().endswith(".pdf"):
            continue
        body = p.get("body") or {}
        if int(body.get("size") or 0) > MAX_PDF_BYTES:
            yield nombre, None, "PDF supera 15 MB"
            continue
        try:
            if body.get("data"):
                archivo = decodificar_b64url(body["data"])
            elif body.get("attachmentId"):
                r = service.users().messages().attachments().get(
                    userId="me", messageId=msg["id"], id=body["attachmentId"]
                ).execute()
                archivo = decodificar_b64url(r["data"])
            else:
                yield nombre, None, "PDF sin contenido recuperable"
                continue
            if len(archivo) > MAX_PDF_BYTES:
                yield nombre, None, "PDF supera 15 MB"
                continue
            yield nombre, archivo, None
        except Exception as e:
            yield nombre, None, "No se pudo descargar PDF: " + str(e)


def fecha_recepcion(msg: dict) -> str:
    try:
        return datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (ValueError, KeyError, TypeError):
        return ""


def cargar_nombres_bsc() -> dict[str, str]:
    """Solo una ayuda para identificar coincidencias exactas; no inventa relaciones."""
    path = ROOT / "datos_transformados" / "proyectos_bsc.csv"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {clave_proyecto(r.get("nombre_proyecto", "")): r.get("nombre_proyecto", "")
                for r in csv.DictReader(f) if r.get("nombre_proyecto")}


def procesar(servicio, consulta: str):
    ids = buscar_ids(servicio, consulta)
    cierres, contratos, auditoria = [], [], []
    pdf_originales = {}  # sha256 -> bytes; se publican solo en --ejecutar
    bsc = cargar_nombres_bsc()
    for idx, mid in enumerate(ids, 1):
        msg = servicio.users().messages().get(userId="me", id=mid, format="full").execute()
        headers = {x.get("name", "").lower(): x.get("value", "") for x in msg.get("payload", {}).get("headers", [])}
        asunto = headers.get("subject", "")
        cuerpo = cuerpo_mensaje(msg.get("payload", {}))
        fecha = fecha_recepcion(msg)
        sub_norm = normalizar(asunto)
        print(f"  [{idx:02d}/{len(ids):02d}] Gmail {mid[:12]} | {asunto[:60]}")
        # El asunto sirve como primer filtro; evita procesar correos no relacionados.
        if re.search(r"factur|cierre\s+mensual", sub_norm):
            try:
                x = parsear_facturacion(asunto, cuerpo)
                x.update({"gmail_message_id": mid, "fecha_correo_utc": fecha,
                          "origen_datos": "SIMULADO", "estado_validacion": "PENDIENTE_CONCILIACION"})
                cierres.append(x)
                auditoria.append({"gmail_message_id": mid, "tipo": "CIERRE", "estado": "EXTRAIDO", "motivo": ""})
            except (ValueError, InvalidOperation) as e:
                auditoria.append({"gmail_message_id": mid, "tipo": "CIERRE", "estado": "REVISAR", "motivo": str(e)})
        for nombre_pdf, contenido, error in adjuntos_pdf(servicio, msg):
            if not ("contrat" in sub_norm or "contrat" in normalizar(nombre_pdf)):
                continue
            if error:
                auditoria.append({"gmail_message_id": mid, "tipo": "CONTRATO", "archivo": nombre_pdf, "estado": "REVISAR", "motivo": error})
                continue
            try:
                t = texto_pdf(contenido)
                x = parsear_contrato(t)
                x.update({"gmail_message_id": mid, "fecha_correo_utc": fecha,
                          "archivo_pdf": nombre_pdf, "sha256_pdf": hashlib.sha256(contenido).hexdigest(),
                          "origen_datos": "SIMULADO", "estado_validacion": "EXTRAIDO_SIN_APROBAR",
                          "coincide_bsc": "SI" if x["proyecto_normalizado"] in bsc else "NO"})
                contratos.append(x)
                pdf_originales[x["sha256_pdf"]] = contenido
                auditoria.append({"gmail_message_id": mid, "tipo": "CONTRATO", "archivo": nombre_pdf, "estado": "EXTRAIDO", "motivo": ""})
            except Exception as e:
                auditoria.append({"gmail_message_id": mid, "tipo": "CONTRATO", "archivo": nombre_pdf, "estado": "REVISAR", "motivo": str(e)})
    # No aplicar arbitrariamente versiones conflictivas de un mismo mes/proyecto.
    agrupar_cierres: dict[str, list[dict]] = {}
    for x in cierres:
        agrupar_cierres.setdefault(x["periodo"], []).append(x)
    for mes, grupo in agrupar_cierres.items():
        distintos = {(x["facturado_clp"], x["pendiente_clp"]) for x in grupo}
        if len(distintos) > 1:
            for x in grupo:
                x["estado_validacion"] = "CONFLICTO_MISMO_MES"
            auditoria.append({"tipo": "CIERRE", "estado": "REVISAR", "motivo": f"Cierres diferentes para {mes}"})
    agrupar_contratos: dict[str, list[dict]] = {}
    for x in contratos:
        agrupar_contratos.setdefault(x["proyecto_normalizado"], []).append(x)
    for proyecto, grupo in agrupar_contratos.items():
        distintos = {(x["fecha_inicio"], x["fecha_termino"], x["monto_contractual_clp"]) for x in grupo}
        if len(distintos) > 1:
            for x in grupo:
                x["estado_validacion"] = "CONFLICTO_CONTRATOS"
            auditoria.append({"tipo": "CONTRATO", "estado": "REVISAR", "motivo": f"Contratos diferentes para {proyecto}"})
    # El mismo Gmail/PDF no se cuenta dos veces en una misma ejecuci\u00f3n.
    cierres = list({(x["periodo"], x["facturado_clp"], x["pendiente_clp"]): x for x in cierres}.values())
    contratos = list({x["sha256_pdf"]: x for x in contratos}.values())
    cierres.sort(key=lambda x: (x["periodo"], x["gmail_message_id"]))
    contratos.sort(key=lambda x: (x["proyecto_normalizado"], x["gmail_message_id"]))
    return len(ids), cierres, contratos, auditoria, pdf_originales


def publicar_json(path: Path, obj):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=OUT, suffix=".tmp", delete=False) as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        temporal = Path(f.name)
    temporal.replace(path)


def publicar_csv(path: Path, rows: list[dict], headers: list[str]):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=OUT, suffix=".tmp", delete=False) as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
        temporal = Path(f.name)
    temporal.replace(path)


def publicar_contratos_originales(contratos: list[dict], pdf_originales: dict[str, bytes]) -> None:
    """Conserva el PDF original por SHA, sin afectar el CSV usado por STAGING.

    Solo se publican los contratos vinculados inequivocamente con nombres BSC.
    Los PDFs con nombre no coincidente quedan para revision en auditoria,
    sin asignarlos erroneamente a otro proyecto.
    """
    directorio = OUT / "contratos_pdf"
    directorio.mkdir(parents=True, exist_ok=True)
    indice = []
    for c in contratos:
        sha = c["sha256_pdf"]
        if c.get("coincide_bsc") != "SI":
            continue
        data = pdf_originales.get(sha)
        if not data or hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError("PDF original ausente o corrupto para " + sha)
        destino = directorio / (sha + ".pdf")
        if destino.exists():
            if hashlib.sha256(destino.read_bytes()).hexdigest() != sha:
                raise RuntimeError("PDF almacenado con huella diferente: " + str(destino))
        else:
            with tempfile.NamedTemporaryFile(dir=directorio, suffix=".tmp", delete=False) as tmp:
                tmp.write(data)
                temporal = Path(tmp.name)
            temporal.replace(destino)
        indice.append({
            "nombre_proyecto": c["nombre_proyecto"],
            "proyecto_normalizado": c["proyecto_normalizado"],
            "archivo_pdf": c["archivo_pdf"],
            "sha256_pdf": sha,
            "gmail_message_id": c["gmail_message_id"],
            "fecha_correo_utc": c["fecha_correo_utc"],
            "estado_validacion": c["estado_validacion"],
            "ruta_relativa": "contratos_pdf/" + sha + ".pdf",
        })
    publicar_json(OUT / "contratos_originales.json", {
        "actualizado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contratos": indice,
    })
    print(f"PDF originales guardados: {len(indice)} contrato(s) vinculado(s) a proyectos BSC")


def main():
    ap = argparse.ArgumentParser(description="MAAS | Gmail solo lectura, cierres y contratos PDF")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="Prueba an\u00e1lisis de textos sin conectar Gmail")
    group.add_argument("--probar", action="store_true", help="Lee Gmail y valida; no escribe resultados locales")
    group.add_argument("--ejecutar", action="store_true", help="Lee Gmail y publica CSV/JSON locales")
    ap.add_argument("--consulta", default=CONSULTA, help="Filtro Gmail; predeterminado label:MAAS-ETL")
    args = ap.parse_args()
    if args.demo:
        e = ("Asunto: Cierre de facturaci\u00f3n\nPeriodo: septiembre 2026\n"
             "Facturaci\u00f3n total: $120.000.000\nPendiente de facturar: $5.000.000")
        p = ("CONTRATO DE PROYECTO\nNombre del proyecto: MLP CAL\n"
             "Fecha de inicio: 01/10/2026\nFecha de t\u00e9rmino: 30/11/2026\n"
             "Monto total del proyecto: $60.288.500")
        assert parsear_facturacion("Cierre de facturaci\u00f3n", e) == {
            "periodo": "2026-09", "facturado_clp": 120000000,
            "pendiente_clp": 5000000, "criterio_facturacion": "POR_VALIDAR_NETO_O_BRUTO"}
        contrato = parsear_contrato(p)
        assert (contrato["nombre_proyecto"], contrato["fecha_inicio"],
                contrato["fecha_termino"], contrato["monto_contractual_clp"]) == (
                    "MLP CAL", "2026-10-01", "2026-11-30", 60288500)
        print("DEMO OK: textos ficticios de cierre y contrato reconocidos; no Gmail ni SQL")
        return 0
    print("MAAS 4 | GMAIL SOLO LECTURA |", "PRUEBA" if args.probar else "EXTRACCION")
    print("Filtro:", args.consulta)
    service = autenticar_gmail()
    encontrados, cierres, contratos, auditoria, pdf_originales = procesar(service, args.consulta)
    print(f"Mensajes: {encontrados} | cierres: {len(cierres)} | contratos: {len(contratos)} | incidencias: {sum(x.get('estado')=='REVISAR' for x in auditoria)}")
    if args.probar:
        print("PRUEBA OK. No se guardaron archivos ni se modific\u00f3 SQL.")
        return 0
    if encontrados == 0:
        print("SIN MENSAJES: no se sobrescribieron resultados anteriores.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    publicar_csv(OUT / "cierres_facturacion.csv", cierres, [
        "periodo", "facturado_clp", "pendiente_clp", "criterio_facturacion",
        "gmail_message_id", "fecha_correo_utc", "origen_datos", "estado_validacion"])
    publicar_csv(OUT / "contratos_pdf.csv", contratos, [
        "nombre_proyecto", "proyecto_normalizado", "fecha_inicio", "fecha_termino",
        "monto_contractual_clp", "gmail_message_id", "fecha_correo_utc", "archivo_pdf",
        "sha256_pdf", "origen_datos", "estado_validacion", "coincide_bsc"])
    publicar_contratos_originales(contratos, pdf_originales)
    publicar_json(OUT / "auditoria_gmail.json", {
        "extraido_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "consulta": args.consulta, "mensajes_revisados": encontrados,
        "cierres": len(cierres), "contratos": len(contratos), "auditoria": auditoria,
        "advertencia": "Datos simulados / extra\u00eddos sin aprobaci\u00f3n; no equivalen a carga a SQL ni al dashboard",
    })
    print("EXTRACCI\u00d3N OK: CSV y auditor\u00eda en datos_fuente/gmail/")
    print("SIGUIENTE: adaptar PASO 02, STAGING, dimensiones/hechos y Streamlit para estas dos fuentes.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
