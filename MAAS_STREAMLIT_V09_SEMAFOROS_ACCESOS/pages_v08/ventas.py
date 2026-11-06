# -*- coding: utf-8 -*-
"""MAAS ECOLOGIA · V14.2 · Ventas 2026 + KPI comerciales SQL.

INSTALACION: reemplazar SOLO pages_v08/ventas.py con este archivo.
No cambia SQL Server, ETL, contraseñas ni otros módulos.
Lee los 9 indicadores comerciales V14 existentes en SQL, sin reescribir el ETL.

Datos y metodología:
- Venta neta: suma COM_VENTAS_NETAS_MES (CLP, no miles de pesos).
- Facturas: suma COM_FACTURAS_MES (del mismo rango mensual).
- Clientes únicos: RUT normalizado; si falta, razón social del reporte.
- Ticket medio: venta neta del período / número de facturas.
- El BSC oficial usa otra fuente y no se sustituye automáticamente.
- No se inventan metas mensuales ni semáforos comerciales.
- Primera compra observada NO implica cliente históricamente nuevo.
- El acumulado anual se calcula desde enero hasta el mes de corte, aunque el filtro empiece después.
"""
from __future__ import annotations

# Acceso basado en la sesión del portal MAAS (no en el perfil de esta página).
# Validar ANTES de consultar datos de SQL Server.
import streamlit as st
_rol_maas = st.session_state.get('maas_portal_perfil')
if not (st.session_state.get('maas_portal_autorizado') is True
        and _rol_maas in {'administracion', 'gerencia'}):
    st.error('Tu sesión no tiene autorización para esta pestaña.')
    st.stop()

from html import escape
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from maas_datos import cargar

# Importante: proteger ANTES de consultar los importes comerciales.
pass  # Acceso libre MAAS 4

AZUL = '#244563'
AZUL_CLARO = '#4E769A'
TURQUESA = '#39A6A0'
VERDE = '#43A27A'
AMARILLO = '#E4B24F'
ROJO = '#D65C63'
GRIS = '#8598AC'
MESES = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
         'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')


