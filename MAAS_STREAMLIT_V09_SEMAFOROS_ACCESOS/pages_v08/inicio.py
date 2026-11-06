# -*- coding: utf-8 -*-
"""MAAS ECOLOGIA 4 - INICIO | Diseno de referencia.

Reemplazar exclusivamente: MAAS_STREAMLIT_V09_SEMAFOROS_ACCESOS/pages_v08/inicio.py
Consulta SQL Server MAAS_ECOLOGIA_4 en SOLO LECTURA.
No escribe en las FACT, DIM, vistas, ETL ni en el resto de Streamlit.
Los datos visibles se obtienen de SQL: no se codifican cifras del diseno de muestra.
"""
from __future__ import annotations

import calendar
import math
import unicodedata
from datetime import datetime, date
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from maas_datos import _conexion
from maas_ui import AREA_HOJAS, metricas, presentacion_valor

AZUL = '#142A4D'
VERDE = '#37A164'
AMARILLO = '#F2B735'
ROJO = '#D95054'
GRIS = '#AAB5C5'
COLORES = {'Cumple': VERDE, 'En riesgo': AMARILLO,
           'No cumple': ROJO, 'Sin datos': GRIS}
MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
         'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def limpio(valor):
    if valor is None:
        return '—'
    try:
        if pd.isna(valor):
            return '—'
    except (TypeError, ValueError):
        pass
    return escape(str(valor), quote=True)


def num(valor):
    try:
        v = float(valor)
        return v if math.isfinite(v) else float('nan')
    except (ValueError, TypeError, OverflowError):
        return float('nan')


def porcentaje(valor, decimales=0):
    v = num(valor)
    return (f'{100*v:.{decimales}f}'.replace('.', ',') + '%') if math.isfinite(v) else '—'


def clp(valor):
    v = num(valor)
    return ('$ ' + f'{round(v):,}'.replace(',', '.')) if math.isfinite(v) else '—'


def miles_clp(valor):
    v = num(valor)
    return clp(v / 1000) if math.isfinite(v) else '—'


def estado(valor):
    v = num(valor)
    if not math.isfinite(v):
        return 'Sin datos'
    if v >= 1.0:
        return 'Cumple'
    return 'En riesgo' if v >= .70 else 'No cumple'


def ancho(valor):
    v = num(valor)
    return max(0., min(100., 100 * v)) if math.isfinite(v) else 0.


def normalizar(valor):
    s = unicodedata.normalize('NFKD', str(valor or ''))
    return ''.join(ch for ch in s if not unicodedata.combining(ch)).casefold().strip()


def valor_bsc(fila, meta=False):
    c = 'Meta' if meta else 'Resultado'
    return presentacion_valor(fila['MetaNumerica' if meta else 'ResultadoNumerico'],
                               fila['MetaTexto' if meta else 'ResultadoTexto'],
                               fila.get('UnidadMedida'))


def fecha_breve(f):
    f = pd.to_datetime(f, errors='coerce')
    if pd.isna(f):
        return 'Sin fecha'
    return f'{int(f.day):02d} {MESES[int(f.month)-1]} {int(f.year)}'


# Lecturas propias para evitar que varias cargas del mismo dia dupliquen KPI.
# No se cambian consultas de otras paginas ni se actualiza SQL.
@st.cache_data(ttl=90, show_spinner=False)
def leer_bsc_inicio():
    sql = """
    WITH UltimaMedicion AS (
      SELECT fe.Fecha, k.CodigoKPI, k.NombreKPI, k.CategoriaKPI,
             k.TipoIndicador, k.EstadoRevision, k.UnidadMedida,
             f.Ambito, a.NombreArea, r.NombreResponsable,
             f.MetaNumerica, f.MetaTexto, f.ResultadoNumerico,
             f.ResultadoTexto, f.Avance, f.Cumplimiento, f.Ponderacion,
             f.EsSimulado, f.CargaID,
             ROW_NUMBER() OVER (
               PARTITION BY f.Fecha_Key, f.KPI_Key, f.Ambito,
                            f.Area_Key, f.GranoTemporal
               ORDER BY f.CargaID DESC, f.Medicion_Key DESC
             ) AS rn
      FROM dbo.FACT_KPI_ESTRATEGICO AS f
      JOIN dbo.DIM_KPI AS k ON k.KPI_Key=f.KPI_Key
      JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key=f.Fecha_Key
      LEFT JOIN dbo.DIM_AREA AS a ON a.Area_Key=f.Area_Key
      LEFT JOIN dbo.DIM_RESPONSABLE AS r
          ON r.Responsable_Key=f.Responsable_Key
      WHERE k.TipoIndicador='OFICIAL_BSC'
        AND f.FuenteResultado='BSC'
    )
    SELECT * FROM UltimaMedicion WHERE rn=1
    ORDER BY Fecha DESC, CodigoKPI, Ambito
    """
    con = _conexion()
    try:
        cur = con.cursor()
        cur.execute(sql)
        campos = [d[0] for d in cur.description]
        datos = pd.DataFrame.from_records(cur.fetchall(), columns=campos)
        if 'rn' in datos:
            datos = datos.drop(columns='rn')
        return datos
    finally:
        con.close()


