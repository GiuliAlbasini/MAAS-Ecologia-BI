# -*- coding: utf-8 -*-
"""MAAS_ECOLOGIA_4 | PASO 06 | HECHOS con proyectos dinamicos + 2 Gmail.

Verifica siempre antes de cargar:
  py .\06_verificar_y_cargar_hechos.py --verificar
  py .\06_verificar_y_cargar_hechos.py --cargar

ADVERTENCIAS:
- Requiere ejecutar MAAS_06_PREPARAR_FACT_22_FUENTES.sql con respaldo ANTES de cargar.
- No borra, renombra ni reemplaza hechos historicos. Una vista de compatibilidad
  proporciona FACT_PROYECTO_ESTRATEGICO hasta adaptar Streamlit.
- 15 KPI BSC, 44 filas departamentales conciliadas y ventas del Excel se mantienen.
- Gmail NO se suma a ventas. Contratos pendientes se guardan como tales, sin
  modificar planificaciones. Los datos de proyecto/caja/Gmail de prueba son simulados.
- Los 11 KPI operacionales legados basados en la vista SQL V12 NO se publican
  ni recalculan hasta adaptar esa vista al nuevo grano de tareas.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from bsc_identidades_estables import registro_para_carga, codigo_para_fila, codigo_para_departamento

DB = "MAAS_ECOLOGIA_4"
SERVER = r"Giuli\GIULIANA"
KPI_COMERCIALES = {
    "COM_VENTAS_NETAS_MES": "ventas_mes",
    "COM_FACTURAS_MES": "facturas_mes",
    "COM_CLIENTES_MES": "clientes_mes",
    "COM_TICKET_MES": "ticket_mes",
    "COM_VENTA_CLIENTE_MES": "venta_cliente_mes",
    "COM_VENTAS_ACUM_ANIO": "ventas_acumuladas_anio",
    "COM_VARIACION_MENSUAL_PCT": "variacion_mes_pct",
    "COM_PRIMERA_COMPRA_OBSERVADA_MES": "primera_compra_observada_mes",
    "COM_PARTICIPACION_CLIENTE_MES_PCT": "participacion_cliente_mes_pct",
}
KPI_COLS = (
    "KPI_Key", "Fecha_Key", "Area_Key", "Cliente_Key", "Responsable_Key",
    "Ambito", "GranoTemporal", "MetaNumerica", "MetaTexto", "ResultadoNumerico",
    "ResultadoTexto", "Avance", "Cumplimiento", "Ponderacion", "FuenteResultado",
    "EsSimulado", "CargaID",
)
# Columnas antiguas de la FACT operacional, sin cambiar su semantica.
OP_COLS = (
    "TipoRegistro", "IDOrigen", "Proyecto_Key", "Fecha_Evento_Key",
    "Responsable_Key", "Costo_Key", "Fecha_InicioPlan_Key",
    "Fecha_TerminoPlan_Key", "Fecha_TerminoReal_Key", "VentaOC_CLP",
    "MargenObjetivo", "MargenActual", "MargenProyectado", "NoCumpleOriginal",
    "CostoPresupuestado_CLP", "EstadoProyecto", "Monto_Costo_CLP",
    "Observaciones", "FuenteDato", "EsSimulado", "CargaID",
)
# Nuevas columnas: medidas solo en FACT, descripciones en DIM_TAREA.
OP_EXTRA = (
    "Tarea_Key", "HH_Planificadas", "HH_Reales", "CostoRealTarea_CLP",
    "AvanceTarea", "CantidadPlanificada", "CantidadUtilizada", "CantidadRestante",
    "PorcentajeUtilizacion", "NombreRecurso", "UnidadRecurso", "Adjudicada",
    "NumeroPropuesta", "MontoAdjudicado_CLP", "FechaAdjudicacion_Key",
    "FechaInicioContrato_Key", "FechaTerminoContrato_Key", "MontoContractual_CLP",
    "EstadoValidacion", "EstadoVinculacion", "DocumentoHash",
)
NEW_TYPES = {"PROYECTO", "TAREA", "RECURSO", "ADJUDICACION", "CONTRATO"}
TECH_KPIS = {"GMAIL_FACTURADO_MES", "GMAIL_PENDIENTE_MES", "CAJA_BRECHA_MES"}


def clean(v):
    return " ".join(str(v).strip().split()) if v is not None else ""

def norm(v):
    v = unicodedata.normalize("NFKD", clean(v))
    v = v.encode("ascii", "ignore").decode("ascii").lower()
    return "_".join(re.findall(r"[a-z0-9]+", v))

def rut(v):
    return re.sub(r"[^0-9K]", "", clean(v).upper())

def dte(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    raise ValueError(f"Formato de fecha inesperado en SQL: {v!r}")

def datekey(v):
    v = dte(v)
    return int(v.strftime("%Y%m%d")) if v is not None else None

def number(v):
    return Decimal(str(v)) if v is not None else None

def money(v):
    return number(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def rows(cur, query, *args):
    cur.execute(query, *args)
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, x)) for x in cur.fetchall()]

def connect(server):
    try:
        import pyodbc
    except ImportError as e:
        raise RuntimeError("Instalar pyodbc: py -m pip install pyodbc") from e
    driver = next((x for x in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server")
                   if x in pyodbc.drivers()), None)
    if not driver:
        raise RuntimeError("Falta ODBC Driver 17 o 18 para SQL Server")
    return pyodbc.connect(
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={DB};"
        "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
        "Connection Timeout=10;Application Name=MAAS_ETL_FACT_PASO06;",
        autocommit=False, timeout=20,
    )

def fk(mapping, category, key, context):
    value = mapping[category].get(key)
    if value is None:
        raise ValueError(f"Falta dimension {category}, clave={key!r}, contexto={context}")
    return value


def make_kpi(kpi, fecha, area, cliente, responsable, ambito, granularidad,
             meta, meta_texto, resultado, resultado_texto, avance, cumplimiento,
             ponderacion, fuente, simulado, carga):
    return (kpi, fecha, area, cliente, responsable, ambito, granularidad,
            number(meta), clean(meta_texto) or None, number(resultado),
            clean(resultado_texto) or None, number(avance), number(cumplimiento),
            number(ponderacion), fuente, int(simulado), carga)

def build_strategic(cur, ids, dims):
    bsc = rows(cur, """SELECT FilaExcel,FechaReferencia,NombreKPI,Responsable,
        MetaOriginal,MetaNumerica,AcumuladoOriginal,AcumuladoNumerico,
        AvanceAcumulado,Cumplimiento,Peso
        FROM dbo.STG_BSC_KPI WHERE CargaID=? ORDER BY FilaExcel""", ids["BSC"])
    dep = rows(cur, """SELECT Departamento,NombreKPI,MetaOriginal,MetaNumerica,
        AcumuladoOriginal,AcumuladoNumerico,AvanceAcumulado,Cumplimiento,Peso,
        FilaExcel,NombreHoja
        FROM dbo.STG_KPI_DEPARTAMENTO WHERE CargaID=? ORDER BY NombreHoja,FilaExcel""", ids["BSC"])
    sales = rows(cur, """SELECT TipoDocumento,Folio,FechaDocumento,RutCliente,Neto_CLP
        FROM dbo.STG_VENTA_DETALLE WHERE CargaID=? ORDER BY FilaExcel""", ids["VENTAS"])
    if not bsc or not dep or not sales:
        raise ValueError("STAGING BSC/VENTAS incompleto")
    identidades=registro_para_carga(cur,ids['BSC'],Path(__file__).resolve().parent)
    fact = []
    bsc_day = set()
    official_by_norm = {}
    for r in bsc:
        kpi_norm = norm(r["NombreKPI"])
        code = codigo_para_fila(identidades,r["FilaExcel"],r["NombreKPI"])
        key = fk(dims, "kpis", code, r["NombreKPI"])
        official_by_norm[kpi_norm] = key
        day = datekey(r["FechaReferencia"])
        fk(dims, "dates", day, r["NombreKPI"])
        bsc_day.add(day)
        owner = (fk(dims, "responsables", norm(r["Responsable"]), r["NombreKPI"])
                 if clean(r["Responsable"]) else None)
        fact.append(make_kpi(key, day, None, None, owner, "GLOBAL", "CORTE",
                             r["MetaNumerica"], r["MetaOriginal"] if r["MetaNumerica"] is None else None,
                             r["AcumuladoNumerico"],
                             r["AcumuladoOriginal"] if r["AcumuladoNumerico"] is None else None,
                             r["AvanceAcumulado"], r["Cumplimiento"], r["Peso"],
                             "BSC", False, ids["BSC"]))
    if len(bsc_day) != 1:
        raise ValueError("BSC con varias fechas de corte; revisar antes de cargar hechos")
    day = next(iter(bsc_day))
    unmapped = []
    dept_loaded = 0
    for r in dep:
        dept_codigo = codigo_para_departamento(identidades,r['NombreHoja'],r['FilaExcel'],r['NombreKPI'])
        key = fk(dims, 'kpis', dept_codigo, r['NombreKPI']) if dept_codigo else None
        if key is None:
            unmapped.append((clean(r["Departamento"]), clean(r["NombreKPI"])))
            continue
        area_id = fk(dims, "areas", norm(r["Departamento"]), r["NombreKPI"])
        fact.append(make_kpi(key, day, area_id, None, None, "AREA", "CORTE",
                             r["MetaNumerica"], r["MetaOriginal"] if r["MetaNumerica"] is None else None,
                             r["AcumuladoNumerico"],
                             r["AcumuladoOriginal"] if r["AcumuladoNumerico"] is None else None,
                             r["AvanceAcumulado"], r["Cumplimiento"], r["Peso"],
                             "BSC", False, ids["BSC"]))
        dept_loaded += 1

    s_by_month = defaultdict(list)
    docs_seen = set()
    all_months = set()
    for r in sales:
        typ = norm(r["TipoDocumento"])
        if not typ.startswith("factura"):
            raise ValueError("Tipo documento aun no cubierto por reglas de ventas: " + str(r["TipoDocumento"]))
        folio = clean(r["Folio"])
        if not folio:
            raise ValueError("Factura sin folio: revisar STAGING")
        unique = (typ, folio)
        if unique in docs_seen:
            raise ValueError(f"Folio duplicado dentro del reporte: {unique}")
        docs_seen.add(unique)
        document_date = dte(r["FechaDocumento"])
        if document_date is None:
            raise ValueError(f"Factura sin fecha: folio {folio}")
        month = document_date.replace(day=1)
        all_months.add(month)
        customer = rut(r["RutCliente"])
        fk(dims, "clientes", customer, f"Folio {folio}")
        if r["Neto_CLP"] is None:
            raise ValueError(f"Factura sin monto NETO: {folio}")
        s_by_month[month].append((customer, money(r["Neto_CLP"])))

    comids = {name: fk(dims, "kpis", name, "COMERCIAL") for name in KPI_COMERCIALES}
    # KPI nuevos de ventas: resultado basado solo en STAGING de la versión ACTIVA.
    # No se usa historial de cargas ETL: podría contar facturas borradas/restauradas.
    monthly_net = {
        month: sum((v for _, v in entries), Decimal("0.00"))
        for month, entries in s_by_month.items()
    }
    first_purchase = {}
    for month in sorted(all_months):
        for customer, _ in s_by_month[month]:
            first_purchase.setdefault(customer, month)
    year_to_date = defaultdict(lambda: Decimal("0.00"))
    for month in sorted(all_months):
        entries = s_by_month[month]
        key = datekey(month)
        fk(dims, "dates", key, f"Mes ventas {month}")
        net = monthly_net[month]
        n = len(entries)
        clients = len({r for r, _ in entries})
        ticket = (net / Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        year_to_date[month.year] += net
        prev_year, prev_month = (month.year - 1, 12) if month.month == 1 else (month.year, month.month - 1)
        previous = monthly_net.get(date(prev_year, prev_month, 1))
        growth = ((net / previous - 1) * Decimal("100")) if previous is not None and previous != 0 else None
        first_observed = sum(1 for customer, initial in first_purchase.items() if initial == month)
        values = {
            "COM_VENTAS_NETAS_MES": net,
            "COM_FACTURAS_MES": n,
            "COM_CLIENTES_MES": clients,
            "COM_TICKET_MES": ticket,
            "COM_VENTAS_ACUM_ANIO": year_to_date[month.year],
            "COM_VARIACION_MENSUAL_PCT": growth,
            "COM_PRIMERA_COMPRA_OBSERVADA_MES": first_observed,
        }
        for code, val in values.items():
            fact.append(make_kpi(comids[code], key, None, None, None, "GLOBAL", "MES",
                                 None, None, val, None, None, None, None,
                                 "VENTAS", False, ids["VENTAS"]))
        per_client = defaultdict(lambda: Decimal("0.00"))
        for customer, val in entries:
            per_client[customer] += val
        for customer, net_client in sorted(per_client.items()):
            customer_id = fk(dims, "clientes", customer, f"Ventas {month}")
            fact.append(make_kpi(comids["COM_VENTA_CLIENTE_MES"], key, None, customer_id,
                                 None, "CLIENTE", "MES", None, None, net_client, None,
                                 None, None, None, "VENTAS", False, ids["VENTAS"]))
            # Participación independiente del BSC; no sustituye ninguna meta oficial.
            share = net_client * Decimal("100") / net if net != 0 else None
            fact.append(make_kpi(comids["COM_PARTICIPACION_CLIENTE_MES_PCT"], key,
                                 None, customer_id, None, "CLIENTE", "MES", None, None,
                                 share, None, None, None, None, "VENTAS", False,
                                 ids["VENTAS"]))
        if net != 0:
            total_share = sum((amount * Decimal("100") / net for amount in per_client.values()), Decimal("0"))
            if abs(total_share - Decimal("100")) > Decimal("0.0000001"):
                raise ValueError(f"Participaciones comerciales no suman 100% en {month}")

    # La hoja RESUMEN se utiliza solamente para conciliar, no se cuenta dos veces.
    resumen = rows(cur, """SELECT TipoDocumento,Cantidad,Neto_CLP
        FROM dbo.STG_VENTA_RESUMEN WHERE CargaID=?""", ids["VENTAS"])
    total_rows = [r for r in resumen if norm(r["TipoDocumento"]) == "total"]
    sales_net = sum((amount for vals in s_by_month.values() for _, amount in vals), Decimal("0.00"))
    if len(total_rows) != 1 or money(total_rows[0]["Neto_CLP"]) != sales_net:
        raise ValueError("Diferencia DETALLE vs RESUMEN de ventas. No cargar hechos.")
    if int(total_rows[0]["Cantidad"]) != len(sales):
        raise ValueError("Diferencia cantidad documentos DETALLE/RESUMEN. No cargar hechos.")

    # Unicidad acorde a los indices filtrados de FACT_KPI_ESTRATEGICO.
    seen = set()
    for row in fact:
        if row[5] == "GLOBAL":
            unique = (row[0], row[1], row[6], "GLOBAL")
        elif row[5] == "AREA":
            unique = (row[0], row[1], row[6], "AREA", row[2])
        else:
            unique = (row[0], row[1], row[6], "CLIENTE", row[3])
        if unique in seen:
            raise ValueError(f"Duplicacion de indicador con misma clave natural: {unique}")
        seen.add(unique)

    official_sales = next((r["AcumuladoNumerico"] for r in bsc
                           if norm(r["NombreKPI"]) == "ventas_2026"), None)
    return fact, {
        "bsc": len(bsc), "dept": dept_loaded, "dept_skipped": unmapped,
        "commercial_months": len(all_months), "invoices": len(sales),
        "sales_net": sales_net, "bsc_sales_reported": official_sales,
    }

def write_kpi(cur, data):
    cols = [f"[{name}]" for name in KPI_COLS]
    insert_cols = ",".join(cols)
    markers = ",".join("?" for _ in cols)
    changes = ",".join(f"[{c}]=?" for c in KPI_COLS[7:])
    sql_update = ("UPDATE dbo.FACT_KPI_ESTRATEGICO SET " + changes + ",ActualizadoUTC=SYSUTCDATETIME() "
                  "WHERE KPI_Key=? AND Fecha_Key=? AND GranoTemporal=? AND Ambito=? "
                  "AND ((Ambito='GLOBAL' AND Area_Key IS NULL AND Cliente_Key IS NULL) "
                  "OR (Ambito='AREA' AND Area_Key=?) OR (Ambito='CLIENTE' AND Cliente_Key=?))")
    sql_insert = f"INSERT INTO dbo.FACT_KPI_ESTRATEGICO ({insert_cols}) VALUES ({markers})"
    for row in data:
        # No se cambian las claves naturales con actualizaciones; solamente medidas y origen.
        c = cur.execute(sql_update, *row[7:], row[0], row[1], row[6], row[5], row[2], row[3])
        if c.rowcount == 0:
            cur.execute(sql_insert, *row)
        elif c.rowcount != 1:
            raise ValueError("Multiples FACT KPI con misma clave natural")


def active_loads(cur):
    """Reutiliza las cargas por huella del paso 05 y valida fuentes dinamicas."""
    step05 = Path(__file__).resolve().parent / "05_cargar_dimensiones.py"
    if not step05.is_file():
        raise FileNotFoundError("Falta 05_cargar_dimensiones.py junto al paso 06")
    spec = importlib.util.spec_from_file_location("maas_dim_step05_in_fact", step05)
    if not spec or not spec.loader:
        raise RuntimeError("No se puede importar el paso 05")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    ids = mod.fuentes_activas(cur)
    if not isinstance(ids, dict):
        raise ValueError("Paso 06: seleccion de cargas invalida; se esperaba un diccionario")
    obligatorias = {"bsc", "ventas", "caja", "gmail_cierres", "gmail_contratos"}
    proyectos = {nombre for nombre in ids if re.fullmatch(r"proyecto_[0-9]{2,}", nombre)}
    faltantes = obligatorias - set(ids)
    inesperadas = set(ids) - obligatorias - proyectos
    if faltantes or inesperadas or not proyectos:
        raise ValueError(
            f"Paso 06: fuentes invalidas; faltantes={sorted(faltantes)}, "
            f"inesperadas={sorted(inesperadas)}, proyectos={len(proyectos)}"
        )
    numeros = [int(nombre.split("_")[1]) for nombre in proyectos]
    if len(numeros) != len(set(numeros)) or sorted(numeros) != list(range(1, len(numeros) + 1)):
        raise ValueError(f"Paso 06: codigos de proyecto duplicados o discontinuos: {sorted(numeros)}")
    if any(not isinstance(carga, int) or isinstance(carga, bool) or carga <= 0 for carga in ids.values()):
        raise ValueError(f"Paso 06: existen fuentes sin CargaID valido: {ids}")
    print(f"FUENTES ACTIVAS: {len(ids)} versiones ({len(proyectos)} proyectos + 3 base + 2 Gmail)")
    return ids


def dimensions(cur):
    mapping = {
        "dates": ("SELECT Fecha_Key FROM dbo.DIM_FECHA", lambda r: int(r["Fecha_Key"]), "Fecha_Key"),
        "kpis": ("SELECT KPI_Key,CodigoKPI FROM dbo.DIM_KPI", lambda r: clean(r["CodigoKPI"]), "KPI_Key"),
        "areas": ("SELECT Area_Key,NombreArea FROM dbo.DIM_AREA", lambda r: norm(r["NombreArea"]), "Area_Key"),
        "responsables": ("SELECT Responsable_Key,NombreResponsable FROM dbo.DIM_RESPONSABLE", lambda r: norm(r["NombreResponsable"]), "Responsable_Key"),
        "clientes": ("SELECT Cliente_Key,RUT_Normalizado FROM dbo.DIM_CLIENTE", lambda r: rut(r["RUT_Normalizado"]), "Cliente_Key"),
        "proyectos": ("SELECT Proyecto_Key,NombreNormalizado FROM dbo.DIM_PROYECTO", lambda r: norm(r["NombreNormalizado"]), "Proyecto_Key"),
        "costos": ("SELECT Costo_Key,CategoriaCosto FROM dbo.DIM_COSTOS", lambda r: norm(r["CategoriaCosto"]), "Costo_Key"),
        "tareas": ("SELECT Tarea_Key,CodigoProyecto,CodigoTarea,Proyecto_Key FROM dbo.DIM_TAREA",
                  lambda r: (clean(r["CodigoProyecto"]).upper(), clean(r["CodigoTarea"]).upper()), "Tarea_Key"),
    }
    result = {}
    for category, (sql, keyfn, pk) in mapping.items():
        entries = {}
        for item in rows(cur, sql):
            key = keyfn(item)
            if key in entries:
                raise ValueError(f"Dimension {category}: clave duplicada {key!r}")
            entries[key] = int(item[pk])
        if category != "costos" and not entries:
            raise ValueError(f"Dimension vacia: {category}")
        result[category] = entries
    return result


def check_structure(cur):
    """Read-only; reporta exactamente que falta antes de --cargar."""
    tables = {r["name"] for r in rows(cur, "SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('dbo')")}
    required = {"FACT_KPI_ESTRATEGICO", "FACT_SEGUIMIENTO_OPERACIONAL", "DIM_KPI", "DIM_TAREA",
                "STG_PROYECTO_RESUMEN", "STG_PROYECTO_GANTT", "STG_TAREA", "STG_RECURSO",
                "STG_ADJUDICACION", "STG_GMAIL_CIERRE_MENSUAL", "STG_GMAIL_CONTRATO",
                "STG_CAJA_MENSUAL"}
    absent = required - tables
    if absent:
        raise ValueError(f"Tablas base ausentes: {sorted(absent)}")
    cols = {r["name"] for r in rows(cur, "SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.FACT_SEGUIMIENTO_OPERACIONAL')")}
    kpi_cols = {r["name"] for r in rows(cur, "SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(N'dbo.FACT_KPI_ESTRATEGICO')")}
    if set(OP_COLS) - cols or set(KPI_COLS) - kpi_cols:
        raise ValueError("Las FACT antiguas no tienen el esquema esperado. No ejecutar migracion sin revisar SQL.")
    new_absent = sorted(set(OP_EXTRA) - cols)
    codes = {r["CodigoKPI"] for r in rows(cur, "SELECT CodigoKPI FROM dbo.DIM_KPI WHERE CodigoKPI IN ('GMAIL_FACTURADO_MES','GMAIL_PENDIENTE_MES','CAJA_BRECHA_MES')")}
    missing_codes = sorted(TECH_KPIS - codes)
    checks = rows(cur, """SELECT name, definition FROM sys.check_constraints
        WHERE parent_object_id IN (OBJECT_ID(N'dbo.FACT_SEGUIMIENTO_OPERACIONAL'),
                                   OBJECT_ID(N'dbo.FACT_KPI_ESTRATEGICO'))""")
    op = next((r["definition"] for r in checks if r["name"] == "CK_FACT_OP_Tipo"), "")
    source = next((r["definition"] for r in checks if r["name"] == "CK_FACT_KPI_Fuente"), "")
    check_problem = not all(x in str(op).upper() for x in ("ADJUDICACION", "TAREA", "CONTRATO")) or "GMAIL" not in str(source).upper()
    alias = rows(cur, "SELECT OBJECT_ID(N'dbo.FACT_PROYECTO_ESTRATEGICO',N'V') AS id")
    missing_view = alias[0]["id"] is None
    return new_absent, missing_codes, check_problem, missing_view


def make_event(kind, identifier, project_id, ref_date, carga, *, simulated=True, **attrs):
    if kind not in NEW_TYPES:
        raise ValueError(f"Tipo de evento no autorizado: {kind}")
    if not identifier or len(identifier) > 150:
        raise ValueError(f"Identificador operacional invalido: {identifier}")
    data = {column: None for column in (*OP_COLS, *OP_EXTRA)}
    data.update({"TipoRegistro": kind, "IDOrigen": identifier, "Proyecto_Key": project_id,
                 "Fecha_Evento_Key": ref_date, "CargaID": carga, "EsSimulado": int(simulated),
                 "FuenteDato": "SIMULADO_EXCEL"})
    unknown = set(attrs) - set(data)
    if unknown:
        raise ValueError(f"Columnas operacionales inesperadas: {sorted(unknown)}")
    data.update(attrs)
    return data


def build_operational_new(cur, ids, dim):
    bsc_projects = rows(cur, """SELECT NombreProyecto, VentaOC_CLP, MargenObjetivo, MargenActual,
        MargenProyectado, NoCumple, FechaReferencia FROM dbo.STG_PROYECTO WHERE CargaID=?""", ids["bsc"])
    bsc = {norm(r["NombreProyecto"]): r for r in bsc_projects}
    # Comprobar duplicados sobre las FILAS originales, no sobre las claves
    # (texto) del diccionario; de otro modo falla con string indices.
    if len(bsc) != len(bsc_projects):
        raise ValueError("BSC: proyectos duplicados o nombres equivalentes tras normalizacion")
    proyectos_fuente = sorted(k for k in ids if re.fullmatch(r"proyecto_[0-9]{2,}", k))
    # La cantidad de proyectos de seguimiento puede superar al catálogo BSC.
    # El modelo operacional admite proyectos registrados solo en Excel.
    events, counts = [], defaultdict(int)
    seen_projects = set()
    project_name_by_code = {}
    for src in proyectos_fuente:
        cid = ids[src]
        resumen = rows(cur, """SELECT CodigoProyecto, NombreProyecto, FechaInicioPlan, FechaTerminoPlan,
            HH_Planificadas,HH_Reales,CostoPlanificado_CLP,CostoReal_CLP,TareasTotal,TareasFinalizadas,OrigenDatos
            FROM dbo.STG_PROYECTO_RESUMEN WHERE CargaID=?""", cid)
        tasks = rows(cur, """SELECT CodigoProyecto,NombreProyecto,CodigoTarea,NombreTarea,
            FechaInicioPlan,FechaTerminoPlan,HH_Planificadas,HH_Reales,
            CostoPlanificado_CLP,CostoReal_CLP,AvanceTarea,EstadoTarea,OrigenDatos
            FROM dbo.STG_TAREA WHERE CargaID=? ORDER BY FilaExcel""", cid)
        gantt = rows(cur, """SELECT CodigoProyecto,CodigoTarea,FechaInicioPlan,FechaTerminoPlan,
            HH_Planificadas,CostoPlanificado_CLP,OrigenDatos
            FROM dbo.STG_PROYECTO_GANTT WHERE CargaID=?""", cid)
        resources = rows(cur, """SELECT CodigoProyecto,FilaExcel,NombreRecurso,Unidad,
            CantidadPlanificada,CantidadUtilizada,CantidadRestante,PorcentajeUtilizacion,OrigenDatos
            FROM dbo.STG_RECURSO WHERE CargaID=?""", cid)
        awards = rows(cur, """SELECT CodigoProyecto,NumeroPropuesta,FechaAdjudicacion,EstadoAdjudicacion,
            Monto_CLP,Adjudicada,OrigenDatos FROM dbo.STG_ADJUDICACION WHERE CargaID=?""", cid)
        if len(resumen) != 1 or not tasks or len(tasks) != len(gantt) or not awards:
            raise ValueError(f"{src}: resumen, tareas, Gantt o adjudicaciones incompletas")
        s = resumen[0]
        code = clean(s["CodigoProyecto"]).upper()
        if code in seen_projects:
            raise ValueError(f"Proyecto repetido entre archivos: {code}")
        seen_projects.add(code)
        if any(clean(r["OrigenDatos"]).upper() != "SIMULADO" for r in [s,*tasks,*gantt,*resources,*awards]):
            raise ValueError(f"{src}: origen no marcado como SIMULADO")
        pnorm = norm(s["NombreProyecto"])
        project_name_by_code[code] = pnorm
        project_id = fk(dim, "proyectos", pnorm, src)
        bp = bsc.get(pnorm)
        # En proyectos sin BSC, se usa la fecha real de INICIO PLANIFICADO como
        # evento; no se inventan márgenes, venta comercial ni fecha de corte BSC.
        ref_date = datekey(bp["FechaReferencia"]) if bp is not None else datekey(s["FechaInicioPlan"])
        fk(dim, "dates", ref_date, src)
        inicio = datekey(s["FechaInicioPlan"])
        final = datekey(s["FechaTerminoPlan"])
        for dk in (inicio, final):
            fk(dim, "dates", dk, src)
        events.append(make_event("PROYECTO", f"PROYECTO:{code}", project_id, ref_date, cid,
            Fecha_InicioPlan_Key=inicio, Fecha_TerminoPlan_Key=final,
            VentaOC_CLP=(money(bp["VentaOC_CLP"]) if bp is not None and bp["VentaOC_CLP"] is not None else None),
            MargenObjetivo=number(bp["MargenObjetivo"]) if bp is not None else None,
            MargenActual=number(bp["MargenActual"]) if bp is not None else None,
            MargenProyectado=number(bp["MargenProyectado"]) if bp is not None else None,
            NoCumpleOriginal=bp["NoCumple"] if bp is not None else None,
            CostoPresupuestado_CLP=money(s["CostoPlanificado_CLP"]),
            HH_Planificadas=number(s["HH_Planificadas"]),
            HH_Reales=number(s["HH_Reales"]),
            CostoRealTarea_CLP=money(s["CostoReal_CLP"]),
            EstadoProyecto="SEGUIMIENTO_SIMULADO",
            Observaciones="Resumen de proyecto: NO sumar junto con detalle de tareas",
            FuenteDato=("MIXTO_BSC_REAL_SEGUIMIENTO_SIMULADO" if bp is not None else "SEGUIMIENTO_SIMULADO_SIN_BSC")))
        counts["PROYECTO"] += 1
        gantt_map = {(clean(r["CodigoProyecto"]).upper(), clean(r["CodigoTarea"]).upper()): r for r in gantt}
        if len(gantt_map) != len(gantt):
            raise ValueError(f"{src}: Gantt con codigos duplicados")
        for task in tasks:
            task_code = clean(task["CodigoTarea"]).upper()
            tcode = clean(task["CodigoProyecto"]).upper()
            if tcode != code:
                raise ValueError(f"{src}: tarea pertenece a otro proyecto")
            gantt_entry = gantt_map.get((code,task_code))
            if gantt_entry is None:
                raise ValueError(f"{src}: tarea {task_code} ausente de Gantt")
            tkey = fk(dim, "tareas", (code, task_code), src)
            for col in ("FechaInicioPlan", "FechaTerminoPlan"):
                if datekey(task[col]) != datekey(gantt_entry[col]):
                    raise ValueError(f"{src}: Gantt y tarea no coinciden: {task_code}/{col}")
            av = number(task["AvanceTarea"])
            if av is None or av < 0 or av > 1:
                raise ValueError(f"{src}: porcentaje avance de tarea invalido: {task_code}")
            planned = datekey(task["FechaInicioPlan"])
            end = datekey(task["FechaTerminoPlan"])
            fk(dim, "dates", planned, task_code)
            fk(dim, "dates", end, task_code)
            events.append(make_event("TAREA", f"TAREA:{code}:{task_code}", project_id, ref_date, cid,
                Tarea_Key=tkey, Fecha_InicioPlan_Key=planned, Fecha_TerminoPlan_Key=end,
                HH_Planificadas=number(task["HH_Planificadas"]), HH_Reales=number(task["HH_Reales"]),
                CostoPresupuestado_CLP=money(task["CostoPlanificado_CLP"]),
                CostoRealTarea_CLP=money(task["CostoReal_CLP"]), AvanceTarea=av,
                EstadoProyecto=clean(task["EstadoTarea"]) or None))
            counts["TAREA"] += 1
        for resource in resources:
            if clean(resource["CodigoProyecto"]).upper() != code:
                raise ValueError(f"{src}: recurso asociado a otro proyecto")
            name = clean(resource["NombreRecurso"])
            rid = f"RECURSO:{code}:{int(resource['FilaExcel'])}"
            events.append(make_event("RECURSO", rid, project_id, ref_date, cid,
                NombreRecurso=name, UnidadRecurso=clean(resource["Unidad"]) or None,
                CantidadPlanificada=number(resource["CantidadPlanificada"]),
                CantidadUtilizada=number(resource["CantidadUtilizada"]),
                CantidadRestante=number(resource["CantidadRestante"]),
                PorcentajeUtilizacion=number(resource["PorcentajeUtilizacion"])))
            counts["RECURSO"] += 1
        for award in awards:
            if clean(award["CodigoProyecto"]).upper() != code:
                raise ValueError(f"{src}: adjudicacion asociada a otro proyecto")
            nro = clean(award["NumeroPropuesta"])
            award_date = datekey(award["FechaAdjudicacion"])
            if award_date is not None:
                fk(dim, "dates", award_date, nro)
            events.append(make_event("ADJUDICACION", f"ADJUDICACION:{code}:{nro}", project_id, ref_date, cid,
                NumeroPropuesta=nro, FechaAdjudicacion_Key=award_date,
                MontoAdjudicado_CLP=money(award["Monto_CLP"]),
                Adjudicada=int(award["Adjudicada"]),
                Observaciones=clean(award["EstadoAdjudicacion"]) or None))
            counts["ADJUDICACION"] += 1
    if counts["PROYECTO"] != len(proyectos_fuente) or len(seen_projects) != len(proyectos_fuente):
        raise ValueError(
            f"No se construyo exactamente un evento por proyecto de seguimiento: {dict(counts)}"
        )
    if counts["TAREA"] < len(proyectos_fuente):
        raise ValueError(f"Tareas insuficientes respecto de proyectos: {dict(counts)}")
    if counts["RECURSO"] < len(proyectos_fuente):
        raise ValueError(f"Recursos insuficientes respecto de proyectos: {dict(counts)}")
    if counts["ADJUDICACION"] < len(proyectos_fuente):
        raise ValueError(f"Adjudicaciones insuficientes respecto de proyectos: {dict(counts)}")
    if ids.get("gmail_contratos") is not None:
        contracts = rows(cur, """SELECT NombreProyectoBSC, CodigoProyectoBSC,EstadoVinculacion,
            FechaInicio,FechaTermino,MontoContractual_CLP,SHA256PDF,GmailMessageID,
            OrigenDatos,EstadoValidacion FROM dbo.STG_GMAIL_CONTRATO WHERE CargaID=?""", ids["gmail_contratos"])
        for r in contracts:
            status = clean(r["EstadoVinculacion"]).upper()
            if not clean(r["NombreProyectoBSC"]) or not clean(r["CodigoProyectoBSC"]):
                counts["CONTRATO_PENDIENTE_VINCULACION"] += 1
                continue   # STAGING conserva el documento para resolverlo mas adelante
            if status not in ("VINCULADO_BSC", "VINCULADO_SEGUIMIENTO"):
                counts["CONTRATO_PENDIENTE_VINCULACION"] += 1
                continue
            code = clean(r["CodigoProyectoBSC"]).upper()
            if project_name_by_code.get(code) != norm(r["NombreProyectoBSC"]):
                raise ValueError("Gmail contrato no concilia codigo/nombre del proyecto Excel")
            project_id = fk(dim, "proyectos", norm(r["NombreProyectoBSC"]), "Gmail contrato")
            start = datekey(r["FechaInicio"])
            end = datekey(r["FechaTermino"])
            if start is None or end is None or start > end:
                raise ValueError("Contrato Gmail con fechas invalidas")
            fk(dim, "dates", start, "Inicio contrato")
            fk(dim, "dates", end, "Termino contrato")
            digest = clean(r["SHA256PDF"])
            mid = clean(r["GmailMessageID"])
            if not digest and not mid:
                raise ValueError("Contrato sin identificador PDF/Gmail")
            events.append(make_event("CONTRATO", "CONTRATO:"+(digest or mid), project_id,
                start, ids["gmail_contratos"],
                FechaInicioContrato_Key=start, FechaTerminoContrato_Key=end,
                MontoContractual_CLP=money(r["MontoContractual_CLP"]) if r["MontoContractual_CLP"] is not None else None,
                EstadoValidacion=clean(r["EstadoValidacion"]) or "PENDIENTE_VALIDACION",
                EstadoVinculacion=status or "PENDIENTE_VINCULACION",
                DocumentoHash=digest or None,
                FuenteDato=clean(r["OrigenDatos"]) or "GMAIL",
                simulated=(clean(r["OrigenDatos"]).upper() == "SIMULADO"),
                Observaciones="Contrato de referencia. No sobrescribe BSC ni Gantt."))
            counts["CONTRATO"] += 1
    keys = [(e["TipoRegistro"],e["IDOrigen"]) for e in events]
    if len(keys) != len(set(keys)):
        raise ValueError("Eventos operacionales con ID de origen duplicado")
    return events, counts


def build_extra_kpis(cur, ids, dim):
    fact = []
    seen = set()
    if ids.get("gmail_cierres") is not None:
        closing = rows(cur, """SELECT Periodo, Facturado_CLP, Pendiente_CLP, OrigenDatos,
             EstadoValidacion FROM dbo.STG_GMAIL_CIERRE_MENSUAL WHERE CargaID=?""", ids["gmail_cierres"])
        for r in closing:
            period = str(r["Periodo"])
            if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", period) or period in seen:
                raise ValueError(f"Cierre Gmail con periodo invalido o repetido: {period}")
            seen.add(period)
            dk = datekey(date.fromisoformat(period+"-01"))
            fk(dim,"dates",dk,period)
            for code, field in (("GMAIL_FACTURADO_MES", "Facturado_CLP"),
                                ("GMAIL_PENDIENTE_MES", "Pendiente_CLP")):
                value = number(r[field])
                if value is None or value < 0:
                    raise ValueError(f"Gmail: valor {field} invalido en {period}")
                fact.append(make_kpi(fk(dim,"kpis",code,"SQL preparacion paso 06"), dk,
                                     None,None,None,"GLOBAL","MES",None,None,value,None,
                                     None,None,None,"GMAIL",
                                     clean(r["OrigenDatos"]).upper() == "SIMULADO",
                                     ids["gmail_cierres"]))
    if ids.get("caja") is not None:
        months = rows(cur, """SELECT Mes, BrechaCaja_CLP, OrigenDatos
                             FROM dbo.STG_CAJA_MENSUAL WHERE CargaID=?""", ids["caja"])
        seen_months = set()
        for r in months:
            period = clean(r["Mes"])
            if not re.fullmatch(r"20\d{2}-(?:0[1-9]|1[0-2])", period) or period in seen_months:
                raise ValueError(f"Caja: periodo invalido o repetido {period}")
            seen_months.add(period)
            if clean(r["OrigenDatos"]).upper() != "SIMULADO":
                raise ValueError("Caja: fuente no identificada como simulada")
            dk = datekey(date.fromisoformat(period+"-01"))
            fk(dim,"dates",dk,"Caja: ejecutar preparacion SQL del paso 06")
            fact.append(make_kpi(fk(dim,"kpis","CAJA_BRECHA_MES","SQL preparacion paso 06"), dk,
                                 None,None,None,"GLOBAL","MES",None,None,
                                 number(r["BrechaCaja_CLP"]),None,None,None,None,
                                 "CAJA",True,ids["caja"]))
    return fact


def write_new_events(cur, events):
    cols = (*OP_COLS, *OP_EXTRA)
    updates = [c for c in cols if c not in ("TipoRegistro", "IDOrigen")]
    insert_sql = "INSERT INTO dbo.FACT_SEGUIMIENTO_OPERACIONAL (" + ",".join("["+c+"]" for c in cols) + ") VALUES ("+",".join("?" for _ in cols)+")"
    update_sql = ("UPDATE dbo.FACT_SEGUIMIENTO_OPERACIONAL SET " +
                  ",".join("["+c+"]= ?" for c in updates) +
                  ",ActualizadoUTC=SYSUTCDATETIME() WHERE TipoRegistro=? AND IDOrigen=?")
    inserted, updated = 0, 0
    for r in events:
        result = cur.execute(update_sql,*[r[c] for c in updates],r["TipoRegistro"],r["IDOrigen"])
        if result.rowcount == 0:
            cur.execute(insert_sql,*[r[c] for c in cols])
            inserted += 1
        elif result.rowcount == 1:
            updated += 1
        else:
            raise ValueError("Mismo evento existente varias veces: " + r["IDOrigen"])
    return inserted,updated


def main():
    parser = argparse.ArgumentParser(description="MAAS 4 paso 06 (fuentes dinamicas) - FACT operacional y KPI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verificar", action="store_true", help="Solo lectura, nunca modifica SQL")
    group.add_argument("--cargar", action="store_true", help="Carga sin bajas, transaccion/rollback")
    parser.add_argument("--servidor", default=SERVER)
    args = parser.parse_args()
    print("MAAS 4 | PASO 06 | " + ("VERIFICACION SIN ESCRIBIR" if args.verificar else "CARGA TRANSACCIONAL"))
    con = connect(args.servidor)
    try:
        cur = con.cursor()
        missing_cols, missing_kpis, bad_check, missing_view = check_structure(cur)
        pending = bool(missing_cols or missing_kpis or bad_check or missing_view)
        if pending:
            print("PREPARACION SQL PENDIENTE: MAAS_06_PREPARAR_FACT_22_FUENTES.sql")
            print(f" - Columnas FACT faltantes: {missing_cols}")
            print(f" - KPI tecnicos faltantes: {missing_kpis}")
            print(f" - Restricciones por ampliar: {bad_check} | Vista alias ausente: {missing_view}")
        ids = active_loads(cur)
        print("STAGING OK: " + str(len(ids)) + " versiones exactas (Drive + Gmail)")
        # Los KPI de facturacion/caja aun no existen si el SQL esta pendiente.
        if pending:
            if args.cargar:
                raise ValueError("No se puede cargar. Preparar estructura SQL antes y verificar nuevamente")
            print("VERIFICACION PRELIMINAR OK. No se escribio SQL.")
            return
        dim = dimensions(cur)
        print("DIMENSIONES: "+", ".join(f"{key}={len(values)}" for key,values in dim.items()))
        events, counts = build_operational_new(cur, ids, dim)
        normal, meta = build_strategic(cur, {"BSC": ids["bsc"], "VENTAS": ids["ventas"]}, dim)
        extra = build_extra_kpis(cur, ids, dim)
        all_kpis = normal + extra
        seen_kpi = set()
        for r in all_kpis:
            k = (r[0],r[1],r[5],r[6],r[2],r[3])
            if k in seen_kpi:
                raise ValueError(f"Indicador duplicado en nuevo lote: {k}")
            seen_kpi.add(k)
        print("EVENTOS NUEVOS: "+" | ".join(f"{k}={v}" for k,v in sorted(counts.items())))
        print(f"FACT KPI: {len(all_kpis)} mediciones propuestas (BSC={meta['bsc']}, dept={meta['dept']}, Gmail/caja={len(extra)})")
        print(f"VENTAS EXCEL: {meta['sales_net']:,.0f} CLP, {meta['invoices']} documentos; Gmail NO se suma a ventas")
        print("AVISO: historial de FACT antiguas se conserva y 11 KPI de proyectos V12 NO se recalculan.")
        print("AVISO: todos los contratos Gmail siguen pendientes de aprobacion; no reemplazan Gantt ni BSC.")
        if meta["dept_skipped"]:
            print("AVISO: alias departamentales sin equivalencia aprobada: "+str(meta["dept_skipped"]))
        if args.verificar:
            print("VERIFICACION OK. SQL consultado en solo lectura. No se insertaron ni actualizaron hechos.")
            return
        try:
            cur.execute("SET XACT_ABORT ON")
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            new, updated = write_new_events(cur, events)
            write_kpi(cur, all_kpis)
            con.commit()
            print(f"COMMIT OK: eventos nuevos={new}, eventos actualizados={updated}; mediciones KPI={len(all_kpis)}.")
            print("STAGING, dimensiones, vistas existentes e historial antiguo intactos. Sin bajas.")
        except Exception:
            con.rollback()
            print("ROLLBACK: no se confirmaron cambios del paso 06",file=sys.stderr)
            raise
    finally:
        if args.verificar:
            con.rollback()
        con.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR PASO 06:",exc,file=sys.stderr)
        sys.exit(1)
