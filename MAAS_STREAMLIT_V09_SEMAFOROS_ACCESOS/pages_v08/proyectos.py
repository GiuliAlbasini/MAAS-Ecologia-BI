# -*- coding: utf-8 -*-
"""MAAS ECOLOGÍA · Seguimiento de proyectos · Vista ETL actual con semáforo de plazo.

INSTALACIÓN: reemplazar SOLO pages_v08/proyectos.py.
Lee las consultas etl_proyectos y etl_tareas de maas_datos.py.
El semáforo usa fecha de término planificada frente al día actual de Chile.
No se infieren cierres ni atrasos contractuales sin datos reales.
"""
from __future__ import annotations

from html import escape
import math
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from maas_datos import cargar
from maas_ficha_proyectos_v2 import panel_ficha_proyecto

AZUL = '#234460'
VERDE = '#4EA276'
AMARILLO = '#E4B448'
ROJO = '#D45A62'
GRIS = '#92A3B7'
FONDO = '#EDF2F7'


def num(x):
    try:
        f = float(x)
        return f if math.isfinite(f) else float('nan')
    except (ValueError, TypeError):
        return float('nan')


def clp(x):
    v = num(x)
    return '$' + f'{round(v):,}'.replace(',', '.') if math.isfinite(v) else '—'


def entero(x):
    v = num(x)
    return f'{round(v):,}'.replace(',', '.') if math.isfinite(v) else '—'


def decimal(x, digits=1):
    v = num(x)
    if not math.isfinite(v):
        return '—'
    return f'{v:,.{digits}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def pc(x):
    v = num(x)
    return decimal(v * 100) + '%' if math.isfinite(v) else '—'


def fecha(x):
    v = pd.to_datetime(x, errors='coerce')
    return '—' if pd.isna(v) else v.strftime('%d/%m/%Y')


def normaliza(x):
    """Normaliza los filtros SIN modificar los datos originales guardados."""
    if x is None or pd.isna(x):
        return ''
    s = unicodedata.normalize('NFKD', str(x))
    s = ''.join(y for y in s if not unicodedata.combining(y))
    return ' '.join(s.upper().split())


def etiqueta_tipo(x):
    clave = normaliza(x)
    if clave == 'OPERACION':
        return 'OPERACIÓN'
    if clave == 'MONTAJE':
        return 'MONTAJE'
    return clave or 'SIN CLASIFICAR'


def etiqueta_estado(x):
    clave = normaliza(x)
    conocidos = {
        'EN EJECUCION': 'En ejecución', 'FINALIZADO': 'Finalizado',
        'POR INICIAR': 'Por iniciar', 'PENDIENTE': 'Pendiente',
    }
    return conocidos.get(clave, clave.capitalize() if clave else 'Sin estado')


def grupo_plazo(valor):
    x = normaliza(valor)
    if x in ('VENCIDO', 'FINALIZADO CON ATRASO'):
        return 'Fuera de plazo'
    if x == 'PENDIENTE VALIDAR CIERRE':
        return 'Cierre por verificar'
    if x == 'POR INICIAR':
        return 'Por iniciar'
    if x in ('DENTRO DE PLAZO', 'FINALIZADO EN PLAZO'):
        return 'En plazo'
    return 'Sin determinar'


def detalle_plazo(valor):
    x = normaliza(valor)
    nombres = {
        'VENCIDO': 'Vencido',
        'FINALIZADO CON ATRASO': 'Finalizado con atraso',
        'PENDIENTE VALIDAR CIERRE': 'Cierre por validar',
        'POR INICIAR': 'Por iniciar',
        'DENTRO DE PLAZO': 'Dentro de plazo',
        'FINALIZADO EN PLAZO': 'Finalizado en plazo',
    }
    return nombres.get(x, 'Sin determinar')


def color_plazo(grupo):
    return {'Fuera de plazo': ROJO, 'Cierre por verificar': AMARILLO,
            'En plazo': VERDE, 'Por iniciar': GRIS,
            'Sin determinar': GRIS}.get(grupo, GRIS)


def costo_estado(presupuesto, gastado):
    """Consumo del presupuesto. NO es % de avance ni rentabilidad."""
    p, g = num(presupuesto), num(gastado)
    if not math.isfinite(p) or p <= 0 or not math.isfinite(g):
        return 'Sin presupuesto', GRIS
    r = g / p
    if r > 1 + 1e-9:
        return 'Sobre presupuesto', ROJO
    if r >= .9:
        return 'Consumo elevado', AMARILLO
    return 'Dentro del presupuesto', VERDE


def html(x):
    return escape(str(x), quote=True)


# Iconos vectoriales integrados: no requieren instalar librerías.
ICONOS = {
    'folder': '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3z"/><path d="M3 11h18"/>',
    'money': '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M12 8v8M15 10c-.6-1-4.7-1-4.7.5s4.7 1 4.7 2.5-4.1 2-4.7.5"/>',
    'activity': '<path d="M3 12h4l3-6 4 12 3-6h4"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    'alert': '<path d="m12 3 10 18H2L12 3z"/><path d="M12 9v5m0 3v.4"/>',
    'chart': '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 16v-4m5 4V7m5 9v-6"/>',
    'pie': '<circle cx="12" cy="12" r="9"/><path d="M12 3v9h9"/>',
    'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
    'file': '<path d="M6 2h8l5 5v15H6z"/><path d="M14 2v6h5M9 13h7m-7 4h7"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    'users': '<circle cx="9" cy="8" r="3"/><path d="M3 19v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m1 4a5 5 0 0 1 4 5"/>',
    'filter': '<path d="M4 5h16l-6 7v6l-4 2v-8L4 5z"/>',
    'briefcase': '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
}

def icono(nombre, color='#326BC3', size=20):
    dibujo = ICONOS.get(nombre, ICONOS['folder'])
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="#326BC3" stroke-width="1.85" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{dibujo}</svg>')


def icono_metrica(nombre):
    n = normaliza(nombre)
    if 'presupuesto' in n and 'sobre' in n: return 'alert'
    if 'presupuesto' in n: return 'money'
    if 'costo' in n: return 'chart'
    if 'oc' in n or 'venta' in n: return 'money'
    if 'ejecucion' in n or 'hh' in n: return 'activity'
    if 'finalizado' in n: return 'check'
    if 'proyectos' in n: return 'folder'
    return 'chart'


def panel_metric(nombre, valor, nota, co=AZUL):
    return (
        f'<div class="pr10-metric" style="--co:{co}">'
        f'<div class="pr-pro-metrichead"><span class="pr-pro-icon" style="--accent:#326BC3">{icono(icono_metrica(nombre), co, 18)}</span>'
        f'<div class="pr10-mlabel">{html(nombre)}</div></div>'
        f'<div class="pr10-mvalue">{html(valor)}</div>'
        f'<div class="pr10-mnote">{html(nota)}</div></div>'
    )


def alertas_html(filas, modo='plazo'):
    if filas.empty:
        return '<div class="pr10-empty">Sin alertas de este tipo en el filtro actual.</div>'
    salida = []
    for _, r in filas.iterrows():
        if modo == 'plazo':
            sub = (f'{entero(r["DiasAtraso"])} días de atraso'
                   if math.isfinite(num(r['DiasAtraso'])) else 'Días por validar')
            sub += f' · Fecha prevista: {fecha(r["FechaTerminoPlanificada"])}'
            tag = r['PlazoTexto']
            col = ROJO if r['PlazoGrupo'] == 'Fuera de plazo' else AMARILLO
        else:
            sub = f'Presupuesto: {clp(r["CostoPresupuestado_CLP"])}'
            sub += f' · Gasto: {clp(r["CostoRealAcumulado_CLP"])}'
            tag = f'+{clp(r["DiferenciaCosto_CLP"])}'
            col = ROJO
        salida.append(
            '<div class="pr10-alertitem">'
            '<div class="pr10-alerttop">'
            f'<div class="pr10-alertname">{html(r["NombreProyecto"])}</div>'
            f'<span class="pr10-alertbadge" style="--co:{col}">{html(tag)}</span>'
            '</div>'
            f'<div class="pr10-alertsub">{html(sub)}</div></div>'
        )
    return ''.join(salida)


