# -*- coding: utf-8 -*-
"""MAAS Ecología · Operaciones · Tablero V10.

Reemplazar solamente pages_v08/operaciones.py por este contenido.
Usa maas_auth.py, maas_datos.py y maas_ui.py de la versión V09 ya instalada.
Solo realiza consultas de lectura en MAAS_ECOLOGIA_4.
Los indicadores y sus porcentajes provienen del BSC; los semáforos son visuales.
Los datos operativos de la tabla de proyectos son SIMULADOS (fines académicos).
"""
from __future__ import annotations

import html
import math
import unicodedata

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from maas_datos import cargar, _conexion
from maas_ui import metricas, presentacion_valor, recortar_bsc

AZUL = '#1F3854'
VERDE = '#4FA272'
AMARILLO = '#E5B33F'
ROJO = '#D15C5D'
GRIS = '#98A8BB'
FRENTES = ['Plazos y montajes', 'Seguridad y calidad', 'Rentabilidad operativa']


def numero(valor):
    try:
        x = float(valor)
        return x if math.isfinite(x) else float('nan')
    except (ValueError, TypeError):
        return float('nan')


def limpio(valor):
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass
    return str(valor or '').strip()


def e(valor):
    return html.escape(limpio(valor), quote=True)


def norm(valor):
    cadena = unicodedata.normalize('NFKD', limpio(valor))
    return ' '.join(''.join(ch for ch in cadena if not unicodedata.combining(ch)).casefold().split())


def local(valor, decimales=1):
    x = numero(valor)
    if not math.isfinite(x):
        return '—'
    return f'{x:,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def pct(valor):
    x = numero(valor)
    return local(x * 100, 1) + '%' if math.isfinite(x) else '—'


def pesos(valor):
    x = numero(valor)
    return '$' + f'{round(x):,}'.replace(',', '.') if math.isfinite(x) else '—'


def estado(valor):
    x = numero(valor)
    if not math.isfinite(x):
        return 'Sin datos'
    if x >= 1:
        return 'Meta alcanzada'
    if x >= .7:
        return 'En progreso'
    return 'Bajo cumplimiento'


def color(valor):
    return {
        'Meta alcanzada': VERDE,
        'En progreso': AMARILLO,
        'Bajo cumplimiento': ROJO,
        'Sin datos': GRIS,
    }[estado(valor)]


def barra(valor):
    x = numero(valor)
    return f'{max(0., min(100., x * 100)):.1f}%' if math.isfinite(x) else '0%'


def valor_bsc(fila, meta=False):
    n = fila.get('MetaNumerica' if meta else 'ResultadoNumerico')
    t = fila.get('MetaTexto' if meta else 'ResultadoTexto')
    u = fila.get('UnidadMedida')
    unidad = norm(u)
    # El archivo del BSC expresa algunos montos en miles de CLP.
    if 'miles' in unidad and ('clp' in unidad or '$' in unidad):
        if math.isfinite(numero(n)):
            return pesos(numero(n) * 1000)
        return limpio(t) or 'Sin dato'
    return presentacion_valor(n, t, u)


def frente(fila):
    """Agrupaciones de pantalla; preservan la categoría y el nombre originales."""
    kpi = norm(fila.get('NombreKPI'))
    if any(x in kpi for x in (
        'accidente', 'seguridad', 'siniestral', 'csat montajes',
        'satisfaccion de montaje', 'calidad de montaje', 'montajes bien ejecutados',
    )):
        return 'Seguridad y calidad'
    if any(x in kpi for x in (
        'dentro de margen', 'facturar dentro', 'rentabilidad', 'margen ebit',
        'margen operativo', 'adicional ap', 'negocios adicionales', 'costo operativo',
    )):
        return 'Rentabilidad operativa'
    if any(x in kpi for x in (
        'ejecucion dentro', 'ejecucion en plazo', 'ejecucion de plazo',
        'montajes plantas', 'montajes planta', 'cumplimiento de plazo',
        'plazo de ejecucion', 'trabajos ejecutados', 'cumplimiento operacional',
    )):
        return 'Plazos y montajes'
    return 'Indicadores transversales'




