# -*- coding: utf-8 -*-
"""MAAS ECOLOGIA 4 | PASO 04: STAGING incremental Drive + Gmail.

    py .\04_cargar_staging.py --verificar       (SIN SQL)
    py .\04_cargar_staging.py --comprobar-sql  (solo lectura SQL)
    py .\04_cargar_staging.py --cargar         (inserta nuevas versiones en STAGING)

IMPORTANTE: primero ejecutar MAAS_04_PREPARAR_STAGING_GMAIL.sql en SSMS,
con respaldo previo de MAAS_ECOLOGIA_4. No ejecutar aun 05, 06 ni el maestro:
los hechos y las dimensiones necesitan adaptarse a los nuevos seguimientos.

No borra ni actualiza filas anteriores. Inserta cada fuente por separado dentro
de una transaccion global (todo o nada). Gmail se conserva separado de Drive;
sus valores NO pasan a las ventas ni a las fechas operacionales sin aprobación.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("Falta pandas/openpyxl: py -m pip install pandas openpyxl")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "datos_fuente" / "ultima_extraccion.json"
REPORT = ROOT / "datos_transformados" / "reporte_validacion.json"
CSV_DIR = ROOT / "datos_transformados"
DB = "MAAS_ECOLOGIA_4"
DEFAULT_SERVER = r"Giuli\GIULIANA"
STATIC = {"bsc", "ventas", "caja"}
GMAIL_SOURCES = {
    "gmail_cierres": ("STG_GMAIL_CIERRE_MENSUAL", "cierres_facturacion.csv", "gmail_cierres_facturacion.csv"),
    "gmail_contratos": ("STG_GMAIL_CONTRATO", "contratos_pdf.csv", "gmail_contratos_pdf.csv"),
}
GMAIL_BASE = ROOT / "datos_fuente" / "gmail"

# Todas las listas incluyen exclusivamente columnas de datos; CargaID se agrega al INSERT.
# Se mantienen las columnas de las 6 tablas antiguas para no romper el modelo previo.
SCHEMA = {
    "STG_BSC_KPI": ["FilaExcel", "FechaReferencia", "Categoria", "NombreKPI", "Detalle", "MetaOriginal", "MetaNumerica", "AcumuladoOriginal", "AcumuladoNumerico", "AvanceAcumulado", "AvanceProyectado", "Cumplimiento", "Responsable", "Peso", "Anotacion", "PendienteValidacion"],
    "STG_KPI_DEPARTAMENTO": ["NombreHoja", "Departamento", "FilaExcel", "Categoria", "NombreKPI", "MetaOriginal", "MetaNumerica", "AcumuladoOriginal", "AcumuladoNumerico", "AvanceAcumulado", "Cumplimiento", "Peso", "Observacion"],
    "STG_BD_KPI": ["FilaExcel", "ColumnaExcel", "NombreKPIOriginal", "TipoContenido", "ValorOriginal", "ValorNumerico"],
    "STG_PROYECTO": ["FilaExcel", "NombreProyecto", "VentaOC_CLP", "MargenObjetivo", "MargenActual", "AvanceOriginal", "AvanceNormalizado", "MargenProyectado", "TipoProyecto", "NoCumple", "FechaReferencia"],
    "STG_VENTA_DETALLE": ["FilaExcel", "Emitido", "TipoDocumento", "Folio", "FechaDocumento", "RutCliente", "CodigoCliente", "RazonSocial", "CiudadCliente", "ComunaCliente", "SucursalCliente", "TipoVenta", "Descuento_CLP", "Recargo_CLP", "Exento_CLP", "Neto_CLP", "IVA_CLP", "Total_CLP", "Pagado", "CodigoVendedor", "UsuarioRegistro", "Observacion", "FilaOriginalJSON"],
    "STG_VENTA_RESUMEN": ["FilaExcel", "TipoDocumento", "Cantidad", "Descuento_CLP", "Recargo_CLP", "Impuesto_CLP", "Exento_CLP", "Neto_CLP", "IVA_CLP", "Total_CLP", "FilaOriginalJSON"],
    "STG_CAJA_MENSUAL": ["FilaExcel", "Mes", "SaldoInicial_CLP", "IngresosCobrados_CLP", "EgresosPagados_CLP", "SaldoFinal_CLP", "BrechaCaja_CLP", "HuboQuiebre", "OrigenDatos", "Observacion"],
    "STG_PROYECTO_RESUMEN": ["CodigoProyecto", "NumeroProyecto", "NombreProyecto", "FechaInicioPlan", "FechaTerminoPlan", "HH_Planificadas", "HH_Reales", "CostoPlanificado_CLP", "CostoReal_CLP", "TareasTotal", "TareasFinalizadas", "OrigenDatos"],
    "STG_PROYECTO_GANTT": ["CodigoProyecto", "NumeroProyecto", "NombreProyecto", "FilaExcel", "CodigoTarea", "NombreTarea", "FechaInicioPlan", "FechaTerminoPlan", "DuracionDias", "HH_Planificadas", "CostoPlanificado_CLP", "TareaPredecesora", "EstadoTarea", "OrigenDatos"],
    "STG_TAREA": ["CodigoProyecto", "NumeroProyecto", "NombreProyecto", "FilaExcel", "CodigoTarea", "NombreTarea", "RecursoPrincipal", "FechaInicioPlan", "FechaTerminoPlan", "HH_Planificadas", "HH_Reales", "CostoPlanificado_CLP", "CostoReal_CLP", "AvanceTarea", "EstadoTarea", "OrigenDatos"],
    "STG_RECURSO": ["CodigoProyecto", "NumeroProyecto", "NombreProyecto", "FilaExcel", "NombreRecurso", "Unidad", "CantidadPlanificada", "CantidadUtilizada", "CantidadRestante", "PorcentajeUtilizacion", "OrigenDatos"],
    "STG_ADJUDICACION": ["CodigoProyecto", "NumeroProyecto", "NombreProyecto", "FilaExcel", "NumeroPropuesta", "Cliente", "CategoriaKPI", "EstadoAdjudicacion", "FechaAdjudicacion", "Anio", "Monto_CLP", "OrigenDatos", "Adjudicada"],
    "STG_GMAIL_CIERRE_MENSUAL": ["Periodo", "Facturado_CLP", "Pendiente_CLP", "CriterioFacturacion", "GmailMessageID", "FechaCorreoUTC", "OrigenDatos", "EstadoValidacion"],
    "STG_GMAIL_CONTRATO": ["NombreProyecto", "ProyectoNormalizado", "CodigoProyectoBSC", "NombreProyectoBSC", "EstadoVinculacion", "FechaInicio", "FechaTermino", "MontoContractual_CLP", "GmailMessageID", "FechaCorreoUTC", "ArchivoPDF", "SHA256PDF", "OrigenDatos", "EstadoValidacion", "CoincideBSC"],
}
BASE_TABLES = {
    "bsc": ["STG_BSC_KPI", "STG_KPI_DEPARTAMENTO", "STG_BD_KPI", "STG_PROYECTO"],
    "ventas": ["STG_VENTA_DETALLE", "STG_VENTA_RESUMEN"],
    "caja": ["STG_CAJA_MENSUAL"],
    "gmail_cierres": ["STG_GMAIL_CIERRE_MENSUAL"],
    "gmail_contratos": ["STG_GMAIL_CONTRATO"],
}
PROJECT_TABLES = ["STG_PROYECTO_RESUMEN", "STG_PROYECTO_GANTT", "STG_TAREA", "STG_RECURSO", "STG_ADJUDICACION"]
DEPT = {"CONTRATOS": "CONTRATOS Y NEGOCIOS", "ADMINISTRACION": "ADMINISTRACION Y CONTROL", "INGENIERIA": "INGENIERIA Y PROPUESTAS", "OPERACIONES": "OPERACIONES"}


def empty(x):
    if x is None:
        return True
    if isinstance(x, str):
        return x.strip().lower() in ("", "nan", "none", "nat")
    try:
        return bool(pd.isna(x))
    except (ValueError, TypeError):
        return False


def txt(x, maxlen=None):
    if empty(x):
        return None
    v = x.isoformat() if isinstance(x, (date, datetime, pd.Timestamp)) else str(x).strip()
    if maxlen is not None and len(v) > maxlen:
        raise ValueError(f"Texto supera límite SQL ({maxlen}): {v[:80]}")
    return v


def integer(x):
    if empty(x):
        return None
    d = Decimal(str(x))
    if not d.is_finite() or d != d.to_integral_value():
        raise ValueError(f"Se esperaba un entero: {x!r}")
    return int(d)


def number(x):
    if empty(x):
        return None
    s = str(x).strip().replace("%", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"Número inválido: {x!r}") from exc
    if not d.is_finite():
        raise ValueError(f"Número NaN/infinito: {x!r}")
    return d / 100 if str(x).strip().endswith("%") else d


def bit(x):
    if empty(x):
        return None
    v = str(x).strip().lower()
    if v in ("1", "1.0", "true", "si", "sí"):
        return 1
    if v in ("0", "0.0", "false", "no"):
        return 0
    raise ValueError(f"Booleano inválido: {x!r}")


def day(x):
    if empty(x):
        return None
    if isinstance(x, (datetime, pd.Timestamp)):
        return x.date()
    if isinstance(x, date):
        return x
    s = str(x).strip()
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"Fecha no ISO YYYY-MM-DD: {x!r}") from exc


def utc_datetime(valor):
    if empty(valor):
        raise ValueError("Falta la fecha UTC de correo de Gmail")
    try:
        d = datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00"))
        if d.tzinfo is None:
            raise ValueError("Falta zona horaria")
        return d.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
    except ValueError as exc:
        raise ValueError(f"Fecha UTC de Gmail inválida: {valor!r}") from exc


def no_negativo(valor, campo):
    n = number(valor)
    if n is None or n < 0 or n != n.to_integral_value():
        raise ValueError(f"Monto CLP faltante/no entero/negativo en {campo}: {valor!r}")
    return n


def csv_rows(filename):
    path = CSV_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Falta {filename}; ejecuta antes 02 --ejecutar")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def original_json(row):
    def native(v):
        if empty(v):
            return None
        if isinstance(v, (date, datetime, pd.Timestamp)):
            return v.isoformat()
        if isinstance(v, (str, int, bool)):
            return v
        if isinstance(v, float):
            return v if math.isfinite(v) else None
        if hasattr(v, "item"):
            return native(v.item())
        return str(v)
    return json.dumps({str(k): native(v) for k, v in row.items()}, ensure_ascii=False, separators=(",", ":"))


def cargados_por_fuente():
    if not MANIFEST.is_file() or not REPORT.is_file():
        raise FileNotFoundError("Falta manifiesto o validación del paso 02")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    if rep.get("version_estructura") != "MAAS_20_FUENTES_GMAIL_V2" or rep.get("errores"):
        raise ValueError("Ejecuta el paso 02 actualizado con Gmail --ejecutar (reporte V2 sin errores)")
    fuentes = {}
    for ent in manifest.get("archivos", []):
        k = str(ent.get("fuente", "")).lower()
        if not k or k in fuentes:
            raise ValueError(f"Fuente vacía o duplicada: {k!r}")
        if k not in STATIC and not re.fullmatch(r"proyecto_\d{2,}", k):
            raise ValueError(f"Fuente no autorizada: {k}")
        path = (ROOT / str(ent.get("ruta_local", ""))).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            raise ValueError(f"Ruta local inválida: {k}")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha != ent.get("version_sha256"):
            raise ValueError(f"Archivo fuente modificado desde la extracción: {k}")
        if sha != rep.get("versiones_fuente_sha256", {}).get(k):
            raise ValueError(f"Fuente {k}: paso 01 distinto al paso 02; vuelve a transformarlo")
        if str(path) != str(rep.get("fuentes", {}).get(k)):
            raise ValueError(f"Fuente {k}: ubicación distinta a la usada en el paso 02")
        fuentes[k] = {"path": path, "meta": ent}
    projects = sorted(k for k in fuentes if k.startswith("proyecto_"))
    nums = sorted(int(k.split("_")[1]) for k in projects)
    if set(fuentes) != STATIC | set(projects) or len(projects) < 17 or nums != list(range(1, max(nums) + 1)):
        raise ValueError("Las fuentes esperadas son bsc, ventas, caja y proyectos numerados sin saltos (mínimo 17)")
    # Se exige que los CSV sean los publicados por el paso 02 y no editados después.
    for name in rep.get("csv_generados", []):
        archivo_csv = CSV_DIR / name
        if not archivo_csv.is_file():
            raise FileNotFoundError(f"CSV del paso 02 ausente: {name}")
        if archivo_csv.stat().st_mtime > REPORT.stat().st_mtime + 1:
            raise ValueError(f"CSV alterado luego de validar: {name}; reejecuta el paso 02")
    # Un reporte de versión vigente debe publicarse DESPUÉS de las fuentes.
    if REPORT.stat().st_mtime < max(x["path"].stat().st_mtime for x in fuentes.values()) - 1:
        raise ValueError("El reporte de validación es anterior a los Excel; vuelve a ejecutar el paso 02")

    # Gmail se valida como 2 fuentes independientes del manifiesto Drive. Su
    # auditoría y sus archivos se comparan byte a byte con el reporte del 02.
    gmail = rep.get("gmail") or {}
    nombres = ("cierres_facturacion.csv", "contratos_pdf.csv", "auditoria_gmail.json")
    if gmail.get("consulta") != "label:MAAS-ETL":
        raise ValueError("Reporte Gmail sin etiqueta MAAS-ETL; repetir paso 02")
    for nombre in nombres:
        path = (GMAIL_BASE / nombre).resolve()
        esperado = str(path)
        if not path.is_file() or str(gmail.get("archivos", {}).get(nombre)) != esperado:
            raise ValueError(f"Gmail {nombre}: archivo o ruta distinta a paso 02")
        if hashlib.sha256(path.read_bytes()).hexdigest() != gmail.get("sha256", {}).get(nombre):
            raise ValueError(f"Gmail {nombre}: contenido modificado desde paso 02")
        if path.stat().st_mtime > REPORT.stat().st_mtime + 1:
            raise ValueError(f"Gmail {nombre}: más reciente que el reporte del paso 02")
    for nombre_fuente, (_, nombre_origen, nombre_csv) in GMAIL_SOURCES.items():
        if nombre_csv not in rep.get("csv_generados", []):
            raise ValueError(f"Gmail: falta CSV {nombre_csv} en reporte de paso 02")
        fuentes[nombre_fuente] = {
            "path": (GMAIL_BASE / nombre_origen).resolve(),
            "meta": {
                "id_drive": "MAAS:GMAIL:MAAS-ETL:" + nombre_fuente.upper(),
                "nombre_drive": "Gmail MAAS-ETL: " + nombre_fuente,
            },
        }
    return fuentes, rep, projects


def build_dataset():
    fuentes, rep, projects = cargados_por_fuente()
    datos = {k: {t: [] for t in (BASE_TABLES[k] if k in BASE_TABLES else PROJECT_TABLES)} for k in fuentes}
    bsc = datos["bsc"]
    for r in csv_rows("bsc_global.csv"):
        bsc["STG_BSC_KPI"].append((
            integer(r["fila_excel"]), day(r["fecha_referencia"]), txt(r["categoria"], 100), txt(r["nombre_kpi"], 300),
            txt(r["detalle"]), txt(r["meta_original"], 100), number(r["meta_numerica"]),
            txt(r["acumulado_original"], 100), number(r["acumulado_numerico"]), number(r["avance_acumulado"]),
            number(r["avance_proyectado"]), number(r["cumplimiento"]), txt(r["responsable"], 150),
            number(r["peso"]), txt(r["anotacion"], 500), bit(r["pendiente_validacion"])))
    for r in csv_rows("bsc_departamentos.csv"):
        hoja = txt(r["hoja"])
        if hoja not in DEPT:
            raise ValueError(f"Departamento inesperado: {hoja}")
        bsc["STG_KPI_DEPARTAMENTO"].append((
            hoja, DEPT[hoja], integer(r["fila_excel"]), txt(r["categoria"], 100), txt(r["nombre_kpi"], 300),
            txt(r["meta_original"], 100), number(r["meta_numerica"]), txt(r["acumulado_original"], 100),
            number(r["acumulado_numerico"]), number(r["avance_acumulado"]), number(r["cumplimiento"]), number(r["peso"]), None))
    raw = pd.read_excel(fuentes["bsc"]["path"], sheet_name="BD", header=None, dtype=object)
    for j in range(1, raw.shape[1]):
        titulo = txt(raw.iat[0, j], 300)
        if not titulo:
            continue
        for i in range(1, len(raw)):
            v = raw.iat[i, j]
            if empty(v):
                continue
            tipo = {1: "DETALLE", 2: "FUENTE", 3: "VALOR"}.get(i, "EVIDENCIA")
            bsc["STG_BD_KPI"].append((i + 1, j + 1, titulo, tipo, txt(v), number(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else None))
    # STG_PROYECTO mantiene estructura y orden anteriores para compatibilidad con DIM_PROYECTO.
    corte = next((r[1] for r in bsc["STG_BSC_KPI"] if r[1] is not None), None)
    proyectos = csv_rows("proyectos_bsc.csv")
    for r in proyectos:
        bsc["STG_PROYECTO"].append((
            integer(r["fila_excel"]), txt(r["nombre_proyecto"], 350), number(r["venta_oc_clp"]),
            number(r["margen_objetivo"]), number(r["margen_actual"]), txt(r["avance_bsc"], 80),
            None, number(r["margen_proyectado"]), txt(r["tipo_proyecto"], 100),
            bit(r["no_cumple_original"]), corte))

    sales = datos["ventas"]
    raw_sale = pd.read_excel(fuentes["ventas"]["path"], sheet_name="DETALLE", dtype=object)
    for r in csv_rows("ventas_detalle.csv"):
        if bit(r["documento_duplicado"]) != 0:
            raise ValueError("Ventas duplicadas, detener carga")
        index = integer(r["fila_excel"]) - 2
        if not 0 <= index < len(raw_sale):
            raise ValueError("Ventas: índice de factura fuera del Excel")
        original = raw_sale.iloc[index].to_dict()
        if str(original.get("DOCUMENTO", "")).strip() != r["tipo_documento"].strip() or str(original.get("FOLIO", "")).strip() != r["folio"].strip():
            raise ValueError(f"Ventas: factura/folio distinto en la fila {r['fila_excel']}")
        if number(original.get("NETO")) != number(r["neto_clp"]):
            raise ValueError(f"Ventas: neto distinto fila {r['fila_excel']}")
        sales["STG_VENTA_DETALLE"].append((
            integer(r["fila_excel"]), txt(original.get("EMITIDO"), 10), txt(r["tipo_documento"], 100), txt(r["folio"], 50),
            day(r["fecha_documento"]), txt(r["rut_cliente"], 25), txt(original.get("CODIGO CLIENTE"), 50),
            txt(r["razon_social"], 300), txt(r["ciudad_cliente"], 150), txt(r["comuna_cliente"], 150),
            txt(original.get("SUCURSALCLIENTE"), 150), txt(original.get("TIPO DE VENTA"), 100),
            number(original.get("DESCUENTO")), number(original.get("RECARGO")), number(original.get("EXENTO")),
            number(r["neto_clp"]), number(r["iva_clp"]), number(r["total_clp"]),
            txt(original.get("PAGADO"), 10), txt(original.get("CODVENDEDOR"), 60),
            txt(original.get("USUARIO"), 150), txt(original.get("OBSERVACION")), original_json(original)))
    raw_sum = pd.read_excel(fuentes["ventas"]["path"], sheet_name="RESUMEN", dtype=object)
    for i, row in raw_sum.iterrows():
        if empty(row.get("DOCUMENTO")):
            continue
        sales["STG_VENTA_RESUMEN"].append((
            i + 2, txt(row.get("DOCUMENTO"), 100), integer(row.get("CANTIDAD")),
            number(row.get("DESCUENTO")), number(row.get("RECARGO")), number(row.get("IMPUESTO")),
            number(row.get("EXENTO")), number(row.get("NETO")), number(row.get("IVA")),
            number(row.get("TOTAL")), original_json(row.to_dict())))

    for r in csv_rows("caja_mensual.csv"):
        if txt(r["origen_datos"]) != "SIMULADO":
            raise ValueError("Caja sin indicación de datos SIMULADOS")
        datos["caja"]["STG_CAJA_MENSUAL"].append((
            integer(r["fila_excel"]), txt(r["mes"], 7), number(r["saldo_inicial_clp"]),
            number(r["ingresos_cobrados_clp"]), number(r["egresos_pagados_clp"]),
            number(r["saldo_final_clp"]), number(r["brecha_caja_clp"]), bit(r["hubo_quiebre"]),
            "SIMULADO", txt(r["observacion"], 500)))

    por_codigo = {r["codigo_proyecto"]: r for r in proyectos}
    # Los CSV de seguimiento son la fuente de proyectos adicionales al BSC.
    nuevos = csv_rows("proyectos_seguimiento_resumen.csv")
    nombres_usados = {str(r["nombre_proyecto"]).strip().casefold() for r in proyectos}
    for r in nuevos:
        cod = txt(r["codigo_proyecto"], 30)
        nombre = txt(r["nombre_proyecto"], 350)
        if cod not in por_codigo:
            if not nombre or nombre.casefold() in nombres_usados:
                raise ValueError(f"Seguimiento con nombre de proyecto duplicado: {nombre}")
            por_codigo[cod] = {"codigo_proyecto": cod, "nombre_proyecto": nombre}
            nombres_usados.add(nombre.casefold())
    # El diccionario enlaza cada CSV con la tabla STAGING correspondiente.
    fuentes_csv = {
        "proyectos_seguimiento_resumen.csv": "STG_PROYECTO_RESUMEN",
        "proyectos_gantt.csv": "STG_PROYECTO_GANTT",
        "proyectos_tareas.csv": "STG_TAREA",
        "proyectos_recursos.csv": "STG_RECURSO",
        "proyectos_adjudicaciones.csv": "STG_ADJUDICACION",
    }
    for file, tabla in fuentes_csv.items():
        for r in csv_rows(file):
            codigo = txt(r["codigo_proyecto"], 30)
            no = integer(r["numero_proyecto"])
            src = f"proyecto_{no:02d}"
            if src not in datos or codigo != f"PRY-2026-{no:03d}":
                raise ValueError(f"Proyecto no disponible o código erróneo: {codigo}")
            b = por_codigo.get(codigo)
            if b is None or txt(r["nombre_proyecto"]) != b["nombre_proyecto"]:
                raise ValueError(f"Proyecto sin correspondencia con seguimiento: {codigo}")
            if txt(r.get("origen_datos")) != "SIMULADO":
                raise ValueError(f"{tabla} {codigo}: faltan datos etiquetados SIMULADO")
            base = (codigo, no, txt(r["nombre_proyecto"], 350))
            if tabla == "STG_PROYECTO_RESUMEN":
                fila = base + (day(r["fecha_inicio_plan"]), day(r["fecha_termino_plan"]),
                    number(r["hh_planificadas"]), number(r["hh_reales"]), number(r["costo_planificado_clp"]),
                    number(r["costo_real_clp"]), integer(r["tareas_total"]), integer(r["tareas_finalizadas"]), "SIMULADO")
            elif tabla == "STG_PROYECTO_GANTT":
                fila = base + (integer(r["fila_excel"]), txt(r["codigo_tarea"], 40), txt(r["nombre_tarea"], 300),
                    day(r["fecha_inicio_plan"]), day(r["fecha_termino_plan"]), integer(r["duracion_dias"]),
                    number(r["hh_planificadas"]), number(r["costo_planificado_clp"]),
                    txt(r["tarea_predecesora"], 40), txt(r["estado_tarea"], 80), "SIMULADO")
            elif tabla == "STG_TAREA":
                fila = base + (integer(r["fila_excel"]), txt(r["codigo_tarea"], 40), txt(r["nombre_tarea"], 300),
                    txt(r["recurso_principal"], 200), day(r["fecha_inicio_plan"]), day(r["fecha_termino_plan"]),
                    number(r["hh_planificadas"]), number(r["hh_reales"]), number(r["costo_planificado_clp"]),
                    number(r["costo_real_clp"]), number(r["avance_tarea"]), txt(r["estado_tarea"], 80), "SIMULADO")
            elif tabla == "STG_RECURSO":
                fila = base + (integer(r["fila_excel"]), txt(r["nombre_recurso"], 200), txt(r["unidad"], 40),
                    number(r["cantidad_planificada"]), number(r["cantidad_utilizada"]), number(r["cantidad_restante"]),
                    number(r["porcentaje_utilizacion"]), "SIMULADO")
            else:
                fila = base + (integer(r["fila_excel"]), txt(r["numero_propuesta"], 100), txt(r["cliente"], 250),
                    txt(r["categoria_kpi"], 100), txt(r["estado_adjudicacion"], 80), day(r["fecha_adjudicacion"]),
                    integer(r["anio"]), number(r["monto_clp"]), "SIMULADO", bit(r["adjudicada"]))
            if len(fila) != len(SCHEMA[tabla]):
                raise RuntimeError(f"Error interno: columnas de {tabla}")
            datos[src][tabla].append(fila)

    # Gmail: solo informacion comercial/contractual; nunca modifica hojas ni
    # STG_TAREA, STG_RECURSO, STG_PROYECTO_GANTT o STG_VENTA_DETALLE.
    cierres_vistos = set()
    for r in csv_rows("gmail_cierres_facturacion.csv"):
        clave = (txt(r["gmail_message_id"], 80), txt(r["periodo"], 7))
        if not clave[0] or not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", clave[1] or ""):
            raise ValueError("Gmail: identificador o periodo de cierre invalido")
        if clave in cierres_vistos:
            raise ValueError("Gmail: cierre duplicado en el mismo mensaje y periodo")
        cierres_vistos.add(clave)
        origen = txt(r["origen_datos"], 30)
        if origen not in ("REAL", "SIMULADO"):
            raise ValueError("Gmail: origen del cierre debe ser REAL o SIMULADO")
        datos["gmail_cierres"]["STG_GMAIL_CIERRE_MENSUAL"].append((
            clave[1], no_negativo(r["facturado_clp"], "facturado_clp"),
            no_negativo(r["pendiente_clp"], "pendiente_clp"),
            txt(r["criterio_facturacion"], 100), clave[0],
            utc_datetime(r["fecha_correo_utc"]), origen,
            txt(r["estado_validacion"], 80),
        ))
    contratos_vistos = set()
    for r in csv_rows("gmail_contratos_pdf.csv"):
        mid = txt(r["gmail_message_id"], 80)
        sha = txt(r["sha256_pdf"], 64)
        if not mid or not sha or not re.fullmatch(r"[a-f0-9]{64}", sha):
            raise ValueError("Gmail: identificador/hash invalido en contrato")
        if sha in contratos_vistos:
            raise ValueError(f"Gmail: PDF repetido dentro de la misma extraccion: {sha}")
        contratos_vistos.add(sha)
        inicio, termino = day(r["fecha_inicio"]), day(r["fecha_termino"])
        if not inicio or not termino or termino < inicio:
            raise ValueError("Gmail: fechas de contrato faltantes o invertidas")
        origen = txt(r["origen_datos"], 30)
        if origen not in ("REAL", "SIMULADO"):
            raise ValueError("Gmail: origen del contrato debe ser REAL o SIMULADO")
        codigo = txt(r["codigo_proyecto_bsc"], 30)
        vinculacion = txt(r["estado_vinculacion"], 40)
        if (codigo and vinculacion not in ("VINCULADO_BSC", "VINCULADO_SEGUIMIENTO")) or (not codigo and vinculacion != "PENDIENTE_VINCULACION"):
            raise ValueError("Gmail: codigo de proyecto y vinculacion inconsistentes")
        if codigo and codigo not in por_codigo:
            raise ValueError(f"Gmail: codigo de proyecto no disponible en seguimiento: {codigo}")
        flag = txt(r["coincide_bsc"], 2)
        if flag != ("SI" if vinculacion == "VINCULADO_BSC" else "NO"):
            raise ValueError("Gmail: coincide_bsc inconsistente")
        datos["gmail_contratos"]["STG_GMAIL_CONTRATO"].append((
            txt(r["nombre_proyecto"], 350), txt(r["proyecto_normalizado"], 350),
            codigo, txt(r["nombre_proyecto_bsc"], 350), vinculacion,
            inicio, termino, no_negativo(r["monto_contractual_clp"], "monto_contractual_clp"),
            mid, utc_datetime(r["fecha_correo_utc"]), txt(r["archivo_pdf"], 260),
            sha, origen, txt(r["estado_validacion"], 80), flag,
        ))
    # Orden determinista para que la huella no dependa del orden de Gmail.
    datos["gmail_cierres"]["STG_GMAIL_CIERRE_MENSUAL"].sort(key=lambda row: (row[4], row[0]))
    datos["gmail_contratos"]["STG_GMAIL_CONTRATO"].sort(key=lambda row: (row[9], row[11]))

    # Comprobación de conteos frente al reporte validado del paso 02.
    previstos = rep["conteos"]
    pruebas = {
        "kpi_global": len(bsc["STG_BSC_KPI"]),
        "kpi_departamentales_filas": len(bsc["STG_KPI_DEPARTAMENTO"]),
        "proyectos_bsc": len(bsc["STG_PROYECTO"]),
        "documentos_ventas": len(sales["STG_VENTA_DETALLE"]),
        "meses_caja": len(datos["caja"]["STG_CAJA_MENSUAL"]),
        "proyectos_con_seguimiento": sum(len(datos[k]["STG_PROYECTO_RESUMEN"]) for k in projects),
        "proyectos_gantt": sum(len(datos[k]["STG_PROYECTO_GANTT"]) for k in projects),
        "proyectos_tareas": sum(len(datos[k]["STG_TAREA"]) for k in projects),
        "proyectos_recursos": sum(len(datos[k]["STG_RECURSO"]) for k in projects),
        "proyectos_adjudicaciones": sum(len(datos[k]["STG_ADJUDICACION"]) for k in projects),
        "gmail_cierres": len(datos["gmail_cierres"]["STG_GMAIL_CIERRE_MENSUAL"]),
        "gmail_contratos": len(datos["gmail_contratos"]["STG_GMAIL_CONTRATO"]),
    }
    for nombre, cantidad in pruebas.items():
        if nombre not in previstos or int(previstos[nombre]) != cantidad:
            raise ValueError(f"Descuadre {nombre}: {cantidad} vs reporte del paso 02 ({previstos.get(nombre)})")
    # Se mantienen los 15 KPI originales y se incorpora Margen Operativo.
    nombres_bsc = [str(fila[3] or "").strip().casefold() for fila in bsc["STG_BSC_KPI"]]
    if len(nombres_bsc) != 16 or nombres_bsc.count("margen operativo") != 1:
        raise ValueError(
            "BSC: se esperan 16 KPI globales, incluido Margen Operativo una sola vez; "
            f"encontrados {len(nombres_bsc)} KPI y "
            f"{nombres_bsc.count('margen operativo')} registros Margen Operativo"
        )
    if any(not rows for nombre, source in datos.items()
           if nombre not in GMAIL_SOURCES for rows in source.values()):
        raise ValueError("STAGING de alguna fuente Drive sin filas; revisar la fuente")
    suma_neto = sum((row[15] or Decimal(0)) for row in sales["STG_VENTA_DETALLE"])
    total = [row for row in sales["STG_VENTA_RESUMEN"] if (row[1] or "").strip().upper() == "TOTAL"]
    if len(total) != 1 or suma_neto != total[0][7] or suma_neto != number(previstos["ventas_netas_clp"]):
        raise ValueError("Venta DETALLE y RESUMEN no concilian: carga bloqueada")
    for proyecto in projects:
        resumen = datos[proyecto]["STG_PROYECTO_RESUMEN"]
        if len(resumen) != 1:
            raise ValueError(f"Seguimiento resumen de {proyecto} debe tener exactamente 1 fila")
        ts = {r[4] for r in datos[proyecto]["STG_TAREA"]}
        gs = {r[4] for r in datos[proyecto]["STG_PROYECTO_GANTT"]}
        if len(ts) != len(datos[proyecto]["STG_TAREA"]) or ts != gs or len(ts) != resumen[0][9]:
            raise ValueError(f"Tareas y Gantt no concilian: {proyecto}")
        rs = {r[4] for r in datos[proyecto]["STG_ADJUDICACION"]}
        if len(rs) != len(datos[proyecto]["STG_ADJUDICACION"]):
            raise ValueError(f"Propuestas duplicadas en {proyecto}")
    return fuentes, datos


def fingerprint(tables):
    def serial(x):
        return x.isoformat() if isinstance(x, date) else str(x) if isinstance(x, Decimal) else x
    blob = json.dumps([[name, [[serial(v) for v in row] for row in rows]] for name, rows in sorted(tables.items())],
                      ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def conectar(servidor):
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("Falta pyodbc. Ejecuta: py -m pip install pyodbc") from exc
    drv = next((x for x in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server") if x in pyodbc.drivers()), None)
    if not drv:
        raise RuntimeError("Falta ODBC Driver 17/18 de SQL Server")
    cstr = (f"DRIVER={{{drv}}};SERVER={servidor};DATABASE={DB};Trusted_Connection=yes;"
            "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=10;Application Name=MAAS_STAGING_20;")
    return pyodbc.connect(cstr, autocommit=False, timeout=10)


def comprobar_sql(conn):
    cur = conn.cursor()
    found = {r[0] for r in cur.execute("SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('dbo')")}
    faltan = sorted((set(SCHEMA) | {"ETL_CARGA"}) - found)
    if faltan:
        raise RuntimeError("Faltan tablas STAGING; prepara primero el SQL nuevo: " + ", ".join(faltan))
    for table, columns in SCHEMA.items():
        existentes = {r[0] for r in cur.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?)", f"dbo.{table}")}
        faltan_col = sorted((set(columns) | {"CargaID"}) - existentes)
        if faltan_col:
            raise RuntimeError(f"Columnas faltantes en {table}: {faltan_col}")
    # Validar CHECK para fallar ANTES de intentar una carga de 20 fuentes.
    check = cur.execute("SELECT definition FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('dbo.ETL_CARGA') AND name='CK_ETL_CARGA_Tipo'").fetchone()
    if not check or any(tipo not in str(check[0]).upper()
                        for tipo in ("PROYECTO", "CAJA", "GMAIL_CIERRES", "GMAIL_CONTRATOS")):
        raise RuntimeError("Falta habilitar GMAIL_CIERRES y GMAIL_CONTRATOS en CK_ETL_CARGA_Tipo")
    return True


def cargar(servidor, fuentes, data):
    conn = conectar(servidor)
    try:
        comprobar_sql(conn)
        cur = conn.cursor()
        cur.execute("SET XACT_ABORT ON")
        # Una única transacción: o se guardan las fuentes Drive y Gmail, o ninguna.
        for codigo in ["bsc", "ventas", "caja", *sorted(k for k in fuentes if k.startswith("proyecto_")),
                       "gmail_cierres", "gmail_contratos"]:
            tablas = data[codigo]
            sha = fingerprint(tablas)
            info = fuentes[codigo]["meta"]
            fid = info.get("id_drive")
            if not fid:
                raise ValueError(f"La fuente {codigo} no tiene identificador Drive")
            count = sum(map(len, tablas.values()))
            if count == 0 and codigo in GMAIL_SOURCES:
                print(f"  {codigo:14s}: SIN REGISTROS (no se crea CargaID)")
                continue
            existente = cur.execute("SELECT CargaID, Estado FROM dbo.ETL_CARGA WHERE IdArchivoDrive=? AND HashArchivoSHA256=?", fid, sha).fetchone()
            if existente:
                if existente[1] != "OK":
                    raise RuntimeError(f"Carga anterior de {codigo} sin estado OK: {existente[1]}")
                print(f"  {codigo:14s}: SIN CAMBIOS (CargaID {existente[0]})")
                continue
            row = cur.execute("""INSERT INTO dbo.ETL_CARGA
                    (TipoFuente, IdArchivoDrive, NombreArchivo, HashArchivoSHA256, Estado, Observaciones)
                    OUTPUT INSERTED.CargaID VALUES (?,?,?,?,?,?)""",
                codigo.upper(), fid, txt(info.get("nombre_drive"), 260) or codigo, sha, "EN_PROCESO",
                ("Gmail MAAS-ETL; SIN APROBACION; no conciliar con ventas ni reemplazar fechas Gantt. "
                 if codigo in GMAIL_SOURCES else
                 "Origen BSC/VENTAS o SIMULADO (CAJA/PROYECTOS). ") +
                "Huella semantica por fuente.").fetchone()
            carga_id = int(row[0])
            for table, rows in tablas.items():
                columnas = ["CargaID", *SCHEMA[table]]
                sql = "INSERT INTO dbo.[" + table + "] (" + ",".join(f"[{x}]" for x in columnas) + ") VALUES (" + ",".join("?" for _ in columnas) + ")"
                cur.executemany(sql, [(carga_id, *r) for r in rows])
            cur.execute("UPDATE dbo.ETL_CARGA SET Estado='OK', FinUTC=SYSUTCDATETIME(), TotalFilas=? WHERE CargaID=?", count, carga_id)
            print(f"  {codigo:14s}: preparado CargaID {carga_id} | {count} filas")
        conn.commit()
        print("COMMIT OK: todas las fuentes confirmadas en SQL")
    except Exception:
        conn.rollback()
        print("ROLLBACK: se revirtieron las inserciones de esta ejecución.", file=sys.stderr)
        raise
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="ETL MAAS 4: STAGING de Drive + Gmail")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verificar", action="store_true", help="Solo validar CSV; sin SQL")
    mode.add_argument("--comprobar-sql", action="store_true", help="Solo comprobar tablas/columnas SQL")
    mode.add_argument("--cargar", action="store_true", help="Insertar versiones nuevas en SQL STAGING")
    ap.add_argument("--servidor", default=DEFAULT_SERVER)
    args = ap.parse_args()
    fuentes, datos = build_dataset()
    print("\nMAAS 4 | PASO 04 | " + ("VERIFICACIÓN SIN SQL" if args.verificar else "COMPROBACIÓN SQL" if args.comprobar_sql else "CARGA STAGING"))
    print(f"Fuentes coherentes con pasos 01 y 02: 20 Drive + 2 Gmail ({len(fuentes)} en total)")
    for nombre in ["bsc", "ventas", "caja"]:
        print(f"  {nombre.upper():8s} | " + " | ".join(f"{t}: {len(rows)}" for t, rows in datos[nombre].items()))
    proyectos = [k for k in fuentes if k.startswith("proyecto_")]
    print(f"  PROYECTOS: {len(proyectos)} fuentes; " + "; ".join(
        f"{t}={sum(len(datos[p][t]) for p in proyectos)}" for t in PROJECT_TABLES))
    print("  GMAIL    | " + " | ".join(
        f"{k}: {sum(map(len, datos[k].values()))}" for k in GMAIL_SOURCES))
    if args.verificar:
        print("\nVERIFICACIÓN OK. No se conectó a SQL Server.")
        print("SIGUIENTE: ejecutar MAAS_04_PREPARAR_STAGING_GMAIL.sql con respaldo antes de --cargar.")
        return 0
    if args.comprobar_sql:
        conn = conectar(args.servidor)
        try:
            comprobar_sql(conn)
            print("\nSQL OK: tablas y columnas listas. No se insertaron registros.")
        finally:
            conn.close()
        return 0
    print("\nInsertando versiones nuevas en una transacción global. No se borra historial.")
    cargar(args.servidor, fuentes, datos)
    print("\nSTAGING OK. No ejecutar aun los pasos 05, 06 ni ETL maestro hasta adaptarlos.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"ERROR PASO 04: {e}", file=sys.stderr)
        sys.exit(1)