def plot_config(fig, height=300):
    fig.update_layout(
        height=height, margin=dict(l=6, r=12, t=8, b=8),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#57718A', size=12),
        showlegend=False,
    )
    return fig


CSS = '''<style>
.pr10-head{display:flex;justify-content:space-between;align-items:center;
  gap:14px;flex-wrap:wrap;margin:4px 0 17px}
.pr10-title{font-size:clamp(1.8rem,2.65vw,2.25rem);font-weight:860;
  color:#1C3452;letter-spacing:-.035em}
.pr10-sub{font-size:.86rem;color:#71879C;margin-top:5px}
.pr10-date{padding:10px 13px;border:1px solid #DDE6EE;border-radius:12px;
 background:#fff;color:#58728E;font-size:.77rem;font-weight:750}
.pr10-sec{color:#22415E;font-size:1.12rem;font-weight:830;margin:25px 0 10px}
.pr10-hint{color:#8295A7;font-size:.76rem;line-height:1.5;margin:0 0 13px}
.pr10-metric{border:1px solid #DEE7EF;border-left:5px solid var(--co);border-radius:15px;
 background:#fff;padding:18px 17px;min-height:130px;margin-bottom:7px;
 box-shadow:0 1px 3px rgba(18,49,82,.03)}
.pr10-mlabel{color:#627A91;font-size:.81rem;font-weight:790}
.pr10-mvalue{color:#1C3956;font-size:clamp(1.55rem,2.1vw,2.05rem);
 letter-spacing:-.025em;font-weight:870;margin:14px 0 6px;overflow-wrap:anywhere}
.pr10-mnote{color:#8A9BAA;font-size:.74rem;line-height:1.4}
.pr10-panel{border:1px solid #DFE7EF;background:#fff;border-radius:15px;
 padding:17px 18px;min-height:230px;margin-bottom:8px}
.pr10-panelname{color:#24415C;font-size:.93rem;font-weight:840;margin:0 0 10px}
.pr10-alertitem{padding:12px 0;border-bottom:1px solid #ECF0F4}
.pr10-alertitem:last-child{border-bottom:0;padding-bottom:2px}
.pr10-alerttop{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.pr10-alertname{font-size:.82rem;font-weight:770;color:#304C67;line-height:1.4;overflow-wrap:anywhere}
.pr10-alertbadge{font-size:.72rem;font-weight:820;color:var(--co);background:#F9F3F3;
 border-radius:30px;padding:4px 9px;white-space:nowrap}
.pr10-alertsub{font-size:.72rem;color:#8798A9;margin-top:5px;line-height:1.5}
.pr10-empty{font-size:.82rem;color:#8899A9;padding:22px 0}
.pr10-note{color:#71869C;font-size:.77rem;line-height:1.55;margin-top:4px}
.pr10-key{border:1px solid #DBE7F0;border-top:4px solid var(--co);
 background:#fff;padding:15px 17px;border-radius:14px;min-height:110px;margin-bottom:8px}
.pr10-keylabel{font-size:.78rem;color:#647B92;font-weight:780}
.pr10-keyval{font-size:1.35rem;color:#1D3954;font-weight:860;margin:8px 0 5px}
.pr10-keysub{font-size:.74rem;color:#8A99A8}

.pr11-rateline{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:9px 0 15px}
.pr11-rate{border:1px solid #DEE7EF;background:#FFF;border-radius:12px;padding:13px 14px;min-width:0}
.pr11-ratelabel{font-size:.78rem;color:#647B92;font-weight:780}
.pr11-ratevalue{font-size:1.35rem;color:#22415E;font-weight:840;margin:6px 0 3px}
.pr11-ratenote{font-size:.72rem;color:#8295A7;line-height:1.45}
@media (max-width:800px){.pr11-rateline{grid-template-columns:1fr}}
</style>'''
st.markdown(CSS, unsafe_allow_html=True)
st.markdown("""<style>
/* Diseño uniforme con Gerencia / Ingeniería / Operaciones */
.pr10-title{font-size:2.15rem!important;color:#152E50!important;font-weight:850!important}
.pr10-sub{color:#788BA1!important}
.pr10-sec{font-size:1.16rem!important;color:#1C3554!important;margin:27px 0 13px!important}
.pr10-metric{background:linear-gradient(180deg,#FFFFFF 0%,#F7FAFE 100%)!important;border:1px solid #DDE6F0!important;border-left:5px solid var(--co)!important;border-radius:19px!important;min-height:150px!important;padding:18px 19px!important;box-shadow:0 4px 14px rgba(20,43,74,.035)!important}
.pr10-mlabel{color:#526984!important;font-size:.85rem!important}
.pr10-mvalue{color:#172F50!important;font-size:2rem!important}
.pr10-mnote{font-size:.75rem!important;color:#8192AA!important}
.pr10-card{background:linear-gradient(180deg,#FFFFFF 0%,#F7FAFE 100%);border:1px solid #DEE7F1;border-radius:19px;padding:17px 20px;box-shadow:0 3px 12px rgba(20,43,74,.025)}
.pr10-cardtitle{color:#1C3453;font-size:.99rem;font-weight:820;margin:0 0 9px}
.pr10-kicker{font-size:.76rem;color:#7489A2;line-height:1.55}
.pr10-detailhead{background:linear-gradient(180deg,#FFFFFF 0%,#F8FBFF 100%);border:1px solid #DFE7F1;border-radius:18px;padding:18px 21px;margin:10px 0 15px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;box-shadow:0 3px 12px rgba(20,43,74,.025)}
.pr10-detailname{font-size:1.18rem;font-weight:850;color:#173553}
.pr10-detailmeta{font-size:.78rem;color:#74879F;margin-top:6px}
.pr10-detailbadge{font-size:.76rem;padding:7px 12px;border-radius:99px;font-weight:780;background:#EAF0F8;color:#355572}
.pr10-dategrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:13px 0 8px}
.pr10-datecard{background:linear-gradient(180deg,#FFFFFF 0%,#F8FBFF 100%);border:1px solid #DEE7F0;border-radius:16px;padding:16px 17px;min-height:95px;box-shadow:0 2px 10px rgba(20,43,74,.02)}
.pr10-datelabel{font-size:.79rem;font-weight:750;color:#71849B;margin-bottom:10px}
.pr10-datevalue{font-size:1.32rem;font-weight:825;color:#193654}
.pr10-progressline{height:10px;background:#E9EEF5;border-radius:100px;overflow:hidden;margin-top:12px}
.pr10-progressline span{display:block;height:100%;border-radius:100px}
.pr10-legend{display:flex;flex-wrap:wrap;gap:15px;margin:12px 0 5px;color:#60778F;font-size:.79rem}
.pr10-legend b{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
.pr10-quickrow{display:flex;justify-content:space-between;gap:14px;padding:10px 0;border-bottom:1px solid #E9EFF5;color:#3E5B77;font-size:.82rem}
.pr10-quickrow:last-child{border-bottom:0;padding-bottom:0}
.pr10-quickrow b{color:#183553}
.pr10-pill{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:#EEF4FA;color:#355572;font-size:.73rem;font-weight:780}
.pr10-pill i{display:inline-block;width:8px;height:8px;border-radius:50%}
div[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(180deg,#FFFFFF 0%,#F7FAFE 100%)!important;border:1px solid #DDE6F0!important;border-radius:20px!important;box-shadow:0 4px 14px rgba(20,43,74,.03)!important}
div[data-testid="stVerticalBlockBorderWrapper"] > div{background:transparent!important}
@media(max-width:750px){.pr10-dategrid{grid-template-columns:1fr}}
</style>""", unsafe_allow_html=True)