@st.cache_data(ttl=90, show_spinner=False)
def leer_ventas_inicio():
    sql = """
    WITH Ultimas AS (
       SELECT fe.Fecha, k.CodigoKPI, f.ResultadoNumerico,
              ROW_NUMBER() OVER (
                PARTITION BY fe.Anio, fe.Mes, k.CodigoKPI
                ORDER BY f.CargaID DESC, f.Medicion_Key DESC
              ) AS rn
       FROM dbo.FACT_KPI_ESTRATEGICO AS f
       JOIN dbo.DIM_KPI AS k ON k.KPI_Key=f.KPI_Key
       JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key=f.Fecha_Key
       WHERE f.FuenteResultado='VENTAS'
         AND f.Ambito='GLOBAL' AND f.GranoTemporal='MES'
         AND k.CodigoKPI='COM_VENTAS_NETAS_MES'
    )
    SELECT Fecha, CodigoKPI, ResultadoNumerico
    FROM Ultimas WHERE rn=1 ORDER BY Fecha
    """
    con = _conexion()
    try:
        cur = con.cursor()
        cur.execute(sql)
        return pd.DataFrame.from_records(cur.fetchall(),
                                         columns=[d[0] for d in cur.description])
    finally:
        con.close()


st.markdown(r'''
<style>
/* Estilo limitado a Inicio: no altera el menu de paginas ni la autenticacion. */
.ma4-icon-box{display:inline-flex;flex:0 0 auto;width:32px;height:32px;align-items:center;justify-content:center;border-radius:10px;background:#EDF4FD;color:#2F6AC1;margin-right:9px;vertical-align:middle}
.ma4-icon-box svg{width:19px;height:19px}
.ma4-icon-mini{display:inline-flex;align-items:center;justify-content:center;width:23px;height:23px;color:#4476BF;background:#F0F5FC;border-radius:7px;margin-right:7px;vertical-align:middle}
.ma4-icon-mini svg{width:15px;height:15px}
.ma4-panel-name{display:flex;align-items:center}
.ma4-title{display:flex;align-items:center;gap:2px}
.ma4-kpi-h{display:flex;align-items:flex-start;gap:3px}
.ma4-sales-h{display:flex;align-items:center}
.ma4-area-name{display:flex;align-items:center}
.ma4-title{font-size:1.35rem;font-weight:850;color:#142A4D;margin:15px 0 8px;letter-spacing:-.025em}
.ma4-panel{background:#fff;border:1px solid #E1E8F1;border-radius:17px;padding:18px 21px;
 box-shadow:0 2px 10px rgba(15,39,72,.045);margin:4px 0 14px}
.ma4-panel-name{font-size:1.02rem;font-weight:800;color:#142A4D;margin:0 0 9px}
.ma4-filter-title{font-size:.81rem;color:#1E3453;font-weight:700;margin:0 0 3px}
.ma4-ring-big{width:160px;height:160px;display:grid;place-items:center;border-radius:50%;
 background:conic-gradient(#37A164 0 var(--a),#F2B735 var(--a) var(--b),
 #D95054 var(--b) var(--c),#E7ECF4 var(--c) 100%);margin:auto}
.ma4-ring-hole{background:#fff;width:112px;height:112px;border-radius:50%;
 display:flex;align-items:center;justify-content:center;font-weight:900;
 font-size:1.9rem;color:#142A4D}
.ma4-summary{display:grid;grid-template-columns:minmax(135px,185px) 1fr;gap:15px;align-items:center;
 min-height:184px}
.ma4-status-row{display:grid;grid-template-columns:1fr 35px;gap:14px;
 color:#435675;font-size:.86rem;margin:8px 0}
.ma4-status-count{font-weight:800;text-align:right;color:#152D4D}
.ma4-ball{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:8px}
.ma4-pill{display:inline-block;padding:5px 11px;border-radius:18px;font-size:.75rem;
 font-weight:780;background:var(--fondo);color:var(--tinta)}
.ma4-area{display:grid;grid-template-columns:minmax(104px,126px) minmax(100px,1fr) 48px;
 align-items:center;gap:12px;margin:14px 0}
.ma4-area-name{color:#243855;font-size:.84rem}
.ma4-track{height:12px;background:#E9EEF5;border-radius:16px;overflow:hidden}
.ma4-track span{height:100%;width:var(--w);display:block;border-radius:16px;background:var(--c)}
.ma4-area-n{font-size:.87rem;text-align:right;font-weight:800;color:#142A4D}
.ma4-kpi{background:white;border:1px solid #E0E8F1;border-radius:16px;
 box-shadow:0 2px 10px rgba(15,39,72,.045);padding:15px 17px;min-height:170px;
 margin:3px 0 9px;display:flex;flex-direction:column;justify-content:space-between}
.ma4-kpi-h{font-size:.84rem;color:#344E71;font-weight:730;line-height:1.35;min-height:38px}
.ma4-kpi-mid{display:grid;grid-template-columns:minmax(0,1fr) 72px;gap:6px;align-items:center;margin:10px 0 6px}
.ma4-kpi-v{font-size:clamp(1.1rem,1.7vw,1.5rem);color:#142A4D;font-weight:900;
 line-height:1.2;overflow-wrap:anywhere}
.ma4-sub{font-size:.77rem;color:#8290A8;margin-top:4px;line-height:1.35}
.ma4-ring-small{width:68px;height:68px;border-radius:50%;display:grid;place-items:center;
 background:conic-gradient(var(--c) 0 var(--w),#E7ECF3 var(--w) 100%)}
.ma4-ring-small i{font-style:normal;background:white;width:51px;height:51px;border-radius:50%;
 display:grid;place-items:center;font-size:.8rem;font-weight:850;color:#142A4D}
.ma4-kpi-footer{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-height:25px}
.ma4-tag{background:#E9EFF7;color:#243C61;border-radius:20px;padding:5px 11px;
 font-size:.72rem;font-weight:780}
.ma4-salesbox{border:1px solid #E0E8F1;border-radius:13px;padding:14px 14px 12px;
 background:#fff;min-height:113px;margin-bottom:5px}
.ma4-sales-h{color:#364E71;font-size:.78rem;font-weight:780;min-height:20px}
.ma4-sales-v{font-size:1.4rem;font-weight:900;color:#142A4D;margin:7px 0 2px}
.ma4-sales-sub{color:#8291A8;font-size:.75rem;line-height:1.4}
.ma4-nodata{font-size:.88rem;color:#8291A8;padding:18px 0}
.ma4-minirow{display:flex;justify-content:space-between;align-items:center;
 gap:10px;color:#2E4562;font-size:.84rem;margin:9px 0}
.ma4-small-note{font-size:.76rem;color:#718198;margin:1px 0 7px}
/* Streamlit controls in the same subtle panel as the reference. */
.st-key-ma4_filtros{background:#fff;border:1px solid #E1E8F1;border-radius:16px;
 padding:11px 16px 7px;box-shadow:0 2px 10px rgba(15,39,72,.045);margin-bottom:16px}
.st-key-ma4_ventas{background:#fff;border:1px solid #E1E8F1;border-radius:18px;
 padding:16px 18px;box-shadow:0 2px 10px rgba(15,39,72,.045)}
.st-key-ma4_ventas [data-testid="stPlotlyChart"]{margin-top:0}
.st-key-ma4_filtros [data-testid="stWidgetLabel"] p{color:#263B58;font-size:.83rem;font-weight:740}
@media(max-width:800px){.ma4-summary{grid-template-columns:1fr}
 .ma4-area{grid-template-columns:95px minmax(70px,1fr) 40px;gap:7px}}
</style>
''', unsafe_allow_html=True)


