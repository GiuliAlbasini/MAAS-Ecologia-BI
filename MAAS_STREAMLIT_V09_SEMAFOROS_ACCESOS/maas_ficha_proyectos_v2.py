# -*- coding: utf-8 -*-
"""Paneles complementarios MAAS (22 fuentes): SOLO LECTURA, datos simulados identificados.

Los paneles se agregan DENTRO de las paginas existentes; nunca modifican
SQL, Drive, Gmail, KPI BSC, permisos de acceso ni datos historicos.
"""
from __future__ import annotations
import math
import os
import json
import hashlib
import re
import unicodedata
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from maas_datos import cargar


def _num(x):
    try:
        n=float(x)
        return n if math.isfinite(n) else float('nan')
    except (TypeError,ValueError):
        return float('nan')


def _clp(x):
    n=_num(x)
    return '$'+f'{round(n):,}'.replace(',','.') if math.isfinite(n) else '\u2014'


def _porc(x):
    n=_num(x)
    return f'{100*n:.1f}%'.replace('.',',') if math.isfinite(n) else '\u2014'


def _fecha(x):
    d=pd.to_datetime(x,errors='coerce')
    return d.strftime('%d/%m/%Y') if pd.notna(d) else '\u2014'


def _solo(cadena):
    return cadena.fillna('\u2014').astype(str)


def _clave_contrato(nombre):
    txt = unicodedata.normalize('NFKD', str(nombre or ''))
    txt = ''.join(c for c in txt if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '_', txt).strip('_')


def _mostrar_pdf_contratos(nombre_proyecto):
    """Muestra \u00fanicamente el contrato exacto del proyecto, si est\u00e1 disponible localmente."""
    raiz_etl = Path(os.environ.get('MAAS_ETL_ROOT') or Path(__file__).resolve().parent)
    indice = raiz_etl / 'datos_fuente' / 'gmail' / 'contratos_originales.json'
    if not indice.is_file():
        st.info('No se encontr\u00f3 el \u00edndice de PDF. Comprueba MAAS_ETL_ROOT y ejecuta el extractor Gmail actualizado.')
        return
    try:
        registros = json.loads(indice.read_text(encoding='utf-8')).get('contratos', [])
    except (OSError, ValueError):
        st.warning('No se pudo leer el \u00edndice local de contratos PDF.')
        return
    propios = [x for x in registros if x.get('proyecto_normalizado') == _clave_contrato(nombre_proyecto)]
    if not propios:
        st.info('No hay PDF original del contrato asociado a este proyecto.')
        return
    st.markdown('**PDF del contrato recibido en Gmail**')
    for registro in propios:
        sha = registro.get('sha256_pdf', '')
        if not re.fullmatch(r'[a-f0-9]{64}', sha):
            st.warning('Huella del PDF inv\u00e1lida; revisa la extracci\u00f3n.')
            continue
        ruta = indice.parent / 'contratos_pdf' / (sha + '.pdf')
        if not ruta.is_file():
            st.warning('Falta el PDF guardado para ' + str(registro.get('archivo_pdf', 'contrato')))
            continue
        contenido = ruta.read_bytes()
        if hashlib.sha256(contenido).hexdigest() != sha:
            st.error('El PDF no coincide con la huella registrada. No se abrir\u00e1.')
            continue
        st.download_button('Descargar contrato \u00b7 ' + str(registro.get('archivo_pdf') or sha[:12] + '.pdf'),
                           data=contenido, file_name=Path(str(registro.get('archivo_pdf') or 'contrato.pdf')).name,
                           mime='application/pdf', key='contrato_' + sha)
        st.caption('Documento recibido por Gmail \u00b7 Estado: ' + str(registro.get('estado_validacion', 'Sin validar')))