st.markdown("""<style>
/* Referencia visual: tarjetas compactas, azul marino y bordes suaves */
.pr10-head{margin:5px 0 12px!important}
.pr10-title{font-size:2.05rem!important}
.pr10-sub{font-size:.91rem!important}
.pr-ref-kicker{font-size:.72rem;color:#7086A0;font-weight:850;letter-spacing:.11em;margin:14px 0 9px}
.pr10-sec{margin:25px 0 11px!important;font-size:1.11rem!important}
.pr10-metric{border-left:0!important;border:1px solid #E1E8F1!important;border-radius:18px!important;min-height:122px!important;padding:15px 15px!important;margin-bottom:0!important;box-shadow:0 3px 9px rgba(25,52,85,.035)!important}
.pr10-mlabel{font-size:.75rem!important;font-weight:750!important}
.pr10-mvalue{font-size:clamp(1.25rem,1.65vw,1.68rem)!important;margin:9px 0 5px!important;white-space:normal}
.pr10-mnote{font-size:.71rem!important}
.pr10-detailhead{border-radius:16px!important}
.pr10-datecard{box-shadow:0 2px 7px rgba(25,52,85,.03);min-height:117px}
.pr10-cardtitle{font-weight:820;font-size:.98rem;color:#193654;margin:2px 0 8px}
.pr-ref-daterow{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid #EDF1F6;gap:15px;font-size:.78rem;color:#425B78}
.pr-ref-daterow:last-child{border-bottom:0}
.pr-ref-daterow b{white-space:nowrap;color:#193653}
[data-testid="stDataFrame"]{border-radius:14px;overflow:hidden}
@media(max-width:850px){.pr10-mvalue{font-size:1.35rem!important}}
</style>""", unsafe_allow_html=True)


st.markdown("""<style>
/* Ficha de proyecto: densidad visual, sin perder información. */
.pr10-detailhead{padding:13px 18px!important;margin:7px 0 9px!important;
    box-shadow:0 2px 9px rgba(24,50,80,.025)}
.pr10-detailname{font-size:1.07rem!important}
.pr10-detailmeta{margin-top:4px!important}
.pr10-detailbadge{padding:5px 11px!important}
.pr10-sec{margin:18px 0 9px!important}
.pr10-metric{min-height:92px!important;padding:12px 16px!important;
    border:1px solid #E1E8F1!important;border-top:3px solid var(--co)!important;
    border-left:1px solid #E1E8F1!important;border-radius:15px!important;
    box-shadow:0 2px 8px rgba(23,52,82,.028)!important}
.pr10-mlabel{font-size:.75rem!important;color:#637992!important}
.pr10-mvalue{font-size:clamp(1.22rem,1.7vw,1.62rem)!important;
    margin:7px 0 3px!important;line-height:1.2!important}
.pr10-mnote{font-size:.69rem!important;line-height:1.35!important}
.pr10-dategrid{gap:10px!important;margin:7px 0 4px!important}
.pr10-datecard{min-height:89px!important;padding:12px 16px!important;
    border:1px solid #E0E7F0!important;border-top:3px solid var(--date-accent,#7896B7)!important;
    border-radius:15px!important;box-shadow:0 2px 8px rgba(23,52,82,.025)!important}
.pr10-datelabel{font-size:.75rem!important;margin-bottom:6px!important}
.pr10-datevalue{font-size:1.18rem!important;letter-spacing:-.01em}
@media(max-width:760px){.pr10-dategrid{grid-template-columns:1fr!important}}
</style>""", unsafe_allow_html=True)



# Colores del tablero: filtros blancos y graficos con fondo blanco.
st.markdown("""<style>
/* Streamlit selectboxes and input: blancos y con borde sutil. */
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
div[data-testid="stTextInput"] div[data-baseweb="input"],
div[data-testid="stTextInput"] input {
    background-color: #FFFFFF !important;
    border-color: #DCE5F0 !important;
    color: #193654 !important;
}
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
div[data-testid="stTextInput"] div[data-baseweb="input"] {
    border-radius: 12px !important;
    box-shadow: 0 2px 7px rgba(30, 56, 85, .035) !important;
}
/* Color de fondo de los graficos Plotly y sus contenedores. */
div[data-testid="stPlotlyChart"],
div[data-testid="stPlotlyChart"] > div {
    background-color: #FFFFFF !important;
    border-radius: 12px !important;
}
</style>""", unsafe_allow_html=True)


st.markdown("""<style>
/* Identidad visual clara y consistente con el panel Gerencia */
.pr10-title{font-size:2.15rem!important;color:#142C4E!important;letter-spacing:-.032em!important}
.pr10-sec{font-weight:830!important;color:#183352!important;margin:23px 0 10px!important}
.pr10-metric{background:#FFFFFF!important;box-shadow:0 4px 16px rgba(25,50,80,.035)!important;
 border:1px solid #DCE6F0!important;border-radius:18px!important;border-top:0!important;
 border-left:0!important;min-height:104px!important;padding:16px 17px!important}
.pr10-mlabel{font-weight:780!important;color:#526986!important}
.pr10-mvalue{color:#132B4A!important;font-weight:850!important;margin-top:9px!important}
.pr10-datecard{background:#FFFFFF!important;box-shadow:0 3px 12px rgba(25,50,80,.03)!important;
 border:1px solid #DFE7F0!important;border-radius:16px!important;border-top:0!important;
 min-height:87px!important;padding:15px 16px!important}
.pr10-detailhead{background:#FFFFFF!important;border:1px solid #DFE7F0!important;box-shadow:0 3px 12px rgba(25,50,80,.03)!important}
.pr10-card,.pr10-panel{background:#FFFFFF!important}
.pr10-project-tile{background:#fff;border:1px solid #DFE7F0;border-radius:15px;
 padding:12px 14px;min-height:112px;box-shadow:0 2px 8px rgba(25,50,80,.025);margin-bottom:5px}
.pr10-project-tile.active{border:1.5px solid #9CB7D7;background:#F9FBFF}
.pr10-project-name{font-size:.83rem;min-height:34px;line-height:1.34;color:#1B3656;font-weight:800}
.pr10-project-muted{font-size:.72rem;color:#7C8DA4;line-height:1.35;margin-top:5px}
.pr10-project-money{font-size:.96rem;font-weight:850;color:#183252;margin-top:7px}
.pr10-project-state{display:inline-block;font-weight:780;font-size:.70rem;color:#48627C;
 border-radius:99px;padding:4px 8px;background:#EEF3F9}
/* Bordes blancos uniformes, sin afectar la barra lateral */
div[data-testid="stVerticalBlockBorderWrapper"]{background:#FFFFFF!important;
 border:1px solid #DFE7F0!important;border-radius:19px!important;box-shadow:0 3px 14px rgba(20,43,74,.03)!important}
div[data-testid="stVerticalBlockBorderWrapper"] > div{background:#FFFFFF!important}
div[data-testid="stPlotlyChart"],div[data-testid="stPlotlyChart"] > div{background:#FFFFFF!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
div[data-testid="stTextInput"] div[data-baseweb="input"],
div[data-testid="stTextInput"] input{background:#FFFFFF!important;border:1px solid #DDE6F0!important;
 border-radius:12px!important;color:#193654!important}

/* Ajuste final: diseño limpio, sin mosaico de proyectos. */
.pr10-metric{height:136px!important;min-height:136px!important;max-height:136px!important;
 display:flex!important;flex-direction:column!important;justify-content:center!important;
 padding:15px 17px!important;box-sizing:border-box!important}
.pr10-mvalue{font-size:clamp(1.20rem,1.65vw,1.62rem)!important;
 white-space:nowrap!important;word-break:normal!important;overflow-wrap:normal!important;
 letter-spacing:-.025em!important;line-height:1.25!important}
.pr10-mnote{line-height:1.4!important}
.pr10-sec{margin-top:24px!important}
.pr10-head{margin-bottom:16px!important}
/* Campos visualmente blancos y de igual altura */
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
div[data-testid="stTextInput"] div[data-baseweb="input"]{
 background:#FFFFFF!important;min-height:48px!important;border:1px solid #DBE5EF!important;
 border-radius:12px!important;box-shadow:none!important}
div[data-testid="stTextInput"] input{background:#FFFFFF!important}
/* Superficies blancas para los gráficos */
div[data-testid="stVerticalBlockBorderWrapper"]{background:#FFFFFF!important;border:1px solid #DFE7EF!important;
 border-radius:18px!important;box-shadow:0 2px 12px rgba(24,47,76,.025)!important}
div[data-testid="stVerticalBlockBorderWrapper"] > div{background:#FFFFFF!important}
[data-testid="stPlotlyChart"]{background:#FFFFFF!important}
</style>""", unsafe_allow_html=True)