# Iconos decorativos SVG para Operaciones (sin dependencias ni cambios en el BSC).
_OP_ICONOS = {
    'operations': '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 8h3v3H7zM14 8h3v3h-3zM7 14h3v3H7zM14 14h3v3h-3z"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'hard-hat': '<path d="M3 18h18M5 15a7 7 0 0 1 14 0M12 7v7M4 15h16v3H4z"/>',
    'cash': '<circle cx="12" cy="12" r="9"/><path d="M15 8.5c-.7-1.5-5-1.5-6.1.2-1.5 2.8 6.5 1.6 6.2 4.6-.2 2.1-5.3 2.7-6.2.7M12 5v14"/>',
    'trend': '<path d="m3 17 6-6 4 4 8-9M15 6h6v6"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
    'check': '<path d="M20 7 10 17l-5-5"/><circle cx="12" cy="12" r="10"/>',
    'clipboard': '<rect x="5" y="4" width="14" height="18" rx="2"/><rect x="9" y="2" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h6"/>',
    'quality': '<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/>',
    'people': '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2c0-4 3-6 6-6s6 2 6 6v2M16 5a3 3 0 0 1 0 6M18 13c2 1 3 3 3 5v2"/>',
    'construction': '<path d="M4 20h16M6 17V8l6-4 6 4v9M3 10h18M12 4v13"/>',
    'truck': '<rect x="2" y="7" width="12" height="10" rx="1"/><path d="M14 10h4l4 4v3h-8"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
    'tools': '<path d="m14 7 3 3-8 8a3 3 0 0 1-4-4l9-9M15 3a6 6 0 0 0 6 6"/>',
    'chart': '<path d="M3 3v18h18M7 16l4-5 4 3 5-7"/>',
    'alert': '<path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5M12 18h.01"/>',
    'table': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    'heart': '<path d="M20 8c0 5-8 11-8 11S4 13 4 8a4 4 0 0 1 8-1 4 4 0 0 1 8 1Z"/>',
    'lightbulb': '<path d="M9 18h6M9 21h6M9 15c-2-1-4-3-4-6a7 7 0 0 1 14 0c0 3-2 5-4 6v3H9z"/>',
    'file': '<path d="M6 2h9l5 5v15H6zM15 2v6h5M9 13h8M9 17h8"/>',
    'graduation': '<path d="m2 9 10-5 10 5-10 5-10-5ZM6 11v6c4 3 8 3 12 0v-6M22 9v7"/>',
}

def op_icono(nombre, clase='op-icon'):
    trazos = _OP_ICONOS.get(nombre, _OP_ICONOS['target'])
    return (f'<span class="{clase}" aria-hidden="true">'
            f'<svg viewBox="0 0 24 24" width="17" height="17" fill="none" '
            f'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
            f'stroke-linejoin="round">{trazos}</svg></span>')

def op_icono_kpi(titulo):
    n = norm(titulo)
    reglas = (
        (('accidente', 'siniestral', 'seguridad', 'prevencion'), 'hard-hat'),
        (('margen', 'rentabilidad', 'facturar', 'costo', 'presupuesto', 'financ'), 'cash'),
        (('montaje', 'planta', 'instalacion', 'faena'), 'construction'),
        (('plazo', 'tiempo', 'fecha', 'entrega'), 'clock'),
        (('transporte', 'vehiculo', 'logistica', 'despacho'), 'truck'),
        (('calidad', 'certificacion', 'norma', 'sicep'), 'quality'),
        (('satisfaccion', 'csat', 'cliente'), 'heart'),
        (('equipo', 'personal', 'colaborador'), 'people'),
        (('capacita', 'formacion'), 'graduation'),
        (('innovacion', 'mejora'), 'lightbulb'),
        (('ejecucion', 'cumplimiento', 'avance', 'kom'), 'check'),
        (('proyecto', 'propuesta', 'contrato'), 'clipboard'),
        (('produccion', 'productividad', 'operativo'), 'tools'),
    )
    return next((icono for palabras, icono in reglas if any(p in n for p in palabras)), 'target')

def op_titulo_icono(titulo, nombre):
    return op_icono(nombre) + e(titulo)

