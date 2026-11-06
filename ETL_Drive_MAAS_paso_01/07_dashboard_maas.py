# -*- coding: utf-8 -*-
"""MAAS ECOLOGIA 4 | PASO 07 - Dashboard local Streamlit (SOLO LECTURA).

Ejecutar desde la carpeta ETL_Drive_MAAS_paso_01:
    py -m pip install streamlit plotly pandas pyodbc
    py -m streamlit run .\07_dashboard_maas.py

IMPORTANTE: Esta app NO ejecuta el ETL ni modifica SQL Server o Google Drive.
Los datos cambiarán cuando se vuelvan a ejecutar los scripts de extracción y carga.
Los costos, fechas y estados del Excel de proyectos son de DEMOSTRACION.
"""
from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

BASE = "MAAS_ECOLOGIA_4"
SERVIDOR_POR_DEFECTO = r"Giuli\GIULIANA"

st.set_page_config(
    page_title="MAAS Ecología | Control de Gestión",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """<style>
    .block-container {padding-top: 1.7rem; max-width: 1600px;}
    div[data-testid="stMetric"] {background: #f4f7f8; border: 1px solid #dce6e5;
      border-radius: 12px; padding: 12px 16px;}
    div[data-testid="stMetricLabel"] {color: #426060;}
    </style>""",
    unsafe_allow_html=True,
)


def sql_connection(server: str):
    import pyodbc

    drivers = pyodbc.drivers()
    driver = next(
        (d for d in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server") if d in drivers),
        None,
    )
    if not driver:
        raise RuntimeError("No se encontró ODBC Driver 17 o 18 para SQL Server.")
    conn_string = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={BASE};"
        "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
        "Connection Timeout=10;Application Name=MAAS_STREAMLIT_LOCAL;"
    )
    # TrustServerCertificate solo para esta instancia local de prueba.
    return pyodbc.connect(conn_string, autocommit=True, timeout=15)


@st.cache_data(ttl=90, show_spinner=False)
def query_df(server: str, sql: str) -> pd.DataFrame:
    """Consulta solo lectura. El cursor y la conexión se cierran al terminar."""
    conn = sql_connection(server)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        columns = [col[0] for col in cur.description]
        return pd.DataFrame.from_records(cur.fetchall(), columns=columns)
    finally:
        conn.close()


def to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for name in cols:
        if name in df:
            df[name] = pd.to_numeric(df[name], errors="coerce")
    return df


def pesos(value) -> str:
    if pd.isna(value):
        return "—"
    return "$" + f"{value:,.0f}".replace(",", ".")


def entero(value) -> str:
    if pd.isna(value):
        return "—"
    return f"{value:,.0f}".replace(",", ".")


def porcentaje(value) -> str:
    if pd.isna(value):
        return "—"
    return f"{float(value) * 100:.1f}%".replace(".", ",")


def tabla(df: pd.DataFrame, **kwargs):
    st.dataframe(df, use_container_width=True, hide_index=True, **kwargs)


