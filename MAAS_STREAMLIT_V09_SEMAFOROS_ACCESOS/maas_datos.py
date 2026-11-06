# -*- coding: utf-8 -*-
"""Lectura de solo consulta de MAAS_ECOLOGIA_4. No ejecuta ETL ni escribe SQL.

V14: conservar project_kpis y agregar consultas de KPI comerciales V14,
sin alterar las consultas anteriores de BSC, ventas, proyectos o cargas.
Los 11 KPI derivados de proyectos tienen EsSimulado=1 y NO son KPI oficiales.
"""
from __future__ import annotations
import os
import pandas as pd
import streamlit as st

BASE = 'MAAS_ECOLOGIA_4'
QUERIES = {
 'bsc': '''SELECT fe.Fecha, k.CodigoKPI, k.NombreKPI, k.CategoriaKPI, k.TipoIndicador,
     k.EstadoRevision, k.UnidadMedida, f.Ambito, ar.NombreArea, f.MetaNumerica,
     f.MetaTexto, f.ResultadoNumerico, f.ResultadoTexto, f.Avance, f.Cumplimiento,
     f.Ponderacion, f.EsSimulado
 FROM dbo.FACT_KPI_ESTRATEGICO f
 JOIN dbo.DIM_KPI k ON k.KPI_Key=f.KPI_Key
 JOIN dbo.DIM_FECHA fe ON fe.Fecha_Key=f.Fecha_Key
 LEFT JOIN dbo.DIM_AREA ar ON ar.Area_Key=f.Area_Key
 WHERE k.TipoIndicador='OFICIAL_BSC' AND f.FuenteResultado='BSC';''',
 'projects': '''SELECT Proyecto_Key, NombreProyecto, TipoProyecto, FechaSeguimiento,
     FechaInicioPlanificada, FechaTerminoPlanificada, FechaTerminoReal,
     EstadoProyecto, EsSimulado, VentaOC_CLP, MargenObjetivo, MargenActual,
     MargenProyectado, NoCumpleOriginal, NoCumpleCalculado, CostoPresupuestado_CLP,
     CostoRealAcumulado_CLP, SaldoPresupuestado_CLP, DiferenciaCosto_CLP,
     DuracionPlanificadaDias, DiasAtraso, SituacionPlazo, Observaciones
 FROM dbo.VW_PROYECTOS_ULTIMO_CORTE ORDER BY NombreProyecto;''',
 'history': '''SELECT Proyecto_Key, NombreProyecto, FechaSeguimiento, EstadoProyecto,
     CostoPresupuestado_CLP,CostoRealAcumulado_CLP,DiferenciaCosto_CLP,
     DiasAtraso, SituacionPlazo
 FROM dbo.VW_SEGUIMIENTO_PROYECTOS ORDER BY NombreProyecto, FechaSeguimiento;''',
 'costs': '''SELECT Proyecto_Key, NombreProyecto, CategoriaCosto, Anio, Mes,
     EsSimulado, CantidadMovimientos,TotalCosto_CLP
 FROM dbo.VW_COSTOS_POR_CATEGORIA ORDER BY NombreProyecto, Anio, Mes, CategoriaCosto;''',
 'months': '''SELECT fe.Fecha, k.CodigoKPI, f.ResultadoNumerico
 FROM dbo.FACT_KPI_ESTRATEGICO f
 JOIN dbo.DIM_KPI k ON k.KPI_Key=f.KPI_Key
 JOIN dbo.DIM_FECHA fe ON fe.Fecha_Key=f.Fecha_Key
 WHERE f.FuenteResultado='VENTAS' AND f.Ambito='GLOBAL'
 AND f.GranoTemporal='MES'
 AND k.CodigoKPI IN ('COM_VENTAS_NETAS_MES','COM_FACTURAS_MES','COM_CLIENTES_MES','COM_TICKET_MES')
 ORDER BY fe.Fecha;''',
 'clients': '''SELECT fe.Fecha, cl.RazonSocial,cl.RUT_Normalizado,cl.EsMinero,
     f.ResultadoNumerico AS VentaNeta_CLP
 FROM dbo.FACT_KPI_ESTRATEGICO f
 JOIN dbo.DIM_KPI k ON k.KPI_Key=f.KPI_Key
 JOIN dbo.DIM_FECHA fe ON fe.Fecha_Key=f.Fecha_Key
 JOIN dbo.DIM_CLIENTE cl ON cl.Cliente_Key=f.Cliente_Key
 WHERE f.FuenteResultado='VENTAS' AND f.Ambito='CLIENTE'
 AND f.GranoTemporal='MES' AND k.CodigoKPI='COM_VENTA_CLIENTE_MES'
 ORDER BY fe.Fecha, cl.RazonSocial;''',
 'sales_v14_months': '''SELECT fe.Fecha, k.CodigoKPI, f.ResultadoNumerico
 FROM dbo.FACT_KPI_ESTRATEGICO AS f
 JOIN dbo.DIM_KPI AS k ON k.KPI_Key = f.KPI_Key
 JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key = f.Fecha_Key
 WHERE f.FuenteResultado='VENTAS' AND f.Ambito='GLOBAL'
   AND f.GranoTemporal='MES' AND k.CodigoKPI IN (
     'COM_VENTAS_ACUM_ANIO', 'COM_VARIACION_MENSUAL_PCT',
     'COM_PRIMERA_COMPRA_OBSERVADA_MES')
 ORDER BY fe.Fecha,k.CodigoKPI;''',
 'sales_client_shares': '''SELECT fe.Fecha, cl.RUT_Normalizado, cl.RazonSocial,
     f.ResultadoNumerico AS ParticipacionPct
 FROM dbo.FACT_KPI_ESTRATEGICO AS f
 JOIN dbo.DIM_KPI AS k ON k.KPI_Key=f.KPI_Key
 JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key=f.Fecha_Key
 JOIN dbo.DIM_CLIENTE AS cl ON cl.Cliente_Key=f.Cliente_Key
 WHERE f.FuenteResultado='VENTAS' AND f.Ambito='CLIENTE'
   AND f.GranoTemporal='MES'
   AND k.CodigoKPI='COM_PARTICIPACION_CLIENTE_MES_PCT'
 ORDER BY fe.Fecha, f.ResultadoNumerico DESC;''',
 'project_kpis': '''SELECT fe.Fecha, k.CodigoKPI, k.NombreKPI, k.CategoriaKPI,
     k.UnidadMedida, k.ReglaCalculo, f.ResultadoNumerico, f.MetaNumerica,
     f.FuenteResultado, f.EsSimulado
 FROM dbo.FACT_KPI_ESTRATEGICO AS f
 JOIN dbo.DIM_KPI AS k ON k.KPI_Key=f.KPI_Key
 JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key=f.Fecha_Key
 WHERE f.FuenteResultado='PROYECTOS' AND f.EsSimulado=1
     AND f.Ambito='GLOBAL' AND f.GranoTemporal='CORTE'
     AND k.TipoIndicador='OPERACIONAL'
     AND k.CodigoKPI LIKE 'PRY[_]%'
     AND f.Fecha_Key=(
         SELECT MAX(f2.Fecha_Key)
         FROM dbo.FACT_KPI_ESTRATEGICO AS f2
         JOIN dbo.DIM_KPI AS k2 ON k2.KPI_Key=f2.KPI_Key
         WHERE f2.FuenteResultado='PROYECTOS' AND f2.EsSimulado=1
           AND f2.Ambito='GLOBAL' AND f2.GranoTemporal='CORTE'
           AND k2.TipoIndicador='OPERACIONAL'
           AND k2.CodigoKPI LIKE 'PRY[_]%'
     )
 ORDER BY k.CodigoKPI;''',
 'loads': '''SELECT TipoFuente,MAX(FinUTC) AS UltimaCargaUTC
 FROM dbo.ETL_CARGA WHERE Estado='OK' GROUP BY TipoFuente ORDER BY TipoFuente;'''
}