def numero(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else float('nan')
    except (ValueError, TypeError):
        return float('nan')


def formato_num(v, decimales=0):
    x = numero(v)
    if not math.isfinite(x):
        return '—'
    return f'{x:,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def clp(v):
    x = numero(v)
    return '$' + f'{round(x):,}'.replace(',', '.') if math.isfinite(x) else '—'


def porcentaje(v, decimales=1):
    x = numero(v)
    if not math.isfinite(x):
        return '—'
    return formato_num(x, decimales) + '%'


def corto(v):
    x = numero(v)
    if not math.isfinite(x):
        return '—'
    if abs(x) >= 1_000_000_000:
        return formato_num(x / 1_000_000_000, 2) + ' mil MM'
    if abs(x) >= 1_000_000:
        return formato_num(x / 1_000_000, 1) + ' MM'
    return clp(x)


def nombre_mes(periodo):
    return f'{MESES[periodo.month - 1]} {periodo.year}'


def html(v):
    return escape(str(v), quote=True)


def variacion(actual, anterior):
    a, b = numero(actual), numero(anterior)
    if not (math.isfinite(a) and math.isfinite(b) and b > 0):
        return float('nan')
    return (a / b - 1) * 100



# Iconografía decorativa SVG: el mismo azul para todas las secciones.
VT_ICONOS = {
    'store': '<path d="M3 10 5 4h14l2 6v10H3V10Z"/><path d="M3 10c1.4 1.8 3 1.8 4.5 0S10 11.8 12 10s3 1.8 4.5 0 3.1 1.8 4.5 0M9 20v-7h6v7"/>',
    'wallet': '<rect x="3" y="6" width="18" height="15" rx="3"/><path d="M6 6V4h12v2M15 13h6v5h-6a2.5 2.5 0 0 1 0-5Z"/>',
    'receipt': '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z"/><path d="M9 8h6M9 12h6"/>',
    'users': '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 5"/>',
    'money': '<circle cx="12" cy="12" r="9"/><path d="M12 6v12M15 9c-.8-1.2-6-1.4-6 1s6 1.3 6 4-5 2.1-6 .7"/>',
    'chart': '<path d="M3 20h18M6 17V9m6 8V5m6 12v-6"/>',
    'trend': '<path d="M3 17 9 11l4 3 8-9M16 5h5v5"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'trophy': '<path d="M7 4h10v7a5 5 0 0 1-10 0V4ZM7 6H4v3a4 4 0 0 0 4 4m9-7h3v3a4 4 0 0 1-4 4M12 16v4m-5 0h10"/>',
    'pie': '<circle cx="12" cy="12" r="9"/><path d="M12 3v9h9"/>',
    'search': '<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
    'filter': '<path d="M4 5h16l-6 7v6l-4 2v-8L4 5Z"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    'list': '<path d="M9 6h12M9 12h12M9 18h12M4 6h.1M4 12h.1M4 18h.1"/>',
    'file': '<path d="M6 2h8l5 5v15H6V2Z"/><path d="M14 2v6h5M9 13h7m-7 4h7"/>',
    'percent': '<circle cx="7" cy="7" r="2"/><circle cx="17" cy="17" r="2"/><path d="M5 19 19 5"/>',
}

def vt_icon(nombre, size=20):
    dibujo = VT_ICONOS.get(nombre, VT_ICONOS['chart'])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="0 0 24 24" fill="none" stroke="#326BC3" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{dibujo}</svg>')

def vt_icon_para(texto):
    titulo = str(texto).lower()
    for terminos, icono in [
        (('ticket',), 'receipt'), (('factura',), 'receipt'),
        (('primera compra',), 'store'), (('meses con compra',), 'calendar'), (('participación sobre',), 'pie'), (('clientes únicos', 'clientes con', 'cliente principal', 'explorar clientes'), 'users'),
        (('participación',), 'pie'), (('variación', 'crecimiento'), 'trend'),
        (('mejor mes',), 'trophy'), (('promedio',), 'chart'),
        (('acumulad', 'facturación', 'ventas', 'venta'), 'money'),
        (('mensual', 'evolución'), 'chart'), (('indicadores',), 'target'),
        (('detalle',), 'list'), (('filtro',), 'filter'),
    ]:
        if any(t in titulo for t in terminos):
            return icono
    return 'chart'

def vt_seccion(titulo):
    return ('<div class="vt10-sec vt-section-icon"><span class="vt-icon">'
            + vt_icon(vt_icon_para(titulo), 20) + '</span><span>' + html(titulo) + '</span></div>')

CSS = '''<style>
.vt10-head{display:flex;justify-content:space-between;align-items:center;
    gap:16px;flex-wrap:wrap;margin:4px 0 16px}
.vt10-title{font-size:clamp(1.85rem,2.6vw,2.35rem);font-weight:850;
    letter-spacing:-.035em;color:#1C3652;line-height:1.18}
.vt10-sub{font-size:.87rem;color:#7B8DA1;margin-top:7px}
.vt10-date{background:#fff;border:1px solid #DCE7F0;padding:10px 14px;
    border-radius:12px;font-size:.78rem;color:#546F89;font-weight:760}
.vt10-sec{font-size:1.13rem;font-weight:830;color:#26415C;margin:22px 0 10px}
.vt10-metric{background:#fff;border:1px solid #DEE7EF;border-top:4px solid var(--co);
    border-radius:14px;padding:17px 17px 16px;min-height:136px;margin-bottom:6px}
.vt10-mname{color:#657C92;font-size:.78rem;font-weight:770}
.vt10-mvalue{color:#1C3754;font-size:clamp(1.22rem,1.9vw,1.98rem);
    font-weight:850;letter-spacing:-.025em;margin:10px 0 7px;overflow-wrap:anywhere}
.vt10-mnote{color:#8295A8;font-size:.74rem;line-height:1.5}
.vt10-insight{background:#fff;border:1px solid #DEE7EF;border-left:4px solid var(--co);
    border-radius:12px;padding:13px 16px;min-height:86px;margin:5px 0 2px}
.vt10-ilabel{color:#71869B;font-size:.77rem;font-weight:760}
.vt10-ivalue{font-size:1.08rem;color:#294965;font-weight:850;margin-top:5px}
.vt10-ihelp{font-size:.72rem;color:#91A0AF;margin-top:4px;line-height:1.3}
.vt10-note{font-size:.78rem;color:#7D8FA2;line-height:1.55}
.vt10-tag{background:#EEF4F8;color:#52718D;border-radius:30px;padding:5px 11px;
    font-size:.7rem;font-weight:780;display:inline-block;margin-top:4px}

/* Ventas: armonía con Inicio/Gerencia, sin cambiar operaciones de datos */
.vt10-title{font-size:2.1rem!important;color:#142C4E!important}
.vt10-head{margin:5px 0 18px!important}
.vt10-icon-title{display:flex;align-items:center;gap:13px}
.vt-icon{width:39px;height:39px;border-radius:12px;background:#EDF4FF;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}
.vt-section-icon{display:flex;align-items:center;gap:10px;line-height:1.25}
.vt-section-icon .vt-icon{width:35px;height:35px;border-radius:11px}
.vt10-metric{background:#fff!important;border:1px solid #DFE7F1!important;border-top:1px solid #DFE7F1!important;
  border-radius:18px!important;min-height:152px!important;height:152px!important;padding:16px 17px!important;
  box-shadow:0 4px 15px rgba(25,52,85,.035)!important;display:flex;flex-direction:column;justify-content:flex-start}
.vt10-metrichead{display:flex;gap:9px;align-items:center;min-height:33px}
.vt10-metrichead .vt-icon{width:33px;height:33px;border-radius:10px}
.vt10-mname{font-size:.79rem!important;color:#3D5776!important;font-weight:780!important;line-height:1.3}
.vt10-mvalue{font-size:clamp(1.13rem,1.65vw,1.67rem)!important;line-height:1.18!important;margin:12px 0 7px!important;
 color:#142F53!important;word-break:normal!important;overflow-wrap:anywhere!important}
.vt10-mnote{font-size:.72rem!important;color:#7A8DA5!important;line-height:1.4!important}
.vt10-insight{background:#fff!important;border:1px solid #DFE7F1!important;border-radius:16px!important;
 box-shadow:0 3px 11px rgba(25,52,85,.028)!important;min-height:115px!important;padding:15px 16px!important}
.vt10-insight .vt-icon{width:30px;height:30px}
.vt10-ilabel{font-size:.76rem!important;color:#3D5776!important}
.vt10-ivalue{color:#142F53!important;font-size:1.12rem!important}
.st-key-vt_filtros{background:#fff!important;border:1px solid #DCE6F1!important;border-radius:19px!important;
 padding:16px 20px 8px!important;box-shadow:0 4px 16px rgba(25,52,85,.04)!important;margin-bottom:17px!important}
.st-key-vt_filtros [data-testid="stSelectbox"] [data-baseweb="select"] > div{
 background:#fff!important;border:1px solid #DCE6F1!important;border-radius:11px!important;min-height:45px!important}
.st-key-vt_filtros [data-testid="stWidgetLabel"] p{font-weight:760!important;color:#294665!important}
[data-testid="stPlotlyChart"]{background:#fff!important;border:1px solid #E3EAF3!important;border-radius:16px!important;
 padding:9px 9px 3px!important;box-shadow:0 3px 12px rgba(25,52,85,.023)!important}
[data-testid="stDataFrame"]{border:1px solid #E0E8F2!important;border-radius:14px!important;overflow:hidden}
@media(max-width:900px){.vt10-metric{height:auto!important;min-height:152px!important}.vt10-title{font-size:1.8rem!important}}
</style>'''
st.markdown(CSS, unsafe_allow_html=True)


def tarjeta(titulo, valor, detalle, color):
    return (f'<div class="vt10-metric" style="--co:{color}">'
            f'<div class="vt10-metrichead"><span class="vt-icon">{vt_icon(vt_icon_para(titulo),18)}</span>'
            f'<div class="vt10-mname">{html(titulo)}</div></div>'
            f'<div class="vt10-mvalue">{html(valor)}</div>'
            f'<div class="vt10-mnote">{html(detalle)}</div></div>')


def detalle_rapido(titulo, valor, detalle, color):
    return (f'<div class="vt10-insight" style="--co:{color}">'
            f'<div class="vt10-metrichead"><span class="vt-icon">{vt_icon(vt_icon_para(titulo),17)}</span>'
            f'<div class="vt10-ilabel">{html(titulo)}</div></div>'
            f'<div class="vt10-ivalue">{html(valor)}</div>'
            f'<div class="vt10-ihelp">{html(detalle)}</div></div>')


def estilo_figura(fig, altura=345, margen_izq=10):
    fig.update_layout(
        height=altura, margin=dict(l=margen_izq, r=12, t=16, b=18),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#57718A', size=12), showlegend=False,
        xaxis=dict(showline=False, zeroline=False, showgrid=False),
        yaxis=dict(showline=False, zeroline=False,
                   gridcolor='#E6EDF3', griddash='dot'),
    )
    return fig


# 1) Preparar los datos mensuales de SQL; solo del año 2026.
fuente_meses = cargar('months')
if fuente_meses.empty:
    st.title('Ventas')
    st.info('Aún no existen indicadores de facturación mensual cargados en SQL Server.')
    st.stop()

m0 = fuente_meses.copy()
m0['Fecha'] = pd.to_datetime(m0['Fecha'], errors='coerce')
m0['ResultadoNumerico'] = pd.to_numeric(m0['ResultadoNumerico'], errors='coerce')
m0['CodigoKPI'] = m0['CodigoKPI'].fillna('').astype(str)
m0 = m0[m0['Fecha'].dt.year.eq(2026)].dropna(subset=['Fecha'])
if m0.empty:
    st.title('Ventas')
    st.info('El reporte comercial no contiene datos para 2026.')
    st.stop()

m0['Periodo'] = m0['Fecha'].dt.to_period('M')
# El hecho ya contiene un dato mensual por código. Una duplicación accidental
# no debe duplicar la facturación al sumar los importes.
duplicados = m0.duplicated(['Periodo', 'CodigoKPI'], keep=False)
if duplicados.any():
    st.warning('Hay indicadores mensuales duplicados en SQL; se muestra un registro '
               'por KPI y mes. Revisa la carga antes de utilizar los totales.')
m0 = m0.sort_values('Fecha').drop_duplicates(['Periodo', 'CodigoKPI'], keep='last')
mensual = m0.pivot(index='Periodo', columns='CodigoKPI', values='ResultadoNumerico').sort_index()
requeridos = ['COM_VENTAS_NETAS_MES', 'COM_FACTURAS_MES',
             'COM_CLIENTES_MES', 'COM_TICKET_MES']
faltan = [cod for cod in requeridos if cod not in mensual.columns]
if faltan:
    st.error('Faltan indicadores comerciales en SQL: ' + ', '.join(faltan))
    st.stop()
mensual[requeridos] = mensual[requeridos].apply(pd.to_numeric, errors='coerce')
mensual = mensual[mensual['COM_VENTAS_NETAS_MES'].notna()]
if mensual.empty:
    st.info('No existen meses de 2026 con venta neta registrada.')
    st.stop()

periodos = mensual.index.tolist()

# KPI comerciales V14: lecturas de la FACT, NO nuevos cálculos manuales.
fuente_v14 = cargar('sales_v14_months')
if fuente_v14.empty:
    st.error('Faltan las mediciones V14 en SQL. Comprueba que el paso 06 V14 se ejecutó correctamente.')
    st.stop()
v14 = fuente_v14.copy()
v14['Fecha'] = pd.to_datetime(v14['Fecha'], errors='coerce')
v14['ResultadoNumerico'] = pd.to_numeric(v14['ResultadoNumerico'], errors='coerce')
v14 = v14[v14['Fecha'].dt.year.eq(2026)].dropna(subset=['Fecha']).copy()
v14['Periodo'] = v14['Fecha'].dt.to_period('M')
if v14.duplicated(['Periodo', 'CodigoKPI']).any():
    st.error('Hay KPI V14 mensuales duplicados en FACT_KPI_ESTRATEGICO. No se muestran resultados ambiguos.')
    st.stop()
v14 = v14.pivot(index='Periodo', columns='CodigoKPI', values='ResultadoNumerico').sort_index()
kpi_v14_requeridos = ['COM_VENTAS_ACUM_ANIO', 'COM_VARIACION_MENSUAL_PCT',
                      'COM_PRIMERA_COMPRA_OBSERVADA_MES']
if any(col not in v14.columns for col in kpi_v14_requeridos):
    st.error('No se encontraron los tres KPI globales nuevos de V14 en SQL.')
    st.stop()
if not mensual.index.isin(v14.index).all():
    st.error('No coinciden los meses de KPI comerciales V14 y las ventas mensuales. Revisa el paso 06.')
    st.stop()
# Confirmar que el acumulado anual coincide con las ventas del mismo año desde FACT.
for periodo in mensual.index:
    acumulado = v14.loc[periodo, 'COM_VENTAS_ACUM_ANIO']
    calculo_control = mensual.loc[(mensual.index.year == periodo.year)
                                 & (mensual.index <= periodo), 'COM_VENTAS_NETAS_MES'].sum()
    if pd.notna(acumulado) and abs(float(acumulado) - float(calculo_control)) > 1:
        st.error('Diferencia entre las ventas mensuales y su KPI acumulado de V14. Revisa SQL.')
        st.stop()

# 2) Preparar facturación por cliente; no sumar clientes mensuales para obtener
# clientes únicos del período (una empresa puede comprar muchos meses).
fuente_clientes = cargar('clients')
cl_base = fuente_clientes.copy()
if not cl_base.empty:
    cl_base['Fecha'] = pd.to_datetime(cl_base['Fecha'], errors='coerce')
    cl_base['VentaNeta_CLP'] = pd.to_numeric(cl_base['VentaNeta_CLP'], errors='coerce')
    cl_base = cl_base[cl_base['Fecha'].dt.year.eq(2026)].dropna(
        subset=['Fecha', 'VentaNeta_CLP']).copy()
    cl_base['Periodo'] = cl_base['Fecha'].dt.to_period('M')
    cl_base['RazonSocial'] = cl_base['RazonSocial'].fillna('').astype(str).str.strip()
    rut = cl_base['RUT_Normalizado'].fillna('').astype(str).str.strip()
    rut = rut.replace({'nan': '', 'None': '', '<NA>': ''})
    cl_base['ClienteID'] = rut.where(rut.ne(''),
                                     cl_base['RazonSocial'].str.casefold())
    cl_base = cl_base[cl_base['ClienteID'].str.strip().ne('')].copy()

# Participación por cliente y mes leída de FACT_KPI_ESTRATEGICO.
participaciones = cargar('sales_client_shares').copy()
if not participaciones.empty:
    participaciones['Fecha'] = pd.to_datetime(participaciones['Fecha'], errors='coerce')
    participaciones['Periodo'] = participaciones['Fecha'].dt.to_period('M')
    participaciones['ParticipacionPct'] = pd.to_numeric(
        participaciones['ParticipacionPct'], errors='coerce')
    participaciones = participaciones[participaciones['Fecha'].dt.year.eq(2026)].copy()
    if participaciones.duplicated(['Periodo', 'RUT_Normalizado']).any():
        st.error('Participaciones SQL duplicadas por RUT y mes. Revisar FACT.')
        st.stop()
    for mes, items in participaciones.groupby('Periodo'):
        if mes in mensual.index and mensual.loc[mes, 'COM_VENTAS_NETAS_MES'] != 0:
            if abs(float(items['ParticipacionPct'].sum()) - 100) > 0.01:
                st.error(f'Las participaciones por cliente no suman 100% para {mes}.')
                st.stop()

# 3) Filtros generales: exclusivamente meses disponibles (no inventar meses).
try:
    hoy = datetime.now(ZoneInfo('America/Santiago')).strftime('%d/%m/%Y · %H:%M')
except Exception:
    hoy = 'Fecha/hora local no disponible'
st.markdown(
    '<div class="vt10-head"><div><div class="vt10-icon-title"><span class="vt-icon">'
    + vt_icon('store', 23) + '</span><div class="vt10-title">Ventas</div></div>'
    '<div class="vt10-sub">Facturación neta, evolución mensual y análisis de clientes</div>'
    f'</div><div class="vt10-date">📅 {html(hoy)} · Chile</div></div>',
    unsafe_allow_html=True,
)

with st.container(key='vt_filtros'):
    st.markdown(vt_seccion('Filtrar ventas'), unsafe_allow_html=True)
    filtro_a, filtro_b, filtro_resumen = st.columns([1, 1, 2], gap='medium')
    etiquetas = [nombre_mes(p) for p in periodos]
    with filtro_a:
        desde = st.selectbox('Desde', etiquetas, index=0, key='v10_sales_desde')
    with filtro_b:
        hasta = st.selectbox('Hasta', etiquetas, index=len(etiquetas) - 1,
                             key='v10_sales_hasta')
    with filtro_resumen:
        st.caption('Los filtros modifican las ventas, los gráficos y el análisis de clientes. '
                   'Importes en pesos chilenos (CLP), sin IVA.')

p_desde, p_hasta = periodos[etiquetas.index(desde)], periodos[etiquetas.index(hasta)]
if p_desde > p_hasta:
    st.warning('El mes «Desde» debe ser anterior o igual al mes «Hasta».')
    st.stop()

m = mensual.loc[(mensual.index >= p_desde) & (mensual.index <= p_hasta)].copy()
cl = cl_base[cl_base['Periodo'].between(p_desde, p_hasta)].copy() if not cl_base.empty else pd.DataFrame()
venta = float(m['COM_VENTAS_NETAS_MES'].sum())
facturas = int(round(float(m['COM_FACTURAS_MES'].fillna(0).sum())))
ticket = venta / facturas if facturas > 0 else float('nan')

if not cl.empty:
    # Nombre vigente por identificador, suma de meses sin duplicar clientes.
    cl = cl.sort_values(['Fecha', 'RazonSocial'])
    cartera = cl.groupby('ClienteID', as_index=False).agg(
        Cliente=('RazonSocial', 'last'), Facturacion=('VentaNeta_CLP', 'sum'),
    )
    cartera['Cliente'] = cartera['Cliente'].where(cartera['Cliente'].str.strip().ne(''),
                                                cartera['ClienteID'])
    cartera = cartera.sort_values('Facturacion', ascending=False).reset_index(drop=True)
    clientes_unicos = len(cartera)
else:
    cartera = pd.DataFrame(columns=['ClienteID', 'Cliente', 'Facturacion'])
    clientes_unicos = None

# 4) Indicadores de ventas. Se conserva una única sección con dos filas.
st.markdown(vt_seccion('Indicadores de ventas'), unsafe_allow_html=True)
cards = [
    ('Facturación neta', clp(venta), 'Total del período seleccionado · CLP', AZUL),
    ('Facturas emitidas', formato_num(facturas), 'Documentos incluidos en el reporte', TURQUESA),
    ('Clientes únicos', formato_num(clientes_unicos) if clientes_unicos is not None else '—',
     'Empresas distintas en los meses seleccionados', VERDE),
    ('Ticket promedio', clp(ticket), 'Facturación neta / número de facturas', AMARILLO),
]
for col, (nombre, valor, comentario, color) in zip(st.columns(4, gap='medium'), cards):
    with col:
        st.markdown(tarjeta(nombre, valor, comentario, color), unsafe_allow_html=True)

# Segunda fila: variación, mejor mes, promedio y clientes con primera compra
# observada. La medida de nuevos clientes se lee del SQL que alimenta el ETL:
# no representa necesariamente altas históricas si el Excel no contiene todo el historial.
ultimo_periodo = m.index[-1]
variacion_sql = numero(v14.loc[ultimo_periodo, 'COM_VARIACION_MENSUAL_PCT'])
compras_nuevas = numero(v14.loc[m.index, 'COM_PRIMERA_COMPRA_OBSERVADA_MES'].sum(min_count=1))
mejor_periodo = m['COM_VENTAS_NETAS_MES'].idxmax()
mejor_importe = m.loc[mejor_periodo, 'COM_VENTAS_NETAS_MES']
color_variacion = VERDE if math.isfinite(variacion_sql) and variacion_sql >= 0 else (ROJO if math.isfinite(variacion_sql) else GRIS)
secundarios = [
    ('Variación del último mes',
     (('+' if variacion_sql > 0 else '') + porcentaje(variacion_sql)) if math.isfinite(variacion_sql) else '—',
     'Respecto al mes calendario anterior · cálculo SQL', color_variacion),
    ('Mejor mes del período', nombre_mes(mejor_periodo), clp(mejor_importe), TURQUESA),
    ('Promedio de venta mensual', clp(venta / len(m)),
     f'{len(m)} mes(es) con datos', AZUL_CLARO),
    ('Clientes nuevos en el reporte', formato_num(compras_nuevas),
     'Primera compra observada por RUT · meses seleccionados', VERDE),
]
for col, (nombre, valor, comentario, color) in zip(st.columns(4, gap='medium'), secundarios):
    with col:
        st.markdown(tarjeta(nombre, valor, comentario, color), unsafe_allow_html=True)

# 6) Dos gráficos de negocio; no se usan metas mensuales no documentadas.
izq, der = st.columns([1.2, 1], gap='large')
with izq:
    st.markdown(vt_seccion('Evolución mensual'), unsafe_allow_html=True)
    st.caption('Venta neta por mes · millones de pesos (MM CLP)')
    meses_nombres = [nombre_mes(p) for p in m.index]
    ventas_millones = m['COM_VENTAS_NETAS_MES'].fillna(0).astype(float) / 1_000_000
    colores = [AZUL] * len(m)
    colores[-1] = '#3973CF'
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=meses_nombres, y=ventas_millones,
        marker=dict(color=colores, cornerradius=6),
        text=[formato_num(v, 1) for v in ventas_millones],
        textposition='outside', textfont=dict(size=10, color=AZUL),
        customdata=[clp(x) for x in m['COM_VENTAS_NETAS_MES']],
        hovertemplate='<b>%{x}</b><br>Venta neta: %{customdata}<extra></extra>',
    ))
    estilo_figura(fig, altura=370)
    fig.update_yaxes(title_text='MM CLP', rangemode='tozero')
    # Mostrar solo el mes en el eje; el año permanece en el tooltip.
    fig.update_xaxes(
        tickmode='array',
        tickvals=meses_nombres,
        ticktext=[MESES[p.month - 1] for p in m.index],
        tickangle=0,
    )
    fig.update_layout(bargap=.35)
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    st.caption('La última barra se destaca en turquesa. No representa cumplimiento de meta.')

