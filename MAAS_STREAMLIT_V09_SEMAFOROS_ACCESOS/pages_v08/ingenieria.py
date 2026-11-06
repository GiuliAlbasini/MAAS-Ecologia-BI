# -*- coding: utf-8 -*-
"""MAAS ECOLOGÍA 4 · Ingeniería y Propuestas · Diseño V10.

INSTRUCCIÓN: reemplazar únicamente pages_v08/ingenieria.py con este contenido.
No modifica SQL, ETL, usuarios ni el resto de Streamlit.
Datos: BSC oficial del área INGENIERIA Y PROPUESTAS (último corte disponible).
Semáforos VISUALES: verde >=100%, amarillo 70-<100%, rojo <70%, gris sin datos.
"""
from __future__ import annotations

import html
import math
import unicodedata

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from maas_datos import cargar, _conexion
from maas_ui import metricas, presentacion_valor, recortar_bsc

# Revisar acceso ANTES de consultar la base de datos.
# La navegación por perfil se controla desde app_maas_4.py.

VERDE = '#4BA474'
AMARILLO = '#E7B541'
ROJO = '#D65B5B'
GRIS = '#97AABE'
AZUL = '#24496B'
GRUPOS = ['Propuestas y adjudicaciones', 'Cumplimiento técnico', 'Innovación y proveedores']


def num(valor):
    try:
        x = float(valor)
        return x if math.isfinite(x) else float('nan')
    except (TypeError, ValueError):
        return float('nan')


def esc(valor):
    if valor is None:
        return '—'
    try:
        if pd.isna(valor):
            return '—'
    except (ValueError, TypeError):
        pass
    return html.escape(str(valor), quote=True)


def normal(valor):
    if valor is None:
        return ''
    cadena = unicodedata.normalize('NFKD', str(valor))
    return ' '.join(''.join(letra for letra in cadena if not unicodedata.combining(letra)).casefold().split())


def numero_local(valor, decimales=1):
    x = num(valor)
    if not math.isfinite(x):
        return '—'
    return f'{x:,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def porcentaje(valor, decimales=1):
    x = num(valor)
    return numero_local(x * 100, decimales) + '%' if math.isfinite(x) else '—'


def estatus(valor):
    x = num(valor)
    if not math.isfinite(x):
        return 'Sin datos'
    if x >= 1:
        return 'Meta alcanzada'
    return 'En progreso' if x >= .7 else 'Bajo cumplimiento'


def tono(valor):
    return {'Meta alcanzada': VERDE, 'En progreso': AMARILLO,
            'Bajo cumplimiento': ROJO, 'Sin datos': GRIS}[estatus(valor)]


def barra(valor):
    x = num(valor)
    return f'{max(0, min(100, x * 100)):.1f}%' if math.isfinite(x) else '0%'


def pesos(valor):
    x = num(valor)
    return '$' + f'{round(x):,}'.replace(',', '.') if math.isfinite(x) else '—'


def valor_bsc(fila, meta=False):
    n = fila.get('MetaNumerica' if meta else 'ResultadoNumerico')
    txt = fila.get('MetaTexto' if meta else 'ResultadoTexto')
    unidad = fila.get('UnidadMedida')
    unidad_norm = normal(unidad)
    if 'miles' in unidad_norm and ('clp' in unidad_norm or '$' in unidad_norm):
        if math.isfinite(num(n)):
            return pesos(num(n) * 1000)
        return 'Sin dato' if txt is None or str(txt).strip() == '' else str(txt)
    return presentacion_valor(n, txt, unidad)


def familia(fila):
    """Solo organización visual. No cambia la categoría original del BSC."""
    texto = normal(fila.get('NombreKPI', ''))
    categoria = normal(fila.get('CategoriaKPI', ''))
    # Las reglas de nombres específicos tienen prioridad sobre la categoría de origen.
    if any(x in texto for x in (
            'propuesta', 'adjudica', 'licitacion', 'cotizacion', 'ofertad',
            'fundacion mlp', 'faena', 'doh', 'andina externos', 'mlp dentro de margen')):
        return GRUPOS[0]
    if any(x in texto for x in ('innovacion', 'alianza', 'proveedor', 'desarrollo')):
        return GRUPOS[2]
    if any(x in texto for x in ('kom', 'certificacion', 'ingenieria', 'entrega tecnica',
                                 'cumplimiento de proyecto', 'diseno', 'plazo de entrega')):
        return GRUPOS[1]
    if categoria in ('propuestas', 'ventas') and 'venta' not in texto:
        return GRUPOS[0]
    if categoria in ('ingenieria', 'transformacion') and 'ventas' not in texto:
        return GRUPOS[1]
    # KPI globales / transversales incluidos en el BSC departamental.
    return 'Indicadores transversales'



