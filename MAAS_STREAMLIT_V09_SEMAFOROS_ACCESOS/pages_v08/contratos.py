# -*- coding: utf-8 -*-
"""MAAS ECOLOGÍA 4 · Contratos y Negocios · V10.

PARA INSTALAR: reemplazar únicamente pages_v08/contratos.py.
Requiere los módulos maas_auth, maas_datos y maas_ui ya instalados en V09.
Este archivo NO modifica la base, el ETL, usuarios ni otras pestañas.

Datos del último corte del BSC departamental de Contratos y Negocios.
Facturación neta 2026: reporte de facturas, FUENTE DIFERENTE del BSC.
Semáforos VISUALES: rojo <70%, amarillo 70% a <100%, verde >=100%.
No interpretar la meta anual como una proyección a la fecha del corte.
"""
from __future__ import annotations

# Acceso basado en la sesión del portal MAAS (no en el perfil de esta página).
# Validar ANTES de consultar datos de SQL Server.
import streamlit as st
_rol_maas = st.session_state.get('maas_portal_perfil')
if not (st.session_state.get('maas_portal_autorizado') is True
        and _rol_maas in {'administracion', 'gerencia', 'operaciones'}):
    st.error('Tu sesión no tiene autorización para esta pestaña.')
    st.stop()

from html import escape
import math
import unicodedata

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from maas_datos import cargar
from maas_ui import metricas, presentacion_valor, recortar_bsc

# Antes de obtener información desde SQL.
pass  # Acceso libre MAAS 4

VERDE = '#48A374'
AMARILLO = '#E7B341'
ROJO = '#D75B60'
GRIS = '#9CAEC0'
AZUL = '#213E5B'
FRENTES = ['Clientes y conversión', 'Adjudicaciones y licitaciones', 'Resultados del negocio']