def panel_cartera_nueva():
    """Resumen de las nuevas 17 filas PROYECTO y 85 tareas; sin V12 historica."""
    st.markdown('#### Planificaci\xf3n y seguimiento desde Excel \xb7 ETL actual')
    p=cargar('etl_proyectos')
    t=cargar('etl_tareas')
    if p.empty:
        st.info('No hay datos de planificaci\xf3n en la FACT actual.')
        return
    a,b,c=st.columns(3)
    a.metric('Proyectos con planificaci\xf3n',len(p))
    b.metric('Tareas de seguimiento',len(t))
    c.metric('Proyectos con tareas',t['Proyecto_Key'].nunique() if not t.empty else 0)
    st.caption('Planificaci\xf3n, avances, HH y costos de los Excel: SIMULADOS. '
               'No representan estados reales ni permiten afirmar un atraso contractual.')
    if p['Proyecto_Key'].duplicated().any():
        st.error('Hay proyectos duplicados en la FACT: revisar antes de presentar el resumen.')
        return
    base=p[['NombreProyecto','FechaInicioPlan','FechaTerminoPlan']].copy()
    base.columns=['Proyecto','Inicio planificado','T\xe9rmino planificado']
    base['Inicio planificado']=base['Inicio planificado'].map(_fecha)
    base['T\xe9rmino planificado']=base['T\xe9rmino planificado'].map(_fecha)
    st.dataframe(base,hide_index=True,use_container_width=True,height=min(340,35*len(base)+45))



# Estética del detalle de Proyectos: consistente con el tablero principal.
_PANEL_CSS = """<style>
.mp-titulo{display:flex;align-items:center;gap:11px;color:#18375B;font-size:1.03rem;font-weight:800;margin:12px 0 13px}
.mp-icono{display:grid;place-items:center;width:38px;height:38px;background:#EAF2FF;border-radius:12px;color:#2F67BB;font-size:1.14rem;flex-shrink:0}
.mp-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:7px 0 15px}
.mp-card{min-width:0;background:#FFFFFF;border:1px solid #E0E9F3;border-radius:16px;padding:15px 17px;box-shadow:0 2px 9px rgba(25,51,86,.035)}
.mp-label{display:flex;align-items:center;gap:8px;font-size:.78rem;color:#59728F;font-weight:720;margin-bottom:9px}
.mp-label .mp-mini{width:28px;height:28px;display:grid;place-items:center;border-radius:9px;background:#EEF4FF;color:#376BC1;font-size:1rem}
.mp-value{color:#173457;font-size:1.35rem;font-weight:830;letter-spacing:-.025em;overflow-wrap:anywhere;line-height:1.25}
.mp-note{font-size:.72rem;color:#8999AC;margin-top:7px;line-height:1.45}
.mp-rule{height:1px;background:#EBF0F6;margin:17px 0}
.mp-pill{display:inline-flex;padding:6px 10px;border-radius:999px;background:#EEF5FC;color:#456989;font-size:.75rem;font-weight:720}
.mp-context{background:#F6F9FD;border:1px solid #E5ECF5;border-radius:12px;padding:10px 13px;color:#6B7F98;font-size:.77rem;margin:8px 0 14px}
.mp-ok{color:#3F9A67;font-weight:740}.mp-alert{color:#D45C61;font-weight:740}.mp-muted{color:#889AB1}
/* Campos y pestañas en azul en lugar del rojo predeterminado. */
div[data-testid="stTabs"] button[aria-selected="true"]{color:#285FAF!important;border-color:#376EC6!important}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{background-color:#376EC6!important}
/* El fondo del gráfico y la tabla se mantiene blanco. */
div[data-testid="stDataFrame"]{border:1px solid #E1E9F3;border-radius:13px;overflow:hidden;background:#FFFFFF!important}
div[data-testid="stTabs"] button[aria-selected="true"]{color:#275FB4!important;border-bottom:3px solid #376EC6!important}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{background:#376EC6!important}
@media(max-width:800px){.mp-cards{grid-template-columns:1fr}}
</style>"""

def _mp_cards(items):
    import html as _html
    rows=[]
    for titulo,valor,icono,nota in items:
        rows.append('<div class="mp-card"><div class="mp-label"><span class="mp-mini">'+_html.escape(str(icono))+'</span>'+_html.escape(str(titulo))+'</div><div class="mp-value">'+_html.escape(str(valor))+'</div>'+(('<div class="mp-note">'+_html.escape(str(nota))+'</div>') if nota else '')+'</div>')
    st.markdown('<div class="mp-cards">'+''.join(rows)+'</div>',unsafe_allow_html=True)

def _mp_title(icono, nombre):
    import html as _html
    st.markdown('<div class="mp-titulo"><span class="mp-icono">'+_html.escape(icono)+'</span>'+_html.escape(nombre)+'</div>',unsafe_allow_html=True)

