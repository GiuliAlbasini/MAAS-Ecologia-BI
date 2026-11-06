# -*- coding: utf-8 -*-
"""Componentes visuales del BSC. Solo muestran datos de MAAS_ECOLOGIA_4."""
from __future__ import annotations
import html
import math
import pandas as pd
import plotly.express as px
import streamlit as st
from maas_datos import cargar

COLORS={'Cumple':'#25A469','En riesgo':'#F4BA39','No cumple':'#D94E52','Sin datos':'#95A5BA'}
AREA_HOJAS={'administracion':'ADMINISTRACION Y CONTROL',
            'ingenieria':'INGENIERIA Y PROPUESTAS',
            'operaciones':'OPERACIONES',
            'contratos':'CONTRATOS Y NEGOCIOS'}

def estilo():
    st.markdown('''<style>
    .stApp {background:#F4F7FB;color:#152B45;}
    .block-container {padding-top:1.4rem;max-width:1520px;padding-bottom:3rem;}
    section[data-testid="stSidebar"] {background:#152D4D;}
    section[data-testid="stSidebar"] * {color:#EDF3FA;}
    section[data-testid="stSidebar"] button {background:#fff;}
    section[data-testid="stSidebar"] button * {color:#152D4D!important;}
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#C4D1E2!important;}
    div[data-testid="stMetric"] {background:#fff;border:1px solid #DAE4EF;border-radius:14px;
      padding:14px 18px;min-height:108px;}
    div[data-testid="stMetricValue"] {font-size:clamp(1.2rem,2vw,1.8rem);}
    .maas-sub{color:#5D7088;margin-top:-8px;margin-bottom:18px;}
    .maas-brand{color:white;font-size:1.25rem;font-weight:850;letter-spacing:.025em;margin:8px 0 4px;}
    .maas-card{background:white;border:1px solid #DCE5EF;border-radius:14px;padding:16px 17px;
      min-height:165px;box-shadow:0 1px 4px rgba(23,46,75,.05);}
    .maas-card-title{font-size:.83rem;font-weight:700;color:#52667E;min-height:38px;
      overflow-wrap:anywhere;line-height:1.2;}
    .maas-card-val{font-size:clamp(1rem,1.6vw,1.45rem);font-weight:850;color:#162D4A;
      overflow-wrap:anywhere;line-height:1.25;}
    .maas-card-meta{font-size:.76rem;color:#788AA1;margin-top:6px;}
    .maas-card-bar{height:9px;background:#E9EEF4;border-radius:7px;overflow:hidden;margin-top:12px;}
    .maas-card-bar span{height:100%;display:block;border-radius:7px;}
    .maas-card-foot{display:flex;justify-content:space-between;align-items:center;margin-top:9px;
      font-size:.78rem;font-weight:650;color:#52667E;}
    .maas-legend{font-size:.8rem;color:#5B6E85;line-height:1.9;}
    .maas-status{font-size:.8rem;font-weight:750;border-radius:20px;padding:5px 11px;
      display:inline-block;border:1px solid #E1E8EF;}
    </style>''',unsafe_allow_html=True)

def metricas(df):
    if df.empty:return float('nan')
    p=pd.to_numeric(df['Cumplimiento'],errors='coerce')
    w=pd.to_numeric(df['Ponderacion'],errors='coerce')
    ok=p.notna() & w.notna() & (w>0)
    return float((p[ok]*w[ok]).sum()/w[ok].sum()) if ok.any() else float('nan')

def _n(x,d=2):
    try:
        v=float(x)
        if not math.isfinite(v):return '—'
        return f'{v:,.{d}f}'.replace(',','X').replace('.',',').replace('X','.')
    except (TypeError,ValueError):return '—'

def pesos(v):
    return '—' if pd.isna(v) else '$'+_n(v,0)

def pct(v):
    try:
        f=float(v)
        return _n(f*100,1)+'%' if math.isfinite(f) else '—'
    except (ValueError,TypeError):return '—'

def estado(p):
    try:
        x=float(p)
        if not math.isfinite(x):return 'Sin datos'
        return 'Cumple' if x>=1.0 else 'En riesgo' if x>=0.7 else 'No cumple'
    except (TypeError,ValueError):return 'Sin datos'