st.markdown("""<style>
/* Identidad de referencia: iconografía azul, tarjetas aireadas y estados discretos. */
.pr-pro-metrichead{display:flex;align-items:center;gap:9px;min-height:31px}
.pr-pro-icon{width:34px;height:34px;display:grid;place-items:center;flex:0 0 34px;
 background:#EEF4FC;border-radius:11px}
.pr10-metric{height:145px!important;min-height:145px!important;max-height:145px!important;
 justify-content:flex-start!important;padding:13px 14px!important}
.pr10-mvalue{margin-top:8px!important;line-height:1.18!important}
.pr10-mnote{margin-top:5px!important}
.pr-pro-section{display:flex;align-items:center;gap:11px;font-size:1.16rem;font-weight:820;
 color:#142D50;margin:24px 0 12px}
.pr-pro-section .pr-pro-icon{--accent:#326BC3;flex-basis:36px;width:36px;height:36px;
 background:#EEF4FC;border-radius:11px}
.pr-pro-cardlabel{display:flex;align-items:center;gap:9px}
.pr-pro-cardlabel .pr-pro-icon{background:#EEF4FC;width:30px;height:30px;flex-basis:30px}
.pr10-datecard{border:1px solid #DFE7F0!important;box-shadow:0 2px 12px rgba(25,50,80,.035)!important}
.pr10-detailhead{border-left:4px solid #316ECC!important}
.pr10-detailbadge{background:#E6F5EC;color:#27864B}
[data-testid="stPlotlyChart"]{border-radius:15px!important;overflow:hidden}
</style>""", unsafe_allow_html=True)


# Estilos exclusivos del encabezado y los filtros de cartera.
st.markdown("""<style>
.pr10-title{display:flex!important;align-items:center!important;gap:13px!important}
.pr-pro-titleicon{width:47px;height:47px;min-width:47px;display:inline-flex;
 align-items:center;justify-content:center;border-radius:14px;background:#EDF3FC}
.pr-pro-titleicon svg{display:block}
.st-key-pr_filtros_cartera{background:#FFFFFF!important;border:1px solid #DFE7F0!important;
 border-radius:19px!important;box-shadow:0 3px 14px rgba(20,43,74,.035)!important;
 padding:16px 19px 13px!important}
.st-key-pr_filtros_cartera [data-testid="stSelectbox"] [data-baseweb="select"],
.st-key-pr_filtros_cartera [data-testid="stSelectbox"] [data-baseweb="select"] > div,
.st-key-pr_filtros_cartera [data-testid="stTextInput"] [data-baseweb="input"],
.st-key-pr_filtros_cartera [data-testid="stTextInput"] [data-baseweb="input"] > div,
.st-key-pr_filtros_cartera [data-testid="stTextInput"] input{
 background-color:#FFFFFF!important;color:#1B3958!important}
.st-key-pr_filtros_cartera [data-testid="stSelectbox"] [data-baseweb="select"] > div,
.st-key-pr_filtros_cartera [data-testid="stTextInput"] [data-baseweb="input"]{
 border:1px solid #DEE6F0!important;border-radius:12px!important;box-shadow:none!important}
.st-key-pr_filtros_cartera [data-testid="stWidgetLabel"] p{
 color:#253C59!important;font-weight:730!important}
@media(max-width:600px){.pr-pro-titleicon{width:39px;height:39px;min-width:39px}}
</style>""", unsafe_allow_html=True)

# Aspecto del panel de filtros inspirado en la referencia: dos filas, encabezados
# azul marino, controles suaves y botón de limpieza discreto.
st.markdown("""<style>
.st-key-pr_filtros_cartera{
    background:#FFFFFF!important;border:1px solid #DDE6F0!important;
    border-radius:19px!important;padding:14px 18px 16px!important;
    box-shadow:0 3px 12px rgba(23,48,87,.035)!important;
}
.st-key-pr_filtros_cartera .pr-filtros-encabezado{
    margin:0 0 4px!important;font-size:1.02rem!important;
    color:#142D50!important;
}
.st-key-pr_filtros_cartera [data-testid="stWidgetLabel"] p{
    font-size:.81rem!important;font-weight:760!important;color:#17365A!important;
}
.st-key-pr_filtros_cartera [data-testid="stSelectbox"] [data-baseweb="select"] > div,
.st-key-pr_filtros_cartera [data-testid="stTextInput"] [data-baseweb="input"]{
    background:#EEF2F8!important;border:1px solid #E7EDF5!important;
    border-radius:11px!important;box-shadow:none!important;
    min-height:48px!important;
}
.st-key-pr_filtros_cartera [data-testid="stSelectbox"] [data-baseweb="select"] > div *,
.st-key-pr_filtros_cartera [data-testid="stTextInput"] input{
    background:transparent!important;color:#142D50!important;
}
.st-key-pr_filtros_cartera .st-key-pr_limpiar_filtros button{
    background:#FFFFFF!important;border:1px solid #CBD7E5!important;
    color:#234466!important;border-radius:11px!important;
    min-height:48px!important;font-weight:650!important;
}
.st-key-pr_filtros_cartera .st-key-pr_limpiar_filtros button:hover{
    background:#F3F7FC!important;border-color:#8EACD3!important;
}
</style>""", unsafe_allow_html=True)

# DATOS VIGENTES: solo hechos del ETL actual de Drive.
# Una fila por proyecto; las tareas son un desglose, NO se suman dos veces.
proyectos = cargar('etl_proyectos').copy()
tareas = cargar('etl_tareas').copy()
contratos = cargar('etl_contratos').copy()
if proyectos.empty:
    st.title('Seguimiento de proyectos')
    st.info('No se encontraron proyectos actuales del ETL.')
    st.stop()
if proyectos['Proyecto_Key'].isna().any() or proyectos['Proyecto_Key'].duplicated().any():
    st.error('Hay claves de proyecto faltantes o repetidas en el ETL. No se calcularán totales.')
    st.stop()

for columna in ('CostoPresupuestado_CLP','CostoRealProyecto_CLP','HH_Planificadas',
                'HH_Reales','VentaOC_CLP'):
    proyectos[columna] = pd.to_numeric(proyectos[columna], errors='coerce')
for columna in ('FechaInicioPlan','FechaTerminoPlan'):
    proyectos[columna] = pd.to_datetime(proyectos[columna], errors='coerce')
for columna in ('HH_Planificadas','HH_Reales','AvanceTarea','CostoPlanificado_CLP',
                'CostoReal_CLP'):
    if columna in tareas:
        tareas[columna] = pd.to_numeric(tareas[columna], errors='coerce')

p = proyectos.copy()
p['TipoVisible'] = p['TipoProyecto'].map(etiqueta_tipo)
p['ConsumoPresupuesto'] = p.apply(
    lambda r: num(r['CostoRealProyecto_CLP']) / num(r['CostoPresupuestado_CLP'])
    if math.isfinite(num(r['CostoRealProyecto_CLP'])) and
       math.isfinite(num(r['CostoPresupuestado_CLP'])) and
       num(r['CostoPresupuestado_CLP']) > 0 else float('nan'), axis=1)
p['EstadoCosto'] = p.apply(lambda r: costo_estado(r['CostoPresupuestado_CLP'],
                                                   r['CostoRealProyecto_CLP'])[0], axis=1)
p['SemaforoCosto'] = p['EstadoCosto'].map({
    'Sobre presupuesto':'🔴', 'Consumo elevado':'🟡',
    'Dentro del presupuesto':'🟢', 'Sin presupuesto':'⚪'}).fillna('⚪')

# Estado operativo SIMULADO: una tarea tiene ejecucion completada cuando
# se registran HH reales > 0, conforme a la regla simple de los Excel.
# No confundir este criterio con una certificacion de entrega contractual.
hoy_chile = datetime.now(ZoneInfo('America/Santiago')).date()