with der:
    st.markdown(vt_seccion('Clientes con mayor compra'), unsafe_allow_html=True)
    st.caption('Participación sobre el total facturado en los meses seleccionados')
    if cartera.empty:
        st.info('Todavía no hay movimientos de facturación por cliente en este período.')
    else:
        top = cartera.head(8).iloc[::-1].copy()
        top['NombreCorto'] = top['Cliente'].map(
            lambda v: v if len(str(v)) <= 25 else str(v)[:23] + '…')
        fig2 = go.Figure(go.Bar(
            x=top['Facturacion'] / 1_000_000, y=top['NombreCorto'],
            orientation='h', marker=dict(color=AZUL_CLARO, cornerradius=5),
            text=[porcentaje(v / venta * 100) if venta > 0 else '—'
                  for v in top['Facturacion']],
            textposition='outside', textfont=dict(color=AZUL, size=11),
            customdata=list(zip(top['Cliente'], [clp(v) for v in top['Facturacion']])),
            hovertemplate='<b>%{customdata[0]}</b><br>Facturación: %{customdata[1]}<extra></extra>',
        ))
        estilo_figura(fig2, altura=370, margen_izq=10)
        fig2.update_xaxes(title_text='MM CLP')
        fig2.update_yaxes(showgrid=False)
        fig2.update_layout(bargap=.32, margin=dict(l=10, r=34, t=16, b=18))
        st.plotly_chart(fig2, use_container_width=True, config={'displayModeBar': False})