def _s(x):return html.escape(str(x),quote=True)

def presentacion_valor(n,txt,unidad):
    if pd.notna(txt) and str(txt).strip():return str(txt).strip()
    if pd.isna(n):return 'Sin dato'
    unidad=str(unidad or '').lower()
    if '%' in unidad or 'porcent' in unidad: return pct(n)
    if 'miles' in unidad: return _n(n,0)+' miles CLP'
    if 'clp' in unidad or '$' in unidad: return pesos(n)
    return _n(n,0 if float(n).is_integer() else 2)

def recortar_bsc(df,area=None):
    if df.empty:return df.copy()
    r=df.copy()
    r['Fecha']=pd.to_datetime(r['Fecha'],errors='coerce')
    r=r.loc[r['Fecha']==r['Fecha'].max()].copy()
    if area is None:return r.loc[r['Ambito']=='GLOBAL'].copy()
    return r.loc[(r['Ambito']=='AREA') &
                 (r['NombreArea'].fillna('').astype(str).str.strip().str.upper()==AREA_HOJAS[area])].copy()

def semaforos(df,titulo='Semáforo de KPI'):
    if titulo: st.markdown('#### '+titulo)
    estados=df['Cumplimiento'].map(estado).value_counts().reindex(list(COLORS),fill_value=0)
    if estados.sum()==0:
        st.info('No hay indicadores para mostrar.')
        return
    fig=px.pie(pd.DataFrame({'Estado':estados.index,'Cantidad':estados.values}),
               names='Estado',values='Cantidad',hole=.68,color='Estado',color_discrete_map=COLORS)
    fig.update_traces(textinfo='none',hovertemplate='%{label}: %{value} KPI<extra></extra>',
                      marker=dict(line=dict(color='#F4F7FB',width=2)))
    fig.update_layout(margin=dict(l=2,r=2,t=4,b=5),height=240,showlegend=False,
                      paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
                      annotations=[dict(text=f'<b>{len(df)}</b><br>KPI',x=.5,y=.5,showarrow=False,font=dict(size=18))])
    st.plotly_chart(fig,use_container_width=True,config={'displayModeBar':False})
    st.markdown('<div class="maas-legend">'+ ' &nbsp; · &nbsp; '.join(
        f'<span style="color:{COLORS[e]}">●</span> {_s(e)}: {int(n)}' for e,n in estados.items()
    )+'</div>',unsafe_allow_html=True)
    st.caption('Verde: ≥100% · Amarillo: 70–99,9% · Rojo: <70% · Gris: sin datos. Son umbrales de visualización.')

def tarjetas_kpi(df,limite=8):
    if df.empty:return
    mostrar=df.copy().sort_values('Ponderacion',ascending=False,na_position='last').head(limite)
    for start in range(0,len(mostrar),4):
        cols=st.columns(4)
        for col,(_,r) in zip(cols,mostrar.iloc[start:start+4].iterrows()):
            s=estado(r['Cumplimiento'])
            try:width=max(0,min(100,100*float(r['Cumplimiento'])))
            except (ValueError,TypeError):width=0
            actual=presentacion_valor(r['ResultadoNumerico'],r['ResultadoTexto'],r['UnidadMedida'])
            meta=presentacion_valor(r['MetaNumerica'],r['MetaTexto'],r['UnidadMedida'])
            with col:
                st.markdown(f'''<div class="maas-card" title="{_s(r['NombreKPI'])}">
                    <div class="maas-card-title">{_s(r['NombreKPI'])}</div>
                    <div class="maas-card-val">{_s(actual)}</div>
                    <div class="maas-card-meta">Meta: {_s(meta)}</div>
                    <div class="maas-card-bar"><span style="width:{width:.1f}%;background:{COLORS[s]}"></span></div>
                    <div class="maas-card-foot"><span style="color:{COLORS[s]}">● {_s(s)}</span><span>{_s(pct(r['Cumplimiento']))}</span></div>
                 </div>''',unsafe_allow_html=True)

