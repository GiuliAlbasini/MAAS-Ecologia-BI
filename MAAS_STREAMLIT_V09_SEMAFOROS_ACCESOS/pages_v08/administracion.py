# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import math
import unicodedata

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from maas_datos import cargar, _conexion
from maas_ui import metricas, presentacion_valor, recortar_bsc

VERDE = '#50A374'
AMARILLO = '#E7B23E'
ROJO = '#D35B5B'
GRIS = '#9DAFC2'
AZUL = '#1C324F'
FONDO = '#F5F7FB'

TONOS = {
    'Cumple': VERDE,
    'En riesgo': AMARILLO,
    'No cumple': ROJO,
    'Sin datos': GRIS,
}

MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
         'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def numero(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else float('nan')
    except (TypeError, ValueError, OverflowError):
        return float('nan')


def texto(v):
    if v is None:
        return '—'
    try:
        if pd.isna(v):
            return '—'
    except (TypeError, ValueError):
        pass
    return html.escape(str(v), quote=True)


def normalizar(v):
    s = unicodedata.normalize('NFKD', str(v or ''))
    return ''.join(ch for ch in s if not unicodedata.combining(ch)).casefold().strip()


def cifra(v, dec=1):
    n = numero(v)
    if not math.isfinite(n):
        return '—'
    return f'{n:,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def porcentaje(v, dec=1):
    n = numero(v)
    return (f'{n*100:.{dec}f}'.replace('.', ',') + '%') if math.isfinite(n) else '—'


def clp(v):
    n = numero(v)
    return '$' + f'{round(n):,}'.replace(',', '.') if math.isfinite(n) else '—'


def estado(v):
    n = numero(v)
    if not math.isfinite(n):
        return 'Sin datos'
    if n >= 1:
        return 'Cumple'
    if n >= 0.70:
        return 'En riesgo'
    return 'No cumple'


def color_estado(v):
    return TONOS[estado(v)]


def ancho(v):
    n = numero(v)
    return min(100.0, max(0.0, n * 100)) if math.isfinite(n) else 0.0


def valor_kpi(fila, meta=False):
    n = fila.get('MetaNumerica' if meta else 'ResultadoNumerico')
    t = fila.get('MetaTexto' if meta else 'ResultadoTexto')
    unidad = normalizar(fila.get('UnidadMedida', ''))
    if math.isfinite(numero(n)) and 'miles' in unidad and ('clp' in unidad or '$' in unidad):
        return clp(numero(n) * 1000)
    return presentacion_valor(n, t, fila.get('UnidadMedida'))


def foco(fila):
    nombre = normalizar(fila.get('NombreKPI'))
    cat = normalizar(fila.get('CategoriaKPI'))
    if (cat in ('finanzas', 'contab', 'ventas') or
            any(t in nombre for t in ('quiebre', 'caja', 'margen', 'venta', 'costo',
                                      'factura', 'presupuesto', 'financ', 'contrato',
                                      'productividad'))):
        return 'Finanzas y control'
    if (cat in ('personas', 'recursos humanos') or
            any(t in nombre for t in ('capacita', 'colaborador', 'vacacion', 'personas',
                                      'salari', 'personal', 'accidente'))):
        return 'Personas y capacitación'
    return 'Procesos y gestión'


def fecha_breve(f):
    f = pd.to_datetime(f, errors='coerce')
    if pd.isna(f):
        return 'Sin fecha'
    return f'{int(f.day):02d} {MESES[int(f.month)-1]} {int(f.year)}'



# Iconos decorativos SVG: no modifican los resultados ni el funcionamiento del tablero.
_ICONOS_ADM = {
    'casco': '<path d="M3 18h18M5 18v-3a7 7 0 0 1 14 0v3M12 8v6M8 9.5V13M16 9.5V13"/>',
    'dinero': '<circle cx="12" cy="12" r="9"/><path d="M15.2 8.5c-1.2-1.3-5.2-1.4-6.2.4-1.6 3 6.8 2.4 6 5.3-.7 2.4-5 2.4-6.3 1.1M12 5.5v13"/>',
    'personas': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    'formacion': '<path d="m2 10 10-5 10 5-10 5-10-5ZM6 12v5c3.5 2.7 8.5 2.7 12 0v-5M22 10v6"/>',
    'documento': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h8"/>',
    'factura': '<path d="M5 2h14v20l-3-2-4 2-4-2-3 2V2ZM8 8h8M8 12h8M8 16h5"/>',
    'caja': '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M7 7V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2M3 13h18M10 13v2h4v-2"/>',
    'grafico': '<path d="M3 3v18h18M7 15l4-4 3 2 6-7"/>',
    'objetivo': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'proceso': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><path d="M10 6.5h4M17.5 10v4M3 17h7M6.5 14v6"/>',
    'escudo': '<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/>',
    'calendario': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
    'reloj': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'usuarios': '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    'busqueda': '<circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/>',
    'edificio': '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 7h2M14 7h2M9 11h2M14 11h2M9 15h2M14 15h2M10 21v-4h4v4"/>',
    'corazon': '<path d="M20.8 5.6a5.5 5.5 0 0 0-7.8 0l-1 1-1-1a5.5 5.5 0 1 0-7.8 7.8L12 22l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
}


