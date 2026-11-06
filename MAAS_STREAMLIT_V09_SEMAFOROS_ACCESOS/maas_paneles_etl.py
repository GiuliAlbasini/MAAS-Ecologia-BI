# -*- coding: utf-8 -*-
"""Paneles complementarios MAAS (22 fuentes): SOLO LECTURA, datos simulados identificados.

Los paneles se agregan DENTRO de las paginas existentes; nunca modifican
SQL, Drive, Gmail, KPI BSC, permisos de acceso ni datos historicos.
"""
from __future__ import annotations
import math
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




def _panel_css():
    if st.session_state.get('_maas_panel_css_loaded'):
        return
    st.session_state['_maas_panel_css_loaded'] = True
    st.markdown("""
    <style>
    .mp-box{background:#ffffff;border:1px solid #dbe4f0;border-radius:18px;padding:18px 20px;box-shadow:0 4px 14px rgba(16,45,90,.05);height:100%;}
    .mp-box.soft{background:#fbfdff;}
    .mp-title{font-size:15px;font-weight:700;color:#244874;margin-bottom:8px;display:flex;align-items:center;gap:8px;}
    .mp-icon{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:12px;background:#eef4ff;color:#2a62d5;font-size:18px;}
    .mp-value{font-size:26px;font-weight:800;color:#102a5c;line-height:1.15;margin-bottom:6px;}
    .mp-sub{font-size:13px;color:#6c7e99;line-height:1.45;}
    .mp-section{font-size:15px;font-weight:800;color:#17396b;margin:8px 0 12px 0;display:flex;align-items:center;gap:8px;}
    .mp-note{background:#f6f9ff;border:1px solid #dce7fb;border-radius:14px;padding:12px 14px;color:#58719a;font-size:13px;line-height:1.45;margin-top:8px;}
    .mp-alert{background:#fff8e8;border:1px solid #f3dd9b;border-radius:14px;padding:12px 14px;color:#8b6a08;font-size:13px;line-height:1.45;margin-top:8px;}
    .mp-mini{background:#ffffff;border:1px solid #dbe4f0;border-radius:16px;padding:14px 16px;height:100%;}
    .mp-mini .k{font-size:13px;color:#6c7e99;margin-bottom:8px;font-weight:600;}
    .mp-mini .v{font-size:20px;color:#102a5c;font-weight:800;line-height:1.1;}
    .mp-mini .s{font-size:12px;color:#8a9ab2;margin-top:6px;}
    .mp-pill{display:inline-block;padding:5px 10px;border-radius:999px;background:#eef4ff;color:#2a62d5;font-size:12px;font-weight:700;}
    .mp-result-ok{background:#eaf7ef;color:#2f8f57;}
    .mp-result-rev{background:#fff4e5;color:#a86a00;}
    .mp-result-no{background:#ffecec;color:#c74c4c;}
    .mp-divider{height:1px;background:#e7eef7;margin:6px 0 16px 0;}
    </style>
    """, unsafe_allow_html=True)


def _box(title, value, subtitle='', icon='📌', soft=False):
    cls = 'mp-box soft' if soft else 'mp-box'
    return f"<div class='{cls}'><div class='mp-title'><span class='mp-icon'>{icon}</span>{title}</div><div class='mp-value'>{value}</div><div class='mp-sub'>{subtitle}</div></div>"


def _mini(title, value, subtitle=''):
    return f"<div class='mp-mini'><div class='k'>{title}</div><div class='v'>{value}</div><div class='s'>{subtitle}</div></div>"


def _badge_result(x):
    txt = str(x)
    low = txt.lower()
    if 'coincide' in low:
        cls = 'mp-pill mp-result-ok'
    elif 'revis' in low or 'diferencia' in low:
        cls = 'mp-pill mp-result-rev'
    else:
        cls = 'mp-pill mp-result-no'
    return f"<span class='{cls}'>{txt}</span>"

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