# Iconos SVG locales, sin fuentes externas ni dependencias adicionales.
_ICONOS_INICIO = {
    'activity': '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    'layers': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'chart': '<path d="M3 3v18h18"/><path d="m7 16 5-5 4 3 5-7"/>',
    'wallet': '<rect x="3" y="6" width="18" height="15" rx="2"/><path d="M3 10h18"/><path d="M7 6V4h11"/>',
    'trend': '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    'building': '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M9 7h2m3 0h2M9 11h2m3 0h2M9 15h2m3 0h2M10 21v-4h4v4"/>',
    'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    'tool': '<path d="M14.7 6.3a5 5 0 0 0-6.4 6.4L3 18l3 3 5.3-5.3a5 5 0 0 0 6.4-6.4l-3.2 3.2-3-3z"/>',
    'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
    'coins': '<circle cx="12" cy="12" r="9"/><path d="M15 9a4 4 0 0 0-6 0c-2 3 6 3 6 6a4 4 0 0 1-6 0M12 6v12"/>',
}

def icono_inicio(nombre, compacto=False):
    dibujo = _ICONOS_INICIO.get(nombre, _ICONOS_INICIO['chart'])
    clase = 'ma4-icon-mini' if compacto else 'ma4-icon-box'
    return (f'<span class="{clase}"><svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{dibujo}</svg></span>')