def panel_ficha_proyecto(proyecto_key):
    """Ficha de planificación: tareas, Carta Gantt y recursos."""
    p=cargar('etl_proyectos')
    t=cargar('etl_tareas')
    r=cargar('etl_recursos')
    p=p[p['Proyecto_Key'].eq(proyecto_key)]
    t=t[t['Proyecto_Key'].eq(proyecto_key)].copy()
    r=r[r['Proyecto_Key'].eq(proyecto_key)].copy()
    if p.empty:
        st.info('El proyecto no tiene planificaci\xf3n cargada desde los Excel nuevos.')
        return
    proyecto=p.iloc[0]
    st.markdown(_PANEL_CSS, unsafe_allow_html=True)
    st.caption('Vista interior renovada · seguimiento de proyectos')
    _mp_title('🗓', 'Información planificada · Excel de seguimiento')
    _mp_cards([
        ('Inicio planificado',_fecha(proyecto['FechaInicioPlan']),'◷','Fecha del Excel'),
        ('Término planificado',_fecha(proyecto['FechaTerminoPlan']),'▦','Fecha del Excel'),
        ('Presupuesto planificado',_clp(proyecto['CostoPresupuestado_CLP']),'＄','Costo estimado'),
    ])
    st.caption('Venta/OC proviene del BSC; el presupuesto, las tareas y el Gantt son datos SIMULADOS.')
    pesta_t,pesta_r=st.tabs(['▦  Tareas y Carta Gantt','▤  Recursos'])
    with pesta_t:
        if t.empty:
            st.info('Todav\xeda no se han incorporado las tareas en la planilla Excel.')
        else:
            t['AvanceTarea']=pd.to_numeric(t['AvanceTarea'],errors='coerce')
            t['HH_Planificadas']=pd.to_numeric(t['HH_Planificadas'],errors='coerce')
            t['HH_Reales']=pd.to_numeric(t['HH_Reales'],errors='coerce')
            t['CostoPlanificado_CLP']=pd.to_numeric(t['CostoPlanificado_CLP'],errors='coerce')
            t['CostoReal_CLP']=pd.to_numeric(t['CostoReal_CLP'],errors='coerce')
            _mp_title('☷','Avance de tareas y planificación')
            _mp_cards([
                ('Tareas registradas',len(t),'☑','Tareas del proyecto'),
                ('HH planificadas (tareas)',f'{t["HH_Planificadas"].sum():,.1f}'.replace(',','.'),'◷','Horas estimadas'),
                ('HH reales (tareas)',f'{t["HH_Reales"].sum():,.1f}'.replace(',','.'),'↗','Horas ejecutadas'),
            ])
            table=t[['CodigoTarea','NombreTarea','EstadoTarea','AvanceTarea',
                     'FechaInicioPlan','FechaTerminoPlan','HH_Planificadas',
                     'HH_Reales','CostoPlanificado_CLP','CostoReal_CLP']].copy()
            table.columns=['C\xf3digo','Tarea','Estado','Avance','Inicio','T\xe9rmino',
                           'HH plan','HH real','Costo plan','Costo real']
            table['Avance']=table['Avance'].map(_porc)
            table['Inicio']=table['Inicio'].map(_fecha)
            table['T\xe9rmino']=table['T\xe9rmino'].map(_fecha)
            table['Costo plan']=table['Costo plan'].map(_clp)
            table['Costo real']=table['Costo real'].map(_clp)
            st.dataframe(table,hide_index=True,use_container_width=True,height=min(390,40*len(table)+42))
            _mp_title('▥','Carta Gantt · fechas planificadas')
            gan=t[['CodigoTarea','NombreTarea','EstadoTarea','FechaInicioPlan','FechaTerminoPlan']].copy()
            gan['Inicio']=pd.to_datetime(gan['FechaInicioPlan'],errors='coerce')
            gan['Fin']=pd.to_datetime(gan['FechaTerminoPlan'],errors='coerce')
            gan=gan.dropna(subset=['Inicio','Fin'])
            gan=gan[gan['Fin']>=gan['Inicio']].copy()
            if not gan.empty:
                gan['Tarea']=gan['CodigoTarea'].astype(str)+' \xb7 '+gan['NombreTarea'].astype(str)
                gan['Estado']=gan['EstadoTarea'].fillna('Sin estado')
                fig=px.timeline(gan,x_start='Inicio',x_end='Fin',y='Tarea',color='Estado',
                                color_discrete_sequence=['#326FC3','#4FA477','#E8B94E','#D65E61','#93A6BB'],
                                hover_data=['CodigoTarea'])
                fig.update_yaxes(autorange='reversed',title=None)
                fig.update_xaxes(title='Fechas planificadas')
                fig.update_layout(height=max(290,48*len(gan)+110),margin=dict(l=0,r=10,t=12,b=10),
                                  legend_title_text='Estado de tarea',paper_bgcolor='#FFFFFF',
                                  plot_bgcolor='#FFFFFF',font=dict(color='#58718E'),
                                  xaxis=dict(gridcolor='#EDF2F7',title='Fechas planificadas'),
                                  legend=dict(orientation='h',y=1.13,x=1,xanchor='right'))
                st.plotly_chart(fig,use_container_width=True,config={'displayModeBar':False})
            st.caption('La Carta Gantt muestra fechas PLANIFICADAS del Excel. Los porcentajes '
                       'de avance provienen de las tareas SIMULADAS, no del contrato.')
    with pesta_r:
        _mp_title('▤','Recursos utilizados por proyecto')
        if r.empty:
            st.info('No hay recursos registrados para este proyecto.')
        else:
            table=r[['NombreRecurso','UnidadRecurso','CantidadPlanificada',
                     'CantidadUtilizada','CantidadRestante','PorcentajeUtilizacion']].copy()
            table.columns=['Recurso','Unidad','Planificado','Utilizado','Restante','Utilizaci\xf3n']
            table['Utilizaci\xf3n']=table['Utilizaci\xf3n'].map(_porc)
            st.dataframe(table,hide_index=True,use_container_width=True,height=min(390,40*len(table)+42))
            st.caption('Cantidades por recurso: SIMULADAS. No se suman cantidades de unidades diferentes.')