def panel_ficha_proyecto(proyecto_key):
    """Contrato y plan se ven juntos, pero nunca sobrescribe uno al otro."""
    _panel_css()
    p=cargar('etl_proyectos')
    t=cargar('etl_tareas')
    r=cargar('etl_recursos')
    c=cargar('etl_contratos')
    p=p[p['Proyecto_Key'].eq(proyecto_key)]
    t=t[t['Proyecto_Key'].eq(proyecto_key)].copy()
    r=r[r['Proyecto_Key'].eq(proyecto_key)].copy()
    c=c[c['Proyecto_Key'].eq(proyecto_key)].copy()
    if p.empty:
        st.info('El proyecto no tiene planificación cargada desde los Excel nuevos.')
        return
    proyecto=p.iloc[0]

    st.markdown("<div class='mp-section'>🧾 Información planificada · Excel de seguimiento</div>", unsafe_allow_html=True)
    a,b,c1=st.columns(3)
    a.markdown(_box('Inicio planificado', _fecha(proyecto['FechaInicioPlan']), 'Fecha registrada en la planificación', '📅'), unsafe_allow_html=True)
    b.markdown(_box('Término planificado', _fecha(proyecto['FechaTerminoPlan']), 'Cierre estimado del proyecto', '🗓️'), unsafe_allow_html=True)
    c1.markdown(_box('Presupuesto planificado', _clp(proyecto['CostoPresupuestado_CLP']), 'Presupuesto base informado en el Excel', '💰'), unsafe_allow_html=True)
    st.markdown("<div class='mp-note'>La información de tareas, recursos y Carta Gantt proviene del Excel de seguimiento. El contrato extraído desde Gmail se presenta sólo como referencia y no reemplaza la planificación.</div>", unsafe_allow_html=True)

    pesta_t,pesta_r,pesta_c=st.tabs(['📋 Tareas y Carta Gantt','🧰 Recursos','📄 Contrato PDF · Gmail'])

    with pesta_t:
        st.markdown("<div class='mp-section'>📋 Avance de tareas del proyecto</div>", unsafe_allow_html=True)
        if t.empty:
            st.info('Todavía no se han incorporado las tareas en la planilla Excel.')
        else:
            t['AvanceTarea']=pd.to_numeric(t['AvanceTarea'],errors='coerce')
            t['HH_Planificadas']=pd.to_numeric(t['HH_Planificadas'],errors='coerce')
            t['HH_Reales']=pd.to_numeric(t['HH_Reales'],errors='coerce')
            t['CostoPlanificado_CLP']=pd.to_numeric(t['CostoPlanificado_CLP'],errors='coerce')
            t['CostoReal_CLP']=pd.to_numeric(t['CostoReal_CLP'],errors='coerce')

            cta, ctb, ctc = st.columns(3)
            cta.markdown(_mini('Tareas registradas', str(len(t)), 'Total cargado en el seguimiento'), unsafe_allow_html=True)
            ctb.markdown(_mini('HH planificadas (tareas)', f"{t['HH_Planificadas'].sum():,.1f}".replace(',', '.'), 'Suma de horas planificadas'), unsafe_allow_html=True)
            ctc.markdown(_mini('HH reales (tareas)', f"{t['HH_Reales'].sum():,.1f}".replace(',', '.'), 'Suma de horas reales registradas'), unsafe_allow_html=True)

            table=t[['CodigoTarea','NombreTarea','EstadoTarea','AvanceTarea',
                     'FechaInicioPlan','FechaTerminoPlan','HH_Planificadas',
                     'HH_Reales','CostoPlanificado_CLP','CostoReal_CLP']].copy()
            table.columns=['Código','Tarea','Estado','Avance','Inicio','Término',
                           'HH plan','HH real','Costo plan','Costo real']
            table['Avance']=table['Avance'].map(_porc)
            table['Inicio']=table['Inicio'].map(_fecha)
            table['Término']=table['Término'].map(_fecha)
            table['Costo plan']=table['Costo plan'].map(_clp)
            table['Costo real']=table['Costo real'].map(_clp)
            st.dataframe(table,hide_index=True,use_container_width=True)

            st.markdown("<div class='mp-section'>🗂️ Carta Gantt planificada</div>", unsafe_allow_html=True)
            gan=t[['CodigoTarea','NombreTarea','EstadoTarea','FechaInicioPlan','FechaTerminoPlan']].copy()
            gan['Inicio']=pd.to_datetime(gan['FechaInicioPlan'],errors='coerce')
            gan['Fin']=pd.to_datetime(gan['FechaTerminoPlan'],errors='coerce')
            gan=gan.dropna(subset=['Inicio','Fin'])
            gan=gan[gan['Fin']>=gan['Inicio']].copy()
            if not gan.empty:
                gan['Tarea']=gan['CodigoTarea'].astype(str)+' · '+gan['NombreTarea'].astype(str)
                gan['Estado']=gan['EstadoTarea'].fillna('Sin estado')
                colores={
                    'Finalizada':'#2f80ed',
                    'En curso':'#6ea8fe',
                    'No iniciada':'#cfdcf5',
                    'Sin estado':'#d8e2f2'
                }
                fig=px.timeline(gan,x_start='Inicio',x_end='Fin',y='Tarea',color='Estado',
                                color_discrete_map=colores,hover_data=['CodigoTarea'])
                fig.update_yaxes(autorange='reversed',title=None)
                fig.update_xaxes(title='Fechas planificadas', showgrid=False)
                fig.update_layout(
                    height=max(330,48*len(gan)+90),
                    margin=dict(l=0,r=10,t=10,b=10),
                    legend_title_text='Estado de tarea',
                    paper_bgcolor='#ffffff',
                    plot_bgcolor='#ffffff'
                )
                st.plotly_chart(fig,use_container_width=True, config={'displayModeBar': False})
            else:
                st.info('No hay fechas válidas para construir la Carta Gantt.')
            st.markdown("<div class='mp-note'>La Carta Gantt muestra fechas planificadas del Excel de seguimiento. Los porcentajes de avance provienen de las tareas registradas en esta misma fuente.</div>", unsafe_allow_html=True)

    with pesta_r:
        st.markdown("<div class='mp-section'>🧰 Recursos utilizados por proyecto</div>", unsafe_allow_html=True)
        if r.empty:
            st.info('No hay recursos registrados para este proyecto.')
        else:
            r['CantidadPlanificada']=pd.to_numeric(r['CantidadPlanificada'],errors='coerce')
            r['CantidadUtilizada']=pd.to_numeric(r['CantidadUtilizada'],errors='coerce')
            r['CantidadRestante']=pd.to_numeric(r['CantidadRestante'],errors='coerce')
            r['PorcentajeUtilizacion']=pd.to_numeric(r['PorcentajeUtilizacion'],errors='coerce')
            cta, ctb, ctc = st.columns(3)
            cta.markdown(_mini('Recursos de los Excel', str(len(r)), 'Cantidad de recursos cargados'), unsafe_allow_html=True)
            ctb.markdown(_mini('Utilización promedio', _porc(r['PorcentajeUtilizacion'].mean()), 'Promedio del uso registrado'), unsafe_allow_html=True)
            ctc.markdown(_mini('Mayor utilización', _porc(r['PorcentajeUtilizacion'].max()), 'Máximo observado en la planilla'), unsafe_allow_html=True)
            table=r[['NombreRecurso','UnidadRecurso','CantidadPlanificada',
                     'CantidadUtilizada','CantidadRestante','PorcentajeUtilizacion']].copy()
            table.columns=['Recurso','Unidad','Planificado','Utilizado','Restante','Utilización']
            table['Utilización']=table['Utilización'].map(_porc)
            st.dataframe(table,hide_index=True,use_container_width=True)
            st.markdown("<div class='mp-note'>Las cantidades por recurso se muestran separadas por unidad y provienen de la hoja de recursos del Excel de seguimiento.</div>", unsafe_allow_html=True)

    with pesta_c:
        st.markdown("<div class='mp-section'>📄 Contrato PDF y comparación con seguimiento</div>", unsafe_allow_html=True)
        if c.empty:
            st.info('Sin contrato PDF asociado en Gmail. La planificación Excel sigue disponible.')
        else:
            contrato=c.iloc[0]
            a,b,c1=st.columns(3)
            a.markdown(_box('Inicio contractual', _fecha(contrato['FechaInicioContrato']), 'Extraído desde Gmail', '📅', True), unsafe_allow_html=True)
            b.markdown(_box('Término contractual', _fecha(contrato['FechaTerminoContrato']), 'Extraído desde Gmail', '🗓️', True), unsafe_allow_html=True)
            c1.markdown(_box('Monto contractual', _clp(contrato['MontoContractual_CLP']), 'Monto detectado en el contrato PDF', '💵', True), unsafe_allow_html=True)

            monto_oc = proyecto.get('Venta_OC_Total_CLP', proyecto.get('VentaOC_CLP', float('nan')))
            monto_pdf = contrato.get('MontoContractual_CLP', float('nan'))
            inicio_plan = proyecto.get('FechaInicioPlan')
            fin_plan = proyecto.get('FechaTerminoPlan')
            inicio_pdf = contrato.get('FechaInicioContrato')
            fin_pdf = contrato.get('FechaTerminoContrato')

            def _compara_num(a,b):
                if math.isfinite(_num(a)) and math.isfinite(_num(b)):
                    return 'Coincide' if round(float(a))==round(float(b)) else 'Diferencia por revisar'
                return 'Sin dato comparable'
            def _compara_fecha(a,b):
                da=pd.to_datetime(a,errors='coerce')
                db=pd.to_datetime(b,errors='coerce')
                if pd.notna(da) and pd.notna(db):
                    return 'Coincide' if da.normalize()==db.normalize() else 'Diferencia por revisar'
                return 'Sin dato comparable'

            comp = pd.DataFrame([
                {'Dato':'Monto OC / contrato', 'Seguimiento proyecto': _clp(monto_oc),
                 'Contrato PDF · Gmail': _clp(monto_pdf), 'Resultado': _compara_num(monto_oc, monto_pdf)},
                {'Dato':'Inicio', 'Seguimiento proyecto': _fecha(inicio_plan),
                 'Contrato PDF · Gmail': _fecha(inicio_pdf), 'Resultado': _compara_fecha(inicio_plan, inicio_pdf)},
                {'Dato':'Término', 'Seguimiento proyecto': _fecha(fin_plan),
                 'Contrato PDF · Gmail': _fecha(fin_pdf), 'Resultado': _compara_fecha(fin_plan, fin_pdf)},
            ])
            comp_show = comp.copy()
            comp_show['Resultado']=comp_show['Resultado'].map(_badge_result)
            st.markdown("<div class='mp-section'>🔎 Comparación de contrato con seguimiento del proyecto</div>", unsafe_allow_html=True)
            st.write(comp_show.to_html(index=False, escape=False), unsafe_allow_html=True)
            estado_val = str(contrato.get('EstadoValidacion', '—'))
            estado_vinc = str(contrato.get('EstadoVinculacion', '—'))
            sim = 'Sí' if bool(contrato.get('EsSimulado', False)) else 'No'
            st.markdown(f"<div class='mp-alert'>Estado de validación: <b>{estado_val}</b> · Vinculación: <b>{estado_vinc}</b> · Dato simulado: <b>{sim}</b>. Este contrato se presenta sólo como referencia y no reemplaza la planificación del proyecto.</div>", unsafe_allow_html=True)



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