def icono_area(nombre):
    return {'Administración':'wallet', 'Ingeniería':'tool',
            'Operaciones':'building', 'Contratos':'file'}.get(nombre, 'layers')


def icono_ventas(titulo):
    return {'Vendido en el año':'coins', 'Deberíamos llevar a esta fecha':'target',
            'Falta para la meta':'chart', 'Ritmo necesario por mes':'trend'}.get(titulo, 'chart')


def panel_contenido(titulo, texto):
    st.markdown(f'<div class="ma4-panel"><div class="ma4-panel-name">{icono_inicio({"Cumplimiento global":"activity","Desempeño por área":"layers"}.get(titulo,"chart"))}{limpio(titulo)}</div>'
                + texto + '</div>', unsafe_allow_html=True)


def tarjeta_kpi(fila):
    titulo = limpio(fila['NombreKPI'])
    valor = limpio(valor_bsc(fila))
    meta = limpio(valor_bsc(fila, meta=True))
    c = num(fila['Cumplimiento'])
    e = estado(c)
    color = COLORES[e]
    peso = num(fila['Ponderacion'])
    peso_str = f'{peso:g}' if math.isfinite(peso) else '—'
    pill_text = (f'<span class="ma4-pill" style="--fondo:{color}26;--tinta:{color}">'
                 f'{e}</span>')
    st.markdown(
        '<div class="ma4-kpi">'
        f'<div class="ma4-kpi-h">{icono_inicio("target", True)}{titulo}</div>'
        '<div class="ma4-kpi-mid"><div>'
        f'<div class="ma4-kpi-v">{valor}</div>'
        f'<div class="ma4-sub">Meta anual: {meta}</div></div>'
        f'<div class="ma4-ring-small" style="--c:{color};--w:{ancho(c):.2f}%">'
        f'<i>{limpio(porcentaje(c))}</i></div></div>'
        '<div class="ma4-kpi-footer">'
        f'{pill_text}<span class="ma4-tag">Peso {limpio(peso_str)}</span>'
        '</div></div>', unsafe_allow_html=True)


def resumen_ventas(titulo, cifra, detalle):
    st.markdown('<div class="ma4-salesbox">'
                f'<div class="ma4-sales-h">{icono_inicio(icono_ventas(titulo), True)}{limpio(titulo)}</div>'
                f'<div class="ma4-sales-v">{limpio(cifra)}</div>'
                f'<div class="ma4-sales-sub">{limpio(detalle)}</div></div>',
                unsafe_allow_html=True)


@st.cache_data(ttl=90, show_spinner=False)
def meta_ventas_desde_sql(anio):
    """BSC hoja METAS_VENTAS -> paso 09 -> SQL; sin metas inventadas."""
    con = _conexion()
    try:
        cur = con.cursor()
        cur.execute("SELECT OBJECT_ID('dbo.CFG_META_VENTAS_ANUAL','U')")
        if cur.fetchone()[0] is None:
            return None
        cur.execute("SELECT MetaAnualCLP FROM dbo.CFG_META_VENTAS_ANUAL WHERE Anio=?", int(anio))
        res = cur.fetchone()
        if res is None:
            return None
        valor = num(res[0])
        return valor if math.isfinite(valor) and valor > 0 else None
    finally:
        con.close()


def meta_ventas_clp(globales, anio):
    return meta_ventas_desde_sql(anio)


def grafico_ventas(mensuales, meta_clp, anio):
    fig = go.Figure()
    mes_nums = list(range(1, 13))
    fig.add_trace(go.Scatter(x=mes_nums, y=[0]*12, mode='lines',
                             line=dict(color='rgba(0,0,0,0)'), showlegend=False,
                             hoverinfo='skip'))
    if meta_clp is not None:
        ref = [meta_clp / 1000 * m / 12 for m in mes_nums]
        fig.add_trace(go.Scatter(
            x=mes_nums, y=ref, mode='lines', name='Meta distribuida por mes',
            line=dict(color='#91A6C0', width=2, dash='dot'),
            hovertemplate='%{x}: $ %{y:,.0f} miles<extra>Referencia</extra>'))
        fig.add_hline(y=meta_clp/1000, line=dict(color=VERDE, dash='dash', width=2),
                      annotation_text='Meta anual', annotation_position='top left')
    if not mensuales.empty:
        t = mensuales.copy().sort_values('Mes')
        t['Acumulado'] = t['Venta_CLP'].cumsum() / 1000
        fig.add_trace(go.Scatter(
            x=t['Mes'].tolist(), y=t['Acumulado'].tolist(), mode='lines+markers',
            name='Vendido acumulado', line=dict(color='#2F6CD4', width=4),
            marker=dict(size=7, color='#2F6CD4'),
            hovertemplate='%{x}: $ %{y:,.0f} miles<extra>Acumulado</extra>'))
    fig.update_layout(
        height=330, margin=dict(l=5, r=15, t=15, b=50),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        showlegend=True, legend=dict(orientation='h', x=.5, xanchor='center', y=-.22,
                                     font=dict(size=11, color='#586A85')),
        font=dict(color='#566C8B'),
        xaxis=dict(tickmode='array', tickvals=mes_nums, ticktext=MESES,
                   range=[.75,12.25], showgrid=False, zeroline=False),
        yaxis=dict(tickformat='.2s', ticksuffix='', gridcolor='#E6ECF4',
                   zeroline=False, rangemode='tozero'),
        hovermode='x unified')
    return fig