# Iconografía decorativa SVG, sin dependencias ni cambios en cálculos.
_ING_ICON_PATHS = {'hard-hat': '<path d="M2 18h20"/><path d="M4 18v-5a8 8 0 0 1 16 0v5"/><path d="M12 5v7"/><path d="M8 6v5"/>', 'graduation-cap': '<path d="m2 10 10-5 10 5-10 5-10-5Z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/><path d="M22 10v6"/>', 'calendar': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>', 'badge-check': '<path d="m12 2 3 2 4-.1.1 4 2 3-2 3-.1 4-4-.1-3 2-3-2-4 .1-.1-4-2-3 2-3 .1-4 4 .1 3-2Z"/><path d="m8 12 3 3 5-6"/>', 'file-check': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 15l2 2 4-4"/>', 'lightbulb': '<path d="M9 18h6M10 22h4M9 15c-2-1-3-3-3-6a6 6 0 0 1 12 0c0 3-1 5-3 6v3H9Z"/>', 'handshake': '<path d="m2 12 4-4 4 2 4-2 4 3 4-1"/><path d="m4 14 5 6 3-2 3 1 5-5"/><path d="m9 10 3-2 3 2"/>', 'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>', 'chart': '<path d="M3 3v18h18"/><path d="m7 16 4-5 3 2 5-8"/>', 'building': '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h2M14 7h2M8 11h2M14 11h2M10 21v-5h4v5"/>', 'clipboard': '<rect x="5" y="5" width="14" height="17" rx="2"/><rect x="9" y="2" width="6" height="5" rx="1"/><path d="M9 12h6M9 16h6"/>', 'users': '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M17 15a5 5 0 0 1 4 5"/>', 'coins': '<circle cx="12" cy="12" r="9"/><path d="M15 8.5c-1-1-5-1-6.2 1-1.4 2 1.2 3 3.2 3s4 1 3 3-5 2-6.2 1M12 6v12"/>', 'briefcase': '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>', 'search': '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>', 'alert': '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5M12 18h.01"/>', 'checklist': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="m7 9 2 2 3-4M14 9h4M7 16h11"/>', 'presentation': '<rect x="3" y="3" width="18" height="14" rx="2"/><path d="M12 17v4M8 21h8M7 13l3-3 3 2 4-4"/>', 'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>'}

def icono_ing(nombre, size='sm'):
    trazos = _ING_ICON_PATHS.get(nombre, _ING_ICON_PATHS['target'])
    return (f'<span class="ingico ingico-{size}" aria-hidden="true">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
            f'{trazos}</svg></span>')

def icono_kpi_ing(nombre):
    t = normal(nombre)
    reglas = [
        (('accidente','seguridad','siniestr'), 'hard-hat'),
        (('capacit','formacion','curso','competencia'), 'graduation-cap'),
        (('vacacion','ausent','permiso'), 'calendar'),
        (('sicep','certific','acredit','calidad','auditor'), 'badge-check'),
        (('proveedor','alianza','convenio'), 'handshake'),
        (('innovacion','desarrollo','mejora'), 'lightbulb'),
        (('lead','conversion','cotizacion','captacion'), 'target'),
        (('propuesta','licitacion','adjudic','oferta'), 'file-check'),
        (('contrato','document'), 'file'),
        (('presupuesto','costo','margen','ebit','venta','ingreso'), 'coins'),
        (('colaborador','personal','equipo','recurso humano'), 'users'),
        (('ingenieria','diseno','tecnic','plano'), 'building'),
        (('kom','reunion','hito','entrega','plazo','proyecto'), 'clipboard'),
        (('productividad','rendimiento','cumplimiento','avance'), 'chart'),
    ]
    for palabras, nombre_icono in reglas:
        if any(p in t for p in palabras):
            return icono_ing(nombre_icono)
    return icono_ing('target')

def icono_seccion_ing(nombre):
    t=normal(nombre)
    if 'panorama' in t or 'cumplimiento ingenieria' in t: return icono_ing('presentation')
    if 'seguimiento por frente' in t: return icono_ing('clipboard')
    if 'prioritario' in t or 'atencion' in t: return icono_ing('alert')
    if 'explorar' in t or 'detalle' in t: return icono_ing('search')
    if 'kpi del area' in t: return icono_ing('target')
    if 'propuestas' in t or 'adjudicaciones' in t: return icono_ing('file-check')
    if 'tecnico' in t: return icono_ing('badge-check')
    if 'innovacion' in t or 'proveedores' in t: return icono_ing('lightbulb')
    if 'lectura' in t: return icono_ing('chart')
    return icono_ing('chart')

CSS = '''<style>
.ing10-title{font-size:clamp(1.85rem,2.5vw,2.3rem);font-weight:850;
 letter-spacing:-.035em;color:#1D3551;line-height:1.16}
.ing10-sub{font-size:.9rem;color:#7488A1;margin-top:7px}
.ing10-header{display:flex;align-items:center;justify-content:space-between;
 gap:12px;flex-wrap:wrap;margin:2px 0 21px}
.ing10-date{border:1px solid #DBE5EE;background:white;color:#426280;
 border-radius:12px;padding:10px 14px;font-size:.82rem;font-weight:750}
.ing10-section{font-size:1.12rem;font-weight:820;color:#203A55;margin:25px 0 12px}
.ing10-muted{color:#8090A3;font-size:.77rem;line-height:1.45}
.ing10-summary{border:1px solid #DFE7EF;background:#fff;border-left:5px solid var(--c);
 padding:16px 17px;border-radius:15px;min-height:131px;margin-bottom:6px}
.ing10-summary-label{font-size:.8rem;font-weight:730;color:#647993}
.ing10-summary-value{font-size:clamp(1.65rem,2.0vw,2.1rem);font-weight:860;
 color:#1E3853;letter-spacing:-.025em;margin:12px 0 6px}
.ing10-summary-desc{font-size:.74rem;color:#7D90A4;line-height:1.4}
.ing10-feature{background:#fff;border:1px solid #DFE7EF;border-top:4px solid var(--c);
 border-radius:15px;padding:17px;min-height:196px;margin-bottom:8px}
.ing10-fname{font-size:.81rem;color:#314963;font-weight:810;line-height:1.38;
 min-height:37px;overflow-wrap:anywhere}
.ing10-fvalue{font-size:clamp(1.35rem,1.8vw,1.85rem);font-weight:860;
 color:#1B3753;letter-spacing:-.025em;margin:10px 0 5px;overflow-wrap:anywhere}
.ing10-meta{font-size:.76rem;color:#7B8FA5;margin-bottom:13px;overflow-wrap:anywhere}
.ing10-track{height:8px;border-radius:20px;background:#E8EFF5;overflow:hidden}
.ing10-fill{height:100%;background:var(--c);width:var(--w);display:block;border-radius:20px}
.ing10-footer{display:flex;align-items:center;justify-content:space-between;gap:6px;
 font-size:.73rem;font-weight:810;color:var(--c);margin-top:9px}
.ing10-block{background:#fff;border:1px solid #DEE7F0;border-radius:16px;
 padding:18px 18px 19px;margin-bottom:10px;min-height:302px}
.ing10-block-header{display:flex;align-items:flex-start;justify-content:space-between;
 gap:10px;margin-bottom:12px}
.ing10-block-title{font-size:.93rem;font-weight:820;color:#244260;line-height:1.38}
.ing10-pill{font-size:.69rem;white-space:nowrap;color:#5C7590;background:#F1F5F9;
 border-radius:999px;padding:5px 9px;font-weight:770}
.ing10-score{display:flex;align-items:baseline;justify-content:space-between;margin:8px 0;
 color:#2B465F;font-size:.74rem;font-weight:750}
.ing10-score b{font-size:1.45rem;color:var(--c);font-weight:870}
.ing10-mini{border-top:1px solid #EDF1F6;padding:12px 0 3px}
.ing10-mini-title{font-size:.79rem;color:#3A516B;font-weight:720;line-height:1.3}
.ing10-mini-sub{font-size:.71rem;color:#8A99AA;margin:5px 0 8px;line-height:1.35}
.ing10-mini-pct{font-size:.75rem;font-weight:830;color:var(--c)}
.ing10-alert{background:#fff;border:1px solid #DEE7EF;border-radius:15px;
 padding:18px 20px;min-height:215px;margin-bottom:12px}
.ing10-alert-title{font-size:.95rem;font-weight:830;color:#27415A;margin-bottom:12px}
.ing10-alert-row{padding:9px 0 10px;border-bottom:1px solid #ECF0F5}
.ing10-alert-row:last-child{border:0}
.ing10-alert-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.ing10-alert-name{font-size:.83rem;font-weight:750;color:#344C65;line-height:1.4}
.ing10-alert-pct{color:var(--c);font-size:.81rem;font-weight:830;white-space:nowrap}
.ing10-alert-sub{font-size:.72rem;color:#8A9AAD;margin-top:5px;line-height:1.45}
.ing10-badge{padding:5px 9px;background:#F3F7FA;border-radius:10px;
 color:#516F8A;font-size:.74rem;font-weight:720}

/* Tarjetas circulares de la referencia */
.ing10-feature.ing10-feature-ring{min-height:270px!important;height:270px!important;
 padding:21px!important;border:1px solid #DFE7EF!important;border-left:0!important;
 border-top:0!important;border-radius:21px!important;box-shadow:0 2px 8px rgba(20,42,77,.035)!important;
 display:flex;flex-direction:column;justify-content:space-between;margin:0 0 12px}
.ing10-feature-ring .ing10-fname{font-size:.87rem!important;color:#516580!important;
 font-weight:790!important;line-height:1.42!important;min-height:48px!important}
.ing10-card-main{display:grid;grid-template-columns:minmax(0,1fr) 98px;align-items:center;gap:8px;flex:1}
.ing10-card-numbers{min-width:0}
.ing10-feature-ring .ing10-fvalue{font-size:1.75rem!important;line-height:1.2!important;
 margin:0 0 8px!important;color:#142A4D!important}
.ing10-feature-ring .ing10-meta{font-size:.75rem!important;color:#8190A9!important;
 line-height:1.56!important;margin:0 0 3px!important}
.ing10-ring{width:96px;height:96px;display:grid;place-items:center;border-radius:50%;
 background:conic-gradient(var(--c) 0 var(--w),#E8EDF5 var(--w) 100%)}
.ing10-ring-hole{width:71px;height:71px;border-radius:50%;background:white;display:grid;
 place-items:center;font-size:.82rem;font-weight:850;color:#142A4D}
.ing10-card-tags{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-top:8px}
.ing10-status-pill{border-radius:999px;color:white;font-size:.76rem;font-weight:820;
 padding:7px 12px;line-height:1.15}
.ing10-weight-pill{border-radius:999px;background:#EDF2F8;color:#526987;
 font-size:.75rem;font-weight:790;padding:7px 11px;line-height:1.15}
@media(max-width:900px){.ing10-card-main{grid-template-columns:minmax(0,1fr) 78px}
 .ing10-ring{width:76px;height:76px}.ing10-ring-hole{width:56px;height:56px}}

/* Iconos integrados en los encabezados existentes: no cambian sus alturas ni columnas */
.ingico{display:inline-flex;vertical-align:middle;align-items:center;justify-content:center;flex:0 0 auto;width:27px;height:27px;border-radius:9px;background:#EEF4FF;color:#3167D0;margin-right:8px}
.ingico svg{width:17px;height:17px;display:block}
.ingico-lg{width:34px;height:34px;border-radius:11px;margin-right:10px}
.ingico-lg svg{width:20px;height:20px}
.ing10-fname,.ing10-mini-title,.ing10-block-title,.ing10-alert-title,.ing10-section,.ing10-visual-title,.ing10-title{display:flex;align-items:center;gap:0}
.ing10-fname .ingico{width:25px;height:25px;min-width:25px;margin-right:7px}
.ing10-mini-title .ingico{width:22px;height:22px;min-width:22px;margin-right:6px}
.ing10-block-title .ingico{min-width:27px}
.ing10-alert-title .ingico{min-width:27px}
</style>'''
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




st.markdown("""<style>
.ing10-title{font-size:2.1rem!important;color:#142A4D!important}
.ing10-visual-card{background:white;border:1px solid #E1E8F1;border-radius:16px;padding:20px;min-height:385px}
.ing10-visual-title{font-size:1rem;color:#142A4D;font-weight:800;margin:4px 0 17px}
.ing10-donut-row{display:flex;align-items:center;justify-content:space-around;gap:14px;flex-wrap:wrap}
.ing10-donut{width:175px;height:175px;flex-shrink:0;border-radius:50%;background:conic-gradient(var(--c) 0 var(--p),#E7ECF3 var(--p) 100%);display:grid;place-items:center}
.ing10-hole{width:125px;height:125px;border-radius:50%;display:grid;place-items:center;background:white;color:#142A4D;font-size:2rem;font-weight:850}
.ing10-legend{font-size:.81rem;color:#3F5572}.ing10-legend p{margin:9px 0}
.ing10-badge{border-radius:999px;padding:5px 10px;font-weight:800;display:inline-block}
.ing10-cut{display:inline-block;background:white;border:1px solid #E1E8F1;border-radius:12px;padding:9px 13px;color:#536A84;font-size:.82rem;margin:1px 0 12px}
.ing10-feature{border-top:0!important;border-left:5px solid var(--c)!important;box-shadow:0 2px 7px rgba(20,42,77,.035)}
.ing10-block,.ing10-alert,.ing10-summary{box-shadow:0 2px 7px rgba(20,42,77,.035)}
.ing10-feature .ing10-track,.ing10-mini .ing10-track{height:9px}
.ing10-fvalue{margin-top:14px!important}
</style>""",unsafe_allow_html=True)

@st.cache_data(ttl=90, show_spinner=False)
def responsables_globales_bsc():
    """Obtiene responsables existentes del BSC global (no inventa asignaciones de área)."""
    con = _conexion()
    try:
        sql = """
        SELECT fe.Fecha, k.CodigoKPI, r.NombreResponsable
        FROM dbo.FACT_KPI_ESTRATEGICO AS f
        JOIN dbo.DIM_KPI AS k ON k.KPI_Key = f.KPI_Key
        JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key = f.Fecha_Key
        JOIN dbo.DIM_RESPONSABLE AS r ON r.Responsable_Key = f.Responsable_Key
        WHERE f.Ambito = 'GLOBAL' AND f.FuenteResultado = 'BSC'
          AND k.TipoIndicador = 'OFICIAL_BSC'
        """
        return pd.read_sql_query(sql, con)
    finally:
        con.close()


def incorporar_responsables(df):
    """Prioriza responsable directo; si falta, usa el del mismo KPI global y fecha."""
    salida = df.copy()
    if 'NombreResponsable' not in salida.columns:
        salida['NombreResponsable'] = pd.NA
    try:
        globales = responsables_globales_bsc()
        globales['Fecha'] = pd.to_datetime(globales['Fecha'], errors='coerce').dt.normalize()
        globales = globales.dropna(subset=['Fecha', 'CodigoKPI'])
        globales = globales.drop_duplicates(['Fecha', 'CodigoKPI'], keep='last')
        salida['_fecha_responsable'] = pd.to_datetime(salida['Fecha'], errors='coerce').dt.normalize()
        salida = salida.merge(
            globales[['Fecha', 'CodigoKPI', 'NombreResponsable']].rename(
                columns={'Fecha': '_fecha_responsable', 'NombreResponsable': '_responsable_global'}),
            on=['_fecha_responsable', 'CodigoKPI'], how='left', sort=False, validate='many_to_one')
        salida['NombreResponsable'] = salida['NombreResponsable'].replace(r'^\s*$', pd.NA, regex=True).fillna(salida['_responsable_global'])
        salida = salida.drop(columns=['_fecha_responsable', '_responsable_global'])
    except Exception as e:
        # Mantener disponible el tablero, aunque falle la consulta suplementaria.
        st.warning(f'No se pudieron consultar responsables del BSC global: {e}')
        salida = salida.drop(columns=['_fecha_responsable', '_responsable_global'], errors='ignore')
    salida['NombreResponsable'] = salida['NombreResponsable'].fillna('—')
    return salida


def resumen_html(titulo, valor, nota, color):
    return (f'<div class="ing10-summary" style="--c:{color}">'
            f'<div class="ing10-summary-label">{esc(titulo)}</div>'
            f'<div class="ing10-summary-value">{esc(valor)}</div>'
            f'<div class="ing10-summary-desc">{esc(nota)}</div></div>')


def tarjeta_html(fila):
    """Tarjeta KPI con anillo circular y etiquetas, como la referencia."""
    cumplimiento = fila['Cumplimiento']
    co = tono(cumplimiento)
    etiqueta = {'Meta alcanzada': 'Cumple', 'En progreso': 'En riesgo',
                'Bajo cumplimiento': 'No cumple', 'Sin datos': 'Sin datos'}[estatus(cumplimiento)]
    pc = num(cumplimiento)
    avance = porcentaje(cumplimiento)
    interior = (f'{round(min(100, max(0, pc * 100)))}%' if math.isfinite(pc) else '—')
    peso = numero_local(fila.get('Ponderacion'), 0)
    return (f'<div class="ing10-feature ing10-feature-ring" style="--c:{co}">'
            f'<div class="ing10-fname">{icono_kpi_ing(fila["NombreKPI"])}{esc(fila["NombreKPI"])}</div>'
            '<div class="ing10-card-main"><div class="ing10-card-numbers">'
            f'<div class="ing10-fvalue">{esc(valor_bsc(fila))}</div>'
            f'<div class="ing10-meta">Meta anual: {esc(valor_bsc(fila, True))}</div>'
            f'<div class="ing10-meta">Avance de la meta:<br>{esc(avance)}</div>'
            '</div>'
            f'<div class="ing10-ring" style="--c:{co};--w:{barra(cumplimiento)}">'
            f'<div class="ing10-ring-hole">{interior}</div></div></div>'
            '<div class="ing10-card-tags">'
            f'<span class="ing10-status-pill" style="background:{co}">{esc(etiqueta)}</span>'
            f'<span class="ing10-weight-pill">Peso {esc(peso)}</span>'
            '</div></div>')


def frente_html(nombre, items):
    if items.empty:
        return (f'<div class="ing10-block"><div class="ing10-block-title">{icono_seccion_ing(nombre)}{esc(nombre)}</div>'
                '<p class="ing10-muted">No hay KPI de este frente en el corte actual.</p></div>')
    score = metricas(items)
    c = tono(score)
    s = (f'<div class="ing10-block"><div class="ing10-block-header">'
         f'<div class="ing10-block-title">{icono_seccion_ing(nombre)}{esc(nombre)}</div>'
         f'<div class="ing10-pill">{len(items)} KPI</div></div>'
         f'<div class="ing10-score" style="--c:{c}"><span>Cumplimiento ponderado</span>'
         f'<b>{esc(porcentaje(score))}</b></div>'
         f'<div class="ing10-track"><span class="ing10-fill" '
         f'style="--c:{c};--w:{barra(score)}"></span></div>')
    subset = items.sort_values('Ponderacion', ascending=False, na_position='last').head(3)
    for _, f in subset.iterrows():
        sem = tono(f['Cumplimiento'])
        s += (f'<div class="ing10-mini"><div class="ing10-alert-top">'
              f'<div class="ing10-mini-title">{icono_kpi_ing(f["NombreKPI"])}{esc(f["NombreKPI"])}</div>'
              f'<div class="ing10-mini-pct" style="--c:{sem}">{esc(porcentaje(f["Cumplimiento"]))}</div>'
              f'</div><div class="ing10-mini-sub">Resultado: {esc(valor_bsc(f))} · '
              f'Meta: {esc(valor_bsc(f, True))}</div></div>')
    return s + '</div>'


# Año antes del recorte al último BSC: así se podrán ver años futuros al cargarlos.
fuente = cargar('bsc')
if fuente.empty:
    st.title('Ingeniería y Propuestas')
    st.info('No hay indicadores BSC cargados.')
    st.stop()
fuente = fuente.copy()
fuente['Fecha'] = pd.to_datetime(fuente['Fecha'], errors='coerce')
anios_reales = fuente['Fecha'].dropna().dt.year.astype(int).unique().tolist()
anios = sorted(set(anios_reales) | set(range(2024, 2029)), reverse=True)
st.markdown(f'<div class="ing10-header"><div><div class="ing10-title">{icono_ing("building", "lg")}Ingeniería y Propuestas</div>'
            '<div class="ing10-sub">Proyectos, adjudicaciones y propuestas</div></div></div>',
            unsafe_allow_html=True)
with st.container(key='ing_filtros_blancos', border=True):
    col_anio, col_periodo, col_categoria, col_responsable = st.columns([.8, 1.4, 1.2, 1.2])
    with col_anio:
        anio_elegido = st.selectbox('Año', anios, index=anios.index(2026) if 2026 in anios else 0,
                                   key='ing_ref_anio')
    fuente_anual = fuente.loc[fuente['Fecha'].dt.year.eq(anio_elegido)].copy()
    if fuente_anual.empty:
        with col_periodo:
            st.selectbox('Período (fecha de corte)', ['Sin datos'], disabled=True)
        with col_categoria:
            st.selectbox('Categoría', ['Todas'], disabled=True)
        with col_responsable:
            st.selectbox('Responsable', ['Todos'], disabled=True)
        st.info(f'No hay información del área para {anio_elegido}. Al cargarla al BSC, aparecerá aquí automáticamente.')
        st.stop()
    fechas = sorted(fuente_anual['Fecha'].dropna().dt.normalize().unique(), reverse=True)
    etiquetas = ['Más reciente (' + pd.Timestamp(fechas[0]).strftime('%d/%m/%Y') + ')'] + [pd.Timestamp(f).strftime('%d/%m/%Y') for f in fechas[1:]]
    with col_periodo:
        periodo_elegido = st.selectbox('Período (fecha de corte)', etiquetas, key='ing_ref_fecha')
    fecha_elegida = pd.Timestamp(fechas[etiquetas.index(periodo_elegido)])
    fuente_corte = fuente_anual.loc[fuente_anual['Fecha'].dt.normalize().eq(fecha_elegida)].copy()
    # recortar_bsc preserva la lógica de área y KPI oficial del proyecto.
    df = recortar_bsc(fuente_corte, 'ingenieria')
    # El indicador de contratos superiores a 1.000 MM se gestiona en Contratos,
    # no en Ingeniería. Excluirlo antes de filtros, métricas, gráficas y tablas.
    if not df.empty:
        nombre_contrato = df['NombreKPI'].fillna('').astype(str).map(normal)
        excluido = nombre_contrato.eq('ganar 1 contrato sobre 1000mm')
        if 'CodigoKPI' in df.columns:
            excluido |= df['CodigoKPI'].fillna('').astype(str).eq('BSC_DEP_ING_13_CONTRATO_1000MM')
        df = df.loc[~excluido].copy()
    if df.empty:
        st.info('No hay KPI de Ingeniería para este período.')
        st.stop()
    df = incorporar_responsables(df.copy())
    with col_categoria:
        cats = ['Todas'] + sorted(df['CategoriaKPI'].dropna().astype(str).unique().tolist())
        cat_elegida = st.selectbox('Categoría', cats, key='ing_ref_cat')
    with col_responsable:
        resp = df.get('NombreResponsable', pd.Series(index=df.index, dtype=str)).fillna('—').astype(str)
        resps = ['Todos'] + sorted(resp.unique().tolist())
        resp_elegido = st.selectbox('Responsable', resps, key='ing_ref_resp')
    if cat_elegida != 'Todas':
        df = df.loc[df['CategoriaKPI'].astype(str).eq(cat_elegida)]
    if resp_elegido != 'Todos':
        df = df.loc[resp.loc[df.index].eq(resp_elegido)]
    if df.empty:
        st.info('No hay KPI para estos filtros.')
        st.stop()
df['Cumplimiento'] = pd.to_numeric(df['Cumplimiento'], errors='coerce')
df['Ponderacion'] = pd.to_numeric(df['Ponderacion'], errors='coerce')
df['CategoriaKPI'] = df['CategoriaKPI'].fillna('Sin categoría').astype(str)
df['NombreKPI'] = df['NombreKPI'].fillna('Sin nombre').astype(str)
df['Frente'] = df.apply(familia, axis=1)
fecha = pd.to_datetime(df['Fecha'].max(), errors='coerce')
corte = fecha.strftime('%d/%m/%Y') if pd.notna(fecha) else 'Sin fecha'
validos = df[df['Cumplimiento'].notna()]
al_dia = int((validos['Cumplimiento'] >= 1).sum())
progreso = int(((validos['Cumplimiento'] >= .7) & (validos['Cumplimiento'] < 1)).sum())
criticos = int((validos['Cumplimiento'] < .7).sum())
sin_datos = int(df['Cumplimiento'].isna().sum())
puntaje = metricas(df)

st.markdown(f'<div class="ing10-cut">📅 Datos al {esc(corte)}</div>', unsafe_allow_html=True)

# Resumen visual del estilo de referencia: anillo y evolución por KPI.
st.markdown(f'<div class="ing10-section">{icono_ing("presentation")}Panorama de Ingeniería</div>', unsafe_allow_html=True)
izq_vis, der_vis = st.columns([1, 1.55], gap='medium')
with izq_vis:
    st.markdown(f'''<div class="ing10-visual-card">
      <div class="ing10-visual-title">{icono_ing("target")}Cumplimiento Ingeniería</div>
      <div class="ing10-donut-row">
        <div class="ing10-donut" style="--c:{tono(puntaje)};--p:{barra(puntaje)}">
          <div class="ing10-hole">{esc(porcentaje(puntaje, 0))}</div>
        </div>
        <div class="ing10-legend">
          <div class="ing10-badge" style="background:{tono(puntaje)}22;color:{tono(puntaje)}">{esc(estatus(puntaje))}</div>
          <p>🟢 Cumple: <b>{al_dia}</b></p><p>🟡 En progreso: <b>{progreso}</b></p>
          <p>🔴 No cumple: <b>{criticos}</b></p><p>⚪ Sin datos: <b>{sin_datos}</b></p>
        </div>
      </div>
    </div>''', unsafe_allow_html=True)
with der_vis:
    st.markdown(f'<div class="ing10-visual-title">{icono_ing("chart")}¿Cómo vamos en los KPI que cuentan para Ingeniería?</div>', unsafe_allow_html=True)
    graf = df.loc[df['Cumplimiento'].notna() & (df['Ponderacion'] > 0)].copy()
    graf = graf.sort_values('Ponderacion', ascending=False).head(9).iloc[::-1]
    if not graf.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(y=graf['NombreKPI'].str.slice(0, 42),
                             x=(graf['Cumplimiento'].clip(lower=0, upper=1.3)*100),
                             orientation='h', marker_color=[tono(v) for v in graf['Cumplimiento']],
                             text=[porcentaje(v, 0) for v in graf['Cumplimiento']],
                             textposition='outside', hovertemplate='%{y}<br>%{x:.0f}%<extra></extra>'))
        fig.add_vline(x=100, line_width=2, line_color='#183454')
        fig.update_layout(height=355, margin=dict(l=10,r=20,t=12,b=35),
                          paper_bgcolor='white', plot_bgcolor='white', showlegend=False,
                          xaxis=dict(title=None, ticksuffix='%', range=[0,145],
                                     gridcolor='#E8EDF4'),
                          yaxis=dict(title=None, tickfont=dict(size=11)))
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info('Sin KPI evaluables para representar.')