def resumen_categorias(df):
    st.markdown('#### Cumplimiento por categoría')
    por=df.groupby('CategoriaKPI',dropna=False)[['Cumplimiento','Ponderacion']].apply(metricas).reset_index(name='Puntaje')
    por['CategoriaKPI']=por['CategoriaKPI'].fillna('Sin categoría')
    por=por[por['Puntaje'].notna()].sort_values('Puntaje')
    if por.empty:
        st.info('No hay categorías con KPI evaluables y ponderación positiva.')
        return
    por['Valor']=100*por['Puntaje']
    por['Estado']=por['Puntaje'].map(estado)
    fig=px.bar(por,x='Valor',y='CategoriaKPI',orientation='h',color='Estado',
               color_discrete_map=COLORS,text=por['Puntaje'].map(lambda x:f'{x:.0%}'))
    fig.update_layout(height=max(280,40*len(por)),margin=dict(l=0,r=20,t=4,b=10),
                      xaxis=dict(range=[0,max(110,por['Valor'].max()*1.13)],title='Cumplimiento (%)'),
                      yaxis_title=None,legend_title=None,showlegend=False)
    fig.update_traces(hovertemplate='%{y}: %{x:.1f}%<extra></extra>',textposition='outside')
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Promedio ponderado solo de KPI evaluables. No representa el cumplimiento oficial de MAAS.')

def tabla_kpis(df):
    if df.empty:return
    tabla=df.copy()
    tabla['Estado']=tabla['Cumplimiento'].map(estado)
    tabla['Semáforo']=tabla['Estado'].map({'Cumple':'🟢','En riesgo':'🟡','No cumple':'🔴','Sin datos':'⚪'})
    tabla['Actual']=tabla.apply(lambda r:presentacion_valor(r['ResultadoNumerico'],r['ResultadoTexto'],r['UnidadMedida']),axis=1)
    tabla['Meta']=tabla.apply(lambda r:presentacion_valor(r['MetaNumerica'],r['MetaTexto'],r['UnidadMedida']),axis=1)
    tabla['Cumplimiento_pct']=pd.to_numeric(tabla['Cumplimiento'],errors='coerce')*100
    tabla=tabla[['Semáforo','NombreKPI','CategoriaKPI','Actual','Meta','Cumplimiento_pct','Ponderacion','EstadoRevision']]
    st.dataframe(tabla,hide_index=True,use_container_width=True,height=min(490,44*len(tabla)+45),
      column_config={
        'Semáforo':st.column_config.TextColumn('Estado',width='small'),
        'NombreKPI':st.column_config.TextColumn('Indicador',width='large'),
        'CategoriaKPI':'Categoría', 'Actual':'Resultado', 'Meta':'Meta',
        'Cumplimiento_pct':st.column_config.ProgressColumn('Cumplimiento',min_value=0,max_value=100,format='%.1f%%'),
        'Ponderacion':st.column_config.NumberColumn('Peso',format='%.1f'),
        'EstadoRevision':'Revisión'
      })

def detalle_interactivo(df,clave):
    if df.empty:return
    nombres=df['NombreKPI'].astype(str).sort_values().unique().tolist()
    elegido=st.selectbox('Selecciona un indicador para revisar su ficha',nombres,key='ficha_'+clave)
    r=df.loc[df['NombreKPI']==elegido].iloc[0]
    a,b,c,d=st.columns(4)
    a.metric('Resultado',presentacion_valor(r['ResultadoNumerico'],r['ResultadoTexto'],r['UnidadMedida']))
    b.metric('Meta',presentacion_valor(r['MetaNumerica'],r['MetaTexto'],r['UnidadMedida']))
    c.metric('Cumplimiento',pct(r['Cumplimiento']))
    d.metric('Peso registrado',_n(r['Ponderacion'],1))
    st.caption('Estado de revisión: '+str(r['EstadoRevision'])+' · Fuente: BSC oficial')