def panel_cierre_mensual():
    st.markdown('#### Cierre mensual de facturaci\xf3n \xb7 Gmail')
    datos=cargar('etl_cierres_gmail')
    if datos.empty:
        st.info('Todav\xeda no existen cierres de facturaci\xf3n extra\xeddos de Gmail.')
        return
    d=datos.copy()
    d['Periodo']=pd.to_datetime(d['Periodo'],errors='coerce')
    d['ResultadoNumerico']=pd.to_numeric(d['ResultadoNumerico'],errors='coerce')
    d=d.dropna(subset=['Periodo'])
    if d.duplicated(['Periodo','CodigoKPI']).any():
        st.error('Hay cierres de Gmail duplicados para un mes. No se muestran sumas ambiguas.')
        return
    tabla=d.pivot(index='Periodo',columns='CodigoKPI',values='ResultadoNumerico').sort_index()
    if not {'GMAIL_FACTURADO_MES','GMAIL_PENDIENTE_MES'} <= set(tabla):
        st.warning('El cierre no tiene los dos importes requeridos (facturado y pendiente).')
        return
    periodo=st.selectbox('Mes del cierre Gmail',list(reversed(tabla.index.tolist())),
                         format_func=lambda x:x.strftime('%m/%Y'),key='maas_gmail_ventas_mes')
    fila=tabla.loc[periodo]
    a,b=st.columns(2)
    a.metric('Facturado informado por Gmail',_clp(fila['GMAIL_FACTURADO_MES']))
    b.metric('Pendiente de facturar informado',_clp(fila['GMAIL_PENDIENTE_MES']))
    raw=d[d['Periodo']==periodo]
    if raw['EsSimulado'].fillna(False).astype(bool).any():
        st.warning('Cierre de facturaci\xf3n FICTICIO usado para probar el ETL; no es un cierre oficial.')
    st.caption('Los cierres Gmail son una fuente independiente. NO se suman '
               'al informe de facturas del Excel ni se concilian autom\xe1ticamente.')
    table=tabla.reset_index()[['Periodo','GMAIL_FACTURADO_MES','GMAIL_PENDIENTE_MES']].copy()
    table.columns=['Mes','Facturaci\xf3n Gmail (CLP)','Pendiente Gmail (CLP)']
    table['Mes']=table['Mes'].dt.strftime('%m/%Y')
    st.dataframe(table,hide_index=True,use_container_width=True)


