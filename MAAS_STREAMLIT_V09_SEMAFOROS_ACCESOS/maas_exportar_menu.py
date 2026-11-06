# -*- coding: utf-8 -*-
"""Exporta un resumen REAL de KPI globales MAAS a PNG y PDF desde SQL."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from maas_datos import consultar
import streamlit as st

COLOR_TINTA = '#172847'
COLOR_GRIS = '#60748D'
COLOR_VERDE = '#42A16D'
COLOR_LINEA = '#DEE6EF'


def _fuente(size, bold=False):
    files = [
        r'C:\Windows\Fonts\arialbd.ttf' if bold else r'C:\Windows\Fonts\arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold
        else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for p in files:
        if Path(p).is_file():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def _valor(v):
    try:
        if pd.isna(v): return '—'
        n=float(v)
        if pd.isna(n): return '—'
        txt=f'{n:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return txt
    except (ValueError,TypeError):
        return str(v)[:22] if v is not None else '—'


@st.cache_data(ttl=90, show_spinner=False)
def exportar_resumen():
    # consultar lee la FACT/DIM vigente y nunca escribe SQL.
    df = consultar('bsc')
    if df.empty:
        raise ValueError('No hay indicadores BSC')
    df = df.loc[df['Ambito'].astype(str).str.upper() == 'GLOBAL'].copy()
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df = df.loc[df['Fecha'] == df['Fecha'].max()].copy()
    # El SQL puede contener varios lotes del mismo dia. No sumar mediciones.
    df = df.drop_duplicates(subset=['CodigoKPI'], keep='last')
    df = df.sort_values('NombreKPI', kind='stable').head(20)
    if df.empty:
        raise ValueError('No hay KPI globales del ultimo corte')
    corte = df['Fecha'].max()
    fecha = corte.strftime('%d/%m/%Y') if pd.notna(corte) else 'Sin fecha'
    alto = 245 + len(df) * 43
    im = Image.new('RGB', (1230, alto), '#F4F7FB')
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((26,24,1204,alto-25),radius=22,fill='#FFFFFF',outline=COLOR_LINEA,width=2)
    draw.text((58,46),'MAAS ECOLOGÍA',font=_fuente(38,True),fill=COLOR_TINTA)
    draw.text((60,101),'INDICADORES ESTRATÉGICOS · BSC GLOBAL',font=_fuente(19,True),fill=COLOR_TINTA)
    draw.text((60,133),f'Corte: {fecha}  ·  Datos consultados desde SQL Server',font=_fuente(17),fill=COLOR_GRIS)
    draw.line([(58,174),(1172,174)],fill=COLOR_LINEA,width=2)
    draw.text((60,186),'KPI',font=_fuente(17,True),fill=COLOR_GRIS)
    draw.text((870,186),'RESULTADO',font=_fuente(17,True),fill=COLOR_GRIS)
    draw.text((1050,186),'META',font=_fuente(17,True),fill=COLOR_GRIS)
    y=228
    for _,fila in df.iterrows():
        nombre=str(fila['NombreKPI'])
        if len(nombre)>54: nombre=nombre[:51]+'…'
        draw.text((60,y),nombre,font=_fuente(16),fill=COLOR_TINTA)
        resultado = fila['ResultadoTexto'] if pd.notna(fila['ResultadoTexto']) and str(fila['ResultadoTexto']).strip() else _valor(fila['ResultadoNumerico'])
        meta = fila['MetaTexto'] if pd.notna(fila['MetaTexto']) and str(fila['MetaTexto']).strip() else _valor(fila['MetaNumerica'])
        draw.text((870,y),str(resultado)[:16],font=_fuente(16,True),fill=COLOR_TINTA)
        draw.text((1050,y),str(meta)[:12],font=_fuente(16),fill=COLOR_GRIS)
        draw.line([(58,y+32),(1172,y+32)],fill='#F1F4F8',width=1)
        y+=43
    io_png=BytesIO(); im.save(io_png,format='PNG')
    io_pdf=BytesIO(); im.save(io_pdf,format='PDF',resolution=120.0)
    return io_png.getvalue(), io_pdf.getvalue()
