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


# Cabecera ejecutiva de Gerencia, sin modificar el menú lateral.
st.markdown('''<style>
.ma4-title{font-weight:850}
.ma4-ger-head{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:8px 0 16px}
.ma4-ger-name{font-size:2.0rem;font-weight:850;color:#142A4D}
.ma4-ger-sub{color:#8290A8;font-size:.90rem}
.ma4-ger-date{border:1px solid #E0E8F1;border-radius:12px;background:white;color:#526985;padding:10px 14px;font-size:.82rem}
.ma4-alert{background:#FFF1F0;border:1px solid #F2C9C8;border-radius:16px;padding:18px 20px;margin:16px 0 10px;color:#203752}
.ma4-alert-title{font-weight:800;margin-bottom:10px}
.ma4-alert-line{font-size:.84rem;padding:4px 0}

/* Iconos decorativos: solo afectan visualmente a Gerencia General. */
.ma4-ger-ico{display:inline-flex;flex-shrink:0;align-items:center;justify-content:center;
 width:31px;height:31px;border-radius:10px;background:#EDF3FC;color:#2E67C6;
 vertical-align:middle;margin-right:8px}
.ma4-ger-ico svg{display:block}
.ma4-title .ma4-ger-ico{margin-right:9px}
.ma4-panel-name .ma4-ger-ico,.ma4-alert-title .ma4-ger-ico{width:28px;height:28px}
.ma4-sales-h .ma4-ger-ico{width:25px;height:25px;margin-right:5px;border-radius:8px}
.ma4-kpi-h .ma4-ger-ico{width:25px;height:25px;margin-right:6px;border-radius:8px}
.ma4-ger-name .ma4-ger-ico{width:38px;height:38px;border-radius:12px;margin-right:10px}
</style>''',unsafe_allow_html=True)


# Iconos ornamentales SVG, sin dependencia de librerias ni efecto sobre datos.
_ICONOS_GERENCIA = {
    'building': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 21v-6h6v6M7 7h.01M12 7h.01M17 7h.01M7 11h.01M12 11h.01M17 11h.01"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'trend': '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    'chart': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    'layers': '<path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5"/>',
    'alert': '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v4M12 17h.01"/>',
    'table': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    'wallet': '<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 9h18M16 14h2"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    'coins': '<circle cx="9" cy="8" r="5"/><path d="M8 13a5 5 0 1 0 7-7M17 17h.01"/>',
    'helmet': '<path d="M3 17h18M5 17v-3a7 7 0 0 1 6-6M13 8a7 7 0 0 1 6 6v3M10 8V5h4v3M12 5v8"/>',
    'money': '<circle cx="12" cy="12" r="9"/><path d="M15 8.5c-.8-.9-2-1.5-3.4-1.5-2 0-3.1 1-3.1 2.4 0 3.4 7 .8 7 4.6 0 1.5-1.4 2.6-3.5 2.6-1.4 0-2.8-.6-3.7-1.7M12 5v14"/>',
    'people': '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 5v1"/>',
    'contract': '<path d="M7 3h7l5 5v13H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    'heart': '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
    'briefcase': '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18M10 12h4v3h-4z"/>',
    'shield': '<path d="m12 2 8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-4Z"/><path d="m9 12 2 2 4-4"/>',
    'award': '<circle cx="12" cy="8" r="5"/><path d="m8 12-2 9 6-3 6 3-2-9"/>',
    'lightbulb': '<path d="M9 18h6M10 21h4M9 14a7 7 0 1 1 6 0l-1 4h-4l-1-4Z"/>',
    'users-check': '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 10-4.5M17 15l2 2 3-4"/>',
    'truck': '<path d="M3 5h11v12H3zM14 9h4l3 4v4h-7M7 17h2M17 17h2"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
    'percent': '<circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/><path d="m5 19 14-14"/>',

}