# Sin tarjetas de resumen duplicadas: se conservan las tarjetas KPI inferiores.

# Ocho KPI en tarjetas circulares, respetando los datos y pesos del corte.
st.markdown(f'<div class="ing10-section">{icono_ing("target")}KPI del área (de mayor a menor peso)</div>', unsafe_allow_html=True)
preferidos = [
    ('colaboradores capacitados',),
    ('horas de capacitacion',),
    ('vacaciones',),
    ('tasa de accidentes',),
    ('avance certificacion sicep',),
    ('conversion de leads',),
    ('innovacion ejecutada',),
    ('alianzas con proveedores',),
]
seleccion = []
usados = set()
for opciones in preferidos:
    for idx, fila in df.iterrows():
        if idx not in usados and any(op in normal(fila['NombreKPI']) for op in opciones):
            seleccion.append(fila)
            usados.add(idx)
            break
for idx, fila in df.sort_values('Ponderacion', ascending=False, na_position='last').iterrows():
    if len(seleccion) >= 8:
        break
    if idx not in usados:
        seleccion.append(fila)
        usados.add(idx)
for inicio in range(0, len(seleccion), 4):
    for col, fila in zip(st.columns(4, gap='medium'), seleccion[inicio:inicio + 4]):
        with col:
            st.markdown(tarjeta_html(fila), unsafe_allow_html=True)