CSS = '''<style>
.op10-head{display:flex;justify-content:space-between;gap:14px;align-items:center;
 flex-wrap:wrap;margin:2px 0 20px}
.op10-title{font-size:clamp(1.85rem,2.5vw,2.35rem);font-weight:850;
 color:#1C3451;letter-spacing:-.035em;line-height:1.2}
.op10-sub{font-size:.91rem;color:#71869E;margin-top:7px}
.op10-date{border:1px solid #DFE6EE;border-radius:13px;background:#fff;
 padding:10px 14px;font-size:.80rem;color:#536D88;font-weight:750}
.op10-section{font-size:1.13rem;font-weight:830;color:#203C59;margin:27px 0 12px}
.op10-caption{color:#8293A5;font-size:.76rem;line-height:1.45;margin:3px 0 12px}
.op10-summary{background:#fff;border:1px solid #DEE7EF;border-left:5px solid var(--c);
 border-radius:15px;padding:17px;min-height:132px;margin-bottom:8px}
.op10-label{font-size:.82rem;font-weight:740;color:#536D87}
.op10-big{font-size:clamp(1.68rem,2.15vw,2.1rem);color:#1E3955;
 font-weight:860;letter-spacing:-.03em;margin:12px 0 7px}
.op10-note{font-size:.73rem;color:#8192A4;line-height:1.42}
.op10-feature{background:#fff;border:1px solid #DFE7EF;border-top:4px solid var(--c);
 border-radius:15px;padding:17px 16px;min-height:201px;margin-bottom:8px}
.op10-feature-name{font-size:.84rem;font-weight:800;color:#314B64;line-height:1.35;
 min-height:39px;overflow-wrap:anywhere}
.op10-feature-num{font-size:clamp(1.4rem,1.85vw,1.92rem);font-weight:860;
 color:#193653;margin:12px 0 6px;overflow-wrap:anywhere}
.op10-feature-meta{font-size:.76rem;color:#8394A5;margin-bottom:13px;overflow-wrap:anywhere}
.op10-track{height:8px;border-radius:20px;background:#E9EFF5;overflow:hidden}
.op10-fill{display:block;height:100%;width:var(--w);background:var(--c);border-radius:20px}
.op10-foot{display:flex;justify-content:space-between;gap:8px;margin-top:10px;
 color:var(--c);font-size:.74rem;font-weight:810}
.op10-panel{border:1px solid #DFE7EF;background:white;border-radius:16px;
 padding:18px 18px 19px;min-height:292px;margin-bottom:10px}
.op10-panelhead{display:flex;align-items:start;justify-content:space-between;
 gap:12px;margin-bottom:14px}
.op10-panelname{color:#26435E;font-size:.96rem;font-weight:840;line-height:1.3}
.op10-pill{background:#EFF4F8;border-radius:99px;padding:5px 10px;
 color:#55728D;font-size:.71rem;font-weight:780;white-space:nowrap}
.op10-row{padding:12px 0 11px;border-bottom:1px solid #ECF1F5}
.op10-row:last-child{border:0;padding-bottom:0}
.op10-rowtop{display:flex;align-items:start;justify-content:space-between;gap:10px}
.op10-name{font-size:.80rem;color:#324D68;font-weight:740;line-height:1.35}
.op10-score{color:var(--c);font-size:.79rem;font-weight:850;white-space:nowrap}
.op10-value{font-size:.72rem;color:#8394A5;margin:6px 0 9px;line-height:1.4}
.op10-alert{border:1px solid #DEE7EE;background:#fff;border-radius:15px;
 padding:18px 19px;min-height:220px;margin-bottom:10px}
.op10-alerttitle{font-size:.95rem;font-weight:830;color:#25405D;margin-bottom:12px}
.op10-alertrow{padding:11px 0;border-bottom:1px solid #ECF1F5}
.op10-alertrow:last-child{border:0}
.op10-alerttext{font-size:.81rem;font-weight:750;line-height:1.34;color:#304C65}
.op10-alertsub{color:#8394A6;font-size:.73rem;margin-top:5px;line-height:1.42}
.op10-alertbadge{color:var(--c);font-size:.76rem;font-weight:830;white-space:nowrap}
.op10-empty{font-size:.82rem;color:#8595A5;line-height:1.55}

/* Únicamente decoraciones e interior de filtros: conservar geometría y colores de estado. */
.op-icon{display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;
 width:29px;height:29px;min-width:29px;margin-right:9px;border-radius:9px;
 background:#EDF3FE;color:#356DC9;flex-shrink:0}
.op-icon svg{width:17px;height:17px}
.op10-title .op-icon{width:39px;height:39px;border-radius:12px;margin-right:11px}
.op10-title .op-icon svg{width:22px;height:22px}
.op10-label .op-icon,.op-card-name .op-icon,.op10-name .op-icon,
.op10-alerttext .op-icon{width:25px;height:25px;min-width:25px;border-radius:8px;margin-right:7px}
.op10-section .op-icon{width:32px;height:32px}
.op10-title,.op10-section,.op-visual-title,.op10-panelname,.op10-alerttitle{display:flex;align-items:center}
.op10-panelname .op-icon{width:28px;height:28px}
.op-card-name{display:flex;align-items:flex-start}
.op10-name,.op10-alerttext{display:flex;align-items:center}
/* La caja es un contenedor REAL de Streamlit y no sólo un cambio del fondo de los selectores. */
.st-key-op_filtros_blancos{
 background:#FFFFFF!important;border:1px solid #DEE7F0!important;border-radius:17px!important;
 box-shadow:0 2px 10px rgba(15,39,72,.045)!important;padding:15px 18px 9px!important;
 margin:3px 0 17px!important;
}
.st-key-op_filtros_blancos [data-baseweb="select"]>div,
.st-key-op_filtros_blancos [data-testid="stSelectbox"] [data-baseweb="select"]>div{
 background:#fff!important;border:1px solid #DEE7F0!important;border-radius:10px!important;
}
.st-key-op_filtros_blancos [data-testid="stWidgetLabel"] p{font-weight:720!important;color:#253C59!important}
</style>'''
st.markdown(CSS, unsafe_allow_html=True)