# Apariencia de las tarjetas y tabla mensual; sin cambios en los cálculos.
st.markdown('''<style>
.vt-mensual-scroll{max-height:520px;overflow:auto;border:1px solid #DEE7F1;
  border-radius:18px;background:#fff;box-shadow:0 4px 15px rgba(25,52,85,.035)}
.vt-mensual-table{border-collapse:separate;border-spacing:0;width:100%;
  min-width:1120px;font-size:.82rem;font-variant-numeric:tabular-nums}
.vt-mensual-table th{position:sticky;top:0;z-index:2;background:#F3F7FC;
  color:#385371;font-weight:800;text-align:left;white-space:nowrap;
  padding:15px 14px;border-bottom:1px solid #DBE5EF}
.vt-mensual-table td{padding:14px;border-bottom:1px solid #EDF1F7;
  color:#314C6B;white-space:nowrap;background:#fff}
.vt-mensual-table tbody tr:nth-child(even) td{background:#FBFCFF}
.vt-mensual-table tbody tr:hover td{background:#F1F6FE}
.vt-mensual-table .vt-mes{font-weight:800;color:#173352}
.vt-mensual-table .vt-num{text-align:right}
.vt-mensual-table .vt-positive{color:#269066;font-weight:800}
.vt-mensual-table .vt-negative{color:#C45A62;font-weight:800}
.vt-mensual-table .vt-neutral{color:#8293A5}
.vt-mensual-table thead th:not(:first-child){text-align:right}
.vt-mensual-table tr:last-child td{border-bottom:0}
</style>''', unsafe_allow_html=True)