def comparativo_avance(df):
    st.markdown('#### Avance acumulado frente a la meta anual')
    rows=df.copy()
    rows['Avance']=pd.to_numeric(rows['Avance'],errors='coerce')
    rows=rows[rows['Avance'].notna() & (rows['Avance']>=0)].copy()
    if rows.empty:
        st.info('Sin datos de avance acumulado para comparar.')
        return
    rows=rows.sort_values('Ponderacion',ascending=False).head(14)
    records=[]
    for _,r in rows.iterrows():
        records.append({'KPI':r['NombreKPI'],'Serie':'Avance acumulado','Porcentaje':float(r['Avance'])*100})
        records.append({'KPI':r['NombreKPI'],'Serie':'Meta anual (referencia)','Porcentaje':100.0})
    data=pd.DataFrame(records)
    fig=px.bar(data,x='Porcentaje',y='KPI',color='Serie',barmode='group',orientation='h',
               color_discrete_map={'Avance acumulado':'#2C68BD','Meta anual (referencia)':'#AEBBCD'},
               height=max(360,len(rows)*37),opacity=.86)
    fig.update_layout(yaxis_title=None,legend_title=None,
                      xaxis_title='Porcentaje de avance / referencia',
                      yaxis=dict(categoryorder='array',categoryarray=rows['NombreKPI'].tolist()[::-1]),
                      margin=dict(l=0,r=12,t=7,b=10))
    st.plotly_chart(fig,use_container_width=True)
    st.caption('La línea gris representa 100% de la meta anual, NO la proyección al día. Esta última no está disponible como columna separada en el hecho actual.')

def aviso_fuentes():
    st.caption('El BSC actualizado contiene 15 KPI manuales; un alias departamental sigue pendiente de homologación. Ventas Excel y cierres Gmail son fuentes independientes.')

def panel_bsc(titulo,area=None):
    st.title(titulo)
    st.markdown('<p class="maas-sub">Indicadores estratégicos · Semáforos y gestión por departamento</p>',unsafe_allow_html=True)
    df=recortar_bsc(cargar('bsc'),area)
    if df.empty:
        st.info('No se encontraron indicadores para este departamento.')
        return
    df['Cumplimiento']=pd.to_numeric(df['Cumplimiento'],errors='coerce')
    df['Ponderacion']=pd.to_numeric(df['Ponderacion'],errors='coerce')
    filtro,filtrar=st.columns([1.2,2])
    with filtro:
        cat=st.selectbox('Categoría',['Todas']+sorted(df['CategoriaKPI'].dropna().unique().tolist()),key='categoria_'+str(area))
    with filtrar:
        posibles=['Todos','Cumple','En riesgo','No cumple','Sin datos']
        estado_sel=st.selectbox('Semáforo',posibles,key='estado_'+str(area))
    if cat!='Todas':df=df[df['CategoriaKPI']==cat].copy()
    df['Estado']=df['Cumplimiento'].map(estado)
    if estado_sel!='Todos':df=df[df['Estado']==estado_sel].copy()
    if df.empty:
        st.info('No hay KPI con estos filtros.')
        return
    r1,r2=st.columns([1,1.5])
    with r1:
        semaforos(df,titulo='Cumplimiento del área')
        st.metric('Cumplimiento ponderado*',pct(metricas(df)))
    with r2:resumen_categorias(df)
    st.caption('*Calculado sobre indicadores evaluables y sus ponderaciones registradas; no sustituye el BSC oficial.')
    st.markdown('#### KPI de mayor peso')
    tarjetas_kpi(df,limite=4)
    l,r=st.columns([1.5,1])
    with l:comparativo_avance(df)
    with r:
        st.markdown('#### KPI críticos')
        faltan=df[(df['Cumplimiento'].notna())&(df['Ponderacion']>0)].copy()
        if faltan.empty:st.info('No hay indicadores evaluables para ordenar.')
        else:
            faltan['BrechaPonderada']=(1-faltan['Cumplimiento'].clip(upper=1))*faltan['Ponderacion']
            faltan=faltan.nlargest(7,'BrechaPonderada')
            faltan['Semáforo']=faltan['Estado'].map({'Cumple':'🟢','En riesgo':'🟡','No cumple':'🔴','Sin datos':'⚪'})
            faltan['Cumple']=faltan['Cumplimiento'].map(pct)
            st.dataframe(faltan[['Semáforo','NombreKPI','Cumple']],hide_index=True,use_container_width=True,
              column_config={'NombreKPI':'Indicador','Cumple':'Cumplimiento'},height=350)
    st.markdown('#### Detalle de KPI del área')
    tabla_kpis(df)
    with st.expander('Ficha interactiva de un KPI'):
        detalle_interactivo(df,clave=str(area))
    aviso_fuentes()