def n(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else float('nan')
    except (TypeError, ValueError):
        return float('nan')


def limpio(v):
    if v is None:
        return ''
    try:
        if pd.isna(v):
            return ''
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def h(v):
    return escape(limpio(v), quote=True)


def norm(v):
    t = unicodedata.normalize('NFKD', limpio(v))
    return ' '.join(''.join(c for c in t if not unicodedata.combining(c)).casefold().split())


def local(x, dec=1):
    value = n(x)
    if not math.isfinite(value):
        return '—'
    return f'{value:,.{dec}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def moneda(v):
    value = n(v)
    return '$' + f'{round(value):,}'.replace(',', '.') if math.isfinite(value) else '—'


def porcentaje(v):
    value = n(v)
    return local(value * 100, 1) + '%' if math.isfinite(value) else '—'


def semaforo(v):
    value = n(v)
    if not math.isfinite(value):
        return 'Sin datos', GRIS, '⚪'
    if value >= 1:
        return 'Meta alcanzada', VERDE, '🟢'
    if value >= .7:
        return 'En progreso', AMARILLO, '🟡'
    return 'Bajo cumplimiento', ROJO, '🔴'


def ancho(v):
    value = n(v)
    return f'{max(0., min(100., value * 100)):.1f}%' if math.isfinite(value) else '0%'


def texto_bsc(fila, meta=False):
    num = fila.get('MetaNumerica' if meta else 'ResultadoNumerico')
    texto = fila.get('MetaTexto' if meta else 'ResultadoTexto')
    unidad = fila.get('UnidadMedida')
    # El BSC registra VENTAS 2026 en miles de pesos; el reporte de facturas,
    # en cambio, guarda pesos CLP completos. Nunca mezclar unidades.
    u = norm(unidad)
    if 'miles' in u and ('clp' in u or '$' in u):
        return moneda(n(num) * 1000) if math.isfinite(n(num)) else (limpio(texto) or 'Sin dato')
    return presentacion_valor(num, texto, unidad)


def frente(fila):
    """Clasificación exclusivamente visual, no cambia el KPI en el BSC."""
    nombre = norm(fila.get('NombreKPI'))
    if any(p in nombre for p in (
        'adjudicada', 'adjudicacion', 'licitacion', 'andina faena',
        'andina externos', 'fundacion mlp', 'doh', 'mlp-faena', 'mlp faena',
    )):
        return FRENTES[1]
    if any(p in nombre for p in (
        'nuevos clientes', 'conversion de leads', 'conversion leads', 'cotizacion',
        'prospeccion', 'contrato', 'satisfaccion de cliente',
    )):
        return FRENTES[0]
    if any(p in nombre for p in ('venta', 'margen', 'productividad salarial', 'ebit')):
        return FRENTES[2]
    return 'Otros indicadores BSC'


# Iconos lineales azules; se utilizan solo en la presentacion.
_CT_ICONOS = {
    'contrato': '<path d="M6 2h9l5 5v15H6z"/><path d="M15 2v5h5M9 12h8m-8 4h8"/>',
    'filtro': '<path d="M4 5h16l-6 7v7l-4 2v-9z"/>',
    'objetivo': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    'alerta': '<path d="m12 3 10 18H2z"/><path d="M12 9v5m0 3v.5"/>',
    'cartera': '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
    'personas': '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m1 4a5 5 0 0 1 4 5"/>',
    'grafico': '<path d="M3 20h18M6 17v-5m6 5V7m6 10v-9"/>',
    'acuerdo': '<path d="m2 12 4-4 4 2 4-2 8 6-5 5-3-2-3 2-5-4z"/><path d="m10 10 3 3"/>',
    'calendario': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
    'dinero': '<circle cx="12" cy="12" r="9"/><path d="M12 6v12m3-9c-1-2-6-2-6 .5s6 1 6 4-5 3-6 1"/>',
    'lista': '<path d="M8 6h13M8 12h13M8 18h13M3 6h.1M3 12h.1M3 18h.1"/>',
}

def ct_icono(tipo, tam=19):
    trazos = _CT_ICONOS.get(tipo, _CT_ICONOS['contrato'])
    return (f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24" fill="none" '
            f'stroke="#326BC3" stroke-width="1.85" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{trazos}</svg>')


def ct_icono_kpi(nombre):
    nombre = norm(nombre)
    if any(x in nombre for x in ('csat', 'satisfaccion', 'cliente')): return 'personas'
    if any(x in nombre for x in ('margen', 'ebit', 'rentabilidad', 'costo')): return 'dinero'
    if any(x in nombre for x in ('licitacion', 'adjudicacion', 'propuesta')): return 'acuerdo'
    if any(x in nombre for x in ('conversion', 'leads', 'meta')): return 'objetivo'
    if any(x in nombre for x in ('contrato', 'oc ')): return 'contrato'
    return 'grafico'


def ct_titulo(texto, icono):
    return '<div class="ct10-section ct-v-title"><span class="ct-v-icon">'+ct_icono(icono)+'</span>'+h(texto)+'</div>'


def ct_fecha(valor):
    fecha = pd.to_datetime(valor, errors='coerce')
    return fecha.strftime('%d/%m/%Y') if pd.notna(fecha) else '—'

CSS = '''<style>
.ct10-head{display:flex;justify-content:space-between;align-items:center;
 gap:14px;flex-wrap:wrap;margin:4px 0 19px}
.ct10-title{font-size:clamp(1.85rem,2.6vw,2.35rem);font-weight:850;
 color:#1C3652;letter-spacing:-.035em;line-height:1.17}
.ct10-sub{color:#7689A0;font-size:.89rem;margin-top:7px}
.ct10-cut{background:#fff;border:1px solid #DDE6EF;border-radius:12px;
 padding:11px 14px;color:#4C6B86;font-size:.8rem;font-weight:750}
.ct10-section{font-size:1.12rem;font-weight:820;color:#26415C;margin:25px 0 12px}
.ct10-tile{background:#fff;border:1px solid #DEE7EF;border-left:5px solid var(--co);
 border-radius:15px;padding:17px;min-height:128px;margin-bottom:8px}
.ct10-label{font-size:.81rem;color:#576D86;font-weight:730;line-height:1.3}
.ct10-number{font-size:clamp(1.6rem,2.15vw,2.2rem);font-weight:850;
 color:#1B3955;margin:11px 0 6px;letter-spacing:-.035em}
.ct10-muted{font-size:.74rem;color:#8495A7;line-height:1.45}
.ct10-feature{background:#fff;border:1px solid #DBE5EF;border-top:4px solid var(--co);
 border-radius:15px;padding:16px 17px;min-height:207px;margin-bottom:8px}
.ct10-feature-name{color:#344C65;font-weight:800;font-size:.82rem;
 line-height:1.35;min-height:39px;overflow-wrap:anywhere}
.ct10-feature-num{color:#1A3653;font-size:clamp(1.45rem,1.9vw,1.9rem);
 font-weight:850;margin:11px 0 5px;overflow-wrap:anywhere}
.ct10-feature-meta{color:#8092A5;font-size:.77rem;margin-bottom:14px}
.ct10-track{height:8px;border-radius:10px;background:#EAF0F5;overflow:hidden}
.ct10-fill{display:block;background:var(--co);height:100%;width:var(--width);border-radius:10px}
.ct10-foot{display:flex;justify-content:space-between;align-items:center;
 font-size:.75rem;font-weight:820;color:var(--co);margin-top:10px;gap:8px}
.ct10-panel{background:#fff;border:1px solid #DEE7EF;border-radius:15px;
 padding:19px;min-height:270px;margin-bottom:10px}
.ct10-phead{display:flex;justify-content:space-between;align-items:start;gap:8px;margin-bottom:14px}
.ct10-ptitle{font-size:.94rem;font-weight:810;color:#27435E;line-height:1.4}
.ct10-badge{background:#F0F5F9;color:#65809A;border-radius:99px;
 padding:5px 9px;font-size:.7rem;font-weight:740;white-space:nowrap}
.ct10-line{border-top:1px solid #EDF1F5;padding:11px 0}
.ct10-line:first-child{border-top:0}
.ct10-linehead{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.ct10-lname{font-weight:730;color:#3A526A;font-size:.8rem;line-height:1.3}
.ct10-lpct{font-size:.78rem;font-weight:850;color:var(--co);white-space:nowrap}
.ct10-info{color:#8395A8;font-size:.73rem;margin:6px 0 9px;line-height:1.45}
.ct10-salegrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.ct10-money{font-weight:850;color:#1D3B58;font-size:clamp(1.3rem,1.9vw,1.8rem);margin:10px 0}
.ct10-sale-label{font-size:.81rem;font-weight:780;color:#506B84}
.ct10-note{color:#8797A8;font-size:.75rem;line-height:1.55;margin-top:7px}
.ct10-empty{color:#8396A8;font-size:.82rem;line-height:1.55;padding:12px 0}
@media(max-width:750px){.ct10-salegrid{grid-template-columns:1fr}}
</style>'''
st.markdown(CSS, unsafe_allow_html=True)

# Tarjetas armonizadas con Inicio: bordes neutros, anillos y etiquetas suaves.
st.markdown("""<style>
.ct10-tile{background:#fff!important;border:1px solid #E0E8F1!important;border-radius:18px!important;
  min-height:145px!important;padding:17px 19px!important;box-shadow:0 3px 12px rgba(17,44,79,.04)!important}
.ct10-label{font-size:.82rem!important;color:#405B77!important}
.ct10-number{color:#142A4D!important;font-size:clamp(1.45rem,2vw,1.85rem)!important;margin:12px 0 6px!important}
.ct10-feature.ct-home-card{height:230px!important;min-height:230px!important;
  background:#fff!important;border:1px solid #DFE7F1!important;border-radius:19px!important;
  box-shadow:0 3px 12px rgba(17,44,79,.045)!important;display:flex!important;
  flex-direction:column!important;justify-content:space-between!important;padding:16px 17px!important}
.ct-home-card .ct10-feature-name{color:#263F62!important;font-weight:790!important;
  font-size:.83rem!important;line-height:1.35!important;min-height:38px!important}
.ct-home-middle{display:grid;grid-template-columns:minmax(0,1fr) 77px;gap:7px;align-items:center;flex:1;min-width:0}
.ct-home-values{min-width:0}
.ct-home-card .ct10-feature-num{color:#142A4D!important;font-size:clamp(1.13rem,1.65vw,1.58rem)!important;
  font-weight:880!important;margin:5px 0 5px!important;line-height:1.2!important}
.ct-home-card .ct10-feature-meta{color:#8595AB!important;font-size:.75rem!important;line-height:1.4!important;
  margin:0!important}
.ct-home-ring{width:76px;height:76px;border-radius:50%;background:conic-gradient(var(--co) 0 var(--pct),#E7ECF3 var(--pct) 100%);
  display:grid;place-items:center;flex-shrink:0}
.ct-home-hole{width:56px;height:56px;border-radius:50%;background:#fff;display:grid;place-items:center;
  color:#142A4D;font-size:.8rem;font-weight:850}
.ct-home-foot{display:flex;gap:7px;align-items:center;flex-wrap:wrap;min-height:27px}
.ct-home-status{background:color-mix(in srgb,var(--co) 13%,#fff);color:var(--co);
  padding:5px 10px;border-radius:999px;font-size:.72rem;font-weight:800}
.ct-home-weight{color:#294263;background:#EAF0F8;padding:5px 10px;border-radius:999px;
  font-size:.72rem;font-weight:790}
@media(max-width:900px){.ct-home-middle{grid-template-columns:minmax(0,1fr) 67px}
 .ct-home-ring{width:65px;height:65px}.ct-home-hole{width:48px;height:48px}}
</style>""", unsafe_allow_html=True)



def tarjeta_resumen(titulo, valor, detalle, co):
    return (f'<div class="ct10-tile" style="--co:{co}">'
            f'<div class="ct10-label ct-v-flex"><span class="ct-v-icon">{ct_icono(ct_icono_kpi(titulo))}</span>{h(titulo)}</div>'
            f'<div class="ct10-number">{h(valor)}</div>'
            f'<div class="ct10-muted">{h(detalle)}</div></div>')


def tarjeta_indicador(f):
    """Mismo lenguaje visual de las tarjetas circulares de Inicio."""
    nombre_estado, co, _ = semaforo(f['Cumplimiento'])
    valor = n(f['Cumplimiento'])
    tramo = max(0., min(100., valor * 100)) if math.isfinite(valor) else 0.
    cifra_anillo = f'{round(tramo)}%' if math.isfinite(valor) else '—'
    return (
        f'<div class="ct10-feature ct-home-card" style="--co:{co};--pct:{tramo:.2f}%">'
        f'<div class="ct10-feature-name ct-v-flex"><span class="ct-v-icon">{ct_icono(ct_icono_kpi(f["NombreKPI"]))}</span>'
        f'{h(f["NombreKPI"])}</div>'
        '<div class="ct-home-middle"><div class="ct-home-values">'
        f'<div class="ct10-feature-num">{h(texto_bsc(f))}</div>'
        f'<div class="ct10-feature-meta">Meta anual: {h(texto_bsc(f, True))}</div>'
        '</div>'
        f'<div class="ct-home-ring"><div class="ct-home-hole">{cifra_anillo}</div></div></div>'
        '<div class="ct-home-foot">'
        f'<span class="ct-home-status" style="--co:{co}">{h(nombre_estado)}</span>'
        f'<span class="ct-home-weight">Peso {h(local(f.get("Ponderacion"),0))}</span>'
        '</div></div>'
    )


def html_frente(nombre, filas):
    salida = (f'<div class="ct10-panel"><div class="ct10-phead">'
              f'<span class="ct10-ptitle ct-v-flex"><span class="ct-v-icon">{ct_icono(ct_icono_kpi(nombre))}</span>{h(nombre)}</span>'
              f'<span class="ct10-badge">{len(filas)} KPI</span></div>')
    if filas.empty:
        return salida + '<div class="ct10-empty">Sin KPI de este grupo en el corte seleccionado.</div></div>'
    # Priorizar peso BSC y relevancia; no sumar adjudicaciones de distintas licitaciones.
    for _, f in filas.sort_values('Ponderacion', ascending=False, na_position='last').head(4).iterrows():
        _, co, _ = semaforo(f['Cumplimiento'])
        salida += (f'<div class="ct10-line"><div class="ct10-linehead">'
                   f'<div class="ct10-lname">{h(f["NombreKPI"])}</div>'
                   f'<span class="ct10-lpct" style="--co:{co}">{h(porcentaje(f["Cumplimiento"]))}</span>'
                   f'</div><div class="ct10-info">{h(texto_bsc(f))} / Meta: {h(texto_bsc(f, True))}</div>'
                   f'<div class="ct10-track"><span class="ct10-fill" '
                   f'style="--co:{co};--width:{ancho(f["Cumplimiento"])}"></span></div></div>')
    return salida + '</div>'


def es_kpi_adjudicaciones(nombre):
    """Busca el indicador solicitado sin confundirlo con adjudicaciones puntuales."""
    t = norm(nombre)
    return ('adjudicacion' in t or 'adjudicadas' in t) and (
        'propuesta' in t or 'ofertada' in t) and (
        'porcentaje' in t or ' vs ' in f' {t} ' or 'v/s' in t or 'tasa' in t)


def buscar_cuatro(df):
    """Prioriza el KPI de adjudicaciones sin rellenar con indicadores ajenos."""
    prioridades = [
        lambda nombre: es_kpi_adjudicaciones(nombre),
        lambda nombre: 'conversion de leads' in norm(nombre) or 'conversion leads' in norm(nombre),
        lambda nombre: 'csat contratos' in norm(nombre),
        lambda nombre: 'nuevos clientes' in norm(nombre),
    ]
    usados = set()
    resultado = []
    for coincide in prioridades:
        for idx, fila in df.iterrows():
            if idx not in usados and coincide(fila['NombreKPI']):
                resultado.append(fila)
                usados.add(idx)
                break
    # No completar con 'Personal capacitado' u otros KPI sin relación.
    if len(resultado) < 4:
        candidatos = df[df['Frente'].isin(FRENTES[:2])].sort_values(
            'Ponderacion', ascending=False, na_position='last')
        for idx, fila in candidatos.iterrows():
            if len(resultado) == 4:
                break
            if idx not in usados:
                resultado.append(fila)
                usados.add(idx)
    return resultado


def facturas_2026(meses):
    """Misma base que Ventas 2026: un dato neto por mes (sin sumar duplicados)."""
    if meses.empty:
        return None, 0
    mensual = meses.copy()
    mensual['Fecha'] = pd.to_datetime(mensual['Fecha'], errors='coerce')
    mensual['ResultadoNumerico'] = pd.to_numeric(mensual['ResultadoNumerico'], errors='coerce')
    mensual = mensual.loc[(mensual['Fecha'].dt.year == 2026) &
                          mensual['CodigoKPI'].eq('COM_VENTAS_NETAS_MES') &
                          mensual['ResultadoNumerico'].notna()].copy()
    if mensual.empty:
        return None, 0
    mensual['Mes'] = mensual['Fecha'].dt.to_period('M')
    mensual = mensual.sort_values('Fecha').drop_duplicates(subset=['Mes'], keep='first')
    return float(mensual['ResultadoNumerico'].sum()), int(len(mensual))


st.markdown("""<style>
.ct-v-icon{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;min-width:34px;border-radius:11px;background:#EEF4FD;vertical-align:middle}
.ct-v-flex{display:flex;align-items:center;gap:9px}
.ct-v-title{display:flex;align-items:center;gap:11px;color:#142E50}
.ct-v-title .ct-v-icon{width:38px;height:38px;min-width:38px}
.ct-v-header{display:flex;align-items:center;gap:13px}
.ct-v-header .ct-v-icon{height:45px;width:45px;min-width:45px;border-radius:14px}
.ct10-head{margin-bottom:15px}
.ct10-title{color:#142E50!important}
.ct10-label.ct-v-flex,.ct10-feature-name.ct-v-flex{align-items:flex-start}
.ct10-label .ct-v-icon,.ct10-feature-name .ct-v-icon,.ct10-ptitle .ct-v-icon{width:29px;height:29px;min-width:29px;border-radius:10px}
.ct10-label .ct-v-icon svg,.ct10-feature-name .ct-v-icon svg,.ct10-ptitle .ct-v-icon svg{width:17px;height:17px}
.st-key-ct10_filtros_blancos{background:#FFFFFF!important;border:1px solid #DEE7F2!important;border-radius:18px!important;padding:17px 19px 10px!important;box-shadow:0 4px 15px rgba(24,47,76,.035)!important;margin:10px 0 14px}
.st-key-ct10_filtros_blancos [data-testid="stSelectbox"] [data-baseweb="select"]>div,
.st-key-ct10_filtros_blancos [data-testid="stTextInput"] [data-baseweb="input"],
.st-key-ct10_filtros_blancos [data-testid="stTextInput"] input{background:#fff!important;border-color:#DFE7F1!important;border-radius:11px!important;color:#1C3C5B!important}
.ct10-tile,.ct10-feature,.ct10-panel{box-shadow:0 3px 13px rgba(22,46,83,.035)}
.ct-contract-table{border:1px solid #DFE8F1;border-radius:16px;overflow:hidden;background:#fff;box-shadow:0 3px 13px rgba(22,46,83,.035)}
.ct-contract-table table{border-collapse:collapse;width:100%;font-size:.87rem;color:#1D3958}
.ct-contract-table th{background:#F7FAFD;color:#526C88;text-align:left;font-weight:800;padding:14px 16px;border-bottom:1px solid #DEE7F1}
.ct-contract-table td{padding:13px 16px;border-bottom:1px solid #EBF0F6}
.ct-contract-table tr:last-child td{border-bottom:0}
.ct-contract-table tr:hover td{background:#FAFCFF}
.ct-contract-table td:last-child,.ct-contract-table th:last-child{text-align:right}
.ct-contract-table-wrap{max-height:480px;overflow:auto}
.ct-contract-table .ct-project{font-weight:730;color:#1B3C64}
</style>""",unsafe_allow_html=True)

st.markdown('''<style>
/* Identidad de Inicio: tarjetas de igual altura y superficies claras. */
.ct10-tile{height:172px!important;min-height:172px!important;max-height:172px!important;
 display:flex!important;flex-direction:column!important;justify-content:space-between!important;
 box-sizing:border-box!important;overflow:hidden!important}
.ct10-number{margin:4px 0!important}
.ct10-muted{min-height:32px}
.ct10-feature.ct-home-card{height:242px!important;min-height:242px!important;max-height:242px!important;
 box-sizing:border-box!important;overflow:hidden!important}
.ct10-feature-name.ct-v-flex{height:49px;min-height:49px!important;overflow:hidden}
.ct10-panel{min-height:294px!important}
.ct-filter-heading{display:flex;align-items:center;gap:9px;color:#142E50;font-weight:820;
 margin:1px 0 13px;font-size:1.01rem}
.ct-filter-heading svg{stroke:#326BC3}
/* El contenedor de los filtros es realmente blanco, no solo los inputs. */
[data-testid="stVerticalBlockBorderWrapper"]:has(.ct-filter-heading){background:#FFFFFF!important;
 border:1px solid #DFE7F1!important;border-radius:18px!important;
 box-shadow:0 3px 14px rgba(22,46,83,.035)!important}
[data-testid="stVerticalBlockBorderWrapper"]:has(.ct-filter-heading) [data-baseweb="select"]>div{
 background:#FFFFFF!important;border:1px solid #DDE6F0!important;border-radius:11px!important}
</style>''', unsafe_allow_html=True)

# Panel de filtros superior: superficie blanca sin cambiar gráficos ni tablas.
st.markdown("""<style>
.st-key-ct_filtro_superior,
.st-key-ct_filtro_superior [data-testid="stVerticalBlockBorderWrapper"],
.st-key-ct_filtro_superior [data-testid="stVerticalBlockBorderWrapper"] > div {
    background-color:#FFFFFF!important;
}
.st-key-ct_filtro_superior {
    border:1px solid #DFE7F1!important;
    border-radius:18px!important;
    box-shadow:0 3px 14px rgba(22,46,83,.035)!important;
}
.st-key-ct_filtro_superior [data-testid="stSelectbox"] [data-baseweb="select"] > div,
.st-key-ct_filtro_superior [data-testid="stSelectbox"] input {
    background:#FFFFFF!important;
    border-color:#DDE6F0!important;
}
</style>""", unsafe_allow_html=True)

# Datos reales del modelo. Si el ETL no cargó la fuente, se muestra la ausencia.
# Se conserva el BSC original; el recorte por año y fecha ocurre ANTES
# de recortar_bsc (que por defecto toma únicamente el último corte).
fuente_bsc = cargar('bsc')
if fuente_bsc.empty:
    st.title('Contratos y Negocios')
    st.info('No hay registros BSC para seleccionar.')
    st.stop()
fuente_bsc = fuente_bsc.copy()
fuente_bsc['Fecha'] = pd.to_datetime(fuente_bsc['Fecha'], errors='coerce')
anios_datos = fuente_bsc['Fecha'].dropna().dt.year.astype(int).unique().tolist()
anios_disponibles = sorted(set(anios_datos) | set(range(2024, 2029)), reverse=True)

# Contenedor nativo real: fondo blanco también en Streamlit recientes.
st.markdown('<div class="ct10-head"><div><div class="ct-v-header"><span class="ct-v-icon">'+ct_icono('contrato',24)+'</span><div class="ct10-title">Contratos y Negocios</div></div><div class="ct10-sub">Clientes, adjudicaciones y desempeño comercial</div></div></div>', unsafe_allow_html=True)
with st.container(border=True, key="ct_filtro_superior"):
    st.markdown('<div class="ct-filter-heading">'+ct_icono('calendario',18)+' <span>Filtrar indicadores y contratos</span></div>', unsafe_allow_html=True)
    anio_col, fecha_col = st.columns([0.9, 1.5], gap='medium')
    with anio_col:
        anio_sel = st.selectbox('Año', anios_disponibles,
                               index=anios_disponibles.index(2026) if 2026 in anios_disponibles else 0,
                               key='ct10_anio')
    fechas_anio = sorted(fuente_bsc.loc[fuente_bsc['Fecha'].dt.year.eq(anio_sel), 'Fecha'].dropna().dt.normalize().unique(), reverse=True)
    fechas_iso = [pd.Timestamp(f).strftime('%Y-%m-%d') for f in fechas_anio]
    with fecha_col:
        if fechas_iso:
            if st.session_state.get('ct10_fecha') not in fechas_iso:
                st.session_state.pop('ct10_fecha', None)
            fecha_elegida = st.selectbox('Período (fecha de corte)', fechas_iso,
                format_func=lambda x: ('Más reciente (' + pd.Timestamp(x).strftime('%d/%m/%Y') + ')') if x == fechas_iso[0] else pd.Timestamp(x).strftime('%d/%m/%Y'),
                key='ct10_fecha')
        else:
            fecha_elegida = None
            st.selectbox('Período (fecha de corte)', ['Sin datos'], disabled=True, key='ct10_fecha_sin_datos')
if fecha_elegida is None:
    st.info(f'No hay indicadores BSC registrados para {anio_sel}.')
    st.stop()
fuente_corte = fuente_bsc.loc[
    fuente_bsc['Fecha'].dt.normalize().eq(pd.Timestamp(fecha_elegida))
].copy()
base = recortar_bsc(fuente_corte, 'contratos')
# El porcentaje de adjudicaciones puede estar registrado como KPI GLOBAL
# en el BSC, por eso se incorpora desde el mismo corte si no quedó en el área.
# No se crea una medición ni se infieren porcentajes desde contratos Gmail.
if not fuente_corte.empty and 'NombreKPI' in fuente_corte.columns:
    candidatos = fuente_corte.loc[
        fuente_corte['NombreKPI'].map(es_kpi_adjudicaciones)
    ].copy()
    if not candidatos.empty:
        ya_presentes = (base['NombreKPI'].map(es_kpi_adjudicaciones).any()
                        if not base.empty and 'NombreKPI' in base.columns else False)
        if not ya_presentes:
            if 'Ambito' in candidatos.columns:
                candidatos['_preferencia'] = candidatos['Ambito'].astype(str).str.upper().map(
                    {'AREA': 0, 'GLOBAL': 1}).fillna(2)
                candidatos = candidatos.sort_values('_preferencia').drop(columns='_preferencia')
            base = pd.concat([base, candidatos.head(1)], ignore_index=True)
if base.empty:
    st.info(f'No hay indicadores del área Contratos y Negocios en el corte seleccionado de {anio_sel}.')
    st.stop()

df = base.copy()
df['NombreKPI'] = df['NombreKPI'].fillna('Sin nombre').astype(str)
df['CategoriaKPI'] = df['CategoriaKPI'].fillna('Sin categoría').astype(str)
df['Cumplimiento'] = pd.to_numeric(df['Cumplimiento'], errors='coerce')
df['Ponderacion'] = pd.to_numeric(df['Ponderacion'], errors='coerce')
# Solo presentación: estos KPI corresponden a otras páginas del BSC.
nombres_excluidos = df['NombreKPI'].map(norm)
excluidos = (nombres_excluidos.str.contains(r'accident|siniestral', regex=True, na=False) |
             nombres_excluidos.str.contains(r'facturacion neta|ventas 2026|venta neta', regex=True, na=False) |
             nombres_excluidos.str.contains(r'personal capacitad|colaborador(es)? capacitad|porcentaje colaboradores capacitados', regex=True, na=False))
df = df.loc[~excluidos].copy()
if df.empty:
    st.info('Sin indicadores de Contratos disponibles para este corte.')
    st.stop()
df['Frente'] = df.apply(frente, axis=1)
fecha = pd.to_datetime(df['Fecha'].max(), errors='coerce')
corte = fecha.strftime('%d/%m/%Y') if pd.notna(fecha) else 'Sin fecha'
activos = df[df['Ponderacion'].gt(0)].copy()
evaluados = activos[activos['Cumplimiento'].notna()]
# Si no hay ponderaciones positivas evaluables, mostrar el promedio simple
# de los KPI con Cumplimiento informado. No estimar datos faltantes.
if evaluados.empty:
    evaluados = df.loc[df['Cumplimiento'].notna()].copy()
    puntaje = float(evaluados['Cumplimiento'].mean()) if not evaluados.empty else float('nan')
    descripcion_cumplimiento = 'Promedio simple · KPI medidos sin peso positivo' if not evaluados.empty else 'Sin KPI con cumplimiento registrado'
else:
    puntaje = metricas(activos)
    descripcion_cumplimiento = 'Promedio ponderado · KPI con peso positivo'
cumplen = int((evaluados['Cumplimiento'] >= 1).sum())
criticos = int((evaluados['Cumplimiento'] < .7).sum())
adjudicaciones = df[df['Frente'].eq(FRENTES[1])]

# Fuente de contratos obtenidos mediante el ETL de Gmail, sin alterar SQL.
try:
    contratos_gmail = cargar('etl_contratos').copy()
except Exception as error:
    contratos_gmail = pd.DataFrame()
    st.warning(f'No se pudo leer la fuente de contratos Gmail: {error}')
# El resumen y la tabla de Gmail respetan el año elegido. Se toma
# el inicio contractual, o el fin cuando no exista fecha de inicio.
if not contratos_gmail.empty:
    _inicio = pd.to_datetime(contratos_gmail.get('FechaInicioContrato', pd.Series(pd.NaT,index=contratos_gmail.index)), errors='coerce')
    _fin = pd.to_datetime(contratos_gmail.get('FechaTerminoContrato', pd.Series(pd.NaT,index=contratos_gmail.index)), errors='coerce')
    _anio_contrato = _inicio.fillna(_fin).dt.year
    contratos_gmail = contratos_gmail.loc[_anio_contrato.eq(anio_sel)].copy()
# Una fila por registro de contrato, sin sumar importes ni mezclar con el BSC.
total_contratos = len(contratos_gmail)

# Se omite el recuadro visual de fecha de corte; el filtro de periodo se conserva.

# 1. Lectura rápida para la jefatura del área.
resumen = [
    ('Cumplimiento del área', porcentaje(puntaje), descripcion_cumplimiento, semaforo(puntaje)[1]),
    ('Metas alcanzadas', str(cumplen), f'De {len(evaluados)} KPI evaluables', VERDE if cumplen else GRIS),
    ('KPI críticos', str(criticos), 'Indicadores evaluables con menos de 70%', ROJO if criticos else VERDE),
    ('Total de contratos', str(total_contratos), 'Registros recibidos desde Gmail', AZUL),
]
for col, info in zip(st.columns(4, gap='medium'), resumen):
    with col:
        st.markdown(tarjeta_resumen(*info), unsafe_allow_html=True)

# 2. Visualizaciones ejecutivas: mismas mediciones BSC del corte elegido.
# Estos gráficos no introducen cifras, fuentes ni cálculos nuevos en SQL.
st.markdown(ct_titulo('Panorama de indicadores', 'grafico'), unsafe_allow_html=True)
col_estado, col_avance = st.columns([0.85, 1.35], gap='medium')

# Semáforo por KPI: incluye los que no tienen medición para no ocultar ausencias.
orden_estados = ['Meta alcanzada', 'En progreso', 'Bajo cumplimiento', 'Sin datos']
colores_estados = [VERDE, AMARILLO, ROJO, GRIS]
conteos_estado = df['Cumplimiento'].map(lambda valor: semaforo(valor)[0]).value_counts()
cantidades = [int(conteos_estado.get(e, 0)) for e in orden_estados]

with col_estado:
    with st.container(border=True):
        st.markdown('**Estado de los KPI**')
        st.caption('Distribución de los indicadores del corte seleccionado')
        dona = go.Figure(go.Pie(
            labels=orden_estados, values=cantidades, hole=0.67,
            marker=dict(colors=colores_estados, line=dict(color='#FFFFFF', width=3)),
            sort=False, direction='clockwise', textinfo='none',
            hovertemplate='%{label}: %{value} KPI (%{percent})<extra></extra>',
        ))
        dona.update_layout(
            height=310, margin=dict(l=10, r=10, t=5, b=15),
            paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#35516F', size=11),
            showlegend=True, legend=dict(orientation='h', x=0.5, xanchor='center',
                                         y=-0.04, yanchor='top', font=dict(size=10)),
            annotations=[dict(text=f'<b>{len(df)}</b><br><span style="font-size:11px">KPI</span>',
                              x=0.5, y=0.5, showarrow=False, font=dict(size=24, color='#142A4D'))],
        )
        st.plotly_chart(dona, use_container_width=True, config={'displayModeBar': False})

with col_avance:
    with st.container(border=True):
        st.markdown('**Cumplimiento por indicador**')
        st.caption('Hasta 7 KPI con cumplimiento registrado · referencia: 100%')
        para_grafico = df.loc[df['Cumplimiento'].notna()].copy()
        para_grafico = para_grafico.sort_values(
            ['Ponderacion', 'NombreKPI'], ascending=[False, True], na_position='last'
        ).head(7)
        if para_grafico.empty:
            st.info('Aún no hay mediciones de cumplimiento para graficar.')
        else:
            # Textos completos disponibles al pasar el cursor; el eje usa nombres
            # abreviados para no forzar el ancho de la página.
            nombres = para_grafico['NombreKPI'].astype(str).tolist()
            etiquetas = [s if len(s) <= 27 else s[:26] + '…' for s in nombres]
            valores = (para_grafico['Cumplimiento'].astype(float) * 100).tolist()
            colores = [semaforo(v)[1] for v in para_grafico['Cumplimiento']]
            fig_cumpl = go.Figure(go.Bar(
                x=valores[::-1], y=etiquetas[::-1], orientation='h',
                marker=dict(color=colores[::-1], cornerradius=5),
                customdata=nombres[::-1],
                text=[local(v, 1) + '%' for v in valores[::-1]],
                textposition='outside', textfont=dict(color='#243F60', size=10),
                hovertemplate='<b>%{customdata}</b><br>Cumplimiento: %{x:.1f}%<extra></extra>',
            ))
            fig_cumpl.add_vline(x=100, line_color='#87A1BE', line_dash='dash', line_width=1.5)
            fig_cumpl.update_layout(
                height=310, margin=dict(l=8, r=46, t=5, b=25),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#536B87', size=11), showlegend=False,
                xaxis=dict(title='Cumplimiento (%)', range=[0, max(115, max(valores)*1.16)],
                           gridcolor='#E8EFF6', zeroline=False),
                yaxis=dict(showgrid=False, automargin=True),
            )
            st.plotly_chart(fig_cumpl, use_container_width=True,
                            config={'displayModeBar': False})

# 2. KPI de la gestión de contratos: cuatro indicadores destacados.
st.markdown(ct_titulo('Indicadores principales', 'objetivo'), unsafe_allow_html=True)
if not df['NombreKPI'].map(es_kpi_adjudicaciones).any():
    st.caption('El KPI de adjudicaciones vs. propuestas ofertadas no figura en el BSC del corte seleccionado.')
for col, item in zip(st.columns(4, gap='medium'), buscar_cuatro(df)):
    with col:
        st.markdown(tarjeta_indicador(item), unsafe_allow_html=True)

# 6. Contratos Gmail: únicamente las cuatro columnas solicitadas.
st.markdown(ct_titulo('Contratos recibidos desde Gmail', 'contrato'), unsafe_allow_html=True)
if contratos_gmail.empty:
    st.info('No hay contratos Gmail vinculados en la fuente actual.')
else:
    def primera_columna(opciones):
        return next((col for col in opciones if col in contratos_gmail.columns), None)

    proyecto_col = primera_columna(('NombreProyecto', 'Proyecto', 'Nombre_Proyecto'))
    inicio_col = primera_columna(('FechaInicioContrato', 'FechaInicio', 'InicioContrato'))
    fin_col = primera_columna(('FechaTerminoContrato', 'FechaFinContrato', 'FechaTermino', 'FechaFin'))
    monto_col = primera_columna(('MontoContractual_CLP', 'MontoContrato_CLP', 'MontoCLP', 'Monto'))
    contract_tab = pd.DataFrame({
        'Proyecto': contratos_gmail[proyecto_col].fillna('—').astype(str) if proyecto_col else ['—']*total_contratos,
        'Inicio': contratos_gmail[inicio_col].map(ct_fecha) if inicio_col else ['—']*total_contratos,
        'Fin': contratos_gmail[fin_col].map(ct_fecha) if fin_col else ['—']*total_contratos,
        'Monto': contratos_gmail[monto_col].map(moneda) if monto_col else ['—']*total_contratos,
    })
    # HTML escapado: mismo aspecto blanco que las demás tablas, sin campos extras.
    encabezados = ''.join('<th>'+h(c)+'</th>' for c in contract_tab.columns)
    filas_tabla = ''.join('<tr>'+''.join(
        '<td'+(' class="ct-project"' if j == 0 else '')+'>'+escape(str(v), quote=True)+'</td>'
        for j,v in enumerate(fila))+'</tr>' for fila in contract_tab.itertuples(index=False,name=None))
    st.markdown('<div class="ct-contract-table"><div class="ct-contract-table-wrap">'
                '<table><thead><tr>'+encabezados+'</tr></thead><tbody>'+filas_tabla+
                '</tbody></table></div></div>', unsafe_allow_html=True)

# 7. La tabla de todos los KPI del área cierra la página.
st.markdown(ct_titulo('Todos los KPI del área', 'lista'), unsafe_allow_html=True)
with st.container(key='ct10_filtros_blancos'):
    a, b, c = st.columns([1.25, .9, 1.35], gap='medium')
    with a:
        sel_frente = st.selectbox('Frente de trabajo', ['Todos'] + FRENTES + ['Otros indicadores BSC'], key='ct10_frente')
    with b:
        sel_estado = st.selectbox('Semáforo', ['Todos', 'Meta alcanzada', 'En progreso',
                                              'Bajo cumplimiento', 'Sin datos'], key='ct10_estado')
    with c:
        buscar = st.text_input('Buscar indicador', placeholder='Nombre del KPI', key='ct10_buscar')

filtro = df.copy()
if sel_frente != 'Todos':
    filtro = filtro[filtro['Frente'].eq(sel_frente)]
if sel_estado != 'Todos':
    filtro = filtro[filtro['Cumplimiento'].map(lambda x: semaforo(x)[0]).eq(sel_estado)]
if buscar.strip():
    filtro = filtro[filtro['NombreKPI'].str.contains(buscar.strip(), regex=False, case=False, na=False)]

if filtro.empty:
    st.info('No hay indicadores con los filtros seleccionados.')
else:
    # Tabla HTML para que cada barra use el semáforo de SU KPI.
    # st.column_config.ProgressColumn no admite color distinto por fila.
    registros = filtro.sort_values(['Ponderacion', 'NombreKPI'],
                                  ascending=[False, True], na_position='last')
    filas_html = []
    exportar = []
    for _, registro in registros.iterrows():
        valor_c = n(registro['Cumplimiento'])
        etiqueta, co, punto = semaforo(valor_c)
        resultado = texto_bsc(registro)
        meta = texto_bsc(registro, True)
        peso = local(registro['Ponderacion'], 1)
        if math.isfinite(valor_c):
            avance = min(100., max(0., valor_c * 100))
            porcentaje_texto = local(valor_c * 100, 1) + '%'
            barra_color = (f'<div class="ct-cumplimiento">'
                           f'<div class="ct-cumplimiento-fondo"><span '
                           f'style="width:{avance:.2f}%;background:{co}"></span></div>'
                           f'<strong style="color:{co}">{h(porcentaje_texto)}</strong></div>')
        else:
            porcentaje_texto = '—'
            barra_color = '<span style="color:#8B9BAF">—</span>'
        filas_html.append(
            f'<tr><td><span class="ct-punto" style="background:{co}" '
            f'title="{h(etiqueta)}"></span></td>'
            f'<td>{h(registro["NombreKPI"])}</td>'
            f'<td>{h(resultado)}</td><td>{h(meta)}</td>'
            f'<td>{barra_color}</td><td>{h(peso)}</td></tr>')
        exportar.append({
            'Estado': etiqueta,
            'KPI': registro['NombreKPI'],
            'Resultado': resultado,
            'Meta': meta,
            'Cumplimiento (%)': porcentaje_texto,
            'Peso': peso,
        })
    st.markdown("""<style>
    .ct-kpi-tabla-wrap{border:1px solid #DEE7F0;background:#fff;border-radius:16px;
        overflow:auto;max-height:530px;box-shadow:0 2px 9px rgba(20,45,70,.035)}
    .ct-kpi-tabla{border-collapse:collapse;width:100%;min-width:780px;font-size:.83rem;color:#253B59}
    .ct-kpi-tabla th{position:sticky;top:0;z-index:1;text-align:left;font-weight:780;
        background:#F8FAFD;color:#647891;padding:13px 15px;border-bottom:1px solid #E2EAF1}
    .ct-kpi-tabla td{padding:13px 15px;border-bottom:1px solid #EBF0F5;vertical-align:middle}
    .ct-kpi-tabla tbody tr:hover{background:#F9FBFF}
    .ct-kpi-tabla th:first-child,.ct-kpi-tabla td:first-child{text-align:center;width:74px}
    .ct-kpi-tabla th:last-child,.ct-kpi-tabla td:last-child{text-align:right;width:95px}
    .ct-kpi-tabla td:nth-child(2){min-width:230px}
    .ct-punto{display:inline-block;width:14px;height:14px;border-radius:100%;
        box-shadow:inset 0 1px 3px rgba(255,255,255,.55)}
    .ct-cumplimiento{display:flex;align-items:center;gap:11px;min-width:205px}
    .ct-cumplimiento-fondo{height:9px;background:#E9EEF4;border-radius:99px;
        overflow:hidden;flex:1}
    .ct-cumplimiento-fondo span{height:100%;display:block;border-radius:99px}
    .ct-cumplimiento strong{min-width:50px;text-align:right;font-size:.77rem}
    </style>""", unsafe_allow_html=True)
    st.markdown('<div class="ct-kpi-tabla-wrap"><table class="ct-kpi-tabla">'
                '<thead><tr><th>Estado</th><th>KPI</th><th>Resultado</th>'
                '<th>Meta</th><th>Cumplimiento (%)</th><th>Peso</th></tr></thead>'
                '<tbody>' + ''.join(filas_html) + '</tbody></table></div>',
                unsafe_allow_html=True)
    st.download_button('⬇️ Exportar indicadores filtrados (CSV)',
                       data=pd.DataFrame(exportar).to_csv(index=False, sep=';').encode('utf-8-sig'),
                       file_name='maas_contratos_kpis.csv', mime='text/csv', key='ct10_exportar')