# 7) Análisis individual de clientes con histórico mensual real.
st.markdown(vt_seccion('Explorar clientes'), unsafe_allow_html=True)
if cartera.empty:
    st.info('Carga los indicadores comerciales por cliente para consultar su historial.')
else:
    # Texto del selector en pantalla; mantener ID como valor para RUT/razones homónimas.
    opciones = [('Selecciona un cliente para ver su evolución', '')]
    for _, fila in cartera.iterrows():
        opciones.append((f'{fila["Cliente"]} · {clp(fila["Facturacion"])}', fila['ClienteID']))
    elecciones = dict(opciones)
    elegido = st.selectbox('Cliente', list(elecciones), key='v10_sales_cliente')
    cid = elecciones[elegido]
    if cid:
        parte = cl[cl['ClienteID'].eq(cid)].copy()
        serie = parte.groupby('Periodo', as_index=False)['VentaNeta_CLP'].sum().sort_values('Periodo')
        total_cliente = float(serie['VentaNeta_CLP'].sum())
        nombre_cliente = parte['RazonSocial'].iloc[-1] or cid
        # Tarjetas coherentes con las tarjetas superiores de Ventas.
        tarjetas_cliente = [
            ('Facturación del cliente', clp(total_cliente),
             'Total facturado en el período seleccionado', AZUL),
            ('Participación sobre el total',
             porcentaje(total_cliente / venta * 100) if venta > 0 else '—',
             'Porcentaje de la facturación del período', TURQUESA),
            ('Meses con compra', formato_num(len(serie)),
             'Meses con facturación registrada', VERDE),
        ]
        for col, datos in zip(st.columns(3, gap='medium'), tarjetas_cliente):
            with col:
                st.markdown(tarjeta(*datos), unsafe_allow_html=True)
        st.caption('Detalle mensual de ' + nombre_cliente + ' · solo facturación neta')
        fcli = go.Figure(go.Scatter(
            x=[nombre_mes(p) for p in serie['Periodo']],
            y=serie['VentaNeta_CLP'] / 1_000_000,
            mode='lines+markers', line=dict(color=TURQUESA, width=3),
            marker=dict(size=9, color=AZUL),
            fill='tozeroy', fillcolor='rgba(57,166,160,.09)',
            customdata=[clp(v) for v in serie['VentaNeta_CLP']],
            hovertemplate='%{x}<br>Venta neta: %{customdata}<extra></extra>',
        ))
        estilo_figura(fcli, altura=240)
        fcli.update_yaxes(title_text='MM CLP', rangemode='tozero')
        st.plotly_chart(fcli, use_container_width=True, config={'displayModeBar': False})

