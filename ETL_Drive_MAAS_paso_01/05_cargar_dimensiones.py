# -*- coding: utf-8 -*-
"""MAAS_ECOLOGIA_4 | PASO 05: dimensiones (20 Drive + 2 Gmail).

Adaptado del 05_cargar_dimensiones.py original del proyecto.

    py .\05_cargar_dimensiones.py --verificar   # Lee SQL; NO escribe
    py .\05_cargar_dimensiones.py --cargar      # SOLO despues de preparar DIM_TAREA

PRECAUCIONES:
- Selecciona las versiones EXACTAS confirmadas en STAGING, usando las huellas
  del paso 04 (nunca MAX(CargaID)). Si faltan versiones, se detiene.
- Mantiene las siete dimensiones previas y agrega DIM_TAREA (85 tareas hoy).
- Dimensiones: atributos descriptivos; HH, costos, porcentajes y montos se
  dejan para FACT. No suma facturacion Gmail a ventas del Excel.
- Los contratos de Gmail siguen sin aprobar: sus fechas NO sobrescriben Gantt.
- No borra, retira ni actualiza registros antiguos; inserta claves nuevas.
- No toca tablas FACT, vistas ni Streamlit.
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
from pathlib import Path

DB = "MAAS_ECOLOGIA_4"
DEFAULT_SERVER = r"Giuli\GIULIANA"
MES = ("", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
       "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")

# Conserva las nueve definiciones comerciales existentes del paso 05 original.
# Definir un KPI en DIM_KPI no constituye calcularlo ni publicarlo en FACT.
COMERCIALES = [
    ("COM_VENTAS_NETAS_MES", "Ventas netas del mes", "Comercial", "CLP", "Suma de neto por mes"),
    ("COM_FACTURAS_MES", "Facturas del mes", "Comercial", "Documentos", "Conteo de documentos por mes"),
    ("COM_CLIENTES_MES", "Clientes con ventas en el mes", "Comercial", "Clientes", "RUT distintos por mes"),
    ("COM_TICKET_MES", "Ticket promedio neto mensual", "Comercial", "CLP", "Venta neta mensual / cantidad de facturas"),
    ("COM_VENTA_CLIENTE_MES", "Ventas netas por cliente y mes", "Comercial", "CLP", "Neto por RUT y mes"),
    ("COM_VENTAS_ACUM_ANIO", "Ventas netas acumuladas del año al mes", "Comercial", "CLP",
     "Suma desde enero hasta el mes del corte, por año según facturas disponibles"),
    ("COM_VARIACION_MENSUAL_PCT", "Variación porcentual de ventas respecto del mes anterior", "Comercial", "%",
     "100 x (ventas mes actual / ventas mes calendario anterior - 1); NULL si no hay mes previo o ventas previas cero"),
    ("COM_PRIMERA_COMPRA_OBSERVADA_MES", "Clientes con primera compra observada en el reporte", "Comercial", "Clientes",
     "RUT cuya primera factura en el período del reporte ocurre en este mes; no equivale a cliente histórico nuevo"),
    ("COM_PARTICIPACION_CLIENTE_MES_PCT", "Participación del cliente en ventas netas del mes", "Comercial", "%",
     "100 x venta mensual del RUT / venta global del mes; NULL si neto global cero"),
]

# Definiciones operacionales heredadas, SIN hechos ni reglas validadas.
# Mantenerlas PENDIENTE_VALIDACION conserva la compatibilidad con el paso 05
# anterior; el paso 06 debe revisar sus formulas con el modelo nuevo.
OPERACIONALES_PROYECTOS = [
    ("PRY_TOTAL_ULTIMO_CORTE", "Proyectos en seguimiento (ultimo corte)", "Proyectos", "Proyectos",
     "Cantidad de proyectos distintos con un ultimo seguimiento"),
    ("PRY_FUERA_PLAZO", "Proyectos fuera de plazo", "Plazos", "Proyectos",
     "Vencidos o finalizados despues de su fecha termino planificada; requiere fechas verificadas"),
    ("PRY_PCT_FUERA_PLAZO", "Porcentaje de proyectos fuera de plazo", "Plazos", "%",
     "100 * proyectos fuera de plazo / proyectos con seguimiento; pendiente de validacion"),
    ("PRY_SOBRECOSTO", "Proyectos sobre presupuesto", "Costos", "Proyectos",
     "Proyectos con costo real acumulado mayor al plan; pendiente de validacion"),
    ("PRY_PCT_SOBRECOSTO", "Porcentaje de proyectos sobre presupuesto", "Costos", "%",
     "100 * proyectos sobre presupuesto / proyectos con presupuesto informado"),
    ("PRY_PRESUPUESTO_TOTAL_CLP", "Presupuesto total de proyectos", "Costos", "CLP",
     "Suma de presupuestos del ultimo seguimiento de cada proyecto"),
    ("PRY_GASTO_ACUM_CLP", "Gasto real acumulado de proyectos", "Costos", "CLP",
     "Costos reales de tareas por proyecto; confirmar si son acumulados o movimientos"),
    ("PRY_DIF_COSTO_CLP", "Desviacion neta de costo", "Costos", "CLP",
     "Suma de costo real menos planificado por proyecto"),
    ("PRY_FINALIZADOS", "Proyectos finalizados", "Plazos", "Proyectos",
     "Proyectos con cierre efectivamente verificado; no inferir cierre desde Gantt"),
    ("PRY_FINALIZADOS_EN_PLAZO", "Proyectos finalizados dentro de plazo", "Plazos", "Proyectos",
     "Finalizados con fechas contractuales y reales verificadas"),
    ("PRY_PCT_FINALIZADOS_EN_PLAZO", "Porcentaje de finalizados dentro de plazo", "Plazos", "%",
     "100 * finalizados en plazo / finalizados con fechas verificables"),
]

# Las siete dimensiones anteriores usan EXACTAMENTE las mismas columnas.
SCHEMA = {
    "DIM_FECHA": ("Fecha_Key Fecha Dia Mes Anio Trimestre NombreMes".split(), "Fecha_Key"),
    "DIM_KPI": ("CodigoKPI NombreKPI CategoriaKPI UnidadMedida TipoIndicador EstadoRevision ReglaCalculo".split(), "CodigoKPI"),
    "DIM_AREA": (["NombreArea"], "NombreArea"),
    "DIM_RESPONSABLE": (["NombreResponsable", "EsSimulado"], "NombreResponsable"),
    "DIM_CLIENTE": (["RUT_Normalizado", "RazonSocial", "Ciudad", "Comuna"], "RUT_Normalizado"),
    "DIM_PROYECTO": (["NombreProyecto", "NombreNormalizado", "TipoProyecto", "FuenteProyecto"], "NombreNormalizado"),
    "DIM_COSTOS": (["CategoriaCosto", "DescripcionCategoria", "Activo"], "CategoriaCosto"),
}
TAREA_COLUMNAS = ["Proyecto_Key", "CodigoProyecto", "CodigoTarea", "NombreTarea",
                  "TareaPredecesora", "RecursoPrincipal", "EsSimulado"]


def limpio(valor):
    return " ".join(str(valor).strip().split()) if valor is not None else ""


def norm(valor):
    s = unicodedata.normalize("NFKD", limpio(valor)).encode("ascii", "ignore").decode("ascii").lower()
    return "_".join(re.findall(r"[a-z0-9]+", s))


def rut_norm(rut):
    return re.sub(r"[^0-9K]", "", limpio(rut).upper())


def dt(valor):
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor.strip()):
        return date.fromisoformat(valor.strip())
    raise ValueError(f"Fecha inesperada en STAGING: {valor!r}")


def fecha_key(d):
    return d.year * 10000 + d.month * 100 + d.day


def conectar(server):
    try:
        import pyodbc
    except ImportError as e:
        raise RuntimeError("Falta pyodbc: py -m pip install pyodbc") from e
    drv = next((d for d in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server")
                if d in pyodbc.drivers()), None)
    if not drv:
        raise RuntimeError("No se encontro ODBC Driver 17/18 para SQL Server")
    cadena = (f"DRIVER={{{drv}}};SERVER={server};DATABASE={DB};"
              "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
              "Connection Timeout=10;Application Name=MAAS_ETL_DIM_PASO05;")
    return pyodbc.connect(cadena, autocommit=False, timeout=15)


def consultar(cur, sql, *params):
    return list(cur.execute(sql, *params).fetchall())


def fuentes_activas(cur):
    """Resuelve 22 CargaID POR HUELLA vigente del paso 04, no por MAX(CargaID).

    Usa build_dataset + fingerprint originales, para que el algoritmo de hash
    sea exactamente el mismo que el que inserto los registros en SQL Server.
    """
    script = Path(__file__).resolve().parent / "04_cargar_staging.py"
    if not script.is_file():
        raise FileNotFoundError("Falta 04_cargar_staging.py al lado del paso 05")
    spec = importlib.util.spec_from_file_location("maas_paso04_activo_05", script)
    if not spec or not spec.loader:
        raise RuntimeError("No se pudo importar el paso 04")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    fuentes, data = mod.build_dataset()
    nproy = sum(k.startswith("proyecto_") for k in fuentes)
    if nproy < 17 or len(fuentes) != nproy + 5:
        raise ValueError(f"Fuentes incoherentes: {len(fuentes)} totales, {nproy} proyectos; "
                         "se necesitan BSC, ventas, caja, 17+ proyectos y 2 Gmail")
    ids = {}
    for codigo in ["bsc", "ventas", "caja", *sorted(k for k in fuentes if k.startswith("proyecto_")),
                   "gmail_cierres", "gmail_contratos"]:
        sha = mod.fingerprint(data[codigo])
        identificador = fuentes[codigo]["meta"].get("id_drive")
        if not identificador:
            raise ValueError(f"Falta identificador de fuente: {codigo}")
        cantidad = sum(map(len, data[codigo].values()))
        rows = consultar(cur, """SELECT CargaID FROM dbo.ETL_CARGA
            WHERE TipoFuente=? AND IdArchivoDrive=? AND HashArchivoSHA256=? AND Estado='OK'""",
            codigo.upper(), identificador, sha)
        if len(rows) != 1:
            if codigo in mod.GMAIL_SOURCES and cantidad == 0 and not rows:
                ids[codigo] = None
                continue
            raise ValueError(f"{codigo}: falta version exacta confirmada en STAGING ({sha[:12]}). "
                             "Revisar paso 04; no cargar dimensiones sobre datos diferentes.")
        ids[codigo] = int(rows[0][0])
    return ids


def comprobar_estructura(cur, permitir_sin_tarea=False):
    tablas = {row[0] for row in consultar(cur, "SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID('dbo')")}
    requeridas = set(SCHEMA) | {"ETL_CARGA", "STG_BSC_KPI", "STG_KPI_DEPARTAMENTO",
                                  "STG_PROYECTO", "STG_VENTA_DETALLE", "STG_PROYECTO_RESUMEN",
                                  "STG_PROYECTO_GANTT", "STG_TAREA", "STG_ADJUDICACION",
                                  "STG_GMAIL_CIERRE_MENSUAL", "STG_GMAIL_CONTRATO"}
    # No exigir ninguna renombrada FACT todavia: esa migracion sera el paso 06.
    faltan = sorted(requeridas - tablas)
    if faltan:
        raise ValueError(f"Faltan tablas SQL requeridas: {faltan}")
    for tabla, (columnas, _) in SCHEMA.items():
        reales = {x[0] for x in consultar(cur, "SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?)", f"dbo.{tabla}")}
        missing = sorted(set(columnas) - reales)
        if missing:
            raise ValueError(f"Columnas faltantes en {tabla}: {missing}")
    tiene_tarea = "DIM_TAREA" in tablas
    if not tiene_tarea and not permitir_sin_tarea:
        raise ValueError("Falta DIM_TAREA: ejecutar MAAS_05_PREPARAR_DIM_TAREA.sql ANTES de --cargar")
    if tiene_tarea:
        reales = {x[0] for x in consultar(cur, "SELECT name FROM sys.columns WHERE object_id=OBJECT_ID(?)", "dbo.DIM_TAREA")}
        missing = sorted((set(TAREA_COLUMNAS) | {"Tarea_Key"}) - reales)
        if missing:
            raise ValueError(f"DIM_TAREA incompatible; faltan columnas: {missing}")
    return tiene_tarea


def construir(cur, ids):
    bsc = consultar(cur, """SELECT NombreKPI, Categoria, Anotacion, PendienteValidacion,
        Responsable, FechaReferencia FROM dbo.STG_BSC_KPI WHERE CargaID=? ORDER BY FilaExcel""", ids["bsc"])
    departamentos = consultar(cur, """SELECT Departamento, NombreKPI FROM dbo.STG_KPI_DEPARTAMENTO
        WHERE CargaID=? ORDER BY NombreHoja,FilaExcel""", ids["bsc"])
    proyectos_bsc = consultar(cur, """SELECT NombreProyecto, TipoProyecto, FechaReferencia
        FROM dbo.STG_PROYECTO WHERE CargaID=? ORDER BY FilaExcel""", ids["bsc"])
    ventas = consultar(cur, """SELECT RutCliente, RazonSocial, CiudadCliente, ComunaCliente,
        FechaDocumento FROM dbo.STG_VENTA_DETALLE WHERE CargaID=? ORDER BY FilaExcel""", ids["ventas"])
    # Verificar 16 KPI globales e identidad del nuevo indicador.
    nombres_bsc = [str(fila[0] or "").strip().casefold() for fila in bsc]
    if (len(nombres_bsc) != 16 or nombres_bsc.count("margen operativo") != 1
            or len(proyectos_bsc) < 17 or not departamentos or not ventas):
        raise ValueError(
            "Conteos BSC/VENTAS incompatibles: se esperan 16 KPI globales "
            "(incluido Margen Operativo una sola vez), al menos 17 proyectos, "
            "indicadores departamentales y facturas"
        )

    fechas = set()
    kpis, responsables, areas, clientes, proyectos = {}, {}, {}, {}, {}
    avisos = []

    def fecha_agregar(x, mes=False):
        d = dt(x)
        if d is not None:
            fechas.add(d)
            if mes:
                fechas.add(d.replace(day=1))

    def responsable_agregar(nombre, simulado):
        n = limpio(nombre)
        if not n:
            return
        k = norm(n)
        if k in responsables:
            if simulado == 0:
                responsables[k] = (responsables[k][0], 0)
        else:
            responsables[k] = (n, int(simulado))

    for nombre, categoria, anotacion, pendiente, responsable, fecha in bsc:
        k = norm(nombre)
        if not k or k in kpis:
            raise ValueError(f"KPI BSC sin nombre o duplicado: {nombre}")
        codigo = "BSC_" + hashlib.sha256(k.encode("utf-8")).hexdigest()[:16].upper()
        estado = "PENDIENTE_VALIDACION" if int(pendiente or 0) or "SACAR" in limpio(anotacion).upper() else "VIGENTE"
        unidad = "Miles CLP" if k == "ventas_2026" else None
        kpis[k] = (codigo, limpio(nombre), limpio(categoria) or None, unidad,
                   "OFICIAL_BSC", estado, None)
        responsable_agregar(responsable, False)
        fecha_agregar(fecha)

    aliases = 0
    for departamento, nombre_kpi in departamentos:
        nk = norm(departamento)
        if not nk:
            raise ValueError("Departamento sin nombre")
        areas.setdefault(nk, limpio(departamento))
        if norm(nombre_kpi) not in kpis:
            aliases += 1
    if aliases:
        avisos.append(f"BSC departamental: {aliases} nombres no identicos a indicadores globales; "
                      "NO crear KPI ni modificar pesos sin validacion")

    for nombre, tipo, fecha in proyectos_bsc:
        k = norm(nombre)
        if not k or k in proyectos:
            raise ValueError(f"Proyecto BSC ausente o nombre ambiguo: {nombre}")
        proyectos[k] = (limpio(nombre), k, limpio(tipo) or None, "BSC/PROYECTOS")
        fecha_agregar(fecha)

    sin_rut = 0
    for rut, razon, ciudad, comuna, fecha in ventas:
        fecha_agregar(fecha, mes=True)
        rutkey = rut_norm(rut)
        if not rutkey:
            sin_rut += 1
            continue
        if rutkey not in clientes:
            clientes[rutkey] = (rutkey, limpio(razon) or None, limpio(ciudad) or None,
                                limpio(comuna) or None)
    if sin_rut:
        avisos.append(f"{sin_rut} facturas sin RUT: no crean DIM_CLIENTE")

    # Nuevas fuentes por proyecto, cada una seleccionada por su CargaID preciso.
    tareas = {}
    total_gantt = total_resumen = total_adj = 0
    for codigo_fuente in sorted(k for k in ids if k.startswith("proyecto_")):
        cid = ids[codigo_fuente]
        resumen = consultar(cur, """SELECT CodigoProyecto, NombreProyecto, FechaInicioPlan,
            FechaTerminoPlan, OrigenDatos FROM dbo.STG_PROYECTO_RESUMEN WHERE CargaID=?""", cid)
        tarea_rows = consultar(cur, """SELECT CodigoProyecto, NombreProyecto, CodigoTarea,
            NombreTarea, RecursoPrincipal, FechaInicioPlan, FechaTerminoPlan, OrigenDatos
            FROM dbo.STG_TAREA WHERE CargaID=? ORDER BY FilaExcel""", cid)
        gantt_rows = consultar(cur, """SELECT CodigoProyecto, CodigoTarea, NombreTarea, TareaPredecesora,
            FechaInicioPlan, FechaTerminoPlan, OrigenDatos
            FROM dbo.STG_PROYECTO_GANTT WHERE CargaID=? ORDER BY FilaExcel""", cid)
        adj = consultar(cur, """SELECT CodigoProyecto, NombreProyecto, FechaAdjudicacion, OrigenDatos
            FROM dbo.STG_ADJUDICACION WHERE CargaID=?""", cid)
        if len(resumen) != 1 or not tarea_rows or len(tarea_rows) != len(gantt_rows) or not adj:
            raise ValueError(f"{codigo_fuente}: faltan resumen, tareas, Gantt o adjudicaciones")
        total_resumen += len(resumen)
        total_gantt += len(gantt_rows)
        total_adj += len(adj)
        for cod, nombre, inicio, fin, origen in resumen:
            clave_proyecto = norm(nombre)
            if not clave_proyecto or limpio(origen) != "SIMULADO":
                raise ValueError(f"{codigo_fuente}: resumen sin nombre o sin etiqueta SIMULADO")
            if clave_proyecto not in proyectos:
                proyectos[clave_proyecto] = (limpio(nombre), clave_proyecto, None, "SEGUIMIENTO")
                avisos.append(f"Proyecto adicional sin BSC: {nombre}")
            fecha_agregar(inicio)
            fecha_agregar(fin)
        gantt_por_clave = {}
        for cod, tarea, nombre, predecesora, inicio, fin, origen in gantt_rows:
            clave = (limpio(cod).upper(), limpio(tarea).upper())
            if clave in gantt_por_clave or limpio(origen) != "SIMULADO":
                raise ValueError(f"{codigo_fuente}: Gantt duplicado o sin SIMULADO: {clave}")
            gantt_por_clave[clave] = (limpio(nombre), limpio(predecesora) or None)
            fecha_agregar(inicio)
            fecha_agregar(fin)
        for cod, nombre_proy, tarea, nombre_tarea, recurso, inicio, fin, origen in tarea_rows:
            clave = (limpio(cod).upper(), limpio(tarea).upper())
            kproy = norm(nombre_proy)
            if kproy not in proyectos or not all(clave) or clave in tareas:
                raise ValueError(f"{codigo_fuente}: tarea sin proyecto, codigo o duplicada: {clave}")
            if clave not in gantt_por_clave or gantt_por_clave[clave][0] != limpio(nombre_tarea):
                raise ValueError(f"{codigo_fuente}: tarea distinta del Gantt: {clave}")
            if limpio(origen) != "SIMULADO":
                raise ValueError(f"{codigo_fuente}: tarea sin etiqueta SIMULADO: {clave}")
            tarea_predecesora = gantt_por_clave[clave][1]
            tareas[clave] = (kproy, clave[0], clave[1], limpio(nombre_tarea),
                            tarea_predecesora, limpio(recurso) or None, 1)
            fecha_agregar(inicio)
            fecha_agregar(fin)
        if len([key for key in tareas if key[0] == resumen[0][0]]) != len(tarea_rows):
            raise ValueError(f"{codigo_fuente}: recuento de tareas por proyecto inconsistente")
        for cod, nombre, fecha, origen in adj:
            if norm(nombre) not in proyectos or limpio(origen) != "SIMULADO":
                raise ValueError(f"{codigo_fuente}: adjudicacion no vinculada o sin SIMULADO")
            fecha_agregar(fecha)
    if total_resumen != len([k for k in ids if k.startswith("proyecto_")]) or len(tareas) != total_gantt or total_adj < total_resumen:
        raise ValueError(f"Descuadre proyectos/Gantt/tareas/adjudicaciones: "
                         f"{total_resumen}/{total_gantt}/{len(tareas)}/{total_adj}")

    # Gmail SIN APROBAR: solamente dias para DIM_FECHA. No sustituye los
    # planes de STG_PROYECTO_GANTT ni agrega medidas en ventas/FACT.
    if ids.get("gmail_cierres"):
        cierres = consultar(cur, """SELECT Periodo, FechaCorreoUTC, OrigenDatos, EstadoValidacion
            FROM dbo.STG_GMAIL_CIERRE_MENSUAL WHERE CargaID=?""", ids["gmail_cierres"])
        for periodo, fecha_mail, _, _ in cierres:
            if periodo:
                if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", str(periodo)):
                    raise ValueError("Gmail: periodo de cierre invalido")
                fecha_agregar(date.fromisoformat(str(periodo) + "-01"))
            fecha_agregar(fecha_mail)
    if ids.get("gmail_contratos"):
        contratos = consultar(cur, """SELECT CodigoProyectoBSC, NombreProyectoBSC,
            FechaInicio, FechaTermino, FechaCorreoUTC, EstadoVinculacion, OrigenDatos,
            EstadoValidacion FROM dbo.STG_GMAIL_CONTRATO WHERE CargaID=?""", ids["gmail_contratos"])
        for cod, nombre, inicio, fin, mail, vinculacion, origen, estado in contratos:
            # Fechas en el calendario no equivalen a aprobacion del contrato.
            fecha_agregar(inicio)
            fecha_agregar(fin)
            fecha_agregar(mail)
            if limpio(nombre) and norm(nombre) not in proyectos:
                avisos.append("Gmail: contrato con nombre distinto del BSC; queda solo en STAGING")
            if limpio(estado).upper() not in ("APROBADO", "VALIDADO"):
                avisos.append("Gmail: contratos pendientes de aprobacion; no sustituyen Gantt ni BSC")

    for code, nombre, cat, unidad, regla in COMERCIALES:
        k = code.lower()
        if k in kpis:
            raise ValueError(f"Codigo KPI comercial duplicado: {code}")
        kpis[k] = (code, nombre, cat, unidad, "COMERCIAL", "VIGENTE", regla)
    for code, nombre, cat, unidad, regla in OPERACIONALES_PROYECTOS:
        k = code.lower()
        if k in kpis:
            raise ValueError(f"Codigo KPI operacional duplicado: {code}")
        kpis[k] = (code, nombre, cat, unidad, "OPERACIONAL", "PENDIENTE_VALIDACION", regla)

    dims = {
        "DIM_FECHA": [(fecha_key(d), d, d.day, d.month, d.year, (d.month - 1) // 3 + 1, MES[d.month])
                      for d in sorted(fechas)],
        "DIM_KPI": list(kpis.values()),
        "DIM_AREA": [(v,) for v in sorted(areas.values())],
        "DIM_RESPONSABLE": [responsables[k] for k in sorted(responsables)],
        "DIM_CLIENTE": [clientes[k] for k in sorted(clientes)],
        "DIM_PROYECTO": [proyectos[k] for k in sorted(proyectos)],
        # STG_TAREA contiene cifras de costo, NO categorias de costo nuevas;
        # se conserva DIM_COSTOS anterior sin introducir categorias ficticias.
        "DIM_COSTOS": [],
    }
    return dims, [tareas[k] for k in sorted(tareas)], list(dict.fromkeys(avisos))


def cargar_dimensiones(conn, dims, tareas):
    cur = conn.cursor()
    try:
        cur.execute("SET XACT_ABORT ON")
        cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        for tabla, filas in dims.items():
            columnas, clave = SCHEMA[tabla]
            idx = columnas.index(clave)
            nombres = ",".join("[" + c + "]" for c in columnas)
            placeholders = ",".join("?" for _ in columnas)
            sql = (f"IF NOT EXISTS (SELECT 1 FROM dbo.[{tabla}] WITH (UPDLOCK,HOLDLOCK) "
                   f"WHERE [{clave}]=?) INSERT INTO dbo.[{tabla}] ({nombres}) VALUES ({placeholders})")
            previo = int(cur.execute(f"SELECT COUNT_BIG(*) FROM dbo.[{tabla}]").fetchone()[0])
            for fila in filas:
                cur.execute(sql, fila[idx], *fila)
            posterior = int(cur.execute(f"SELECT COUNT_BIG(*) FROM dbo.[{tabla}]").fetchone()[0])
            print(f"  {tabla:<18s}: {posterior - previo} nuevas | {len(filas)} propuestas")

        por_proyecto = {limpio(nombre): int(pid) for pid, nombre in
                        consultar(cur, "SELECT Proyecto_Key, NombreNormalizado FROM dbo.DIM_PROYECTO")}
        previo = int(cur.execute("SELECT COUNT_BIG(*) FROM dbo.DIM_TAREA").fetchone()[0])
        sql_tarea = """IF NOT EXISTS (
            SELECT 1 FROM dbo.DIM_TAREA WITH (UPDLOCK, HOLDLOCK)
            WHERE CodigoProyecto=? AND CodigoTarea=?
        ) INSERT INTO dbo.DIM_TAREA
            (Proyecto_Key, CodigoProyecto, CodigoTarea, NombreTarea,
             TareaPredecesora, RecursoPrincipal, EsSimulado)
          VALUES (?, ?, ?, ?, ?, ?, ?)"""
        for nombre_normal, codigo_proy, codigo_tarea, nombre_tarea, predecesora, recurso, simulado in tareas:
            pid = por_proyecto.get(nombre_normal)
            if pid is None:
                raise ValueError(f"DIM_TAREA: proyecto no cargado en DIM_PROYECTO: {codigo_proy}")
            cur.execute(sql_tarea, codigo_proy, codigo_tarea, pid, codigo_proy,
                        codigo_tarea, nombre_tarea, predecesora, recurso, simulado)
        posterior = int(cur.execute("SELECT COUNT_BIG(*) FROM dbo.DIM_TAREA").fetchone()[0])
        print(f"  {'DIM_TAREA':<18s}: {posterior - previo} nuevas | {len(tareas)} propuestas")
        conn.commit()
        print("COMMIT OK: dimensiones confirmadas. FACT intactas.")
    except Exception:
        conn.rollback()
        print("ROLLBACK PASO 05: no se confirmaron inserciones de esta ejecucion", file=sys.stderr)
        raise


def main():
    p = argparse.ArgumentParser(description="Paso 05: dimensiones Drive+Gmail en MAAS_ECOLOGIA_4")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--verificar", action="store_true", help="Solo lectura y propuesta de dimensiones")
    group.add_argument("--cargar", action="store_true", help="Insertar claves ausentes, sin eliminar anteriores")
    p.add_argument("--servidor", default=DEFAULT_SERVER)
    args = p.parse_args()
    print("MAAS 4 | PASO 05 | " + ("VERIFICAR SIN ESCRIBIR" if args.verificar else "CARGAR DIMENSIONES"))
    conn = conectar(args.servidor)
    try:
        cur = conn.cursor()
        tiene_tarea = comprobar_estructura(cur, permitir_sin_tarea=args.verificar)
        ids = fuentes_activas(cur)
        print(f"STAGING ACTIVO: {sum(v is not None for v in ids.values())} versiones exactas confirmadas "
              "(Drive + Gmail)")
        dims, tareas, avisos = construir(cur, ids)
        for tabla, filas in dims.items():
            print(f"  {tabla:<18s}: {len(filas)} registros propuestos")
        print(f"  {'DIM_TAREA':<18s}: {len(tareas)} registros propuestos")
        if avisos:
            print("AVISOS:")
            for m in avisos:
                print(" - " + m)
        if args.verificar:
            if not tiene_tarea:
                print("DIM_TAREA aun no existe: preparar con MAAS_05_PREPARAR_DIM_TAREA.sql ANTES de --cargar")
            print("VERIFICACION OK. SQL consultado en solo lectura; no se escribio ninguna tabla.")
        else:
            cargar_dimensiones(conn, dims, tareas)
            print("DIMENSIONES LISTAS. NO ejecutar paso 06 ni el ETL maestro sin adaptarlos.")
    finally:
        if args.verificar:
            conn.rollback()
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR PASO 05: {exc}", file=sys.stderr)
        sys.exit(1)