# Tres agrupaciones diseñadas para Ingeniería, no copias de las otras páginas.
st.markdown(f'<div class="ing10-section">{icono_ing("clipboard")}Seguimiento por frente de trabajo</div>', unsafe_allow_html=True)
for col, nombre in zip(st.columns(3, gap='medium'), GRUPOS):
    with col:
        st.markdown(frente_html(nombre, df[df['Frente'].eq(nombre)]), unsafe_allow_html=True)

st.markdown(f'<div class="ing10-section">{icono_ing("alert")}¿Qué necesita atención?</div>', unsafe_allow_html=True)
izquierda, derecha = st.columns([1.35, .9], gap='medium')
with izquierda:
    # Las brechas son un ordenamiento derivado, NO otro KPI oficial.
    pendientes = df.loc[(df['Cumplimiento'].notna()) &
                        (df['Cumplimiento'] < 1) & (df['Ponderacion'] > 0)].copy()
    pendientes['Brecha'] = (1 - pendientes['Cumplimiento'].clip(lower=0, upper=1)) * pendientes['Ponderacion']
    pendientes['EsPropio'] = pendientes['Frente'].isin(GRUPOS)
    pendientes = pendientes.sort_values(['EsPropio', 'Brecha'], ascending=False)
    items = ''
    for i, (_, row) in enumerate(pendientes.head(5).iterrows(), 1):
        c = tono(row['Cumplimiento'])
        items += (f'<div class="ing10-alert-row"><div class="ing10-alert-top">'
                  f'<div class="ing10-alert-name">{i}. {esc(row["NombreKPI"])}</div>'
                  f'<div class="ing10-alert-pct" style="--c:{c}">{esc(porcentaje(row["Cumplimiento"]))}</div>'
                  f'</div><div class="ing10-alert-sub">{esc(valor_bsc(row))} de '
                  f'{esc(valor_bsc(row, True))} · Peso: {esc(numero_local(row["Ponderacion"], 0))}'
                  f' · {esc(row["Frente"])}</div><div class="ing10-alert-track"><span style="width:{barra(row["Cumplimiento"])};background:{c}"></span></div></div>')
    st.markdown(f'<div class="ing10-alert ing10-alert-focus"><div class="ing10-alert-title">{icono_ing("alert")}KPI prioritarios que requieren seguimiento</div><div class="ing10-alert-help">Ordenados por impacto en el cumplimiento del área</div>' +
                (items or '<div class="ing10-muted">No hay KPI evaluables por debajo de su meta.</div>') +
                '</div>', unsafe_allow_html=True)