def estado_proyecto_tareas(sub):
    if sub.empty:
        return 'Sin tareas registradas'
    hh = pd.to_numeric(sub['HH_Reales'], errors='coerce').fillna(0)
    if (hh > 0).all():
        return 'Finalizado'
    if (hh > 0).any():
        return 'En curso'
    return 'No iniciado'

estados = {clave: estado_proyecto_tareas(sub) for clave, sub in tareas.groupby('Proyecto_Key')}
p['EstadoEjecucionTareas'] = p['Proyecto_Key'].map(estados).fillna('Sin tareas registradas')

# Contratos Gmail: nunca atribuir un contrato a otro proyecto.
# Si hay contratos distintos para un mismo proyecto, no seleccionar uno arbitrariamente.
# En los contratos 'EXTRAIDO_SIN_APROBAR' la comparación es PRELIMINAR.
if not contratos.empty:
    contratos['FechaInicioContrato'] = pd.to_datetime(contratos['FechaInicioContrato'], errors='coerce')
    contratos['FechaTerminoContrato'] = pd.to_datetime(contratos['FechaTerminoContrato'], errors='coerce')


def referencia_contractual(clave):
    grupo = contratos.loc[contratos['Proyecto_Key'] == clave] if not contratos.empty else pd.DataFrame()
    if grupo.empty:
        return None, 'Sin contrato PDF', ''
    if (grupo['EstadoVinculacion'].fillna('').astype(str).str.upper().str.contains('PENDIENTE|SIN_VINCULAR|CONFLICTO|AMBIGU')).any():
        return None, 'Vinculación por revisar', ''
    if (grupo['EstadoValidacion'].fillna('').astype(str).str.upper().str.contains('CONFLICTO')).any():
        return None, 'Contratos en conflicto', ''
    fechas = grupo['FechaTerminoContrato'].dropna().dt.normalize().unique()
    if len(fechas) != 1:
        return None, 'Contrato sin fecha única', ''
    estado_validacion = str(grupo.iloc[0].get('EstadoValidacion') or '').strip()
    return pd.Timestamp(fechas[0]), 'Contrato disponible', estado_validacion


referencias = {clave: referencia_contractual(clave) for clave in p['Proyecto_Key']}
p['FinContrato'] = p['Proyecto_Key'].map(lambda k: referencias[k][0])
p['EstadoContrato'] = p['Proyecto_Key'].map(lambda k: referencias[k][1])
p['ValidacionContrato'] = p['Proyecto_Key'].map(lambda k: referencias[k][2])


# Mostrar "Finalizado" solo cuando coinciden dos fuentes:
#  1) todas las tareas registran HH reales > 0 (criterio SIMULADO de Excel), y
#  2) existe un contrato Gmail vinculado de manera univoca.
# Tener contrato por si solo NO prueba entrega real: la clasificacion es preliminar,
# especialmente mientras el contrato este EXTRAIDO_SIN_APROBAR.
# Sin contrato, un proyecto con HH positivas se mantiene "En curso".
def estado_visible_segun_contrato(r):
    estado_tareas = r['EstadoEjecucionTareas']
    if estado_tareas == 'Finalizado':
        if r['EstadoContrato'] == 'Contrato disponible' and pd.notna(r['FinContrato']):
            return 'Finalizado'
        return 'En curso'
    return estado_tareas


p['EstadoVisible'] = p.apply(estado_visible_segun_contrato, axis=1)

# Ultima fecha FIN de las tareas, sin reemplazarla con la fecha de hoy.
# El FIN del Excel es planificado, no registra ejecucion efectiva.
if 'FechaTerminoPlan' in tareas:
    tareas['FechaTerminoPlan'] = pd.to_datetime(tareas['FechaTerminoPlan'], errors='coerce')
ultimas_fechas = tareas.groupby('Proyecto_Key')['FechaTerminoPlan'].max().to_dict()
p['UltimaFechaGantt'] = p['Proyecto_Key'].map(ultimas_fechas)


def evaluar_plazo_referencial(r):
    fin_contrato = r['FinContrato']
    fin_gantt = r['UltimaFechaGantt']
    estado = r['EstadoVisible']
    if pd.isna(fin_contrato):
        return ('⚪ Sin contrato', None)
    if estado == 'Finalizado':
        if pd.isna(fin_gantt):
            return ('⚪ Con contrato · sin fecha de Gantt', None)
        diferencia = (pd.Timestamp(fin_gantt).date() - pd.Timestamp(fin_contrato).date()).days
        if diferencia > 0:
            return ('🔴 Plan fuera de contrato', diferencia)
        return ('🟢 Plan dentro de contrato', 0)
    prefijo = 'No iniciado' if estado == 'No iniciado' else 'En curso'
    dias = (pd.Timestamp(fin_contrato).date() - hoy_chile).days
    if dias < 0:
        return (f'🔴 {prefijo} · con atraso', -dias)
    if dias <= 30:
        return (f'🟡 {prefijo} · próximo a vencer', 0)
    return (f'🟢 {prefijo} · en plazo', 0)

p['EvaluacionPlazo'] = p.apply(evaluar_plazo_referencial, axis=1)
p['SemaforoPlazo'] = p['EvaluacionPlazo'].map(lambda resultado: resultado[0])
p['DiasSobrePlazo'] = p['EvaluacionPlazo'].map(lambda resultado: resultado[1])

st.markdown('<div class="pr10-head"><div><div class="pr10-title">'
            '<span class="pr-pro-titleicon">' + icono('folder', '#326BC3', 23) + '</span>'
            'Seguimiento de proyectos</div>'
            '<div class="pr10-sub">Control de cartera · avance financiero · fechas y planificación por proyecto</div>'
            '</div></div>', unsafe_allow_html=True)


# MAAS · Estilo visual de referencia: paneles luminosos, controles blancos y jerarquía compacta.
st.markdown("""<style>
/* Alcance: área principal de la página; no altera la barra lateral. */
[data-testid="stAppViewContainer"]{background:#F4F7FB!important}
[data-testid="stMainBlockContainer"]{max-width:1530px!important;padding-top:1.5rem!important}
.pr10-title{font-size:2.05rem!important;color:#142E54!important;font-weight:850!important}
.pr10-sub{color:#7B8DA5!important;font-size:.90rem!important}
.pr-ref-kicker{font-size:.70rem!important;color:#607997!important;letter-spacing:.10em!important;margin:16px 0 9px!important}
.pr10-sec{font-size:1.11rem!important;color:#153556!important;margin:22px 0 12px!important}
.pr10-metric{background:#FFFFFF!important;border:1px solid #E0E8F2!important;border-top:1px solid #E0E8F2!important;
  border-left:1px solid #E0E8F2!important;border-radius:18px!important;min-height:126px!important;
  box-shadow:0 5px 18px rgba(23,48,87,.045)!important;padding:18px 17px!important}
.pr10-mlabel{color:#516987!important;font-size:.77rem!important;line-height:1.25!important}
.pr10-mvalue{color:#142F54!important;font-size:clamp(1.12rem,1.52vw,1.6rem)!important;
  overflow-wrap:normal!important;word-break:normal!important;white-space:nowrap!important;margin:12px 0 5px!important}
.pr10-mnote{color:#8092A9!important;line-height:1.4!important;font-size:.71rem!important}
.pr10-detailhead{border-radius:18px!important;padding:16px 20px!important;
  background:#fff!important;box-shadow:0 5px 18px rgba(23,48,87,.045)!important}
.pr10-detailname{font-size:1.10rem!important;color:#153456!important}
.pr10-detailbadge{background:#E8F6EE!important;color:#28804F!important}
.pr10-datecard{background:#fff!important;border:1px solid #E2EAF3!important;border-top:1px solid #E2EAF3!important;
  border-radius:16px!important;min-height:95px!important;box-shadow:0 3px 10px rgba(23,48,87,.028)!important}
.pr10-datelabel{color:#687F9A!important}.pr10-datevalue{color:#153456!important}
.pr10-cardtitle{font-size:.97rem!important;color:#19385B!important;font-weight:820!important}
/* Contenedores de gráficos/estructura, con blanco sólido. */
[data-testid="stVerticalBlockBorderWrapper"]{background:#FFFFFF!important;border:1px solid #E0E8F2!important;
  border-radius:19px!important;box-shadow:0 5px 18px rgba(23,48,87,.04)!important}
[data-testid="stVerticalBlockBorderWrapper"] > div{background:transparent!important}
[data-testid="stPlotlyChart"], [data-testid="stPlotlyChart"] > div{background:#FFFFFF!important}
/* Todos los controles de filtro e inputs blancos. */
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stTextInput"] input{
 background:#FFFFFF!important;border:1px solid #DDE6F0!important;border-radius:11px!important;color:#1B3958!important;
 box-shadow:none!important}
[data-testid="stSelectbox"] label, [data-testid="stTextInput"] label{color:#375474!important;font-weight:740!important;font-size:.79rem!important}
/* Botones discretos. */
[data-testid="stDownloadButton"] button{background:#FFFFFF!important;border:1px solid #DDE6F0!important;
 color:#234569!important;border-radius:11px!important}
/* Tabla principal: esquinas, líneas y fuente elegantes. */
[data-testid="stDataFrame"]{border:1px solid #E2EAF3!important;border-radius:14px!important;overflow:hidden!important}
/* Navegación de la ficha individual. */
[data-testid="stTabs"] [role="tab"]{font-weight:730!important;color:#56708E!important}
[data-testid="stTabs"] [aria-selected="true"]{color:#1D4E89!important}
@media(max-width:900px){.pr10-mvalue{white-space:normal!important;font-size:1.25rem!important}}
</style>""", unsafe_allow_html=True)