def grafico_mensual(mensuales):
    fig = go.Figure()
    if not mensuales.empty:
        fig.add_trace(go.Bar(x=mensuales['Mes'], y=mensuales['Venta_CLP']/1000,
                             marker_color='#3677CE', name='Venta mensual',
                             hovertemplate='%{x}: $ %{y:,.0f} miles<extra></extra>'))
    fig.update_layout(
        height=330, margin=dict(l=5, r=15, t=15, b=35),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False, font=dict(color='#566C8B'),
        xaxis=dict(tickmode='array', tickvals=list(range(1,13)),ticktext=MESES,
                   range=[.5,12.5],showgrid=False,zeroline=False),
        yaxis=dict(tickformat='.2s', gridcolor='#E6ECF4',zeroline=False,
                   rangemode='tozero'))
    return fig


def resetear_filtros():
    for clave in ('ma4_fecha', 'ma4_categoria', 'ma4_responsable',
                  'ma4_ocultar_peso_cero'):
        st.session_state.pop(clave, None)


def asegurar_opcion(clave, opciones):
    if clave in st.session_state and st.session_state[clave] not in opciones:
        st.session_state.pop(clave)


# ---------- Origen: las dos consultas solo leen SQL Server. ----------
try:
    bsc = leer_bsc_inicio()
    ventas = leer_ventas_inicio()
except Exception as exc:
    st.error('No se pudieron consultar los datos vigentes de SQL Server. '
             'No se reemplazarán por cifras de ejemplo.')
    st.exception(exc)
    st.stop()

if bsc.empty:
    st.info('No existen mediciones BSC disponibles para Inicio.')
    st.stop()

bsc = bsc.copy()
bsc['Fecha'] = pd.to_datetime(bsc['Fecha'], errors='coerce').dt.normalize()
for campo in ('Cumplimiento', 'Avance', 'Ponderacion',
              'MetaNumerica', 'ResultadoNumerico'):
    bsc[campo] = pd.to_numeric(bsc[campo], errors='coerce')
bsc['NombreResponsable'] = bsc['NombreResponsable'].fillna('Sin responsable')
bsc['CategoriaKPI'] = bsc['CategoriaKPI'].fillna('Sin categoría')

# El selector permanece visible aun si todavía no hay mediciones para el año.
# Incorpora automáticamente los años nuevos que aparezcan en SQL.
anios_bsc = set(bsc['Fecha'].dropna().dt.year.astype(int).tolist())
fechas_venta = pd.to_datetime(ventas.get('Fecha', pd.Series(dtype='datetime64[ns]')), errors='coerce')
anios_ventas = set(fechas_venta.dropna().dt.year.astype(int).tolist())
anio_actual = date.today().year
anios_disponibles = sorted(set(range(2024, max(2030, anio_actual + 2) + 1)) |
                           anios_bsc | anios_ventas, reverse=True)
if 'ma4_anio' in st.session_state and st.session_state['ma4_anio'] not in anios_disponibles:
    st.session_state.pop('ma4_anio', None)
if 'ma4_anio' not in st.session_state:
    st.session_state['ma4_anio'] = 2026 if 2026 in anios_disponibles else anios_disponibles[0]
# Encabezado principal de Inicio, coherente con las demás áreas.
st.markdown("""<style>
.ma4-pagehead{display:flex;align-items:center;gap:12px;margin:4px 0 6px}
.ma4-pagehead .ma4-icon-box{width:43px;height:43px;border-radius:12px;margin-right:0}
.ma4-pagehead .ma4-icon-box svg{width:23px;height:23px}
.ma4-pagetitle{font-size:clamp(1.85rem,2.6vw,2.2rem);font-weight:850;
 color:#142A4D;letter-spacing:-.035em;line-height:1.2}
.ma4-pagesub{color:#788BA1;font-size:.9rem;margin:0 0 19px}
</style>""", unsafe_allow_html=True)
st.markdown('<div class="ma4-pagehead">' + icono_inicio('layers') +
            '<div class="ma4-pagetitle">Panel general</div></div>'
            '<div class="ma4-pagesub">Indicadores estratégicos y resumen ejecutivo de MAAS Ecología</div>',
            unsafe_allow_html=True)