# 8) Detalle mensual y listado de clientes exportables.
st.markdown(vt_seccion('Detalle de facturación mensual'), unsafe_allow_html=True)
filas = []
for periodo, fila in m.iterrows():
    cambio_mes = numero(v14.loc[periodo, 'COM_VARIACION_MENSUAL_PCT'])
    filas.append({
        'Mes': nombre_mes(periodo),
        'Venta neta': clp(fila['COM_VENTAS_NETAS_MES']),
        'Facturas': formato_num(fila['COM_FACTURAS_MES']),
        'Clientes del mes': formato_num(fila['COM_CLIENTES_MES']),
        'Ticket promedio': clp(fila['COM_TICKET_MES']),
        'Variación mensual': (('+' if cambio_mes > 0 else '') + porcentaje(cambio_mes))
        if math.isfinite(cambio_mes) else '—',
        'Venta acumulada 2026': clp(v14.loc[periodo, 'COM_VENTAS_ACUM_ANIO']),
    })
tabla_mes = pd.DataFrame(filas)
# Tabla HTML estilizada, con encabezado fijo, cifras alineadas y variación coloreada.
# La tabla y su exportación CSV muestran las mismas siete columnas visibles.
encabezados = list(tabla_mes.columns)
filas_html = []
for _, registro in tabla_mes.iterrows():
    celdas = []
    for indice, columna in enumerate(encabezados):
        valor = str(registro[columna])
        clase = 'vt-mes' if indice == 0 else 'vt-num'
        if columna == 'Variación mensual':
            clase += (' vt-positive' if valor.startswith('+') else
                      ' vt-negative' if valor.startswith('-') else ' vt-neutral')
        celdas.append(f'<td class="{clase}">{html(valor)}</td>')
    filas_html.append('<tr>' + ''.join(celdas) + '</tr>')