st.markdown("""<style>
.op-overview{background:#fff;border:1px solid #DEE7F0;border-radius:17px;padding:19px;min-height:390px}
.op-visual-title{font-size:.98rem;color:#1C324F;font-weight:830;margin-bottom:25px}
.op-donut-layout{display:flex;align-items:center;justify-content:center;gap:20px;flex-wrap:wrap;margin-bottom:24px}
.op-donut{width:174px;height:174px;flex-shrink:0;border-radius:50%;background:conic-gradient(var(--c) 0 var(--w),#E8EDF5 var(--w) 100%);display:grid;place-items:center}
.op-hole{width:129px;height:129px;border-radius:50%;background:white;display:grid;place-items:center;font-size:1.75rem;font-weight:870;color:#1C324F}
.op-legend{font-size:.8rem;color:#566C84;min-width:120px}
.op-legend>div{display:flex;align-items:center;gap:7px;margin:11px 0}
.op-legend b{margin-left:auto;color:#1C324F}
.op-bullet{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.op-muted{font-size:.75rem;color:#7D8DA2;line-height:1.5}
.op-card-round{background:white;border:1px solid #DDE6EF;border-radius:20px;padding:19px;min-height:253px;display:flex;flex-direction:column;justify-content:space-between;box-shadow:0 3px 10px rgba(30,48,76,.035);margin-bottom:12px}
.op-card-name{font-size:.86rem;color:#3F5572;font-weight:790;min-height:45px;line-height:1.38;overflow-wrap:anywhere}
.op-card-main{display:grid;grid-template-columns:minmax(0,1fr) 82px;gap:8px;align-items:center;flex:1}
.op-card-values{min-width:0}
.op-card-value{font-size:1.6rem;color:#142D4D;font-weight:890;margin-bottom:7px;overflow-wrap:anywhere}
.op-card-sub{font-size:.73rem;color:#7E8FA5;margin-top:3px;line-height:1.5}
.op-smallring{width:82px;height:82px;border-radius:50%;background:conic-gradient(var(--c) 0 var(--w),#E8EDF5 var(--w) 100%);display:grid;place-items:center}
.op-smallhole{width:61px;height:61px;border-radius:50%;background:white;display:grid;place-items:center;color:#142D4D;font-weight:860;font-size:.82rem}
.op-card-tags{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:10px}
.op-status{color:white;padding:5px 10px;border-radius:999px;font-size:.72rem;font-weight:820}
.op-weight{background:#EDF2F8;color:#526986;padding:5px 9px;border-radius:999px;font-size:.72rem;font-weight:770}
.op-table-scroll{overflow:auto;border:1px solid #DFE7EF;border-radius:16px;background:white;max-height:600px}
.op-table{border-collapse:collapse;width:100%;min-width:950px;font-size:.82rem}
.op-table th{position:sticky;top:0;background:#F7F9FC;color:#536984;text-align:left;font-weight:790;padding:15px 13px;border-bottom:1px solid #DEE6EE;white-space:nowrap}
.op-table td{padding:14px 13px;vertical-align:middle;border-bottom:1px solid #E9EEF5;color:#263F5B}
.op-table tbody tr:hover{background:#F9FBFD}
.op-center{text-align:center;width:72px}
.op-table-dot{display:inline-block;width:13px;height:13px;border-radius:50%}
.op-progress{display:flex;align-items:center;gap:11px;min-width:205px}
.op-progress-bg{background:#E9EEF3;height:10px;border-radius:99px;flex:1;overflow:hidden}
.op-progress-bg span{display:block;height:100%;border-radius:99px}
.op-progress b{font-size:.77rem;min-width:47px;text-align:right}
</style>""",unsafe_allow_html=True)


def resumen_html(titulo, dato, nota, tono):
    return (f'<div class="op10-summary" style="--c:{tono}">'
            f'<div class="op10-label">{op_icono(op_icono_kpi(titulo))}{e(titulo)}</div>'
            f'<div class="op10-big">{e(dato)}</div>'
            f'<div class="op10-note">{e(nota)}</div></div>')


def kpi_html(fila):
    """Tarjeta circular uniforme, con meta, resultado, avance y ponderación."""
    cumplimiento = fila['Cumplimiento']
    co = color(cumplimiento)
    n = numero(cumplimiento)
    interior = f'{min(100, max(0, round(n * 100)))}%' if math.isfinite(n) else '—'
    etiqueta = {'Meta alcanzada': 'Cumple', 'En progreso': 'En riesgo',
                'Bajo cumplimiento': 'No cumple', 'Sin datos': 'Sin datos'}[estado(cumplimiento)]
    return (f'<div class="op-card-round" style="--c:{co}">'
            f'<div class="op-card-name">{op_icono(op_icono_kpi(fila["NombreKPI"]))}{e(fila["NombreKPI"])}</div>'
            '<div class="op-card-main"><div class="op-card-values">'
            f'<div class="op-card-value">{e(valor_bsc(fila))}</div>'
            f'<div class="op-card-sub">Meta anual: {e(valor_bsc(fila, True))}</div>'
            f'<div class="op-card-sub">Avance: {e(pct(cumplimiento))}</div>'
            '</div>'
            f'<div class="op-smallring" style="--w:{barra(cumplimiento)}">'
            f'<div class="op-smallhole">{interior}</div></div></div>'
            '<div class="op-card-tags">'
            f'<span class="op-status" style="background:{co}">{e(etiqueta)}</span>'
            f'<span class="op-weight">Peso {e(local(fila.get("Ponderacion"), 0))}</span>'
            '</div></div>')