def icono_gerencia(nombre):
    paths = _ICONOS_GERENCIA.get(nombre, _ICONOS_GERENCIA['target'])
    return ('<span class="ma4-ger-ico" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" '
            'width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + paths + '</svg></span>')

def icono_para_kpi(nombre):
    """Asigna un icono decorativo según el nombre; no cambia el KPI ni sus datos."""
    n = normalizar(nombre)
    if any(x in n for x in ('accidente', 'siniestr', 'seguridad', 'prevencion')):
        return 'helmet'
    if any(x in n for x in ('margen', 'rentabil', 'utilidad', 'ebit', 'financ')):
        return 'money'
    if any(x in n for x in ('ventas', 'facturacion', 'ingresos', 'venta neta')):
        return 'trend'
    if any(x in n for x in ('cliente', 'captacion', 'leads')):
        return 'people'
    if any(x in n for x in ('contrato', 'licitacion', 'adjudic')):
        return 'contract'
    if any(x in n for x in ('csat', 'satisfaccion', 'calidad')):
        return 'heart'
    if any(x in n for x in ('capacitacion', 'personal', 'colaborador', 'salari')):
        return 'users-check'
    if any(x in n for x in ('productividad', 'operacion', 'eficiencia')):
        return 'briefcase'
    if any(x in n for x in ('certificacion', 'sicep', 'cumplimiento norm')):
        return 'shield'
    if any(x in n for x in ('innovacion', 'desarrollo')):
        return 'lightbulb'
    if any(x in n for x in ('montaje', 'logistica', 'entrega')):
        return 'truck'
    return 'target'


def icono_para_venta(titulo):
    n = normalizar(titulo)
    if 'ritmo' in n or 'mes' in n:
        return 'clock'
    if 'falta' in n or 'brecha' in n:
        return 'target'
    if 'deberiamos' in n or 'meta' in n:
        return 'chart'
    return 'money'


def panel_contenido(titulo, texto):
    st.markdown(f'<div class="ma4-panel"><div class="ma4-panel-name">{icono_gerencia("chart" if "desempeño" in normalizar(titulo) else "layers")}{limpio(titulo)}</div>'
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
        f'<div class="ma4-kpi-h">{icono_gerencia(icono_para_kpi(fila["NombreKPI"]))}{titulo}</div>'
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
                f'<div class="ma4-sales-h">{icono_gerencia(icono_para_venta(titulo))}{limpio(titulo)}</div>'
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

# Mostrar únicamente años presentes en los datos oficiales del BSC, más 2026
# como año de referencia del proyecto. Evita abrir en 2030 sin información.
anios_bsc = set(bsc['Fecha'].dropna().dt.year.astype(int).tolist())
anios_disponibles = sorted(anios_bsc | {2026}, reverse=True)

# Si había quedado guardado un año inexistente (por ejemplo, 2030),
# volver a 2026 sin perder las selecciones válidas de años con datos.
if st.session_state.get('ma4_anio') not in anios_disponibles:
    st.session_state['ma4_anio'] = 2026

# El encabezado debe dibujarse ANTES del selector y de cualquier st.stop().
# La fecha del recuadro corresponde al último corte BSC del año seleccionado.
_anio_cabecera = st.session_state['ma4_anio']
_fechas_cabecera = bsc.loc[
    bsc['Fecha'].dt.year.eq(_anio_cabecera) & bsc['Ambito'].eq('GLOBAL'), 'Fecha'
].dropna()
_etiqueta_fecha = (fecha_breve(_fechas_cabecera.max()) if not _fechas_cabecera.empty
                  else 'Sin datos para el año')
st.markdown(
    '<div class="ma4-ger-head"><div><div class="ma4-ger-name">'
    + icono_gerencia('building') + 'Gerencia General</div>'
    '<div class="ma4-ger-sub">Indicadores estratégicos y resumen ejecutivo</div></div>'
    '<div class="ma4-ger-date">📅 ' + limpio(_etiqueta_fecha) + '</div></div>',
    unsafe_allow_html=True,
)

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
            '🗓️ Periodo (fecha de corte)', fechas_opciones,
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

# ------------------------ Tarjetas ejecutivas ---------------------------
# El margen operativo es un KPI estratégico compartido para la vista de Ventas,
# pero NO pertenece a Ingeniería ni a otras categorías ajenas.
# Su valor se obtiene del BSC GLOBAL del mismo corte, nunca de un valor fijo.
mostrar_margen = normalizar(categoria) in ('todas', 'finanzas', 'ventas')
margen_fuente = global_corte.loc[
    global_corte['NombreKPI'].fillna('').astype(str).map(normalizar).eq('margen operativo')
].copy()
if responsable != 'Todos':
    margen_fuente = margen_fuente.loc[margen_fuente['NombreResponsable'].eq(responsable)]
if ocultar:
    margen_fuente = margen_fuente.loc[margen_fuente['Ponderacion'].fillna(0).gt(0)]
# Preferir el registro de Finanzas cuando el BSC incluya el KPI en varios frentes.
# Si hay más de uno, favorecer el que tenga una medición real.
if not margen_fuente.empty:
    margen_fuente['_prioridad_finanzas'] = margen_fuente['CategoriaKPI'].map(
        lambda x: normalizar(x) == 'finanzas')
    margen_fuente['_con_resultado'] = margen_fuente['ResultadoNumerico'].notna() | (
        margen_fuente['ResultadoTexto'].fillna('').astype(str).str.strip().ne(''))
    margen_fuente = margen_fuente.sort_values(
        ['_prioridad_finanzas', '_con_resultado', 'CargaID'],
        ascending=[False, False, False], na_position='last')

# Si el KPI no tiene registro en el corte, no se crea una tarjeta con cifra inventada.
mostrar_tarjeta_margen = mostrar_margen and not margen_fuente.empty
st.markdown('<div class="ma4-title">' + icono_gerencia('target') + 'Indicadores estratégicos</div>', unsafe_allow_html=True)
columnas_estrategicas = st.columns(4 if mostrar_tarjeta_margen else 3, gap='small')
res, k1, k2 = columnas_estrategicas[:3]
with res:
    if normalizar(categoria) == 'ventas':
        # Indicador comercial SOLO para la categoría Ventas.
        # Meta anual y facturación provienen de SQL, sin cifras predefinidas.
        _anio_ventas = int(corte.year)
        _meta_ventas = meta_ventas_desde_sql(_anio_ventas)
        _ventas_corte = ventas.copy()
        _ventas_corte['Fecha'] = pd.to_datetime(_ventas_corte['Fecha'], errors='coerce')
        _ventas_corte['ResultadoNumerico'] = pd.to_numeric(
            _ventas_corte['ResultadoNumerico'], errors='coerce')
        _ventas_corte = _ventas_corte.loc[
            (_ventas_corte['Fecha'].dt.year == _anio_ventas)
            & (_ventas_corte['Fecha'].dt.month <= int(corte.month))
            & _ventas_corte['ResultadoNumerico'].notna()
        ].copy()
        _venta_acumulada = float(_ventas_corte['ResultadoNumerico'].sum())
        _datos_validos = (not _ventas_corte.empty and _meta_ventas is not None
                          and math.isfinite(_meta_ventas) and _meta_ventas > 0)
        _avance_ventas = (_venta_acumulada / _meta_ventas) if _datos_validos else float('nan')
        _color_ventas = (VERDE if _datos_validos and _avance_ventas >= 1 else
                         '#3973CF' if _datos_validos else GRIS)
        _valor_ventas = porcentaje(_avance_ventas) if _datos_validos else '—'
        _nota_ventas = ('Avance de la meta anual de ventas' if _datos_validos
                        else 'Sin meta anual o ventas comparables en SQL')
        _detalle_ventas = ('Vendido: ' + clp(_venta_acumulada) if _datos_validos
                           else 'Consulta la meta de ventas en el BSC')
        _contenido = (
            '<div class="ma4-kpi"><div class="ma4-kpi-h">'
            + icono_gerencia('trend') + 'Desempeño de ventas</div>'
            '<div class="ma4-kpi-mid"><div><div class="ma4-kpi-v">'
            + limpio(_valor_ventas) + '</div><div class="ma4-sub">'
            + limpio(_nota_ventas) + '</div><div class="ma4-sub">'
            + limpio(_detalle_ventas) + '</div></div>'
            '<div class="ma4-ring-small" style="--c:' + _color_ventas
            + ';--w:' + f'{ancho(_avance_ventas):.1f}%' + '"><i>'
            + limpio(_valor_ventas) + '</i></div></div></div>'
        )
        st.markdown(_contenido, unsafe_allow_html=True)
    else:
        indice = metricas(mostrar) if not mostrar.empty else float('nan')
        color = COLORES[estado(indice)]
        html = ('<div class="ma4-kpi"><div class="ma4-kpi-h">' + icono_gerencia('chart') + 'Desempeño general</div>'
                '<div class="ma4-kpi-mid"><div><div class="ma4-kpi-v">'+limpio(porcentaje(indice))+'</div>'
                '<div class="ma4-sub">Meta: 92% de cumplimiento</div>'
                '<div class="ma4-sub">'+limpio(estado(indice))+'</div></div>'
                '<div class="ma4-ring-small" style="--c:'+color+';--w:'+f'{ancho(indice):.1f}%'+ '">'
                '<i>'+limpio(porcentaje(indice))+'</i></div></div></div>')
        st.markdown(html, unsafe_allow_html=True)

# Mantener los otros dos KPI destacados, sin duplicar Margen Operativo.
es_margen_operativo = mostrar['NombreKPI'].fillna('').astype(str).map(
    lambda nombre: normalizar(nombre) == 'margen operativo')
seleccion = mostrar.loc[~es_margen_operativo].sort_values(
    'Ponderacion', ascending=False, na_position='last').head(2)
for columna, (_, fila) in zip((k1, k2), seleccion.iterrows()):
    with columna:
        tarjeta_kpi(fila)

if mostrar_tarjeta_margen:
    with columnas_estrategicas[3]:
        tarjeta_kpi(margen_fuente.iloc[0])

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

st.markdown(f'<div class="ma4-title">' + icono_gerencia('trend') + f'Ventas {anio}: ¿vamos avanzando mes a mes?</div>',
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

# --------------------- KPI más importantes y áreas -----------------------
izq, der = st.columns([1.65, 1], gap='medium')
with izq:
    st.markdown('<div class="ma4-title">' + icono_gerencia('chart') + '¿Cómo van los KPI de mayor peso?</div>',unsafe_allow_html=True)
    ranking = mostrar.sort_values('Ponderacion',ascending=False,na_position='last').head(6).copy()
    ranking = ranking.dropna(subset=['Avance'])
    fig = go.Figure()
    if not ranking.empty:
        fig.add_trace(go.Bar(x=[100*num(v) for v in ranking.iloc[::-1]['Avance']],
             y=ranking.iloc[::-1]['NombreKPI'].astype(str),orientation='h',
             marker_color=[COLORES[estado(v)] for v in ranking.iloc[::-1]['Cumplimiento']],
             hovertemplate='%{y}<extra></extra>%{x:.1f}%',showlegend=False))
        fig.add_vline(x=100,line_color=AZUL,line_width=2)
    fig.update_layout(height=390,margin=dict(l=10,r=20,t=20,b=35),
        plot_bgcolor='rgba(0,0,0,0)',paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(ticksuffix='%',gridcolor='#E7EDF4'),yaxis=dict(automargin=True),
        font=dict(color='#526681'))
    st.plotly_chart(fig,use_container_width=True,config={'displayModeBar':False})
with der:
    departamentos=bsc.loc[(bsc['Ambito']=='AREA')&(bsc['Fecha']<=corte)].copy()
    departamentos['normalizada']=departamentos['NombreArea'].map(normalizar)
    partes=''
    for clave, nombre in [('administracion','Administración'),('ingenieria','Ingeniería'),
                          ('operaciones','Operaciones')]:
        if clave not in AREA_HOJAS: continue
        a=departamentos.loc[departamentos['normalizada']==normalizar(AREA_HOJAS[clave])]
        if a.empty: continue
        a=a.loc[a['Fecha']==a['Fecha'].max()]
        v=metricas(a)
        partes+=('<div class="ma4-area"><span class="ma4-area-name">'+limpio(nombre)+'</span>'
                 '<div class="ma4-track"><span style="--w:'+f'{ancho(v):.2f}%'+
                 ';--c:'+COLORES[estado(v)]+'"></span></div><span class="ma4-area-n">'+
                 limpio(porcentaje(v))+'</span></div>')
    panel_contenido('Desempeño por área',partes or '<div class="ma4-nodata">Sin datos por área.</div>')

# -------------------------- Alertas y detalle ----------------------------
criticos=mostrar.loc[mostrar['Ponderacion'].fillna(0)>0].copy()
criticos['impacto']=(1-criticos['Cumplimiento'].clip(0,1))*criticos['Ponderacion']
criticos=criticos.loc[criticos['impacto']>0].sort_values('impacto',ascending=False).head(3)
lineas=''.join('<div class="ma4-alert-line">🔴 <strong>'+limpio(r['NombreKPI'])+'</strong> · '
               'cumplimiento '+limpio(porcentaje(r['Cumplimiento']))+' · resp. '+
               limpio(r['NombreResponsable'])+'</div>' for _,r in criticos.iterrows())
st.markdown('<div class="ma4-alert"><div class="ma4-alert-title">' + icono_gerencia('alert') + 'Alertas estratégicas '
            '(los KPI que más puntos restan a la nota)</div>'+ (lineas or 'Sin alertas en el corte seleccionado.') +
            '</div>',unsafe_allow_html=True)

st.markdown('<div class="ma4-title">' + icono_gerencia('table') + 'Detalle de todos los KPI (de mayor a menor peso)</div>',unsafe_allow_html=True)
if not mostrar.empty:
    detalle=mostrar.sort_values('Ponderacion',ascending=False,na_position='last').copy()
    detalle['Estado']=detalle['Cumplimiento'].map(lambda x: {'Cumple':'🟢','En riesgo':'🟡',
                                      'No cumple':'🔴','Sin datos':'⚪'}[estado(x)])
    detalle['Actual']=detalle.apply(valor_bsc,axis=1)
    detalle['Meta anual']=detalle.apply(lambda x: valor_bsc(x,meta=True),axis=1)
    detalle['Cumplimiento (%)']=detalle['Cumplimiento'].map(
        lambda x: 100*num(x) if math.isfinite(num(x)) else None)
    tabla=detalle[['Estado','NombreKPI','CategoriaKPI','Meta anual','Actual',
                   'Cumplimiento (%)','NombreResponsable','Ponderacion']].rename(columns={
          'NombreKPI':'KPI','CategoriaKPI':'Categoría','NombreResponsable':'Resp.',
          'Ponderacion':'Peso'})
    # Barras por fila: color según el cumplimiento real del BSC.
    # st.column_config.ProgressColumn aplica un solo color a toda la columna;
    # renderizar aquí evita que los indicadores verdes aparezcan rojos.
    def celda_cumplimiento(valor):
        v = num(valor)
        if not math.isfinite(v):
            return '<span style="color:#8793A4">Sin datos</span>'
        color = VERDE if v >= 100 else (AMARILLO if v >= 70 else ROJO)
        ancho_barra = max(0, min(100, v))
        valor_txt = f'{v:.1f}'.replace('.', ',') + '%'
        return (f'<div class="ma4-cumplimiento"><div class="ma4-cumplimiento-track">'
                f'<span style="width:{ancho_barra:.2f}%;background:{color}"></span></div>'
                f'<strong style="color:{color}">{valor_txt}</strong></div>')

    cabeceras = list(tabla.columns)
    filas_html = []
    for _, registro in tabla.iterrows():
        celdas = []
        for col in cabeceras:
            if col == 'Cumplimiento (%)':
                valor_html = celda_cumplimiento(registro[col])
            elif col == 'Peso':
                valor_html = limpio(f'{num(registro[col]):g}' if math.isfinite(num(registro[col])) else '—')
            else:
                valor_html = limpio(registro[col])
            celdas.append('<td>' + valor_html + '</td>')
        filas_html.append('<tr>' + ''.join(celdas) + '</tr>')
    encabezado = ''.join('<th>' + limpio(c) + '</th>' for c in cabeceras)
    st.markdown('''<style>
    .ma4-tabla-scroll{max-height:470px;overflow:auto;border:1px solid #DFE5ED;
        border-radius:13px;background:white}
    .ma4-tabla-color{width:100%;border-collapse:separate;border-spacing:0;
        font-size:.84rem;color:#243451;min-width:850px}
    .ma4-tabla-color th{position:sticky;top:0;background:#F7F9FC;z-index:1;
        color:#748198;font-weight:500;text-align:left;padding:12px 10px;
        border-bottom:1px solid #DCE3EB;white-space:nowrap}
    .ma4-tabla-color td{padding:10px;border-bottom:1px solid #E5EAF1;
        vertical-align:middle}
    .ma4-tabla-color td:nth-child(2){min-width:240px}
    .ma4-tabla-color td:last-child{text-align:right}
    .ma4-cumplimiento{display:flex;align-items:center;gap:9px;min-width:150px}
    .ma4-cumplimiento-track{flex:1;height:8px;border-radius:20px;
        background:#F0F2F5;overflow:hidden;min-width:65px}
    .ma4-cumplimiento-track span{display:block;height:100%;border-radius:20px}
    .ma4-cumplimiento strong{font-size:.78rem;min-width:46px;text-align:right}
    </style>''',unsafe_allow_html=True)
    st.markdown('<div class="ma4-tabla-scroll"><table class="ma4-tabla-color">'
                '<thead><tr>' + encabezado + '</tr></thead><tbody>' +
                ''.join(filas_html) + '</tbody></table></div>', unsafe_allow_html=True)