# Filtros de seguimiento: año, proyecto y responsable cuando está informado.
# Un proyecto pertenece al año si su planificación se solapa con él.
# La fecha contractual procede de Gmail y puede estar pendiente de aprobación.
responsable_columnas = ('NombreResponsable', 'ResponsableProyecto', 'Responsable',
                        'JefeProyecto', 'EncargadoProyecto', 'CoordinadorProyecto')
col_responsable = next((c for c in responsable_columnas if c in p.columns), None)
if col_responsable:
    p['ResponsableVisible'] = p[col_responsable].fillna('').astype(str).str.strip()
    p.loc[p['ResponsableVisible'].str.lower().isin(('', 'nan', 'none', 'sin asignar')), 'ResponsableVisible'] = '—'
else:
    p['ResponsableVisible'] = '—'

# La duración se obtiene del plan original; no se simula una fecha de entrega real.
p['FechaFinSeguimiento'] = p['FechaTerminoPlan'].combine_first(p['UltimaFechaGantt'])
fechas_año = pd.concat([p['FechaInicioPlan'],p['FechaFinSeguimiento'],p['FinContrato']]).dropna()
anios_disponibles = sorted(set(fechas_año.dt.year.astype(int).tolist()) | set(range(2024, 2029)), reverse=True)
if not anios_disponibles:
    anios_disponibles = [2027, 2026, 2025, 2024]
# Filtros compactos en dos filas, con la distribución de la referencia.
# Solo se modifica la presentación; se conservan las mismas condiciones de filtrado.
def limpiar_filtros_proyectos():
    for clave in ('pr_seguimiento_anio', 'pr_seguimiento_proyecto',
                  'pr_seguimiento_responsable', 'pro_tipo_actual',
                  'pro_estado_actual', 'pro_buscar_actual'):
        st.session_state.pop(clave, None)

with st.container(border=True, key="pr_filtros_cartera"):
    st.markdown('<div class="pr-pro-section pr-filtros-encabezado"><span class="pr-pro-icon">'+icono('filter')+'</span>Filtrar cartera</div>', unsafe_allow_html=True)
    # Fila 1: tres filtros y el botón de limpieza.
    fc1, fc2, fc3, fc_limpiar = st.columns([1, 1.35, 1.15, .9], gap='medium', vertical_alignment='bottom')
    with fc1:
        anio = st.selectbox('Año', anios_disponibles,
                            index=anios_disponibles.index(2026) if 2026 in anios_disponibles else 0,
                            key='pr_seguimiento_anio')
    inicio_anio = pd.Timestamp(year=int(anio),month=1,day=1)
    fin_anio = pd.Timestamp(year=int(anio),month=12,day=31)
    inicios = p['FechaInicioPlan'].combine_first(p['FechaFinSeguimiento']).combine_first(p['FinContrato'])
    fines = p['FechaFinSeguimiento'].combine_first(p['FechaInicioPlan']).combine_first(p['FinContrato'])
    interseccion = (inicios.le(fin_anio) & fines.ge(inicio_anio)) | (
        inicios.isna() & fines.isna())
    p_anio = p.loc[interseccion].copy()
    with fc2:
        opciones_proyectos = ['Todos los proyectos'] + sorted(p_anio['NombreProyecto'].dropna().astype(str).unique().tolist())
        proyecto_sel = st.selectbox('Proyecto', opciones_proyectos, key='pr_seguimiento_proyecto')
    with fc3:
        opciones_responsables = ['Todos'] + sorted(x for x in p_anio['ResponsableVisible'].unique() if x != '—')
        responsable_sel = st.selectbox('Responsable', opciones_responsables,
                                       key='pr_seguimiento_responsable',
                                       help='Se muestra únicamente cuando el ETL entrega un responsable explícito.')
    with fc_limpiar:
        st.button('🧹 Limpiar filtros', key='pr_limpiar_filtros',
                  use_container_width=True, on_click=limpiar_filtros_proyectos)
    p_filtrado = p_anio.copy()
    if proyecto_sel != 'Todos los proyectos':
        p_filtrado = p_filtrado.loc[p_filtrado['NombreProyecto'].eq(proyecto_sel)].copy()
    if responsable_sel != 'Todos':
        p_filtrado = p_filtrado.loc[p_filtrado['ResponsableVisible'].eq(responsable_sel)].copy()
    if p_filtrado.empty:
        st.info(f'No hay proyectos para los filtros seleccionados en {anio}.')
        st.stop()

    # Iniciar la cartera con los proyectos ya filtrados por año, proyecto y responsable.
    # Antes se utilizaba `f` sin definir, provocando NameError.
    f = p_filtrado.copy()

    # 2. CARTERA: filtros adicionales de tipo, ejecución y nombre.
    a, b, c = st.columns([1, 1, 2.1], gap='medium')
    with a:
        tipo = st.selectbox('Tipo', ['Todos'] + sorted(f['TipoVisible'].dropna().unique().tolist()), key='pro_tipo_actual')
    with b:
        estado = st.selectbox('Ejecución', ['Todos'] + sorted(f['EstadoVisible'].dropna().unique().tolist()), key='pro_estado_actual')
    with c:
        buscar = st.text_input('Buscar proyecto', placeholder='Nombre del proyecto…', key='pro_buscar_actual')
    if tipo != 'Todos':
        f = f.loc[f['TipoVisible'] == tipo].copy()
    if estado != 'Todos':
        f = f.loc[f['EstadoVisible'] == estado].copy()
    if buscar.strip():
        f = f.loc[f['NombreProyecto'].fillna('').map(normaliza).str.contains(normaliza(buscar), regex=False)].copy()
    if f.empty:
        st.info('Ningún proyecto cumple los filtros adicionales.')
        st.stop()

# 1. INDICADORES PRINCIPALES: reflejan los filtros del año/proyecto/responsable.
st.markdown('<div class="pr-pro-section"><span class="pr-pro-icon">'+icono('chart')+'</span>Resumen del año seleccionado</div>', unsafe_allow_html=True)
presupuesto = f['CostoPresupuestado_CLP'].sum(min_count=1)
gasto = f['CostoRealProyecto_CLP'].sum(min_count=1)
completados = int((f['EstadoVisible'] == 'Finalizado').sum())
con_ejecucion = int(f['EstadoVisible'].isin(('En curso', 'Finalizado')).sum())
sobrecosto = int((f['EstadoCosto'] == 'Sobre presupuesto').sum())
resumen = [
    ('Proyectos', entero(len(f)), f'Cartera de {anio}', AZUL),
    ('Monto total de OC', '$' + decimal(f['VentaOC_CLP'].sum(min_count=1) / 1_000_000, 1) + ' MM', 'Suma de proyectos seleccionados', AZUL),
    ('En ejecución', entero(con_ejecucion), 'Con HH registradas, preliminar', AMARILLO),
    ('Finalizados', entero(completados), 'Cierre provisional, por validar', VERDE),
    ('Sobre presupuesto', entero(sobrecosto), 'Costo registrado mayor al plan', ROJO if sobrecosto else VERDE),
]
for col, item in zip(st.columns(5, gap='small'), resumen):
    with col:
        st.markdown(panel_metric(*item), unsafe_allow_html=True)