def panel_html(nombre, filas):
    filas = filas.sort_values('Ponderacion', ascending=False, na_position='last')
    salida = (f'<div class="op10-panel"><div class="op10-panelhead">'
              f'<span class="op10-panelname">{op_icono(op_icono_kpi(nombre))}{e(nombre)}</span>'
              f'<span class="op10-pill">{len(filas)} KPI</span></div>')
    if filas.empty:
        return salida + '<div class="op10-empty">No hay KPI de este grupo en el corte BSC.</div></div>'
    salida += ''
    for _, f in filas.head(3).iterrows():
        tono = color(f['Cumplimiento'])
        salida += (f'<div class="op10-row"><div class="op10-rowtop">'
                   f'<div class="op10-name">{op_icono(op_icono_kpi(f["NombreKPI"]))}{e(f["NombreKPI"])}</div>'
                   f'<div class="op10-score" style="--c:{tono}">{e(pct(f["Cumplimiento"]))}</div></div>'
                   f'<div class="op10-value">Resultado: {e(valor_bsc(f))} · '
                   f'Meta: {e(valor_bsc(f, True))}</div>'
                   f'<div class="op10-track"><span class="op10-fill" '
                   f'style="--w:{barra(f["Cumplimiento"])};--c:{tono}"></span></div></div>')
    return salida + '</div>'


def alerta_html(fila, orden):
    co = color(fila['Cumplimiento'])
    peso = local(fila['Ponderacion'], 0)
    return (f'<div class="op10-alertrow"><div class="op10-rowtop">'
            f'<div class="op10-alerttext">{op_icono(op_icono_kpi(fila["NombreKPI"]))}{orden}. {e(fila["NombreKPI"])}</div>'
            f'<span class="op10-alertbadge" style="--c:{co}">{e(pct(fila["Cumplimiento"]))}</span></div>'
            f'<div class="op10-alertsub">Resultado: {e(valor_bsc(fila))} · '
            f'Meta: {e(valor_bsc(fila, True))} · Peso BSC: {e(peso)}</div></div>')


@st.cache_data(ttl=90, show_spinner=False)
def responsables_globales_bsc_operaciones():
    """Responsables oficiales del mismo KPI y fecha, solo lectura SQL."""
    con = _conexion()
    try:
        return pd.read_sql_query("""
            SELECT fe.Fecha, k.CodigoKPI, r.NombreResponsable
            FROM dbo.FACT_KPI_ESTRATEGICO f
            JOIN dbo.DIM_KPI k ON k.KPI_Key = f.KPI_Key
            JOIN dbo.DIM_FECHA fe ON fe.Fecha_Key = f.Fecha_Key
            JOIN dbo.DIM_RESPONSABLE r ON r.Responsable_Key = f.Responsable_Key
            WHERE f.Ambito = 'GLOBAL' AND f.FuenteResultado = 'BSC'
              AND k.TipoIndicador = 'OFICIAL_BSC'
        """, con)
    finally:
        con.close()


def incorporar_responsables_operaciones(datos):
    salida = datos.copy()
    if 'NombreResponsable' not in salida.columns:
        salida['NombreResponsable'] = pd.NA
    if 'CodigoKPI' not in salida.columns:
        return salida
    try:
        globales = responsables_globales_bsc_operaciones()
        globales['Fecha'] = pd.to_datetime(globales['Fecha'], errors='coerce').dt.normalize()
        globales = globales.dropna(subset=['Fecha','CodigoKPI']).drop_duplicates(['Fecha','CodigoKPI'], keep='last')
        salida['_fecha_resp'] = pd.to_datetime(salida['Fecha'], errors='coerce').dt.normalize()
        salida = salida.merge(globales[['Fecha','CodigoKPI','NombreResponsable']].rename(
            columns={'Fecha':'_fecha_resp','NombreResponsable':'_resp_global'}),
            on=['_fecha_resp','CodigoKPI'],how='left',sort=False,validate='many_to_one')
        salida['NombreResponsable'] = salida['NombreResponsable'].replace(r'^\s*$',pd.NA,regex=True).fillna(salida['_resp_global'])
        salida = salida.drop(columns=['_fecha_resp','_resp_global'])
    except Exception as ex:
        st.warning(f'No fue posible consultar los responsables del BSC global: {ex}')
        salida = salida.drop(columns=['_fecha_resp','_resp_global'], errors='ignore')
    return salida


# Cargar BSC antes de recortar al área para que el filtro de año sea real.
fuente = cargar('bsc')
if fuente.empty:
    st.title('Operaciones')
    st.info('Todavía no hay información del BSC.')
    st.stop()
fuente = fuente.copy()
fuente['Fecha'] = pd.to_datetime(fuente['Fecha'], errors='coerce')
anios_datos = fuente['Fecha'].dropna().dt.year.astype(int).unique().tolist()
anios = sorted(set(anios_datos) | set(range(2024, 2029)), reverse=True)

st.markdown('<div class="op10-head"><div><div class="op10-title">' + op_icono('operations') + 'Operaciones</div>'
            '<div class="op10-sub">Ejecución, seguridad, montajes y rentabilidad</div></div></div>',
            unsafe_allow_html=True)