# Fuentes nuevas del ETL de 22 versiones: consultas de SOLO LECTURA,
# sin concatenar cierres Gmail con ventas Excel.
QUERIES['etl_proyectos'] = '''
SELECT p.Proyecto_Key,p.NombreProyecto,p.TipoProyecto,f.IDOrigen,
 fi.Fecha AS FechaInicioPlan,ft.Fecha AS FechaTerminoPlan,
 f.VentaOC_CLP,f.MargenObjetivo,f.MargenActual,f.MargenProyectado,
 f.CostoPresupuestado_CLP,f.CostoRealTarea_CLP AS CostoRealProyecto_CLP,
 f.HH_Planificadas,f.HH_Reales,f.FuenteDato,f.EsSimulado
 FROM dbo.FACT_SEGUIMIENTO_OPERACIONAL AS f
 JOIN dbo.DIM_PROYECTO AS p ON p.Proyecto_Key=f.Proyecto_Key
 LEFT JOIN dbo.DIM_FECHA AS fi ON fi.Fecha_Key=f.Fecha_InicioPlan_Key
 LEFT JOIN dbo.DIM_FECHA AS ft ON ft.Fecha_Key=f.Fecha_TerminoPlan_Key
 WHERE f.TipoRegistro='PROYECTO' ORDER BY p.NombreProyecto;
'''
QUERIES['etl_tareas'] = '''
SELECT p.Proyecto_Key,p.NombreProyecto,d.CodigoProyecto,d.CodigoTarea,
 d.NombreTarea,d.TareaPredecesora,d.RecursoPrincipal,
 f.EstadoProyecto AS EstadoTarea,fi.Fecha AS FechaInicioPlan,
 ft.Fecha AS FechaTerminoPlan,f.AvanceTarea,f.HH_Planificadas,
 f.HH_Reales,f.CostoPresupuestado_CLP AS CostoPlanificado_CLP,
 f.CostoRealTarea_CLP AS CostoReal_CLP,f.EsSimulado
 FROM dbo.FACT_SEGUIMIENTO_OPERACIONAL AS f
 JOIN dbo.DIM_TAREA AS d ON d.Tarea_Key=f.Tarea_Key
 JOIN dbo.DIM_PROYECTO AS p ON p.Proyecto_Key=f.Proyecto_Key
 LEFT JOIN dbo.DIM_FECHA AS fi ON fi.Fecha_Key=f.Fecha_InicioPlan_Key
 LEFT JOIN dbo.DIM_FECHA AS ft ON ft.Fecha_Key=f.Fecha_TerminoPlan_Key
 WHERE f.TipoRegistro='TAREA' ORDER BY p.NombreProyecto,d.CodigoTarea;
'''
QUERIES['etl_recursos'] = '''
SELECT p.Proyecto_Key,p.NombreProyecto,f.IDOrigen,f.NombreRecurso,
 f.UnidadRecurso,f.CantidadPlanificada,f.CantidadUtilizada,
 f.CantidadRestante,f.PorcentajeUtilizacion,f.EsSimulado
 FROM dbo.FACT_SEGUIMIENTO_OPERACIONAL AS f
 JOIN dbo.DIM_PROYECTO AS p ON p.Proyecto_Key=f.Proyecto_Key
 WHERE f.TipoRegistro='RECURSO' ORDER BY p.NombreProyecto,f.NombreRecurso;
'''
QUERIES['etl_adjudicaciones'] = '''
SELECT p.Proyecto_Key,p.NombreProyecto,f.NumeroPropuesta,
 a.Fecha AS FechaAdjudicacion,f.Adjudicada,
 f.MontoAdjudicado_CLP,f.Observaciones,f.EsSimulado
 FROM dbo.FACT_SEGUIMIENTO_OPERACIONAL AS f
 JOIN dbo.DIM_PROYECTO AS p ON p.Proyecto_Key=f.Proyecto_Key
 LEFT JOIN dbo.DIM_FECHA AS a ON a.Fecha_Key=f.FechaAdjudicacion_Key
 WHERE f.TipoRegistro='ADJUDICACION' ORDER BY p.NombreProyecto,a.Fecha DESC;
'''
QUERIES['etl_contratos'] = '''
SELECT p.Proyecto_Key,p.NombreProyecto,f.IDOrigen,
 fi.Fecha AS FechaInicioContrato,ft.Fecha AS FechaTerminoContrato,
 f.MontoContractual_CLP,f.EstadoValidacion,
 f.EstadoVinculacion,f.EsSimulado,f.FuenteDato
 FROM dbo.FACT_SEGUIMIENTO_OPERACIONAL AS f
 JOIN dbo.DIM_PROYECTO AS p ON p.Proyecto_Key=f.Proyecto_Key
 LEFT JOIN dbo.DIM_FECHA AS fi ON fi.Fecha_Key=f.FechaInicioContrato_Key
 LEFT JOIN dbo.DIM_FECHA AS ft ON ft.Fecha_Key=f.FechaTerminoContrato_Key
 WHERE f.TipoRegistro='CONTRATO' ORDER BY p.NombreProyecto,fi.Fecha DESC;
'''
QUERIES['etl_cierres_gmail'] = '''
SELECT fe.Fecha AS Periodo,k.CodigoKPI,f.ResultadoNumerico,
 f.EsSimulado,k.EstadoRevision,f.FuenteResultado
 FROM dbo.FACT_KPI_ESTRATEGICO AS f
 JOIN dbo.DIM_KPI AS k ON k.KPI_Key=f.KPI_Key
 JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key=f.Fecha_Key
 WHERE f.FuenteResultado='GMAIL' AND f.GranoTemporal='MES'
 AND f.Ambito='GLOBAL'
 AND k.CodigoKPI IN ('GMAIL_FACTURADO_MES','GMAIL_PENDIENTE_MES')
 ORDER BY fe.Fecha,k.CodigoKPI;
'''
QUERIES['etl_caja'] = '''
SELECT fe.Fecha AS Periodo,f.ResultadoNumerico AS BrechaCaja_CLP,
 f.EsSimulado
 FROM dbo.FACT_KPI_ESTRATEGICO AS f
 JOIN dbo.DIM_KPI AS k ON k.KPI_Key=f.KPI_Key
 JOIN dbo.DIM_FECHA AS fe ON fe.Fecha_Key=f.Fecha_Key
 WHERE f.FuenteResultado='CAJA' AND f.Ambito='GLOBAL'
 AND f.GranoTemporal='MES' AND k.CodigoKPI='CAJA_BRECHA_MES'
 ORDER BY fe.Fecha;
'''