anio_elegido = st.selectbox('📅 Año', anios_disponibles, key='ma4_anio')
bsc = bsc.loc[bsc['Fecha'].dt.year.eq(anio_elegido)].copy()
if bsc.empty or not bsc['Ambito'].eq('GLOBAL').any():
    st.info(f'Todavía no hay indicadores BSC registrados para {anio_elegido}. '
            'Cuando se carguen datos de ese año, aparecerán automáticamente aquí.')
    st.stop()

fechas = sorted(bsc.loc[bsc['Ambito'].eq('GLOBAL'), 'Fecha'].dropna().unique(), reverse=True)
if not fechas:
    st.info('No hay KPI globales en la fuente BSC.')
    st.stop()
fechas_opciones = [pd.Timestamp(f).date().isoformat() for f in fechas]
asegurar_opcion('ma4_fecha', fechas_opciones)

with st.container(key='ma4_filtros'):
    filtros = st.columns([2.3,1.6,1.6,1.4,.75], gap='small', vertical_alignment='bottom')
    with filtros[0]:
        corte_str = st.selectbox(
            '📅 Periodo (fecha de corte)', fechas_opciones,
            format_func=lambda x: 'Más reciente (' + fecha_breve(x) + ')' if x == fechas_opciones[0]
                                 else fecha_breve(x),
            key='ma4_fecha')

    corte = pd.Timestamp(corte_str)
    global_corte = bsc.loc[(bsc['Ambito'] == 'GLOBAL') & (bsc['Fecha'] == corte)].copy()
    categorias = ['Todas'] + sorted(global_corte['CategoriaKPI'].dropna().unique().tolist())
    responsables = ['Todos'] + sorted(
        global_corte.loc[global_corte['NombreResponsable'] != 'Sin responsable',
                         'NombreResponsable'].dropna().unique().tolist())
    asegurar_opcion('ma4_categoria', categorias)
    asegurar_opcion('ma4_responsable', responsables)
    with filtros[1]:
        categoria = st.selectbox('Categoría', categorias, key='ma4_categoria')
    with filtros[2]:
        responsable = st.selectbox('Responsable', responsables, key='ma4_responsable')
    with filtros[3]:
        ocultar = st.toggle('Ocultar KPI con peso 0', value=False,
                           key='ma4_ocultar_peso_cero')
    with filtros[4]:
        st.button('Limpiar', use_container_width=True, on_click=resetear_filtros)

mostrar = global_corte.copy()
if categoria != 'Todas':
    mostrar = mostrar.loc[mostrar['CategoriaKPI'] == categoria]
if responsable != 'Todos':
    mostrar = mostrar.loc[mostrar['NombreResponsable'] == responsable]
if ocultar:
    mostrar = mostrar.loc[mostrar['Ponderacion'].fillna(0) > 0]

indice = metricas(mostrar) if not mostrar.empty else float('nan')
sem = mostrar['Cumplimiento'].map(estado).value_counts().reindex(
    list(COLORES), fill_value=0)

# ----------------------------- Primera fila -----------------------------
res_col, areas_col = st.columns([1.05, 1], gap='medium')
with res_col:
    total = int(sem.sum())
    acum = 0.0
    sectores = []
    for nombre in COLORES:
        acum += 100 * int(sem[nombre]) / total if total else 0
        sectores.append(acum)
    fondo = (f'--a:{sectores[0]:.2f}%;--b:{sectores[1]:.2f}%;'
             f'--c:{sectores[2]:.2f}%')
    leyenda = ''.join(
        f'<div class="ma4-status-row"><span><span class="ma4-ball" '
        f'style="background:{COLORES[et]}"></span>{limpio(et)}</span>'
        f'<span class="ma4-status-count">{int(sem[et])}</span></div>'
        for et in ('Cumple','En riesgo','No cumple'))
    score_color = COLORES[estado(indice)]
    relleno = ('#E9EEF5' if not total else '')
    html = (
        '<div class="ma4-summary">'
        f'<div class="ma4-ring-big" style="{fondo};background-color:{relleno}">'
        f'<div class="ma4-ring-hole">{limpio(porcentaje(indice))}</div></div>'
        '<div>'
        f'<span class="ma4-pill" style="--fondo:{score_color}33;--tinta:{score_color}">'
        f'{limpio(estado(indice))}</span>'
        f'<div class="ma4-small-note" style="margin-top:10px">'
        f'{total} KPI en el corte seleccionado</div>'
        + leyenda + '</div></div>')
    panel_contenido('Cumplimiento global', html)