# Las fechas y responsables figuran en la cartera filtrable a continuación.

# 2. VISUALIZACIÓN CON ESTILO DE REFERENCIA: ejecución de costos y cartera por tipo.
# No se presenta el consumo del presupuesto como margen: son métricas distintas.
st.markdown('<div class="pr-pro-section"><span class="pr-pro-icon">'+icono('pie')+'</span>Vista general de la cartera</div>', unsafe_allow_html=True)
col_grafico, col_distribucion = st.columns([1.55, .95], gap='medium')
with col_grafico:
    with st.container(border=True):
        st.markdown('<div class="pr10-cardtitle pr-pro-cardlabel"><span class="pr-pro-icon">'+icono('chart')+'</span>Costo registrado vs. presupuesto, por proyecto</div>', unsafe_allow_html=True)
        comp = f[['NombreProyecto', 'CostoPresupuestado_CLP', 'CostoRealProyecto_CLP']].copy()
        comp = comp.dropna(subset=['CostoPresupuestado_CLP', 'CostoRealProyecto_CLP'], how='all')
        comp = comp.sort_values('CostoPresupuestado_CLP', ascending=False).head(12).iloc[::-1]
        if comp.empty:
            st.info('Sin importes para comparar en este período.')
        else:
            fig_c = go.Figure()
            exceso = comp['CostoRealProyecto_CLP'] > comp['CostoPresupuestado_CLP']
            fig_c.add_trace(go.Bar(
                y=comp['NombreProyecto'], x=comp['CostoRealProyecto_CLP'], orientation='h',
                marker_color=[ROJO if x else VERDE for x in exceso],
                customdata=comp['CostoPresupuestado_CLP'],
                hovertemplate='%{y}<br>Costo registrado: $%{x:,.0f}<br>Presupuesto: $%{customdata:,.0f}<extra></extra>',
                showlegend=False))
            # Una marca oscura por proyecto señala el presupuesto de referencia.
            for _, rr in comp.iterrows():
                v=num(rr['CostoPresupuestado_CLP'])
                if math.isfinite(v):
                    fig_c.add_trace(go.Scatter(
                        x=[v], y=[rr['NombreProyecto']], mode='markers',
                        marker=dict(symbol='line-ns', size=22, line=dict(width=3, color=AZUL), color=AZUL),
                        showlegend=False, hoverinfo='skip'))
            fig_c.update_layout(height=max(310, len(comp)*30+80), margin=dict(l=8,r=14,t=18,b=27),
                paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF',
                font=dict(color='#70849C',size=11),
                xaxis=dict(tickformat=',.2s',gridcolor='#ECF0F5', zeroline=False),
                yaxis=dict(automargin=True), showlegend=False)
            st.plotly_chart(fig_c,use_container_width=True,config={'displayModeBar':False})
        st.caption('Verde: dentro del presupuesto · rojo: sobre presupuesto · marca azul: presupuesto planificado. Datos de seguimiento, no margen de ventas.')
with col_distribucion:
    with st.container(border=True):
        st.markdown('<div class="pr10-cardtitle pr-pro-cardlabel"><span class="pr-pro-icon">'+icono('pie')+'</span>¿Dónde está la venta / OC?</div>', unsafe_allow_html=True)
        ventas_por_tipo = f.groupby('TipoVisible', dropna=False)['VentaOC_CLP'].sum(min_count=1).dropna()
        ventas_por_tipo = ventas_por_tipo[ventas_por_tipo > 0]
        if ventas_por_tipo.empty:
            st.info('Sin ventas / OC registradas para estos proyectos.')
        else:
            fig_d = go.Figure(go.Pie(labels=ventas_por_tipo.index.tolist(),
                values=ventas_por_tipo.tolist(), hole=.62,
                marker=dict(colors=['#3973CF','#86A9E5','#B4C8EB','#D6E0F1'][:len(ventas_por_tipo)]),
                textinfo='percent', textfont=dict(size=12),
                hovertemplate='%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>'))
            fig_d.update_layout(height=305, margin=dict(l=9,r=9,t=17,b=5),
                paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF', showlegend=True,
                legend=dict(orientation='h',y=-.05,x=.5,xanchor='center',font=dict(size=11,color='#506987')))
            st.plotly_chart(fig_d,use_container_width=True,config={'displayModeBar':False})
        st.caption('Participación del valor de venta / OC por tipo de proyecto.')
# Desplegables de ficha de proyecto: cerrados al ingresar y uniformes con el tablero.
st.markdown("""<style>
[data-testid="stExpander"]{border:1px solid #DFE7F0!important;border-radius:16px!important;
 background:#FFFFFF!important;box-shadow:0 3px 12px rgba(25,50,80,.03)!important;
 margin:8px 0!important;overflow:hidden!important}
[data-testid="stExpander"] details summary{color:#173553!important;font-weight:780!important;
 padding:11px 14px!important}
[data-testid="stExpander"] details summary:hover{background:#F4F8FE!important}
[data-testid="stExpander"] details[open] summary{border-bottom:1px solid #E9EFF6!important}
</style>""", unsafe_allow_html=True)

# 3. DETALLE DEL PROYECTO: ficha resumida y panel de tareas, Gantt, recursos y Gmail.
st.markdown('<div class="pr-pro-section"><span class="pr-pro-icon">'+icono('briefcase')+'</span>Ficha de seguimiento del proyecto</div>', unsafe_allow_html=True)
claves = f['Proyecto_Key'].tolist()
nombres = f.set_index('Proyecto_Key')['NombreProyecto'].to_dict()
# La selección debe seguir siendo válida cuando cambian los filtros.
if st.session_state.get('pr10_proyecto') not in claves:
    st.session_state['pr10_proyecto'] = claves[0]
seleccion = st.selectbox('Selecciona un proyecto', claves,
                         format_func=lambda k:nombres.get(k,str(k)),key='pr10_proyecto')
actual = p.loc[p['Proyecto_Key'] == seleccion].iloc[0]
st.markdown(
    '<div class="pr10-detailhead"><div><div class="pr10-detailname pr-pro-cardlabel"><span class="pr-pro-icon" style="--accent:#326BC3">'+icono('briefcase')+'</span>' +
    html(actual['NombreProyecto']) + '</div><div class="pr10-detailmeta">Responsable: ' +
    html(actual['ResponsableVisible']) + ' · ' + html(actual['TipoVisible']) +
    '</div></div><span class="pr10-detailbadge">' + html(actual['EstadoVisible']) +
    '</span></div>', unsafe_allow_html=True)