with st.container(key='op_filtros_blancos'):
    f1, f2 = st.columns([0.8, 1.5], gap='medium')
    with f1:
        anio_sel = st.selectbox('Año', anios, index=anios.index(2026) if 2026 in anios else 0, key='op_anio')
    fuente_anio = fuente.loc[fuente['Fecha'].dt.year.eq(anio_sel)]
    if fuente_anio.empty:
        with f2:
            st.selectbox('Período (fecha de corte)', ['Sin datos'], disabled=True)
        st.info(f'No hay registros del BSC para {anio_sel}.')
        st.stop()
    fechas = sorted(fuente_anio['Fecha'].dropna().dt.normalize().unique(), reverse=True)
    if not fechas:
        st.info('No hay fechas válidas para el año seleccionado.')
        st.stop()
    etiquetas = ['Más reciente (' + pd.Timestamp(fechas[0]).strftime('%d/%m/%Y') + ')'] + [pd.Timestamp(f).strftime('%d/%m/%Y') for f in fechas[1:]]
    with f2:
        periodo_sel = st.selectbox('Período (fecha de corte)', etiquetas, key='op_periodo')
    fecha_sel = pd.Timestamp(fechas[etiquetas.index(periodo_sel)])
fuente_corte = fuente_anio.loc[fuente_anio['Fecha'].dt.normalize().eq(fecha_sel)].copy()
df = recortar_bsc(fuente_corte, 'operaciones')
if df.empty:
    st.info('No hay KPI oficiales de Operaciones para este corte.')
    st.stop()
df = incorporar_responsables_operaciones(df.copy())
df['Cumplimiento'] = pd.to_numeric(df['Cumplimiento'], errors='coerce')
df['Ponderacion'] = pd.to_numeric(df['Ponderacion'], errors='coerce')
df['NombreKPI'] = df['NombreKPI'].fillna('Sin nombre').astype(str)
df['CategoriaKPI'] = df['CategoriaKPI'].fillna('Sin categoría').astype(str)
df['Frente'] = df.apply(frente, axis=1)
fecha = pd.to_datetime(df['Fecha'].max(), errors='coerce')
corte = fecha.strftime('%d/%m/%Y') if pd.notna(fecha) else 'Sin fecha'
indicador = metricas(df)
evaluados = df.loc[df['Cumplimiento'].notna()]
metas = int((evaluados['Cumplimiento'] >= 1).sum())
criticos = int((evaluados['Cumplimiento'] < .7).sum())
progreso = int(((evaluados['Cumplimiento'] >= .7) & (evaluados['Cumplimiento'] < 1)).sum())
sin_datos = int(df['Cumplimiento'].isna().sum())


# Dos visuales en la misma fila: anillo ponderado y comparación por KPI.
st.markdown('<div class="op10-section">' + op_icono('chart') + 'Panorama de Operaciones</div>', unsafe_allow_html=True)
izq, der = st.columns([0.9, 1.5], gap='medium')
with izq:
    st.markdown(f"""<div class="op-overview">
      <div class="op-visual-title">{op_icono('target')}Cumplimiento Operaciones</div>
      <div class="op-donut-layout">
        <div class="op-donut" style="--c:{color(indicador)};--w:{barra(indicador)}"><div class="op-hole">{e(pct(indicador))}</div></div>
        <div class="op-legend">
          <div><span class="op-bullet" style="background:{VERDE}"></span>Cumple <b>{metas}</b></div>
          <div><span class="op-bullet" style="background:{AMARILLO}"></span>En riesgo <b>{progreso}</b></div>
          <div><span class="op-bullet" style="background:{ROJO}"></span>No cumple <b>{criticos}</b></div>
          <div><span class="op-bullet" style="background:{GRIS}"></span>Sin datos <b>{sin_datos}</b></div>
        </div>
      </div>
      <div class="op-muted">Promedio ponderado de los KPI evaluables del área</div>
     </div>""", unsafe_allow_html=True)
with der:
    with st.container(border=True):
        st.markdown('**📊 ¿Cómo vamos en los KPI que cuentan para Operaciones?**')
        tab1, tab2 = st.tabs(['Avance real vs. esperado', 'Qué KPI restan más puntos'])
        graf = df.loc[df['Cumplimiento'].notna() & (df['Ponderacion'] > 0)].copy()
        graf = graf.sort_values('Ponderacion', ascending=False).head(10)
        with tab1:
            if graf.empty:
                st.info('Sin KPI evaluables para este gráfico.')
            else:
                t = graf.iloc[::-1]
                fig = go.Figure(go.Bar(x=t['Cumplimiento'].clip(0, 1.3) * 100,
                    y=t['NombreKPI'].str.slice(0, 44), orientation='h',
                    marker_color=[color(v) for v in t['Cumplimiento']],
                    hovertemplate='%{y}: %{x:.1f}%<extra></extra>'))
                fig.add_vline(x=100, line_color=AZUL, line_width=2)
                fig.update_layout(height=340, margin=dict(l=6,r=12,t=8,b=25),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(range=[0,135], ticksuffix='%', gridcolor='#E9EFF5'),
                    yaxis=dict(tickfont=dict(size=10), automargin=True), showlegend=False)
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar':False})
        with tab2:
            if graf.empty:
                st.info('Sin brechas calculables.')
            else:
                t = graf.assign(Brecha=(1-graf['Cumplimiento'].clip(0,1))*graf['Ponderacion']).sort_values('Brecha').tail(10)
                fig = go.Figure(go.Bar(x=t['Brecha'], y=t['NombreKPI'].str.slice(0,44),
                    orientation='h', marker_color=ROJO))
                fig.update_layout(height=340, margin=dict(l=6,r=12,t=8,b=25),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(title='Puntos de impacto', gridcolor='#E9EFF5'),
                    yaxis=dict(tickfont=dict(size=10), automargin=True), showlegend=False)
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar':False})