with areas_col:
    partes = ''
    departamentos = bsc.loc[(bsc['Ambito']=='AREA') & (bsc['Fecha']<=corte)].copy()
    departamentos['normalizada'] = departamentos['NombreArea'].map(normalizar)
    if categoria != 'Todas':
        departamentos = departamentos.loc[departamentos['CategoriaKPI'] == categoria]
    if responsable != 'Todos':
        departamentos = departamentos.loc[departamentos['NombreResponsable'] == responsable]
    nombres_areas = [
        ('administracion', 'Administración'),
        ('ingenieria', 'Ingeniería'),
        ('operaciones', 'Operaciones'),
        ('contratos', 'Contratos'),
    ]
    for clave, nombre in nombres_areas:
        a = departamentos.loc[
            departamentos['normalizada'] == normalizar(AREA_HOJAS[clave])].copy()
        if a.empty:
            continue
        ultimo_corte = a['Fecha'].max()
        a = a.loc[a['Fecha'] == ultimo_corte]
        if ocultar:
            a = a.loc[a['Ponderacion'].fillna(0) > 0]
        valor = metricas(a)
        c = COLORES[estado(valor)]
        partes += (
            '<div class="ma4-area">'
            f'<span class="ma4-area-name">{icono_inicio(icono_area(nombre), True)}{limpio(nombre)}</span>'
            '<div class="ma4-track">'
            f'<span style="--w:{ancho(valor):.2f}%;--c:{c}"></span></div>'
            f'<span class="ma4-area-n">{limpio(porcentaje(valor))}</span>'
            '</div>')
    if not partes:
        partes = '<div class="ma4-nodata">Sin datos por área</div>'
    panel_contenido('Desempeño por área', partes)

# -------------------------- KPI de mayor peso ---------------------------
st.markdown(f'<div class="ma4-title">{icono_inicio("target")}KPI de mayor peso</div>', unsafe_allow_html=True)
principales = mostrar.sort_values('Ponderacion', ascending=False, na_position='last').head(4)
if principales.empty:
    st.info('No hay KPI con esos filtros.')
else:
    columnas = st.columns(4, gap='small')
    for col, (_, fila) in zip(columnas, principales.iterrows()):
        with col:
            tarjeta_kpi(fila)

# ---------------------- Ventas desde FACT comerciales -------------------
ventas_2026 = ventas.copy()
ventas_2026['Fecha'] = pd.to_datetime(ventas_2026['Fecha'], errors='coerce')
ventas_2026['ResultadoNumerico'] = pd.to_numeric(
    ventas_2026['ResultadoNumerico'], errors='coerce')
anio = int(corte.year)
ventas_2026 = ventas_2026.loc[
    (ventas_2026['Fecha'].dt.year == anio)
    & (ventas_2026['Fecha'].dt.month <= int(corte.month))
    & ventas_2026['ResultadoNumerico'].notna()
].copy()
ventas_2026['Mes'] = ventas_2026['Fecha'].dt.month
ventas_2026 = (ventas_2026.groupby('Mes', as_index=False)
               ['ResultadoNumerico'].sum()
               .rename(columns={'ResultadoNumerico': 'Venta_CLP'}))

ventas_total = float(ventas_2026['Venta_CLP'].sum())
meta_total = meta_ventas_clp(global_corte, anio)
meta_valida = meta_total is not None and math.isfinite(meta_total) and meta_total > 0

st.markdown(f'<div class="ma4-title">{icono_inicio("coins")}Ventas {anio}: ¿vamos avanzando mes a mes?</div>',
            unsafe_allow_html=True)
with st.container(key='ma4_ventas'):
    st.markdown(
        f'<div class="ma4-small-note">Cifras en miles de pesos · datos al '
        f'{limpio(fecha_breve(corte))} (corte BSC) · ventas mensuales de SQL</div>',
        unsafe_allow_html=True)

    meses_cerrados = max(0, min(12, int(corte.month)-1))
    esperado = meta_total*meses_cerrados/12 if meta_valida else float('nan')
    falta = max(0.,meta_total-ventas_total) if meta_valida else float('nan')
    diferencia = ventas_total-esperado if math.isfinite(esperado) else float('nan')
    dias_mes = calendar.monthrange(anio, int(corte.month))[1]
    meses_restantes = 12-int(corte.month) + (dias_mes-int(corte.day))/dias_mes
    ritmo = falta/meses_restantes if math.isfinite(falta) and meses_restantes>0 else float('nan')

    c1,c2,c3,c4 = st.columns(4,gap='small')
    with c1:
        texto_meta = (porcentaje(ventas_total/meta_total) + ' de la meta anual'
                      if meta_valida else 'Venta neta en facturas')
        resumen_ventas('Vendido en el año', miles_clp(ventas_total),texto_meta)
    with c2:
        dif_txt = ('Adelanto ' + miles_clp(diferencia) if diferencia >= 0
                   else 'Brecha ' + miles_clp(-diferencia)) if math.isfinite(diferencia) else 'Meta anual no registrada'
        resumen_ventas('Deberíamos llevar a esta fecha',
                       miles_clp(esperado),dif_txt)
    with c3:
        resumen_ventas('Falta para la meta', miles_clp(falta),
                       ('Meta anual: ' + miles_clp(meta_total)) if meta_valida
                       else 'Meta monetaria no disponible en BSC vigente')
    with c4:
        resumen_ventas('Ritmo necesario por mes',miles_clp(ritmo),
                       ('Meses restantes: ' + f'{meses_restantes:.1f}'.replace('.', ','))
                       if meta_valida else 'Sin meta monetaria comparable')

    ver = st.radio('Ver ventas:', ['Acumulado', 'Mensual'],
                   horizontal=True, key='ma4_tipo_ventas')
    if ver == 'Acumulado':
        fig = grafico_ventas(ventas_2026, meta_total if meta_valida else None, anio)
    else:
        fig = grafico_mensual(ventas_2026)
    st.plotly_chart(fig, use_container_width=True,
                    config={'displayModeBar': False})