def panel_caja_mensual():
    st.markdown('#### Brechas de caja mensuales \xb7 ETL')
    d=cargar('etl_caja')
    if d.empty:
        st.info('A\xfan no existen datos de caja mensual desde el Excel.')
        return
    d=d.copy()
    d['Periodo']=pd.to_datetime(d['Periodo'],errors='coerce')
    d['BrechaCaja_CLP']=pd.to_numeric(d['BrechaCaja_CLP'],errors='coerce')
    d=d.dropna(subset=['Periodo']).sort_values('Periodo')
    if d.duplicated(['Periodo']).any():
        st.error('Hay dos valores de brecha para el mismo mes. Revisar los hechos.')
        return
    st.warning('Los valores de caja son SIMULADOS para la tesis, no saldos reales de MAAS.')
    a,b=st.columns(2)
    a.metric('Meses con dato de brecha',len(d))
    b.metric('Brecha acumulada informada',_clp(d['BrechaCaja_CLP'].sum(min_count=1)))
    plot=d[['Periodo','BrechaCaja_CLP']].copy()
    plot['Mes']=plot['Periodo'].dt.strftime('%m/%Y')
    fig=px.bar(plot,x='Mes',y='BrechaCaja_CLP',labels={'BrechaCaja_CLP':'Brecha de caja (CLP)'})
    fig.update_layout(height=300,margin=dict(l=0,r=8,t=12,b=10))
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Brecha de caja exclusivamente del Excel simulado: no corresponde a facturaci\xf3n Gmail.')


def panel_adjudicaciones():
    st.markdown('#### Propuestas y adjudicaciones registradas \xb7 Excel')
    d=cargar('etl_adjudicaciones')
    if d.empty:
        st.info('A\xfan no existen adjudicaciones en el seguimiento.')
        return
    a,b=st.columns(2)
    a.metric('Propuestas registradas en la muestra',len(d))
    b.metric('Marcadas como adjudicadas',int(pd.to_numeric(d['Adjudicada'],errors='coerce').fillna(0).sum()))
    st.warning('Muestra SIMULADA vinculada a los 17 Excel de proyecto: NO representa '
               'el universo de licitaciones o propuestas reales de MAAS.')
    tab=d[['NombreProyecto','NumeroPropuesta','FechaAdjudicacion','Adjudicada','MontoAdjudicado_CLP']].copy()
    tab.columns=['Proyecto','Propuesta','Fecha','Adjudicada','Monto adjudicado']
    tab['Fecha']=tab['Fecha'].map(_fecha)
    tab['Monto adjudicado']=tab['Monto adjudicado'].map(_clp)
    st.dataframe(tab,hide_index=True,use_container_width=True)


def panel_resumen_operaciones():
    st.markdown('#### Tareas y recursos del seguimiento operacional')
    tareas=cargar('etl_tareas')
    recursos=cargar('etl_recursos')
    if tareas.empty:
        st.info('Sin tareas de seguimiento disponibles.')
        return
    a,b=st.columns(2)
    a.metric('Tareas de los Excel',len(tareas))
    b.metric('Recursos de los Excel',len(recursos))
    t=tareas[['NombreProyecto','CodigoTarea','NombreTarea','EstadoTarea','AvanceTarea']].copy()
    t.columns=['Proyecto','C\xf3digo','Tarea','Estado','Avance']
    t['Avance']=t['Avance'].map(_porc)
    st.dataframe(t,hide_index=True,use_container_width=True,height=370)
    st.caption('Datos SIMULADOS. El avance no es un porcentaje contractual aprobado; '
               'los recursos se revisan en el detalle de Seguimiento de proyectos.')


def panel_contratos_gmail():
    st.markdown('#### Contratos recibidos desde Gmail \xb7 ETL')
    d=cargar('etl_contratos')
    if d.empty:
        st.info('Sin contratos vinculados desde Gmail.')
        return
    cols=['NombreProyecto','FechaInicioContrato','FechaTerminoContrato',
          'MontoContractual_CLP','EstadoValidacion','EstadoVinculacion','EsSimulado']
    t=d[cols].copy()
    t.columns=['Proyecto','Inicio contractual','T\xe9rmino contractual',
               'Monto contractual','Validaci\xf3n','Vinculaci\xf3n','Simulado']
    t['Inicio contractual']=t['Inicio contractual'].map(_fecha)
    t['T\xe9rmino contractual']=t['T\xe9rmino contractual'].map(_fecha)
    t['Monto contractual']=t['Monto contractual'].map(_clp)
    t['Simulado']=t['Simulado'].map(lambda x:'S\xed' if bool(x) else 'No')
    st.dataframe(t,hide_index=True,use_container_width=True)
    st.warning('Los contratos en Gmail est\xe1n pendientes de aprobaci\xf3n. No sustituyen '
               'los montos del BSC ni las fechas simuladas de la planificaci\xf3n.')