with derecha:
    propios = df[df['Frente'].isin(GRUPOS)]
    st.markdown(f'<div class="ing10-alert"><div class="ing10-alert-title">{icono_ing("chart")}Lectura rápida del área</div>'
                f'<div class="ing10-mini"><div class="ing10-alert-top"><div class="ing10-mini-title">KPI propios de Ingeniería</div>'
                f'<span class="ing10-badge">{len(propios)}</span></div></div>'
                f'<div class="ing10-mini"><div class="ing10-alert-top"><div class="ing10-mini-title">Indicadores transversales</div>'
                f'<span class="ing10-badge">{len(df) - len(propios)}</span></div></div>'
                f'<div class="ing10-mini"><div class="ing10-alert-top"><div class="ing10-mini-title">KPI marcados SACAR en origen</div>'
                f'<span class="ing10-badge">{int(df["EstadoRevision"].fillna("").astype(str).str.contains("SACAR", case=False).sum())}</span></div></div>'
                '<div class="ing10-mini"><div class="ing10-muted">Los KPI transversales se conservan en la tabla inferior, '
                'pero las alertas priorizan los indicadores propios del departamento.</div></div></div>',
                unsafe_allow_html=True)

# Herramienta: busca, filtra y examina sin sobrecargar la portada.
st.markdown(f'<div class="ing10-section">{icono_ing("search")}Explorar indicadores de Ingeniería</div>', unsafe_allow_html=True)
a, b, c = st.columns([1.2, .9, 1.25], gap='medium')
with a:
    grupo_sel = st.selectbox('Frente de trabajo', ['Todos'] + GRUPOS + ['Indicadores transversales'], key='ing10_frente')