# --------------------- Avance KPI y distribucion -----------------------
izq, der = st.columns([1.55, 1], gap='medium')
with izq:
    with st.container():
        st.markdown(f'<div class="ma4-title">{icono_inicio("chart")}¿Cómo vamos en los KPI más importantes?</div>',
                    unsafe_allow_html=True)
        opcion = st.radio('Comparación',
                          ['Avance frente a meta anual', 'Cumplimiento por categoría'],
                          horizontal=True, key='ma4_comparacion',
                          label_visibility='collapsed')
        if opcion == 'Avance frente a meta anual':
            ranking = mostrar.sort_values('Ponderacion',ascending=False).head(10).copy()
            ranking = ranking.dropna(subset=['Avance'])
            fig = go.Figure()
            for _, r in ranking.iloc[::-1].iterrows():
                fig.add_trace(go.Bar(
                    x=[100*num(r['Avance'])], y=[str(r['NombreKPI'])],
                    orientation='h', marker_color=COLORES[estado(r['Cumplimiento'])],
                    hovertemplate='%{y}: %{x:.1f}%<extra>Avance</extra>',
                    showlegend=False))
            if not ranking.empty:
                fig.add_vline(x=100, line_color=AZUL, line_width=2,
                              annotation_text='Meta anual')
            fig.update_layout(
                height=max(360,45*len(ranking)+80),barmode='overlay',
                margin=dict(l=10,r=22,t=22,b=30),
                xaxis=dict(title=None,gridcolor='#EEF1F5',ticksuffix='%',zeroline=False),
                yaxis=dict(title=None,automargin=True),
                plot_bgcolor='rgba(0,0,0,0)',paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#5D7089'))
            st.plotly_chart(fig, use_container_width=True,
                            config={'displayModeBar': False})
        else:
            grupos = []
            for cat, g in mostrar.groupby('CategoriaKPI'):
                v = metricas(g)
                if math.isfinite(num(v)):
                    grupos.append((cat, v))
            grupos.sort(key=lambda x:x[1])
            fig = go.Figure(go.Bar(
                x=[100*v for _,v in grupos],y=[c for c,_ in grupos],
                orientation='h',marker_color=[COLORES[estado(v)] for _,v in grupos],
                showlegend=False))
            fig.update_layout(height=max(340,len(grupos)*43+80),
                margin=dict(l=10,r=22,t=22,b=30),
                xaxis=dict(ticksuffix='%',gridcolor='#EDF1F6'),
                yaxis=dict(automargin=True),
                plot_bgcolor='rgba(0,0,0,0)',paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig,use_container_width=True,
                            config={'displayModeBar': False})

with der:
    st.markdown(f'<div class="ma4-title">{icono_inicio("layers")}Estado de KPI · {len(mostrar)} en total</div>',
                unsafe_allow_html=True)
    figuras = [(k, int(sem[k])) for k in ('Cumple','En riesgo','No cumple','Sin datos')
               if int(sem[k]) > 0]
    if figuras:
        fig = go.Figure(go.Pie(
            labels=[k for k,_ in figuras],values=[n for _,n in figuras],
            hole=.62, marker=dict(colors=[COLORES[k] for k,_ in figuras],
                                   line=dict(color='white',width=2)),
            textinfo='value',textposition='inside',
            hovertemplate='%{label}: %{value}<extra></extra>'))
        fig.update_layout(height=350,margin=dict(l=10,r=10,t=0,b=25),
                          showlegend=True,legend=dict(orientation='h',
                          x=.5,xanchor='center',y=-.10),
                          plot_bgcolor='rgba(0,0,0,0)',
                          paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig,use_container_width=True,
                        config={'displayModeBar': False})