def icono_admin(nombre, titulo=None):
    if titulo is not None:
        n = normalizar(titulo)
        reglas = [
            (('accident', 'seguridad', 'siniestr', 'lesion'), 'casco'),
            (('margen', 'ebit', 'rentabil', 'utilidad'), 'dinero'),
            (('caja', 'liquidez', 'quiebre'), 'caja'),
            (('factur', 'documento tributario'), 'factura'),
            (('capacit', 'formacion', 'entrenam'), 'formacion'),
            (('salari', 'remuner', 'nomina', 'sueldo'), 'personas'),
            (('colaborad', 'personal', 'dotacion', 'equipo humano'), 'personas'),
            (('cliente', 'csat', 'satisfacc'), 'corazon'),
            (('contrat', 'licitac'), 'documento'),
            (('certific', 'auditor', 'cumplimiento norm'), 'escudo'),
            (('plazo', 'tiempo', 'dias', 'oportunidad', 'atras'), 'reloj'),
            (('presupuest', 'costo', 'gasto', 'precio', 'financ'), 'dinero'),
            (('venta', 'ingreso', 'crecim'), 'grafico'),
            (('productividad', 'eficiencia', 'proceso', 'gestion'), 'proceso'),
        ]
        nombre = next((ico for palabras, ico in reglas if any(k in n for k in palabras)), nombre)
    ruta = _ICONOS_ADM.get(nombre, _ICONOS_ADM['objetivo'])
    return ('<span class="ad-icon" aria-hidden="true"><svg viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="1.8" '
            'stroke-linecap="round" stroke-linejoin="round">' + ruta + '</svg></span>')

def tarjeta_resumen(label, value, sub, tono):
    return f'''
    <div class="ad-card" style="--line:{tono}">
      <div class="ad-label">{texto(label)}</div>
      <div class="ad-value">{texto(value)}</div>
      <div class="ad-sub">{texto(sub)}</div>
    </div>
    '''


def tarjeta_kpi(row):
    c = color_estado(row.get('Cumplimiento'))
    return f'''
    <div class="ad-kpi-card" style="--line:{c}">
      <div class="ad-kpi-name">{icono_admin("objetivo", row['NombreKPI'])}{texto(row['NombreKPI'])}</div>
      <div class="ad-kpi-big">{texto(valor_kpi(row))}</div>
      <div class="ad-kpi-meta">Meta: {texto(valor_kpi(row, True))}</div>
      <div class="ad-track"><span style="width:{ancho(row.get('Cumplimiento')):.1f}%;background:{c};"></span></div>
      <div class="ad-kpi-foot"><span>{texto(estado(row.get('Cumplimiento')))}</span><span>{texto(porcentaje(row.get('Cumplimiento')))}</span></div>
    </div>
    '''


def fila_kpi(row):
    c = color_estado(row.get('Cumplimiento'))
    return f'''
    <div class="ad-row-item">
      <div class="ad-row-top">
        <span class="ad-row-name">{icono_admin("objetivo", row['NombreKPI'])}{texto(row['NombreKPI'])}</span>
        <span class="ad-row-pct" style="color:{c};">{texto(porcentaje(row.get('Cumplimiento')))}</span>
      </div>
      <div class="ad-row-sub">Resultado: {texto(valor_kpi(row))} · Meta: {texto(valor_kpi(row, True))}</div>
      <div class="ad-track"><span style="width:{ancho(row.get('Cumplimiento')):.1f}%;background:{c};"></span></div>
    </div>
    '''


def bloque(nombre, filas):
    filas = filas.sort_values('Ponderacion', ascending=False, na_position='last')
    if filas.empty:
        interior = '<div class="ad-empty">No hay KPI en este grupo.</div>'
    else:
        interior = ''.join(fila_kpi(r) for _, r in filas.head(4).iterrows())
    return f'''
    <div class="ad-panel">
      <div class="ad-panel-title"><span>{icono_admin("dinero" if "Finanzas" in nombre else "personas" if "Personas" in nombre else "proceso")}{texto(nombre)}</span><span class="ad-mini">{len(filas)} KPI</span></div>
      {interior}
    </div>
    '''


def badge_estado(v):
    c = color_estado(v)
    return f'<span class="ad-badge" style="background:{c}15;color:{c};border-color:{c}35;">{texto(estado(v))}</span>'


def barra_html(v):
    c = color_estado(v)
    return (
        f'<div class="ad-barcell">'
        f'<div class="ad-bar-bg"><div class="ad-bar-fill" style="width:{ancho(v):.1f}%;background:{c};"></div></div>'
        f'<span style="color:{c};font-weight:800;">{texto(porcentaje(v))}</span>'
        f'</div>'
    )


def punto_estado(v):
    c = color_estado(v)
    return f'<div class="ad-state" title="{texto(estado(v))}" aria-label="{texto(estado(v))}"><span class="ad-dot" style="--dot-color:{c};" aria-hidden="true"></span></div>'