with b:
    estado_sel = st.selectbox('Semáforo', ['Todos', 'Meta alcanzada', 'En progreso',
                                         'Bajo cumplimiento', 'Sin datos'], key='ing10_estado')
with c:
    busca = st.text_input('Buscar KPI', placeholder='Escribe el nombre del indicador', key='ing10_buscar')

consulta = df.copy()
if grupo_sel != 'Todos':
    consulta = consulta[consulta['Frente'].eq(grupo_sel)]
if estado_sel != 'Todos':
    consulta = consulta[consulta['Cumplimiento'].map(estatus).eq(estado_sel)]
if busca.strip():
    consulta = consulta[consulta['NombreKPI'].str.contains(busca.strip(), case=False, regex=False, na=False)]

if consulta.empty:
    st.info('No hay indicadores con estos filtros.')
else:
    # Exportación con las mismas columnas y el mismo orden de la tabla visible.
    tabla = consulta.copy()
    tabla['Estado'] = tabla['Cumplimiento'].map(estatus)
    tabla['Meta anual'] = tabla.apply(lambda fila: valor_bsc(fila, True), axis=1)
    tabla['Actual'] = tabla.apply(valor_bsc, axis=1)
    tabla['Cumplimiento'] = tabla['Cumplimiento'].map(porcentaje)
    tabla['Resp.'] = tabla['NombreResponsable'].fillna('—')
    tabla = tabla[['Estado', 'NombreKPI', 'CategoriaKPI', 'Meta anual', 'Actual',
                   'Cumplimiento', 'Resp.', 'Ponderacion']].rename(columns={
                       'NombreKPI': 'KPI', 'CategoriaKPI': 'Categoría',
                       'Ponderacion': 'Peso'})
    # Tabla HTML para colorear cada barra según su propio tramo de cumplimiento.
    celdas = []
    for _, fila_tabla in consulta.iterrows():
        progreso_kpi = fila_tabla['Cumplimiento']
        co = tono(progreso_kpi)
        relleno = barra(progreso_kpi)
        estado_kpi = estatus(progreso_kpi)
        indicador = esc(fila_tabla['NombreKPI'])
        categoria = esc(fila_tabla.get('CategoriaKPI'))
        res = esc(valor_bsc(fila_tabla))
        meta = esc(valor_bsc(fila_tabla, True))
        peso = esc(numero_local(fila_tabla['Ponderacion'], 1))
        responsable = esc(fila_tabla.get('NombreResponsable') if pd.notna(fila_tabla.get('NombreResponsable')) and str(fila_tabla.get('NombreResponsable')).strip() else '—')
        celdas.append(
            f'<tr><td class="ing10-state-cell"><span class="ing10-dot" style="background:{co}" title="{esc(estado_kpi)}" aria-label="{esc(estado_kpi)}"></span></td>'
            f'<td>{indicador}</td><td>{categoria}</td><td>{meta}</td><td>{res}</td>'
            f'<td><div class="ing10-table-progress"><div class="ing10-table-track">'
            f'<span style="width:{relleno};background:{co}"></span></div>'
            f'<strong style="color:{co}">{esc(porcentaje(progreso_kpi))}</strong></div></td>'
            f'<td>{responsable}</td><td>{peso}</td></tr>'
        )
    tabla_html = (
        '<div class="ing10-table-scroll"><table class="ing10-table"><thead><tr>'
        '<th>Estado</th><th>KPI</th><th>Categoría</th><th>Meta anual</th><th>Actual</th>'
        '<th>Cumplimiento</th><th>Resp.</th><th>Peso</th>'
        '</tr></thead><tbody>' + ''.join(celdas) + '</tbody></table></div>'
    )
    st.markdown('**Detalle de KPI del área**', unsafe_allow_html=True)
    st.markdown(tabla_html, unsafe_allow_html=True)
    st.caption('Tabla actualizada · Estado | KPI | Categoría | Meta anual | Actual | Cumplimiento | Resp. | Peso')
    st.download_button('⬇️ Exportar indicadores filtrados (CSV)',
                       tabla.to_csv(index=False, sep=';').encode('utf-8-sig'),
                       file_name='ingenieria_kpis_maas.csv', mime='text/csv', key='ing10_exportar')