# Tarjetas circulares de los KPI operacionales; no duplicar resúmenes superiores.
st.markdown('<div class="op10-section">' + op_icono('target') + 'KPI propios del área (de mayor a menor peso)</div>', unsafe_allow_html=True)
propios = df[df['Frente'].isin(FRENTES)].sort_values('Ponderacion', ascending=False, na_position='last')
if propios.empty:
    st.info('No hay indicadores propios del área en el corte seleccionado.')
else:
    for comienzo in range(0, len(propios), 4):
        for col, (_, fila) in zip(st.columns(4, gap='medium'), propios.iloc[comienzo:comienzo+4].iterrows()):
            with col:
                st.markdown(kpi_html(fila), unsafe_allow_html=True)

# Frente operativo: menos texto y grupos con propósito propio.
st.markdown('<div class="op10-section">' + op_icono('clipboard') + 'Control por frente de trabajo</div>', unsafe_allow_html=True)
for col, nombre in zip(st.columns(3, gap='medium'), FRENTES):
    with col:
        st.markdown(panel_html(nombre, df[df['Frente'].eq(nombre)]), unsafe_allow_html=True)

# Seguimiento compacto: mostrar brechas del corte en lugar de tarjetas vacías.
st.markdown('<div class="op10-section">' + op_icono('alert') + '¿Qué necesita atención?</div>', unsafe_allow_html=True)
izquierda, derecha = st.columns([1.15, 1], gap='medium')
with izquierda:
    pendientes = df.loc[df['Cumplimiento'].notna() & (df['Cumplimiento'] < 1) &
                        (df['Ponderacion'].fillna(0) > 0)].copy()
    pendientes['Brecha'] = ((1 - pendientes['Cumplimiento'].clip(lower=0, upper=1)) *
                           pendientes['Ponderacion'].clip(lower=0))
    pendientes = pendientes.sort_values(['Brecha','Ponderacion'], ascending=False)
    contenido = ''
    for i, (_, fila) in enumerate(pendientes.head(4).iterrows(), 1):
        co = color(fila['Cumplimiento'])
        contenido += (
            f'<div class="op10-alertrow"><div class="op10-rowtop">'
            f'<div class="op10-alerttext">{op_icono(op_icono_kpi(fila["NombreKPI"]))}{i}. {e(fila["NombreKPI"])}</div>'
            f'<span class="op10-alertbadge" style="--c:{co}">{e(pct(fila["Cumplimiento"]))}</span></div>'
            f'<div class="op10-alertsub">Actual: {e(valor_bsc(fila))} · Meta: '
            f'{e(valor_bsc(fila,True))} · Peso: {e(local(fila["Ponderacion"],0))}</div>'
            f'<div class="op10-track" style="margin-top:9px"><span class="op10-fill" '
            f'style="--c:{co};--w:{barra(fila["Cumplimiento"])}"></span></div></div>')
    if not contenido:
        contenido = '<div class="op10-empty">No hay KPI ponderados por debajo de su meta en este corte.</div>'
    st.markdown('<div class="op10-alert" style="min-height:0">'
                '<div class="op10-alerttitle">' + op_icono('alert') + 'Brechas de cumplimiento prioritarias</div>'
                f'<div class="op10-alertsub" style="margin-bottom:12px">{len(pendientes)} KPI con peso y cumplimiento inferior al 100%. Ordenados por impacto ponderado.</div>'
                + contenido + '</div>', unsafe_allow_html=True)