def servidor_sql():
    try:
        s = st.secrets.get('conexion',{}).get('servidor')
    except (FileNotFoundError, RuntimeError):
        s = None
    return os.environ.get('MAAS_SQL_SERVER') or s or r'Giuli\GIULIANA'


def _conexion():
    import pyodbc
    driver = next((d for d in ('ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server')
                   if d in pyodbc.drivers()),None)
    if driver is None:
        raise RuntimeError('Falta ODBC Driver 17 o 18 de SQL Server.')
    cs=(f'DRIVER={{{driver}}};SERVER={servidor_sql()};DATABASE={BASE};'
        'Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;'
        'Connection Timeout=10;Application Name=MAAS_STREAMLIT_LOCAL;')
    return pyodbc.connect(cs,autocommit=True,timeout=15)


@st.cache_data(ttl=90,show_spinner=False)
def consultar(nombre: str) -> pd.DataFrame:
    if nombre not in QUERIES:
        raise ValueError('Consulta no admitida')
    conn=_conexion()
    try:
        cur=conn.cursor()
        cur.execute(QUERIES[nombre])
        cols=[z[0] for z in cur.description]
        return pd.DataFrame.from_records(cur.fetchall(),columns=cols)
    finally:
        conn.close()


def cargar(nombre: str):
    try:
        return consultar(nombre)
    except Exception as exc:
        st.error('No fue posible consultar MAAS_ECOLOGIA_4. Revisa SQL Server y sus vistas.')
        with st.expander('Detalles técnicos (pruebas locales)'):
            st.code(f'{type(exc).__name__}: {exc}')
        st.stop()