encabezado_html = ''.join(f'<th>{html(nombre)}</th>' for nombre in encabezados)
st.markdown(
    '<div class="vt-mensual-scroll"><table class="vt-mensual-table">'
    '<thead><tr>' + encabezado_html + '</tr></thead><tbody>'
    + ''.join(filas_html) + '</tbody></table></div>',
    unsafe_allow_html=True,
)

filcol1, filcol2 = st.columns([1, 1], gap='medium')
with filcol1:
    st.download_button('⬇️ Exportar ventas mensuales (CSV)',
                       data=tabla_mes.to_csv(index=False, sep=';').encode('utf-8-sig'),
                       file_name='MAAS_Ventas_2026_Mensual.csv',
                       mime='text/csv', key='v10_sales_export_mes', use_container_width=True)
with filcol2:
    if not cartera.empty:
        tabla_cliente = cartera[['Cliente', 'Facturacion']].copy()
        tabla_cliente['Participación'] = (tabla_cliente['Facturacion'] / venta * 100) if venta > 0 else 0
        tabla_cliente['Facturacion'] = tabla_cliente['Facturacion'].map(clp)
        tabla_cliente['Participación'] = tabla_cliente['Participación'].map(porcentaje)
        tabla_cliente.columns = ['Cliente', 'Facturación neta', 'Participación (%)']
        st.download_button('⬇️ Exportar clientes (CSV)',
                           data=tabla_cliente.to_csv(index=False, sep=';').encode('utf-8-sig'),
                           file_name='MAAS_Ventas_2026_Clientes.csv', mime='text/csv',
                           key='v10_sales_export_client', use_container_width=True)

if not cartera.empty:
    difer = abs(float(cartera['Facturacion'].sum()) - venta)
    if difer > max(1, abs(venta) * .01):
        st.warning('La suma de facturación agrupada por cliente no coincide con el total '
                   'de los KPI mensuales. Revisa la integridad de los registros y la carga del ETL.')