with derecha:
    # Indicadores resumidos del corte; calculados únicamente a partir del BSC.
    st.markdown(f'''<div class="op10-alert" style="min-height:0">
      <div class="op10-alerttitle">{op_icono('clipboard')}Estado del seguimiento</div>
      <div class="op10-alertrow"><div class="op10-rowtop"><span class="op10-alerttext">KPI que cumplen la meta</span><b style="color:{VERDE}">{metas}</b></div></div>
      <div class="op10-alertrow"><div class="op10-rowtop"><span class="op10-alerttext">KPI en riesgo (70%–99,9%)</span><b style="color:{AMARILLO}">{progreso}</b></div></div>
      <div class="op10-alertrow"><div class="op10-rowtop"><span class="op10-alerttext">KPI críticos (bajo 70%)</span><b style="color:{ROJO}">{criticos}</b></div></div>
      <div class="op10-alertrow"><div class="op10-rowtop"><span class="op10-alerttext">KPI sin medición</span><b style="color:{GRIS}">{sin_datos}</b></div></div>
      <div class="op10-alertsub" style="margin-top:12px">Resumen del BSC del período seleccionado; no incluye indicadores simulados de proyectos.</div>
      </div>''', unsafe_allow_html=True)
    proyectos = cargar('projects').copy()
    if not proyectos.empty and 'DiasAtraso' in proyectos.columns:
        atrasados = proyectos.loc[pd.to_numeric(proyectos['DiasAtraso'], errors='coerce') > 0].copy()
        if not atrasados.empty:
            atrasados['DiasAtraso'] = pd.to_numeric(atrasados['DiasAtraso'],errors='coerce')
            items = ''.join(
                f'<div class="op10-alertrow"><div class="op10-rowtop"><span class="op10-alerttext">{e(r.get("NombreProyecto"))}</span>'
                f'<b style="color:{ROJO}">{int(r["DiasAtraso"])} días</b></div></div>'
                for _,r in atrasados.sort_values('DiasAtraso',ascending=False).head(3).iterrows()
            )
            st.markdown('<div class="op10-alert" style="min-height:0;margin-top:12px">'
                        '<div class="op10-alerttitle">' + op_icono('clock') + 'Proyectos con atraso · Referencia simulada</div>'
                        +items+'</div>',unsafe_allow_html=True)
    st.caption('Los datos de plazos de proyectos son simulados y corresponden a la cartera general.')

# Tabla con diseño uniforme de Administración e Ingeniería.
st.markdown('<div class="op10-section">' + op_icono('table') + 'Consultar indicadores del área</div>', unsafe_allow_html=True)
a, b, c = st.columns([1.1, 0.9, 1.25], gap='medium')
with a:
    frente_sel = st.selectbox('Frente', ['Todos'] + FRENTES + ['Indicadores transversales'], key='ops10_frente')
with b:
    estado_sel = st.selectbox('Semáforo', ['Todos', 'Meta alcanzada', 'En progreso', 'Bajo cumplimiento', 'Sin datos'], key='ops10_estado')
with c:
    buscar = st.text_input('Buscar KPI', placeholder='Buscar por nombre', key='ops10_buscar')
consulta = df.copy()
if frente_sel != 'Todos':
    consulta = consulta[consulta['Frente'].eq(frente_sel)]
if estado_sel != 'Todos':
    consulta = consulta[consulta['Cumplimiento'].map(estado).eq(estado_sel)]
if buscar.strip():
    consulta = consulta[consulta['NombreKPI'].str.contains(buscar.strip(), case=False, regex=False, na=False)]
if consulta.empty:
    st.info('No se encontraron indicadores con esos filtros.')
else:
    rows = []
    exportar = []
    for _, f in consulta.sort_values(['Ponderacion','NombreKPI'], ascending=[False,True], na_position='last').iterrows():
        v = f['Cumplimiento']
        co = color(v)
        res, meta = valor_bsc(f), valor_bsc(f, True)
        responsable = limpio(f.get('NombreResponsable')) or '—'
        peso = local(f.get('Ponderacion'), 1)
        rows.append('<tr>'
            f'<td class="op-center"><span class="op-table-dot" style="background:{co}" title="{e(estado(v))}"></span></td>'
            f'<td>{e(f["NombreKPI"])}</td><td>{e(f["CategoriaKPI"])}</td>'
            f'<td>{e(meta)}</td><td>{e(res)}</td>'
            f'<td><div class="op-progress"><div class="op-progress-bg"><span style="background:{co};width:{barra(v)}"></span></div>'
            f'<b style="color:{co}">{e(pct(v))}</b></div></td>'
            f'<td>{e(responsable)}</td><td>{e(peso)}</td></tr>')
        exportar.append({'Estado': estado(v), 'KPI':f['NombreKPI'], 'Categoría':f['CategoriaKPI'],
            'Meta anual':meta,'Actual':res,'Cumplimiento':pct(v),'Resp.':responsable,'Peso':peso})
    st.markdown('<div class="op-table-scroll"><table class="op-table"><thead><tr>'
        '<th>Estado</th><th>KPI</th><th>Categoría</th><th>Meta anual</th><th>Actual</th>'
        '<th>Cumplimiento</th><th>Resp.</th><th>Peso</th></tr></thead><tbody>'
        + ''.join(rows) + '</tbody></table></div>', unsafe_allow_html=True)
    st.download_button('⬇️ Exportar indicadores filtrados (CSV)',
        data=pd.DataFrame(exportar).to_csv(index=False, sep=';').encode('utf-8-sig'),
        file_name='maas_operaciones_kpi.csv', mime='text/csv', key='ops10_exportar')