st.markdown("""<style>
/* KPI cards: bordes suaves, jerarquía clara y estado coloreado sin barras rojas fijas */
.ing10-feature{border:1px solid #DFE7EF!important;border-left:5px solid var(--c)!important;
 border-radius:19px!important;min-height:226px!important;padding:20px!important;
 box-shadow:0 4px 18px rgba(20,42,77,.055)!important;
 display:flex;flex-direction:column;justify-content:space-between}
.ing10-fname{font-size:.88rem!important;color:#253D5B!important;line-height:1.4!important}
.ing10-fvalue{font-size:2.05rem!important;color:#172F51!important;margin:12px 0 3px!important}
.ing10-meta{font-size:.8rem!important}
.ing10-feature .ing10-track{height:11px!important;background:#EAF0F6!important}
.ing10-footer{font-size:.79rem!important;border-top:1px solid #EFF2F6;padding-top:10px}
.ing10-alert-focus{background:#FFF8F8!important;border-color:#F1D7D7!important;
 border-left:5px solid #D75A60!important;box-shadow:0 4px 14px rgba(172,67,74,.035)!important}
.ing10-alert-title{font-size:1.03rem!important;color:#193454!important}
.ing10-alert-help{color:#8492A7;font-size:.77rem;margin:-5px 0 13px}
.ing10-alert-row{padding:13px 0 16px!important}
.ing10-alert-name{font-size:.87rem!important;color:#1E3956!important}
.ing10-alert-pct{font-size:.88rem!important}
.ing10-alert-track{background:#EBEFF5;height:8px;border-radius:20px;overflow:hidden;margin-top:10px}
.ing10-alert-track span{height:100%;display:block;border-radius:20px}
.ing10-table-scroll{max-height:560px;overflow:auto;border-radius:16px;border:1px solid #E0E7F0;background:white}
.ing10-table{border-collapse:collapse;width:100%;font-size:.84rem;min-width:980px;table-layout:auto}
.ing10-table th{position:sticky;top:0;z-index:1;background:#F7F9FC;color:#536B85;text-align:left;
 padding:13px 12px;font-weight:790;border-bottom:1px solid #D8E3EF}
.ing10-table td{padding:14px 12px;border-bottom:1px solid #EDF1F6;color:#253B59;vertical-align:middle}
.ing10-table tbody tr:hover{background:#F8FAFD}
.ing10-dot{width:14px;height:14px;border-radius:50%;display:inline-block;vertical-align:middle}
.ing10-state-cell{width:64px;min-width:64px;text-align:center!important}
.ing10-table th:first-child{width:64px;min-width:64px;text-align:center}
.ing10-state{font-size:.75rem;font-weight:750;white-space:nowrap}
.ing10-table-progress{display:flex;align-items:center;gap:10px;min-width:190px}
.ing10-table-track{height:9px;background:#EBF0F6;flex:1;border-radius:15px;overflow:hidden}
.ing10-table-track span{display:block;height:100%;border-radius:15px}
.ing10-table-progress strong{min-width:43px;text-align:right;font-size:.75rem}
.ing10-table th:last-child,.ing10-table td:last-child{text-align:right;white-space:nowrap}
</style>""", unsafe_allow_html=True)