def tabla_html(df):
    if df.empty:
        return '<div class="ad-empty">No hay KPI para los filtros seleccionados.</div>'
    filas = []
    for _, r in df.iterrows():
        filas.append(
            '<tr>'
            f'<td>{punto_estado(r.get("Cumplimiento"))}</td>'
            f'<td>{texto(r.get("NombreKPI"))}</td>'
            f'<td>{texto(r.get("Foco"))}</td>'
            f'<td>{texto(valor_kpi(r))}</td>'
            f'<td>{texto(valor_kpi(r, True))}</td>'
            f'<td>{barra_html(r.get("Cumplimiento"))}</td>'
            f'<td>{texto(cifra(r.get("Ponderacion"), 1))}</td>'
            f'<td>{texto(r.get("NombreResponsable") or "—")}</td>'
            '</tr>'
        )
    return (
        '<div class="ad-table-wrap"><table class="ad-table">'
        '<thead><tr>'
        '<th>Estado</th><th>KPI</th><th>Ámbito</th><th>Resultado</th><th>Meta</th>'
        '<th>Cumplimiento</th><th>Peso</th><th>Resp.</th>'
        '</tr></thead><tbody>' + ''.join(filas) + '</tbody></table></div>'
    )


CSS = '''
<style>
.ad-icon{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;min-width:28px;margin-right:8px;vertical-align:middle;border-radius:9px;background:#edf4ff;color:#326bce;flex-shrink:0}
.ad-icon svg{width:17px;height:17px;display:block}
.ad-kpi-name .ad-icon,.ad-row-name .ad-icon,.ad-card-round-head .ad-icon,.ad-table td .ad-icon{width:25px;height:25px;min-width:25px;border-radius:8px;margin-right:7px}
.ad-kpi-name .ad-icon svg,.ad-row-name .ad-icon svg,.ad-card-round-head .ad-icon svg,.ad-table td .ad-icon svg{width:15px;height:15px}
.ad-title .ad-icon{width:36px;height:36px;min-width:36px;border-radius:12px}
.ad-title .ad-icon svg{width:21px;height:21px}

.ad-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin:6px 0 14px}
.ad-title{font-size:2.05rem;font-weight:850;color:#1C324F;letter-spacing:-.03em;line-height:1.08}
.ad-subtitle{font-size:1rem;color:#6F8198;margin-top:4px}
.ad-date{padding:10px 14px;border:1px solid #DEE6EE;background:#fff;border-radius:14px;color:#48617D;font-size:.84rem;font-weight:750}
.ad-filter-box{background:#fff;border:1px solid #DFE7F0;border-radius:16px;padding:14px 16px 4px;margin:0 0 18px 0;box-shadow:0 2px 8px rgba(22,42,70,.03)}
.ad-card{background:#fff;border:1px solid #DDE6EF;border-left:5px solid var(--line);border-radius:16px;padding:18px 17px;min-height:130px;box-shadow:0 2px 6px rgba(23,46,72,.025)}
.ad-label{font-size:.85rem;color:#5A6F87;font-weight:730;line-height:1.3}
.ad-value{color:#1D3552;font-size:2.15rem;font-weight:870;letter-spacing:-.03em;margin:10px 0 6px}
.ad-sub{font-size:.78rem;color:#788DA3;line-height:1.45}
.ad-section{font-size:1.15rem;font-weight:830;color:#203853;margin:26px 0 12px}
.ad-kpi-card{background:#fff;border:1px solid #DFE7F0;border-left:5px solid var(--line);border-radius:16px;padding:17px;min-height:188px}
.ad-kpi-name{font-size:.84rem;font-weight:790;color:#364E67;line-height:1.35;min-height:40px}
.ad-kpi-big{font-size:1.9rem;font-weight:850;letter-spacing:-.02em;color:#1D3552;margin:14px 0 6px}
.ad-kpi-meta{font-size:.76rem;color:#7D8DA1;margin-bottom:12px}
.ad-track{height:8px;border-radius:40px;background:#E9EFF4;overflow:hidden}
.ad-track span{display:block;height:100%;border-radius:40px}
.ad-kpi-foot{display:flex;justify-content:space-between;gap:8px;font-size:.74rem;font-weight:800;margin-top:10px;color:var(--line)}
.ad-panel{background:#fff;border:1px solid #DFE7F0;border-radius:16px;padding:18px 19px;min-height:260px}
.ad-panel-title{display:flex;justify-content:space-between;gap:10px;align-items:center;font-size:.97rem;font-weight:820;color:#233B55;margin-bottom:12px}
.ad-mini{color:#667D93;font-size:.74rem;font-weight:700}
.ad-row-item{padding:0 0 11px 0;border-bottom:1px solid #EEF1F5;margin-bottom:11px}
.ad-row-item:last-child{border-bottom:0;margin-bottom:0;padding-bottom:0}
.ad-row-top{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.ad-row-name{font-size:.83rem;font-weight:760;color:#2A415B;line-height:1.35}
.ad-row-pct{font-size:.82rem;font-weight:830;white-space:nowrap}
.ad-row-sub{font-size:.72rem;color:#8291A2;margin:4px 0 8px;line-height:1.4}
.ad-empty{font-size:.84rem;color:#8291A2;padding:14px 0}
.ad-note{font-size:.78rem;color:#8091A2;line-height:1.55}
.ad-badge{display:inline-block;padding:5px 10px;border-radius:999px;font-size:.74rem;font-weight:800;border:1px solid #ddd}
.ad-state{display:flex;align-items:center;justify-content:flex-start;min-height:20px}
.ad-dot{width:16px;height:16px;flex-shrink:0;border-radius:50%;display:inline-block;background:radial-gradient(circle at 30% 27%,color-mix(in srgb,var(--dot-color) 52%,white),var(--dot-color) 72%);box-shadow:inset 0 0 1px rgba(0,0,0,.08)}
.ad-barcell{display:flex;align-items:center;gap:10px;min-width:220px}
.ad-bar-bg{height:10px;flex:1;background:#E9EFF4;border-radius:999px;overflow:hidden}
.ad-bar-fill{height:100%;border-radius:999px}
.ad-table-wrap{background:#fff;border:1px solid #DFE7F0;border-radius:16px;overflow:auto}
 table.ad-table{width:100%;border-collapse:collapse;font-size:.84rem}
 .ad-table thead th{position:sticky;top:0;background:#F8FAFD;color:#51677F;text-align:left;font-weight:800;padding:12px 14px;border-bottom:1px solid #E5EDF5;white-space:nowrap}
 .ad-table tbody td{padding:12px 14px;border-bottom:1px solid #EEF2F7;vertical-align:middle;color:#233B55}
 .ad-table tbody tr:hover{background:#FBFCFE}
 .ad-table th:first-child,.ad-table td:first-child{width:78px;min-width:78px;max-width:78px;padding-left:18px;padding-right:12px}
.ad-executive{background:#fff;border:1px solid #DEE7F2;border-radius:18px;padding:20px 22px;min-height:365px;box-shadow:0 3px 10px rgba(20,45,75,.035)}
.ad-ex-title{font-size:1rem;font-weight:820;color:#1E3453;margin-bottom:12px}
.ad-ringwrap{display:flex;align-items:center;justify-content:center;gap:20px;flex-wrap:wrap;margin:22px 0}
.ad-ring{width:188px;height:188px;border-radius:100%;background:conic-gradient(var(--c) 0 var(--p),#E8EDF5 var(--p) 100%);display:grid;place-items:center;flex-shrink:0}
.ad-ring-inner{width:136px;height:136px;border-radius:100%;background:white;display:grid;place-items:center;color:#1C324F;font-size:2rem;font-weight:900}
.ad-ringfacts{min-width:175px;color:#657B94;font-size:.84rem;line-height:2.05}
.ad-ringfacts b{color:#1C324F}
.ad-ringfact{display:flex;justify-content:space-between;gap:16px}
.ad-card-round{background:#fff;border:1px solid #DEE7F2;border-radius:17px;padding:17px 17px;min-height:213px;box-shadow:0 2px 7px rgba(20,40,65,.025)}
.ad-card-round-head{font-size:.83rem;color:#556A87;font-weight:780;min-height:42px}
.ad-card-round-flex{display:flex;justify-content:space-between;gap:8px;align-items:center;margin:10px 0}
.ad-card-round-value{font-size:1.35rem;color:#172E50;font-weight:900}
.ad-card-round-desc{font-size:.72rem;color:#7788A0;line-height:1.5}
.ad-smallring{width:76px;height:76px;border-radius:50%;background:conic-gradient(var(--c) 0 var(--p),#E8EDF5 var(--p) 100%);display:grid;place-items:center;flex-shrink:0}
.ad-smallhole{width:56px;height:56px;border-radius:50%;background:white;display:grid;place-items:center;font-size:.78rem;font-weight:850;color:#1C324F}
.ad-card-round-footer{margin-top:9px;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.ad-state-pill{font-size:.72rem;font-weight:780;color:white;padding:4px 10px;border-radius:16px}
.ad-peso-pill{font-size:.72rem;font-weight:750;background:#EDF2FA;color:#56718B;border-radius:16px;padding:4px 9px}
.ad-summary-areas{font-size:.77rem;color:#75889E;margin-top:5px}
.st-key-adm_barra_filtros{background:white;border:1px solid #DEE7F2;padding:13px 16px 4px;border-radius:16px;margin-bottom:16px}
</style>
'''