SQL_PROJECTS = """
SELECT Proyecto_Key, NombreProyecto, TipoProyecto, FechaSeguimiento,
       FechaInicioPlanificada, FechaTerminoPlanificada, FechaTerminoReal,
       EstadoProyecto, EsSimulado, VentaOC_CLP, MargenObjetivo, MargenActual,
       MargenProyectado, NoCumpleOriginal, NoCumpleCalculado,
       CostoPresupuestado_CLP, CostoRealAcumulado_CLP,
       SaldoPresupuestado_CLP, DiferenciaCosto_CLP,
       DuracionPlanificadaDias, DiasAtraso, SituacionPlazo, Observaciones
FROM dbo.VW_PROYECTOS_ULTIMO_CORTE
ORDER BY NombreProyecto;
"""
SQL_HISTORY = """
SELECT Proyecto_Key, NombreProyecto, FechaSeguimiento, EstadoProyecto,
       CostoPresupuestado_CLP, CostoRealAcumulado_CLP,
       DiferenciaCosto_CLP, DiasAtraso, SituacionPlazo
FROM dbo.VW_SEGUIMIENTO_PROYECTOS
ORDER BY NombreProyecto, FechaSeguimiento;
"""
SQL_COSTS = """
SELECT Proyecto_Key, NombreProyecto, CategoriaCosto, Anio, Mes,
       EsSimulado, CantidadMovimientos, TotalCosto_CLP
FROM dbo.VW_COSTOS_POR_CATEGORIA
ORDER BY NombreProyecto, Anio, Mes, CategoriaCosto;
"""
SQL_BSC = """
SELECT f.Fecha_Key, fe.Fecha, k.CodigoKPI, k.NombreKPI, k.CategoriaKPI,
       k.TipoIndicador, k.EstadoRevision, k.UnidadMedida, f.Ambito,
       ar.NombreArea, f.MetaNumerica, f.MetaTexto,
       f.ResultadoNumerico, f.ResultadoTexto, f.Avance,
       f.Cumplimiento, f.Ponderacion
FROM dbo.FACT_KPI_ESTRATEGICO AS f
JOIN dbo.DIM_KPI AS k ON k.KPI_Key = f.KPI_Key
JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key = f.Fecha_Key
LEFT JOIN dbo.DIM_AREA AS ar ON ar.Area_Key = f.Area_Key
WHERE k.TipoIndicador = 'OFICIAL_BSC' AND f.FuenteResultado = 'BSC'
ORDER BY fe.Fecha DESC, k.NombreKPI;
"""
SQL_MONTHS = """
SELECT fe.Fecha, k.CodigoKPI, f.ResultadoNumerico
FROM dbo.FACT_KPI_ESTRATEGICO AS f
JOIN dbo.DIM_KPI AS k ON k.KPI_Key = f.KPI_Key
JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key = f.Fecha_Key
WHERE f.FuenteResultado='VENTAS' AND f.Ambito='GLOBAL'
  AND f.GranoTemporal='MES'
  AND k.CodigoKPI IN
      ('COM_VENTAS_NETAS_MES','COM_FACTURAS_MES','COM_CLIENTES_MES','COM_TICKET_MES')
ORDER BY fe.Fecha;
"""
SQL_CLIENTS = """
SELECT fe.Fecha, cl.RazonSocial, cl.RUT_Normalizado,
       cl.EsMinero, f.ResultadoNumerico AS VentaNeta_CLP
FROM dbo.FACT_KPI_ESTRATEGICO AS f
JOIN dbo.DIM_KPI AS k ON k.KPI_Key=f.KPI_Key
JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key=f.Fecha_Key
JOIN dbo.DIM_CLIENTE AS cl ON cl.Cliente_Key=f.Cliente_Key
WHERE f.FuenteResultado='VENTAS' AND f.Ambito='CLIENTE'
  AND f.GranoTemporal='MES' AND k.CodigoKPI='COM_VENTA_CLIENTE_MES'
ORDER BY fe.Fecha, cl.RazonSocial;
"""
SQL_LOADS = """
SELECT TipoFuente, MAX(FinUTC) AS UltimaCargaUTC
FROM dbo.ETL_CARGA WHERE Estado='OK' GROUP BY TipoFuente
ORDER BY TipoFuente;
"""