# Secciones cerradas inicialmente; se despliegan solo al pulsar su encabezado.
# Mantienen intactos los indicadores y el panel de planificación existentes.
with st.expander('Ficha y fechas clave', expanded=False):
    presupuesto_actual = num(actual['CostoPresupuestado_CLP'])
    costo_actual = num(actual['CostoRealProyecto_CLP'])
    consumo_actual = (costo_actual / presupuesto_actual if math.isfinite(presupuesto_actual)
                      and presupuesto_actual > 0 and math.isfinite(costo_actual) else float('nan'))
    cols = st.columns(3, gap='medium')
    for col, item in zip(cols,[
        ('Presupuesto de costos',clp(presupuesto_actual),'Planificación del Excel',AZUL),
        ('Costo real de tareas',clp(costo_actual),'Ejecución registrada',AMARILLO),
        ('Consumo presupuesto',pc(consumo_actual),actual['EstadoCosto'],
         costo_estado(presupuesto_actual,costo_actual)[1]),
    ]):
        with col:
            st.markdown(panel_metric(*item),unsafe_allow_html=True)
    st.markdown('<div class="pr-pro-section"><span class="pr-pro-icon">'+icono('calendar')+'</span>Fechas importantes del proyecto</div>',unsafe_allow_html=True)
    puntos = [
        ('Inicio planificado', fecha(actual['FechaInicioPlan'])),
        ('Término planificado', fecha(actual['FechaTerminoPlan'])),
        ('Término contractual', fecha(actual['FinContrato'])),
    ]
    acentos_fecha = ('#326BC3', '#326BC3', '#326BC3')
    fecha_html = ''.join(
        '<div class="pr10-datecard" style="--date-accent:'+acento+'">'
        '<div class="pr-pro-cardlabel"><span class="pr-pro-icon" style="--accent:'+acento+'">'+icono('calendar',acento,18)+'</span><div class="pr10-datelabel">'+html(titulo)+'</div></div>'
        '<div class="pr10-datevalue">'+html(valor)+'</div></div>'
        for (titulo, valor), acento in zip(puntos, acentos_fecha)
    )
    st.markdown('<div class="pr10-dategrid">'+fecha_html+'</div>',unsafe_allow_html=True)
    st.markdown('<div class="pr-pro-section"><span class="pr-pro-icon">'+icono('users')+'</span>Recursos y orden de compra</div>', unsafe_allow_html=True)
    d, e, g = st.columns(3, gap='medium')
    for col, dato in zip((d,e,g), [
        ('HH planificadas',entero(actual['HH_Planificadas']),AZUL),
        ('HH reales',entero(actual['HH_Reales']),VERDE),
        ('Venta / OC',clp(actual['VentaOC_CLP']),AZUL),
    ]):
        with col:
            st.markdown(panel_metric(dato[0],dato[1], 'Dato registrado en el seguimiento',dato[2]),
                        unsafe_allow_html=True)

with st.expander('Planificación y tareas', expanded=False):
    panel_ficha_proyecto(seleccion)



# Estilo unificado de íconos y tabla de cartera. Los estados conservan sus colores semánticos.
st.markdown("""<style>
.pr-pro-icon{background:#EEF4FC!important;color:#326BC3!important}
.pr10-datecard .pr-pro-icon,.pr-pro-metrichead .pr-pro-icon{background:#EEF4FC!important}
.pr-cartera-scroll{width:100%;max-height:570px;overflow:auto;background:#FFFFFF;
 border:1px solid #DEE7F0;border-radius:17px;box-shadow:0 3px 13px rgba(20,43,74,.035)}
.pr-cartera-table{width:100%;min-width:1190px;border-collapse:separate;border-spacing:0;
 font-size:.82rem;color:#253C59}
.pr-cartera-table th{position:sticky;top:0;z-index:2;background:#F4F7FC;color:#435F7C;
 font-weight:820;text-align:left;padding:14px 15px;border-bottom:1px solid #DCE5EF;white-space:nowrap}
.pr-cartera-table td{padding:13px 15px;border-bottom:1px solid #EAF0F6;
 vertical-align:middle;background:#FFFFFF;white-space:nowrap}
.pr-cartera-table tbody tr:nth-child(even) td{background:#FAFCFF}
.pr-cartera-table tbody tr:hover td{background:#EFF5FD}
.pr-cartera-table tr:last-child td{border-bottom:0}
.pr-cartera-table td:first-child{font-weight:740;color:#183A60;min-width:190px;
 white-space:normal;line-height:1.4}
.pr-cartera-table td.monto{font-weight:790;color:#173657;font-variant-numeric:tabular-nums}
.pr-cartera-pill{display:inline-flex;align-items:center;border-radius:999px;
 background:#EDF3FB;color:#3B5877;padding:6px 10px;font-weight:730;font-size:.76rem}
.pr-cartera-estado{background:#EFF4F9;color:#3D5871}
.pr-cartera-status{display:inline-flex;align-items:center;gap:7px;border-radius:999px;
 padding:6px 10px;font-size:.76rem;font-weight:760;background:var(--bg);color:var(--fg)}
.pr-cartera-status i{width:8px;height:8px;border-radius:50%;background:var(--fg);display:inline-block}
</style>""", unsafe_allow_html=True)

# 4. TABLA GENERAL AL FINAL: conserva todos los proyectos del filtro actual.
st.markdown('<div class="pr-pro-section"><span class="pr-pro-icon">'+icono('folder')+'</span>Todos los proyectos</div>', unsafe_allow_html=True)
st.caption('Resumen de montos de órdenes de compra, plazos, presupuestos y costos de la cartera seleccionada.')
tabla = pd.DataFrame({
    'Proyecto': f['NombreProyecto'],
    'Monto proyecto': f['VentaOC_CLP'].map(clp),
    'Tipo': f['TipoVisible'],
    'Estado': f['EstadoVisible'],
    'Inicio': f['FechaInicioPlan'].map(fecha),
    'Término planificado': f['FechaFinSeguimiento'].map(fecha),
    'Término contrato': f['FinContrato'].map(fecha),
    'Semáforo plazo': f['SemaforoPlazo'],
    'Presupuesto': f['CostoPresupuestado_CLP'].map(clp),
    'Gasto real': f['CostoRealProyecto_CLP'].map(clp),
})
# Tabla HTML diseñada para mantener la estética del resto de MAAS.
# Se conserva el DataFrame original para la exportación CSV sin alterar valores.
def cartera_estado_html(v):
    estado = str(v).strip()
    claves = {
        'Finalizado': ('#E7F5ED', '#278253'),
        'En curso': ('#FFF5DF', '#956D13'),
        'No iniciado': ('#EEF2F8', '#60738D'),
    }
    fondo, tinta = claves.get(estado, ('#EDF3FB', '#466482'))
    return (f'<span class="pr-cartera-status" style="--bg:{fondo};--fg:{tinta}">'
            f'<i></i>{html(estado)}</span>')

def cartera_plazo_html(v):
    estado = str(v).strip()
    etiqueta = estado.split(' ', 1)[1] if ' ' in estado and estado[0] in '🔴🟢🟡⚪' else estado
    if 'fuera' in etiqueta.casefold() or 'atraso' in etiqueta.casefold():
        fondo, tinta = '#FCEBEC', '#B84350'
    elif 'dentro' in etiqueta.casefold() or 'en plazo' in etiqueta.casefold():
        fondo, tinta = '#E7F5ED', '#288554'
    elif 'vencer' in etiqueta.casefold() or 'validar' in etiqueta.casefold():
        fondo, tinta = '#FFF5DF', '#956D13'
    else:
        fondo, tinta = '#F0F3F8', '#71829A'
    return (f'<span class="pr-cartera-status" style="--bg:{fondo};--fg:{tinta}">'
            f'<i></i>{html(etiqueta)}</span>')

columnas_cartera = list(tabla.columns)
filas_cartera = []
for _, registro in tabla.iterrows():
    celdas = []
    for columna in columnas_cartera:
        valor = registro[columna]
        if columna == 'Estado':
            contenido = cartera_estado_html(valor)
        elif columna == 'Semáforo plazo':
            contenido = cartera_plazo_html(valor)
        elif columna == 'Tipo':
            contenido = f'<span class="pr-cartera-pill">{html(valor)}</span>'
        else:
            contenido = html(valor)
        clase = ' class="monto"' if columna in ('Monto proyecto', 'Presupuesto', 'Gasto real') else ''
        celdas.append(f'<td{clase}>{contenido}</td>')
    filas_cartera.append('<tr>' + ''.join(celdas) + '</tr>')
cabeceras_cartera = ''.join(f'<th>{html(nombre)}</th>' for nombre in columnas_cartera)
st.markdown('<div class="pr-cartera-scroll"><table class="pr-cartera-table">'
            '<thead><tr>' + cabeceras_cartera + '</tr></thead><tbody>'
            + ''.join(filas_cartera) + '</tbody></table></div>',
            unsafe_allow_html=True)
st.download_button('⬇ Descargar cartera filtrada (CSV)',
                   data=tabla.to_csv(index=False, sep=';').encode('utf-8-sig'),
                   file_name='MAAS_cartera_seguimiento.csv', mime='text/csv',
                   key='descargar_cartera_actual')