st.markdown(CSS, unsafe_allow_html=True)
st.markdown('''
<style>
.st-key-ing_filtros_blancos, .st-key-adm_filtros_blancos {background:#FFFFFF!important;border:1px solid #DFE7F0!important;border-radius:17px!important;padding:16px 20px 10px!important;box-shadow:0 2px 10px rgba(20,42,77,.045)!important;margin:8px 0 16px!important;}
.st-key-ing_filtros_blancos [data-testid="stSelectbox"] [data-baseweb="select"]>div,
.st-key-adm_filtros_blancos [data-testid="stSelectbox"] [data-baseweb="select"]>div,
.st-key-adm_filtros_blancos [data-testid="stTextInput"] [data-baseweb="input"] {background:#fff!important;border:1px solid #E0E8F1!important;border-radius:11px!important;}
.st-key-ing_filtros_blancos [data-testid="stSelectbox"] [data-baseweb="select"]>div *,
.st-key-adm_filtros_blancos [data-testid="stSelectbox"] [data-baseweb="select"]>div * {background:transparent!important;}
</style>
''', unsafe_allow_html=True)

# Ajuste exclusivamente visual de filtros: fondo blanco como Inicio y Gerencia.
st.markdown("""<style>
/* El selector no hereda el fondo gris del tema; conserva tamaños y ubicación. */
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] [data-baseweb="select"] > div:first-child,
[data-testid="stTextInput"] [data-baseweb="input"] > div,
[data-testid="stTextInput"] input {
    background-color:#FFFFFF !important;
    border-color:#DFE7F0 !important;
    color:#1C324F !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
    border:1px solid #DFE7F0 !important;
    border-radius:12px !important;
    box-shadow:0 1px 3px rgba(20,42,77,.025) !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
[data-testid="stTextInput"] [data-baseweb="input"] > div:hover {
    border-color:#B6C8E2 !important;
}
[data-testid="stSelectbox"] label p,
[data-testid="stTextInput"] label p {color:#304762 !important;}
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=90, show_spinner=False)
def responsables_oficiales_bsc():
    """Responsables registrados en las mediciones oficiales BSC de SQL.

    Consulta de solo lectura. No se asignan nombres por similitud de categoría.
    """
    con = _conexion()
    try:
        return pd.read_sql_query("""
            WITH Ultimos AS (
                SELECT fe.Fecha, k.CodigoKPI, k.NombreKPI,
                       r.NombreResponsable, f.Ambito, a.NombreArea,
                       ROW_NUMBER() OVER (
                           PARTITION BY f.Fecha_Key, f.KPI_Key, f.Ambito,
                                        f.Area_Key, f.GranoTemporal
                           ORDER BY f.CargaID DESC, f.Medicion_Key DESC
                       ) AS rn
                FROM dbo.FACT_KPI_ESTRATEGICO f
                JOIN dbo.DIM_KPI k ON k.KPI_Key = f.KPI_Key
                JOIN dbo.DIM_FECHA fe ON fe.Fecha_Key = f.Fecha_Key
                LEFT JOIN dbo.DIM_RESPONSABLE r ON r.Responsable_Key = f.Responsable_Key
                LEFT JOIN dbo.DIM_AREA a ON a.Area_Key = f.Area_Key
                WHERE f.FuenteResultado = 'BSC'
                  AND k.TipoIndicador = 'OFICIAL_BSC'
            )
            SELECT Fecha, CodigoKPI, NombreKPI, NombreResponsable,
                   Ambito, NombreArea
            FROM Ultimos WHERE rn = 1
        """, con)
    finally:
        con.close()


def incorporar_responsables_administracion(datos):
    """Conservar el responsable directo y completar solo coincidencias inequívocas.

    Orden: código+fecha del área; código+fecha global; nombre+fecha global.
    Un valor literal 'Todos' no es el nombre de un responsable.
    """
    salida = datos.copy()
    if 'NombreResponsable' not in salida:
        salida['NombreResponsable'] = pd.NA
    salida['NombreResponsable'] = salida['NombreResponsable'].astype('string').str.strip()
    salida['NombreResponsable'] = salida['NombreResponsable'].mask(
        salida['NombreResponsable'].fillna('').str.casefold().isin(
            ['', 'todos', 'sin responsable', 'nan', 'none', '—']))
    try:
        fuentes = responsables_oficiales_bsc()
    except Exception as error:
        st.warning(f'No se pudo consultar la asignación de responsables del BSC: {error}')
        salida['NombreResponsable'] = salida['NombreResponsable'].fillna('Sin responsable registrado')
        return salida

    if fuentes.empty:
        salida['NombreResponsable'] = salida['NombreResponsable'].fillna('Sin responsable registrado')
        return salida

    fuentes['Fecha'] = pd.to_datetime(fuentes['Fecha'], errors='coerce').dt.normalize()
    fuentes['NombreResponsable'] = fuentes['NombreResponsable'].astype('string').str.strip()
    fuentes = fuentes.loc[~fuentes['NombreResponsable'].fillna('').str.casefold().isin(
        ['', 'todos', 'sin responsable', 'nan', 'none', '—'])].copy()
    fuentes['CodigoKPI'] = fuentes['CodigoKPI'].astype('string').fillna('').str.strip()
    fuentes['NombreNormalizado'] = fuentes['NombreKPI'].map(normalizar)
    salida['_fecha_resp'] = pd.to_datetime(salida['Fecha'], errors='coerce').dt.normalize()
    salida['_codigo_resp'] = salida.get('CodigoKPI', pd.Series('', index=salida.index)).astype('string').fillna('').str.strip()
    salida['_nombre_resp'] = salida['NombreKPI'].map(normalizar)

    def diccionario_univoco(tabla, claves):
        dic = {}
        for llave, grupo in tabla.groupby(claves, dropna=True):
            personas = grupo['NombreResponsable'].dropna().unique().tolist()
            if len(personas) == 1:
                dic[llave if isinstance(llave, tuple) else (llave,)] = personas[0]
        return dic

    ambito = fuentes['Ambito'].fillna('').astype(str).str.upper()
    area = fuentes['NombreArea'].map(normalizar)
    propios = fuentes.loc[ambito.eq('AREA') & area.str.contains('administra', regex=False)]
    globales = fuentes.loc[ambito.eq('GLOBAL')]
    mapas = [
        (diccionario_univoco(propios, ['Fecha', 'CodigoKPI']), '_codigo_resp'),
        (diccionario_univoco(globales, ['Fecha', 'CodigoKPI']), '_codigo_resp'),
        (diccionario_univoco(globales, ['Fecha', 'NombreNormalizado']), '_nombre_resp'),
    ]
    for i, fila in salida.iterrows():
        if pd.notna(fila['NombreResponsable']):
            continue
        for mapa, campo in mapas:
            identificador = fila[campo]
            if pd.isna(identificador) or not str(identificador):
                continue
            candidato = mapa.get((fila['_fecha_resp'], identificador))
            if candidato:
                salida.at[i, 'NombreResponsable'] = candidato
                break
    salida = salida.drop(columns=['_fecha_resp', '_codigo_resp', '_nombre_resp'])
    salida['NombreResponsable'] = salida['NombreResponsable'].fillna('Sin responsable registrado')
    return salida


# =========================
# DATOS
# =========================
datos_bsc = cargar('bsc')
base = recortar_bsc(datos_bsc, 'administracion')
if base.empty:
    st.title('Administración y Control')
    st.info('Todavía no hay indicadores del BSC para Administración y Control.')
    st.stop()

base = base.copy()
base['Fecha'] = pd.to_datetime(base['Fecha'], errors='coerce')
base['Cumplimiento'] = pd.to_numeric(base['Cumplimiento'], errors='coerce')
base['Ponderacion'] = pd.to_numeric(base['Ponderacion'], errors='coerce')
base['Foco'] = base.apply(foco, axis=1)
base = incorporar_responsables_administracion(base)

# Años visibles incluso si todavía no hay datos.
anios_data = sorted({int(a) for a in base['Fecha'].dropna().dt.year.unique().tolist()})
if anios_data:
    anio_min = min(anios_data + [2024])
    anio_max = max(anios_data + [2027])
    anios = list(range(anio_max, anio_min - 1, -1))
else:
    anios = [2027, 2026, 2025, 2024]

anio_default = 2026 if 2026 in anios else anios[0]

st.markdown(
    '<div class="ad-head">'
    f'<div><div class="ad-title">{icono_admin("edificio")}Administración y Control</div>'
    '<div class="ad-subtitle">Finanzas, personas y control de gestión</div></div>'
    '</div>',
    unsafe_allow_html=True
)

with st.container(key="adm_filtros_blancos", border=True):
    # Controles nativos Streamlit
    c1, c2, c3, c4, c5 = st.columns([0.9, 1.35, 1.1, 1.1, 1.1], gap='medium')
    with c1:
        anio_sel = st.selectbox('Año', anios, index=anios.index(anio_default), key='adm_anio')

    base_anio = base.loc[base['Fecha'].dt.year.eq(anio_sel)].copy()
    fechas = sorted(base_anio['Fecha'].dropna().dt.normalize().unique().tolist(), reverse=True)
    if fechas:
        etiquetas = [f'Más reciente ({fecha_breve(fechas[0])})'] + [fecha_breve(f) for f in fechas]
    else:
        etiquetas = ['Sin datos']

    with c2:
        periodo_sel = st.selectbox('Periodo (fecha de corte)', etiquetas, index=0, key='adm_periodo')
    with c3:
        focos = ['Todos', 'Finanzas y control', 'Personas y capacitación', 'Procesos y gestión']
        foco_sel = st.selectbox('Ámbito', focos, key='adm_foco')
    with c4:
        responsables = ['Todos'] + sorted(x for x in base_anio['NombreResponsable'].dropna().astype(str).unique().tolist() if x != 'Todos')
        resp_sel = st.selectbox('Responsable', responsables, key='adm_resp')
    with c5:
        semaforos = ['Todos', 'Cumple', 'En riesgo', 'No cumple', 'Sin datos']
        sem_sel = st.selectbox('Semáforo', semaforos, key='adm_semaforo')

    buscar = st.text_input('Buscar KPI', placeholder='Nombre del indicador...', key='adm_buscar')
    # Fin de filtros

if base_anio.empty:
    st.info(f'No hay datos para el año {anio_sel}. El filtro ya quedó listo para cuando cargues información de ese año.')

    st.stop()

# Filtrar por fecha de corte
fecha_sel = fechas[0] if periodo_sel.startswith('Más reciente') else pd.to_datetime(periodo_sel, format='%d %b %Y', errors='coerce')
# fallback robusto por etiqueta localizada
if pd.isna(fecha_sel):
    # reconstruir buscando etiqueta exacta
    mapa = {fecha_breve(f): f for f in fechas}
    fecha_sel = pd.to_datetime(mapa.get(periodo_sel, fechas[0]), errors='coerce')

view = base_anio.loc[base_anio['Fecha'].dt.normalize().eq(pd.to_datetime(fecha_sel).normalize())].copy()
view['EstadoVisual'] = view['Cumplimiento'].map(estado)
if foco_sel != 'Todos':
    view = view.loc[view['Foco'].eq(foco_sel)].copy()
if resp_sel != 'Todos':
    view = view.loc[view['NombreResponsable'].astype(str).eq(resp_sel)].copy()
if sem_sel != 'Todos':
    view = view.loc[view['EstadoVisual'].eq(sem_sel)].copy()
if buscar.strip():
    view = view.loc[view['NombreKPI'].astype(str).str.contains(buscar.strip(), case=False, regex=False, na=False)].copy()
if view.empty:
    st.info('No hay KPI para los filtros seleccionados.')
    st.stop()


# Filtros para tabla y algunas secciones secundarias
vista = view.copy()
if foco_sel != 'Todos':
    vista = vista.loc[vista['Foco'].eq(foco_sel)]
if resp_sel != 'Todos':
    vista = vista.loc[vista['NombreResponsable'].astype(str).eq(resp_sel)]
if sem_sel != 'Todos':
    vista = vista.loc[vista['EstadoVisual'].eq(sem_sel)]
if buscar.strip():
    vista = vista.loc[vista['NombreKPI'].astype(str).str.contains(buscar.strip(), case=False, regex=False, na=False)]

# Resumen principal con la fecha/corte seleccionada.
indice = metricas(view)
evaluables = view[view['Cumplimiento'].notna()].copy()
cumplen = int((evaluables['Cumplimiento'] >= 1).sum())
riesgo = int(((evaluables['Cumplimiento'] >= 0.70) & (evaluables['Cumplimiento'] < 1)).sum())
alertas = int((evaluables['Cumplimiento'] < 0.70).sum())
sin_datos = len(view) - len(evaluables)

# Distribución ejecutiva del diseño de referencia: anillo + gráfico.
st.markdown(f'<div class="ad-section">{icono_admin("edificio")}Cuadro de mando de Administración</div>', unsafe_allow_html=True)
col_anillo, col_graf = st.columns([0.9, 1.35], gap='medium')
with col_anillo:
    tono = color_estado(indice)
    p = ancho(indice)
    html_anillo = f"""
    <div class="ad-executive">
      <div class="ad-ex-title">{icono_admin("objetivo")}Cumplimiento Administración</div>
      <div class="ad-ringwrap">
        <div class="ad-ring" style="--c:{tono};--p:{p:.1f}%"><div class="ad-ring-inner">{texto(porcentaje(indice,0))}</div></div>
        <div class="ad-ringfacts">
          <div>{badge_estado(indice)}</div>
          <div class="ad-ringfact"><span>🟢 Cumple</span><b>{cumplen}</b></div>
          <div class="ad-ringfact"><span>🟡 En riesgo</span><b>{riesgo}</b></div>
          <div class="ad-ringfact"><span>🔴 No cumple</span><b>{alertas}</b></div>
          <div class="ad-ringfact"><span>⚪ Sin datos</span><b>{sin_datos}</b></div>
        </div>
      </div>
      <div class="ad-summary-areas">Promedio ponderado de los KPI evaluables del área</div>
    </div>
    """
    st.markdown(html_anillo, unsafe_allow_html=True)
with col_graf:
    with st.container(border=True):
        st.markdown('**📊 ¿Cómo vamos en los KPI que cuentan para Administración?**')
        tab1, tab2 = st.tabs(['📈 Avance real vs. esperado', '🎯 Qué KPI restan más puntos'])
        top = view.loc[(view['Ponderacion'] > 0) & view['Cumplimiento'].notna()].copy()
        top = top.sort_values('Ponderacion', ascending=False).head(8)
        with tab1:
            if top.empty:
                st.info('No hay indicadores evaluables para el gráfico.')
            else:
                t = top.iloc[::-1].copy()
                t['Avance (%)'] = t['Cumplimiento'].clip(lower=0, upper=1.25) * 100
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=t['Avance (%)'], y=t['NombreKPI'], orientation='h',
                    marker_color=[color_estado(v) for v in t['Cumplimiento']],
                    hovertemplate='%{y}: %{x:.0f}%<extra></extra>', showlegend=False))
                fig.add_vline(x=100, line_color='#203853', line_width=2)
                fig.update_layout(height=320, margin=dict(l=8,r=12,t=10,b=30),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(range=[0,130], ticksuffix='%', gridcolor='#E9EEF5', zeroline=False),
                    yaxis=dict(tickfont=dict(size=10), automargin=True),
                    bargap=.34, font=dict(color='#6F8198'))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar':False})
        with tab2:
            faltantes = view.loc[(view['Ponderacion'] > 0) & view['Cumplimiento'].notna()].copy()
            faltantes['Brecha'] = (1-faltantes['Cumplimiento'].clip(lower=0, upper=1)) * faltantes['Ponderacion']
            faltantes = faltantes.sort_values('Brecha', ascending=False).head(8).iloc[::-1]
            if faltantes.empty:
                st.info('Sin brechas ponderadas para este corte.')
            else:
                fig = go.Figure(go.Bar(x=faltantes['Brecha'], y=faltantes['NombreKPI'],
                    orientation='h', marker_color=ROJO, showlegend=False))
                fig.update_layout(height=320, margin=dict(l=8,r=12,t=10,b=30),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(title='Puntos de impacto', gridcolor='#E9EEF5'),
                    yaxis=dict(tickfont=dict(size=10), automargin=True))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar':False})

st.markdown(f'<div class="ad-section">{icono_admin("objetivo")}KPI propios del área (de mayor a menor peso)</div>', unsafe_allow_html=True)
propios = view.sort_values('Ponderacion', ascending=False, na_position='last').head(8)
for comienzo in range(0, len(propios), 4):
    cols = st.columns(4, gap='medium')
    for col, (_, fila) in zip(cols, propios.iloc[comienzo:comienzo+4].iterrows()):
        with col:
            c = color_estado(fila.get('Cumplimiento'))
            st.markdown(f"""
            <div class="ad-card-round">
              <div class="ad-card-round-head">{icono_admin("objetivo", fila['NombreKPI'])}{texto(fila['NombreKPI'])}</div>
              <div class="ad-card-round-flex">
                <div><div class="ad-card-round-value">{texto(valor_kpi(fila))}</div>
                <div class="ad-card-round-desc">Meta anual: {texto(valor_kpi(fila,True))}<br>Avance de la meta: {texto(porcentaje(fila.get('Cumplimiento')))}</div></div>
                <div class="ad-smallring" style="--c:{c};--p:{ancho(fila.get('Cumplimiento')):.1f}%"><div class="ad-smallhole">{texto(porcentaje(fila.get('Cumplimiento'),0))}</div></div>
              </div>
              <div class="ad-card-round-footer"><span class="ad-state-pill" style="background:{c};">{texto(estado(fila.get('Cumplimiento')))}</span><span class="ad-peso-pill">Peso {texto(cifra(fila.get('Ponderacion'),0))}</span></div>
            </div>""", unsafe_allow_html=True)

# Control por ámbito
st.markdown(f'<div class="ad-section">{icono_admin("proceso")}Control por ámbito de gestión</div>', unsafe_allow_html=True)
cols = st.columns(3, gap='medium')
for col, nombre in zip(cols, ['Finanzas y control', 'Personas y capacitación', 'Procesos y gestión']):
    with col:
        st.markdown(bloque(nombre, view[view['Foco'].eq(nombre)]), unsafe_allow_html=True)

# Tabla filtrable
st.markdown(f'<div class="ad-section">{icono_admin("busqueda")}Consultar indicadores del área</div>', unsafe_allow_html=True)
st.markdown(tabla_html(vista.sort_values(['Ponderacion', 'NombreKPI'], ascending=[False, True])), unsafe_allow_html=True)

# KPI compartidos globales: se muestran separados de los propios del área.
try:
    globales = recortar_bsc(datos_bsc, 'gerencia').copy()
    globales['Fecha'] = pd.to_datetime(globales['Fecha'], errors='coerce')
    globales['Cumplimiento'] = pd.to_numeric(globales['Cumplimiento'], errors='coerce')
    globales['Ponderacion'] = pd.to_numeric(globales['Ponderacion'], errors='coerce')
    globales = globales.loc[globales['Fecha'].dt.year.eq(anio_sel)].copy()
    if not globales.empty:
        corte_global = globales['Fecha'].max()
        globales = globales.loc[globales['Fecha'].eq(corte_global)]
        nombres_compartidos = ['margen ebit', 'tasa de accidentes', 'ventas 2026',
                               'productividad salarial', 'csat contratos', 'nuevos clientes']
        escogidos = []
        for termino in nombres_compartidos:
            coincidencias = globales.loc[globales['NombreKPI'].map(normalizar).str.contains(termino, regex=False, na=False)]
            if not coincidencias.empty:
                escogidos.append(coincidencias.iloc[0])
        if escogidos:
            st.markdown(f'<div class="ad-section">{icono_admin("usuarios")}KPI compartidos de la empresa</div>', unsafe_allow_html=True)
            for inicio in range(0, len(escogidos), 4):
                cols = st.columns(4, gap='medium')
                for col, fila in zip(cols, escogidos[inicio:inicio+4]):
                    with col:
                        c = color_estado(fila.get('Cumplimiento'))
                        st.markdown(f"""
                        <div class="ad-card-round"><div class="ad-card-round-head">{icono_admin("objetivo", fila['NombreKPI'])}{texto(fila['NombreKPI'])}</div>
                        <div class="ad-card-round-flex"><div><div class="ad-card-round-value">{texto(valor_kpi(fila))}</div>
                        <div class="ad-card-round-desc">Meta anual: {texto(valor_kpi(fila, True))}</div></div>
                        <div class="ad-smallring" style="--c:{c};--p:{ancho(fila.get('Cumplimiento')):.1f}%"><div class="ad-smallhole">{texto(porcentaje(fila.get('Cumplimiento'),0))}</div></div></div>
                        <div class="ad-card-round-footer"><span class="ad-state-pill" style="background:{c};">{texto(estado(fila.get('Cumplimiento')))}</span><span class="ad-peso-pill">Peso {texto(cifra(fila.get('Ponderacion'),0))}</span></div></div>
                        """, unsafe_allow_html=True)
except (KeyError, TypeError, ValueError):
    pass