st.sidebar.title("🌿 MAAS Ecología")
st.sidebar.caption("ETL + Data Warehouse · MAAS_ECOLOGIA_4")
server = st.sidebar.text_input(
    "Servidor SQL Server", value=os.environ.get("MAAS_SQL_SERVER", SERVIDOR_POR_DEFECTO)
)
page = st.sidebar.radio(
    "Secciones",
    ["📁 Seguimiento de proyectos", "📊 BSC y KPI", "💰 Ventas 2026"],
    label_visibility="collapsed",
)
if st.sidebar.button("Actualizar lectura desde SQL"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.warning(
    "Los costos, fechas, responsables y estados de proyectos son SIMULADOS. "
    "No utilizar estos resultados para decisiones reales de MAAS."
)
st.sidebar.caption(
    "Esta aplicación solo lee SQL Server. Para actualizar datos desde Drive, "
    "primero hay que ejecutar el ETL."
)

try:
    loads = query_df(server, SQL_LOADS)
except Exception as exc:
    st.error("No se pudo conectar a SQL Server o consultar MAAS_ECOLOGIA_4.")
    st.code(str(exc))
    st.info("Verifica que SQL Server esté abierto, el nombre del servidor y la conexión de Windows.")
    st.stop()

if not loads.empty:
    st.sidebar.markdown("**Últimas cargas en SQL**")
    for r in loads.itertuples(index=False):
        stamp = pd.to_datetime(r.UltimaCargaUTC, errors="coerce")
        label = stamp.strftime("%d/%m/%Y %H:%M UTC") if pd.notna(stamp) else "Sin fecha"
        st.sidebar.caption(f"{r.TipoFuente}: {label}")

if page.startswith("📁"):
    st.title("Seguimiento de proyectos")
    st.caption("Eje central de la tesis · resultados al último corte de cada proyecto")
    st.info("🧪 Vista de demostración: las fechas y los costos operacionales provienen del archivo simulado de proyectos.")
    try:
        projects = query_df(server, SQL_PROJECTS)
        history = query_df(server, SQL_HISTORY)
        costs = query_df(server, SQL_COSTS)
    except Exception as exc:
        st.error(f"No fue posible consultar las vistas de proyectos: {exc}")
        st.stop()
    if projects.empty:
        st.warning("Aún no hay seguimientos cargados en el Data Warehouse.")
        st.stop()
    if projects["Proyecto_Key"].duplicated().any():
        st.error("Se encontraron proyectos repetidos en la vista de último corte. Revisar SQL.")
        st.stop()
    to_numeric(projects, ["CostoPresupuestado_CLP", "CostoRealAcumulado_CLP",
                          "DiferenciaCosto_CLP", "DiasAtraso", "VentaOC_CLP",
                          "MargenObjetivo", "MargenActual", "NoCumpleOriginal", "NoCumpleCalculado"])
    to_numeric(history, ["CostoRealAcumulado_CLP", "CostoPresupuestado_CLP", "DiasAtraso"])
    to_numeric(costs, ["TotalCosto_CLP", "CantidadMovimientos"])

    left, right = st.columns(2)
    with left:
        types = ["Todos"] + sorted(projects["TipoProyecto"].dropna().astype(str).unique().tolist())
        typ = st.selectbox("Tipo de proyecto", types)
    with right:
        states = ["Todos"] + sorted(projects["EstadoProyecto"].dropna().astype(str).unique().tolist())
        state = st.selectbox("Estado", states)
    sel = projects.copy()
    if typ != "Todos": sel = sel[sel["TipoProyecto"] == typ]
    if state != "Todos": sel = sel[sel["EstadoProyecto"] == state]
    if sel.empty:
        st.info("No hay proyectos para esos filtros.")
        st.stop()

    late = sel["SituacionPlazo"].isin(["Vencido", "Finalizado con atraso"])
    overdue_open = (sel["SituacionPlazo"] == "Vencido").sum()
    finished = (sel["EstadoProyecto"] == "Finalizado").sum()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Proyectos", entero(sel["Proyecto_Key"].nunique()))
    col2.metric("Finalizados", entero(finished))
    col3.metric("Con atraso", entero(late.sum()), help="Vencidos o finalizados fuera de plazo")
    col4.metric("Vencidos y abiertos", entero(overdue_open))
    col5, col6, col7 = st.columns(3)
    col5.metric("Costo presupuestado", pesos(sel["CostoPresupuestado_CLP"].sum()))
    col6.metric("Costo real acumulado", pesos(sel["CostoRealAcumulado_CLP"].sum()))
    col7.metric("Diferencia real - presupuesto", pesos(sel["DiferenciaCosto_CLP"].sum()))
    st.caption("Las sumas incluyen solo el último seguimiento por proyecto; no se suman cortes históricos.")

    st.subheader("Situación de los proyectos")
    main = sel[["NombreProyecto", "EstadoProyecto", "SituacionPlazo", "DiasAtraso",
                "FechaTerminoPlanificada", "FechaTerminoReal", "CostoPresupuestado_CLP",
                "CostoRealAcumulado_CLP", "DiferenciaCosto_CLP"]].copy()
    for c in ("FechaTerminoPlanificada", "FechaTerminoReal"):
        main[c] = pd.to_datetime(main[c], errors="coerce").dt.strftime("%d/%m/%Y").fillna("—")
    for c in ["CostoPresupuestado_CLP", "CostoRealAcumulado_CLP", "DiferenciaCosto_CLP"]:
        main[c] = main[c].map(pesos)
    main = main.rename(columns={
        "NombreProyecto": "Proyecto", "EstadoProyecto": "Estado",
        "SituacionPlazo": "Situación del plazo", "DiasAtraso": "Días de atraso",
        "FechaTerminoPlanificada": "Término planificado", "FechaTerminoReal": "Término real",
        "CostoPresupuestado_CLP": "Costo presupuestado", "CostoRealAcumulado_CLP": "Costo real",
        "DiferenciaCosto_CLP": "Desviación de costo",
    })
    tabla(main)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        statuses = sel.groupby("SituacionPlazo", dropna=False).size().reset_index(name="Proyectos")
        fig = px.bar(statuses, x="SituacionPlazo", y="Proyectos", text="Proyectos",
                     labels={"SituacionPlazo":"Situación de plazo"}, title="Cumplimiento de plazos")
        fig.update_layout(showlegend=False, height=390)
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        if not costs.empty:
            pkeys = set(sel["Proyecto_Key"].tolist())
            cost_slice = costs[costs["Proyecto_Key"].isin(pkeys)]
            grouped = cost_slice.groupby("CategoriaCosto", as_index=False)["TotalCosto_CLP"].sum()
            fig = px.bar(grouped, x="CategoriaCosto", y="TotalCosto_CLP",
                         labels={"CategoriaCosto":"Categoría", "TotalCosto_CLP":"CLP"},
                         title="Gastos por categoría (simulados)")
            fig.update_layout(showlegend=False, height=390)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Detalle e historial de un proyecto")
    selected_name = st.selectbox("Selecciona un proyecto", sorted(sel["NombreProyecto"].tolist()))
    project = sel[sel["NombreProyecto"] == selected_name].iloc[0]
    project_history = history[history["Proyecto_Key"] == project["Proyecto_Key"]].copy()
    project_history["FechaSeguimiento"] = pd.to_datetime(project_history["FechaSeguimiento"])
    project_history = project_history.sort_values("FechaSeguimiento")
    a, b, c = st.columns(3)
    a.metric("Costo real acumulado", pesos(project["CostoRealAcumulado_CLP"]))
    b.metric("Costo presupuestado", pesos(project["CostoPresupuestado_CLP"]))
    c.metric("Días de atraso al corte", entero(project["DiasAtraso"]))
    if not project_history.empty:
        fig = px.line(project_history, x="FechaSeguimiento", y="CostoRealAcumulado_CLP",
                      markers=True, title="Evolución del costo real acumulado",
                      labels={"FechaSeguimiento": "Fecha del seguimiento", "CostoRealAcumulado_CLP": "CLP"})
        st.plotly_chart(fig, use_container_width=True)
    discrepancy = sel[
        sel["NoCumpleOriginal"].notna()
        & sel["NoCumpleCalculado"].notna()
        & (sel["NoCumpleOriginal"] != sel["NoCumpleCalculado"])
    ]
    if not discrepancy.empty:
        st.warning("Hay diferencias entre la bandera de margen original y la calculada. "
                   "No se modifican los datos oficiales.")
        tabla(discrepancy[["NombreProyecto", "MargenObjetivo", "MargenActual",
                            "NoCumpleOriginal", "NoCumpleCalculado"]])

elif page.startswith("📊"):
    st.title("Cuadro de mando estratégico (BSC)")
    st.caption("Indicadores oficiales informados por MAAS · se conservan los que dicen 'SACAR'")
    try:
        bsc = query_df(server, SQL_BSC)
    except Exception as exc:
        st.error(f"No fue posible consultar los KPI: {exc}")
        st.stop()
    if bsc.empty:
        st.warning("No hay mediciones del BSC cargadas.")
        st.stop()
    to_numeric(bsc, ["MetaNumerica", "ResultadoNumerico", "Cumplimiento", "Ponderacion", "Avance"])
    dates = sorted(pd.to_datetime(bsc["Fecha"], errors="coerce").dropna().dt.date.unique(), reverse=True)
    chosen_date = st.selectbox("Fecha de referencia", dates, format_func=lambda d: d.strftime("%d/%m/%Y"))
    bsc = bsc[pd.to_datetime(bsc["Fecha"], errors="coerce").dt.date == chosen_date]
    areas = ["GLOBAL"] + sorted(bsc["NombreArea"].dropna().unique().tolist())
    scope = st.selectbox("Vista", areas)
    chosen = bsc[bsc["Ambito"] == ("GLOBAL" if scope == "GLOBAL" else "AREA")].copy()
    if scope != "GLOBAL":
        chosen = chosen[chosen["NombreArea"] == scope]
    cats = ["Todas"] + sorted(chosen["CategoriaKPI"].dropna().unique().tolist())
    cat = st.selectbox("Categoría", cats)
    if cat != "Todas": chosen = chosen[chosen["CategoriaKPI"] == cat]
    col1, col2, col3 = st.columns(3)
    col1.metric("Indicadores mostrados", entero(len(chosen)))
    col2.metric("Pendientes de revisión", entero((chosen["EstadoRevision"] == "PENDIENTE_VALIDACION").sum()))
    col3.metric("Cumplimiento promedio*", porcentaje(chosen["Cumplimiento"].mean()))
    st.caption("* Promedio descriptivo simple, NO es el puntaje BSC ponderado oficial.")
    if chosen.empty:
        st.info("Sin mediciones para los filtros seleccionados.")
        st.stop()
    show = chosen[["NombreKPI", "CategoriaKPI", "MetaNumerica", "MetaTexto",
                   "ResultadoNumerico", "ResultadoTexto", "Avance", "Cumplimiento",
                   "Ponderacion", "EstadoRevision"]].copy()
    show["Meta"] = show.apply(lambda r: r["MetaTexto"] if pd.notna(r["MetaTexto"]) and str(r["MetaTexto"]) else
                              (f"{r['MetaNumerica']:,.3f}" if pd.notna(r["MetaNumerica"]) else "—"), axis=1)
    show["Resultado"] = show.apply(lambda r: r["ResultadoTexto"] if pd.notna(r["ResultadoTexto"]) and str(r["ResultadoTexto"]) else
                                   (f"{r['ResultadoNumerico']:,.3f}" if pd.notna(r["ResultadoNumerico"]) else "—"), axis=1)
    show["Cumplimiento"] = show["Cumplimiento"].map(porcentaje)
    show["Avance"] = show["Avance"].map(porcentaje)
    show = show[["NombreKPI", "CategoriaKPI", "Meta", "Resultado", "Avance",
                 "Cumplimiento", "Ponderacion", "EstadoRevision"]]
    tabla(show.rename(columns={"NombreKPI": "Indicador", "CategoriaKPI": "Categoría",
                               "Ponderacion": "Peso de la fuente", "EstadoRevision": "Revisión"}))
    plot_data = chosen[chosen["Cumplimiento"].notna()][["NombreKPI", "Cumplimiento"]].copy()
    if not plot_data.empty:
        plot_data["Cumplimiento_pct"] = plot_data["Cumplimiento"].clip(lower=0) * 100
        fig = px.bar(plot_data.sort_values("Cumplimiento_pct"), x="Cumplimiento_pct",
                     y="NombreKPI", orientation="h", height=max(450, 27*len(plot_data)),
                     labels={"NombreKPI": "KPI", "Cumplimiento_pct": "Cumplimiento (%)"},
                     title="Cumplimiento registrado por indicador")
        fig.update_layout(yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)
    st.caption("Cuatro nombres departamentales no tienen equivalencia confirmada y quedan pendientes de validación.")

else:
    st.title("Análisis de ventas 2026")
    st.caption("Indicadores calculados desde las facturas del reporte de ventas de MAAS")
    try:
        month = query_df(server, SQL_MONTHS)
        clients = query_df(server, SQL_CLIENTS)
    except Exception as exc:
        st.error(f"No fue posible consultar los datos comerciales: {exc}")
        st.stop()
    if month.empty:
        st.warning("No hay ventas mensuales calculadas en el Data Warehouse.")
        st.stop()
    to_numeric(month, ["ResultadoNumerico"])
    month["Fecha"] = pd.to_datetime(month["Fecha"])
    monthly = month.pivot_table(index="Fecha", columns="CodigoKPI", values="ResultadoNumerico",
                               aggfunc="first").sort_index()
    needed = ["COM_VENTAS_NETAS_MES", "COM_FACTURAS_MES", "COM_CLIENTES_MES", "COM_TICKET_MES"]
    missing = [code for code in needed if code not in monthly.columns]
    if missing:
        st.error(f"Faltan KPI comerciales en SQL: {', '.join(missing)}")
        st.stop()
    monthly["Mes"] = monthly.index.strftime("%Y-%m")
    total_net = monthly["COM_VENTAS_NETAS_MES"].sum()
    total_documents = monthly["COM_FACTURAS_MES"].sum()
    cl1, cl2, cl3, cl4 = st.columns(4)
    cl1.metric("Venta neta acumulada", pesos(total_net))
    cl2.metric("Facturas", entero(total_documents))
    cl3.metric("Meses registrados", entero(len(monthly)))
    cl4.metric("Ticket promedio global", pesos(total_net / total_documents if total_documents else float("nan")))
    st.warning("Las ventas del reporte y las del BSC oficial tienen criterios/períodos aún por conciliar. No se sustituyen.")
    fig = px.bar(monthly.reset_index(), x="Mes", y="COM_VENTAS_NETAS_MES", title="Ventas netas por mes",
                 labels={"COM_VENTAS_NETAS_MES": "Ventas netas (CLP)"})
    fig.update_layout(xaxis_tickangle=-35)
    st.plotly_chart(fig, use_container_width=True)
    view = monthly[["Mes", "COM_VENTAS_NETAS_MES", "COM_FACTURAS_MES",
                    "COM_CLIENTES_MES", "COM_TICKET_MES"]].copy()
    view["COM_VENTAS_NETAS_MES"] = view["COM_VENTAS_NETAS_MES"].map(pesos)
    view["COM_TICKET_MES"] = view["COM_TICKET_MES"].map(pesos)
    view = view.rename(columns={"Mes":"Mes", "COM_VENTAS_NETAS_MES":"Ventas netas",
                                "COM_FACTURAS_MES":"Facturas", "COM_CLIENTES_MES":"Clientes distintos",
                                "COM_TICKET_MES":"Ticket promedio"})
    tabla(view)

    if not clients.empty:
        to_numeric(clients, ["VentaNeta_CLP"])
        rank = clients.groupby(["RUT_Normalizado", "RazonSocial"], dropna=False,
                               as_index=False)["VentaNeta_CLP"].sum().sort_values("VentaNeta_CLP", ascending=False)
        st.subheader("Clientes con mayor facturación")
        fig = px.bar(rank.head(10).sort_values("VentaNeta_CLP"), x="VentaNeta_CLP", y="RazonSocial",
                     orientation="h", labels={"RazonSocial":"Cliente", "VentaNeta_CLP":"Ventas netas (CLP)"})
        fig.update_layout(yaxis_title=None, height=450)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Clasificación minera pendiente: DIM_CLIENTE.EsMinero requiere validación de MAAS. "
                   "Los clientes nuevos requieren historial de años anteriores y criterios comerciales.")

st.divider()
st.caption("MAAS_ECOLOGIA_4 · Tablero local · Consultas de solo lectura · "
           "Datos de proyectos y costos simulados para evaluación académica")
