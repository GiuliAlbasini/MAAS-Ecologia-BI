# -*- coding: utf-8 -*-
"""MAAS 4 - auditoria funcional (solo SELECT, no cambia SQL/Drive/ETL).

Instalar junto a 08_ejecutar_etl_maas.py. Ejecutar:
    python -u .\14_validar_maas4_solo_lectura.py
    python -u .\14_validar_maas4_solo_lectura.py --streamlit "C:\\ruta\\MAAS_STREAMLIT_V09_SEMAFOROS_ACCESOS"

Escribe un informe TXT LOCAL en logs_etl. Los datos personales/clientes no
aparecen en el informe; solo indicadores agregados y fallas identificadas.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
import sys

DATABASE = 'MAAS_ECOLOGIA_4'
SERVER_DEFAULT = r'Giuli\GIULIANA'
CODES_GLOBAL = (
    'COM_VENTAS_NETAS_MES', 'COM_FACTURAS_MES', 'COM_CLIENTES_MES',
    'COM_TICKET_MES', 'COM_VENTAS_ACUM_ANIO', 'COM_VARIACION_MENSUAL_PCT',
    'COM_PRIMERA_COMPRA_OBSERVADA_MES',
)
CODES_CLIENT = ('COM_VENTA_CLIENTE_MES', 'COM_PARTICIPACION_CLIENTE_MES_PCT')
MANUAL_CODE = 'BSC_DEP_ING_13_CONTRATO_1000MM'
R = []
FAILS = 0
WARNINGS = 0


def line(s=''):
    s = str(s)
    R.append(s)
    print(s)


def result(ok, title, detail='', severity='fail'):
    global FAILS, WARNINGS
    if ok:
        mark = 'OK'
    elif severity == 'warn':
        mark = 'PENDIENTE'
        WARNINGS += 1
    else:
        mark = 'FALLA'
        FAILS += 1
    line(f'[{mark}] {title}' + (f' | {detail}' if detail else ''))
    return ok


def query(cur, statement, *args):
    # Toda consulta emitida por esta herramienta debe ser SELECT / CTE SELECT.
    s = statement.strip()
    if not re.match(r'^(SELECT|WITH)\b', s, re.I):
        raise ValueError('Consulta no permitida por auditor: no es SELECT/CTE')
    cur.execute(s, *args)
    names = [c[0] for c in cur.description]
    return [dict(zip(names, values)) for values in cur.fetchall()]


def one(cur, sql, *args):
    rows = query(cur, sql, *args)
    return rows[0] if rows else None


def D(v):
    return None if v is None else Decimal(str(v))


def money(v):
    return D(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def date_value(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def norm_rut(v):
    return re.sub('[^0-9K]', '', str(v or '').upper())


def latest(cur, source):
    # En el ETL las fuentes activas se identifican por hash y CargaID. Usar la
    # ultima carga OK por fuente para el control de lote confirmado reciente.
    row = one(cur, '''SELECT TOP (1) CargaID, FinUTC FROM dbo.ETL_CARGA
        WHERE TipoFuente=? AND Estado='OK'
        ORDER BY CargaID DESC''', source)
    if not row:
        raise RuntimeError('No hay version OK para ' + source)
    return int(row['CargaID'])


def check_bsc(cur, bsc_id):
    line('\n1. BSC / KPI manuales / identidad')
    all_rows = query(cur, '''SELECT k.CodigoKPI,k.NombreKPI,k.TipoIndicador,k.EstadoRevision,
        f.Ambito,f.ResultadoNumerico,f.ResultadoTexto,f.MetaNumerica,f.MetaTexto,f.Area_Key
        FROM dbo.FACT_KPI_ESTRATEGICO AS f
        JOIN dbo.DIM_KPI AS k ON k.KPI_Key=f.KPI_Key
        WHERE f.CargaID=? AND f.FuenteResultado='BSC' ''', bsc_id)
    gc = [r for r in all_rows if r['Ambito']=='GLOBAL']
    dc = [r for r in all_rows if r['Ambito']=='AREA']
    result(len(gc)==15, '15 KPI globales en FACT (lote vigente)', str(len(gc)))
    result(len(dc)==45, '45 KPI departamentales en FACT (lote vigente)', str(len(dc)))
    m = [r for r in dc if r['CodigoKPI']==MANUAL_CODE]
    result(len(m)==1, 'KPI contrato >1000MM incorporado una sola vez', 'Registros: '+str(len(m)))
    if len(m)==1:
        r=m[0]
        result(r['TipoIndicador']=='OFICIAL_BSC', 'KPI manual visible para consulta BSC',
               'TipoIndicador='+str(r['TipoIndicador']))
        result(r['EstadoRevision']=='PENDIENTE_VALIDACION', 'KPI 1000MM mantiene advertencia de validacion',
               'Estado='+str(r['EstadoRevision']), severity='warn')
        result(r['ResultadoNumerico'] is not None or (r['ResultadoTexto'] or '').strip(),
               'KPI 1000MM contiene un resultado manual',
               'Con valor' if r['ResultadoNumerico'] is not None else 'Sin resultado', severity='warn')
    keys = query(cur, '''SELECT CodigoKPI,COUNT_BIG(*) AS N FROM dbo.DIM_KPI
        GROUP BY CodigoKPI HAVING COUNT_BIG(*)>1''')
    result(not keys, 'DIM_KPI sin codigos duplicados', f'Duplicados: {len(keys)}')
    for label, group in [('globales', gc), ('departamentales', dc)]:
        missing = sum(x['ResultadoNumerico'] is None and not str(x['ResultadoTexto'] or '').strip() for x in group)
        result(missing==0, 'Resultados presentes en KPI '+label,
               f'Sin resultado: {missing}/{len(group)}', severity='warn')
    return all_rows


def expected_sales(cur, sales_id):
    invoices = query(cur, '''SELECT TipoDocumento,Folio,FechaDocumento,RutCliente,Neto_CLP
        FROM dbo.STG_VENTA_DETALLE WHERE CargaID=?''', sales_id)
    seen = set()
    by_month = defaultdict(list)
    bad=[]
    for r in invoices:
        key=(str(r['TipoDocumento']).strip().lower(),str(r['Folio']).strip())
        if key in seen: bad.append('folio duplicado')
        seen.add(key)
        try:
            month=date_value(r['FechaDocumento']).replace(day=1)
            value=money(r['Neto_CLP'])
            cust=norm_rut(r['RutCliente'])
            if not cust: bad.append('cliente sin RUT')
            by_month[month].append((cust,value))
        except (ValueError,TypeError,AttributeError):
            bad.append('fecha/monto invalido')
    result(len(invoices)>0 and not bad, 'STAGING ventas valido: folios, fechas y montos',
           f'{len(invoices)} facturas | incidencias: {len(bad)}')
    if bad or not invoices:
        return {},{},len(invoices),Decimal(0)
    aggregate={}
    per_client={}
    totals={month:sum((v for _,v in entries),Decimal(0)) for month,entries in by_month.items()}
    seen_client={}
    for month in sorted(by_month):
        for client,_ in by_month[month]:
            seen_client.setdefault(client,month)
    ytd=defaultdict(lambda:Decimal(0))
    for month in sorted(by_month):
        vals=by_month[month]
        n=len(vals)
        net=totals[month]
        ytd[month.year]+=net
        prior=(date(month.year-1,12,1) if month.month==1 else date(month.year,month.month-1,1))
        prev=totals.get(prior)
        growth=(net/prev-1)*100 if prev is not None and prev!=0 else None
        aggregate[month]={
            'COM_VENTAS_NETAS_MES':net,
            'COM_FACTURAS_MES':Decimal(n),
            'COM_CLIENTES_MES':Decimal(len({c for c,_ in vals})),
            'COM_TICKET_MES':(net/Decimal(n)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),
            'COM_VENTAS_ACUM_ANIO':ytd[month.year],
            'COM_VARIACION_MENSUAL_PCT':growth,
            'COM_PRIMERA_COMPRA_OBSERVADA_MES':Decimal(sum(first==month for first in seen_client.values())),
        }
        by_customer=defaultdict(lambda:Decimal(0))
        for cust,v in vals: by_customer[cust]+=v
        for cust,v in by_customer.items():
            per_client[(month,cust)]={'COM_VENTA_CLIENTE_MES':v,
                  'COM_PARTICIPACION_CLIENTE_MES_PCT':v*100/net if net else None}
    net_total=sum(totals.values(),Decimal(0))
    summary=query(cur, '''SELECT TipoDocumento,Cantidad,Neto_CLP FROM dbo.STG_VENTA_RESUMEN
        WHERE CargaID=?''',sales_id)
    summary_total=[x for x in summary if str(x['TipoDocumento']).strip().lower()=='total']
    result(len(summary_total)==1 and int(summary_total[0]['Cantidad'])==len(invoices) and
           money(summary_total[0]['Neto_CLP'])==net_total,
           'Ventas DETALLE concilia con RESUMEN',
           f'Facturas: {len(invoices)} | Neto: ${int(net_total):,}'.replace(',','.'))
    return aggregate,per_client,len(invoices),net_total


def compare(a,b,code):
    if a is None or b is None:
        return a is None and b is None
    tolerance = Decimal('0.02') if code not in ('COM_VARIACION_MENSUAL_PCT','COM_PARTICIPACION_CLIENTE_MES_PCT') else Decimal('0.001')
    return abs(D(a)-D(b))<=tolerance


def check_sales(cur, sales_id):
    line('\n2. Recalculo INDEPENDIENTE de los 9 KPI de ventas')
    globals_expected,clients_expected,n,net=expected_sales(cur,sales_id)
    if not globals_expected:
        return
    data=query(cur, '''SELECT k.CodigoKPI, f.Ambito, f.ResultadoNumerico,
        f.Cliente_Key, df.Fecha, dc.RUT_Normalizado
        FROM dbo.FACT_KPI_ESTRATEGICO f
        JOIN dbo.DIM_KPI k ON k.KPI_Key=f.KPI_Key
        JOIN dbo.DIM_FECHA df ON df.Fecha_Key=f.Fecha_Key
        LEFT JOIN dbo.DIM_CLIENTE dc ON dc.Cliente_Key=f.Cliente_Key
        WHERE f.CargaID=? AND f.FuenteResultado='VENTAS'
        AND k.CodigoKPI LIKE 'COM[_]%' ''',sales_id)
    values={}
    duplicated=[]
    for r in data:
        month=date_value(r['Fecha']).replace(day=1)
        code=r['CodigoKPI']
        cust=norm_rut(r['RUT_Normalizado']) if r['Ambito']=='CLIENTE' else None
        key=(month,cust,code)
        if key in values: duplicated.append(key)
        values[key]=r['ResultadoNumerico']
    result(not duplicated,'No hay duplicados en KPI comerciales vigentes',f'Duplicados: {len(duplicated)}')
    checks=Counter()
    sample=[]
    expected_keys=set()
    for month, codes in globals_expected.items():
        for code, val in codes.items():
            key=(month,None,code)
            expected_keys.add(key)
            checks[code]+=1
            if key not in values or not compare(val,values.get(key),code):
                sample.append(f'{code} mes {month:%Y-%m}')
    for (month,cust), codes in clients_expected.items():
        for code,val in codes.items():
            key=(month,cust,code)
            expected_keys.add(key)
            checks[code]+=1
            if key not in values or not compare(val,values.get(key),code):
                sample.append(f'{code} mes {month:%Y-%m} cliente anonimizado')
    extra=set(values)-expected_keys
    result(not sample and not extra,'Los 9 indicadores comerciales coinciden con facturas',
           f'Comparaciones: {sum(checks.values())} | diferencias: {len(sample)} | sobrantes: {len(extra)}')
    if sample:
        for s in sample[:8]: line('  DIFERENCIA: '+s)
    if extra:
        line(f'  EXTRA: {len(extra)} mediciones comerciales no justificadas por el DETALLE actual')
    for code in CODES_GLOBAL+CODES_CLIENT:
        line(f"  {code}: {checks[code]} comprobaciones")


def check_events(cur):
    line('\n3. Proyectos, contratos y cierres')
    count=query(cur, '''SELECT TipoRegistro,COUNT_BIG(*) AS N,
        COUNT(DISTINCT IDOrigen) AS Unicos
        FROM dbo.FACT_SEGUIMIENTO_OPERACIONAL
        WHERE TipoRegistro IN ('PROYECTO','TAREA','RECURSO','ADJUDICACION','CONTRATO')
        GROUP BY TipoRegistro''')
    current={r['TipoRegistro']:(int(r['N']),int(r['Unicos'])) for r in count}
    for key,expected in [('PROYECTO',17),('TAREA',85),('RECURSO',110),('ADJUDICACION',17)]:
        got,unique=current.get(key,(0,0))
        result(got==expected and got==unique,f'{key}: registros actuales sin duplicados',f'{got}/{expected}')
    contracts,unique=current.get('CONTRATO',(0,0))
    result(contracts>=3 and unique==contracts,'Contratos en hechos y sin duplicados',f'{contracts} contrato(s)')
    pc=one(cur,'''SELECT COUNT(DISTINCT Proyecto_Key) AS N FROM dbo.FACT_SEGUIMIENTO_OPERACIONAL
        WHERE TipoRegistro='CONTRATO' AND Proyecto_Key IS NOT NULL''')
    result(pc is not None and pc['N']>=1,'Contratos vinculados a proyecto',
           f'Proyectos con contrato: {pc["N"] if pc else 0}')
    gg=query(cur,'''SELECT df.Fecha,k.CodigoKPI,COUNT_BIG(*) N
        FROM dbo.FACT_KPI_ESTRATEGICO f
        JOIN dbo.DIM_KPI k ON k.KPI_Key=f.KPI_Key
        JOIN dbo.DIM_FECHA df ON df.Fecha_Key=f.Fecha_Key
        WHERE f.FuenteResultado='GMAIL' AND f.GranoTemporal='MES'
        AND k.CodigoKPI IN ('GMAIL_FACTURADO_MES','GMAIL_PENDIENTE_MES')
        GROUP BY df.Fecha,k.CodigoKPI''')
    periods=defaultdict(set)
    repeats=False
    for r in gg:
        periods[date_value(r['Fecha'])].add(r['CodigoKPI'])
        if int(r['N'])!=1:repeats=True
    result(len(periods)>=3 and not repeats and all(len(x)==2 for x in periods.values()),
           'Cierres Gmail: dos indicadores por mes, sin duplicar',f'Meses: {len(periods)}')


def find_streamlit(custom):
    if custom:
        root=Path(custom)
        return root if (root/'maas_datos.py').exists() else None
    base=Path(__file__).resolve().parent
    for root in [base,base.parent,base.parent.parent]:
        if (root/'maas_datos.py').is_file():return root
        for x in root.glob('MAAS_STREAMLIT*/maas_datos.py'):
            return x.parent
    return None


def query_constants(path):
    tree=ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
    out={}
    for stmt in tree.body:
        if isinstance(stmt,ast.Assign):
            for t in stmt.targets:
                if isinstance(t,ast.Name) and t.id=='QUERIES':
                    out.update(ast.literal_eval(stmt.value))
                if isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name) and t.value.id=='QUERIES':
                    key=ast.literal_eval(t.slice)
                    out[key]=ast.literal_eval(stmt.value)
    return out


def check_streamlit(cur, custom):
    line('\n4. Consultas reales de Streamlit y sintaxis')
    root=find_streamlit(custom)
    if root is None:
        result(False,'Directorio de Streamlit no localizado',
               'Repite con --streamlit "RUTA_CARPETA_STREAMLIT" para revisar el dashboard',severity='warn')
        return
    line('Carpeta Streamlit: '+str(root))
    scripts=[p for p in root.rglob('*.py') if not any(x in {'venv','.venv','__pycache__'} for x in p.parts)]
    errors=[]
    for path in scripts:
        try:ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
        except (SyntaxError,UnicodeDecodeError) as e:errors.append(f'{path.relative_to(root)}: {e}')
    result(not errors,'Sintaxis Python de paginas Streamlit',f'{len(scripts)} archivos | errores: {len(errors)}')
    for s in errors[:8]:line('  '+s)
    try:queries=query_constants(root/'maas_datos.py')
    except Exception as e:
        result(False,'Leer consultas de maas_datos.py',str(e))
        return
    # Ejecuta las mismas SELECT del dashboard, no valores inventados.
    errors=[]
    seen={}
    for name,sql in queries.items():
        try:
            if not isinstance(sql,str) or not re.match(r'^\s*(SELECT|WITH)\b',sql,re.I):
                raise ValueError('No SELECT')
            data=query(cur,sql)
            seen[name]=len(data)
        except Exception as e:
            errors.append((name,str(e).splitlines()[0][:220]))
    result(not errors,'Consultas SQL de maas_datos.py ejecutan correctamente',
           f'{len(queries)-len(errors)}/{len(queries)} consultas exitosas')
    for name,err in errors[:12]:line(f'  CONSULTA CON ERROR: {name} | {err}')
    if 'bsc' in seen:
        result(seen['bsc']>=60,'Streamlit recibe 15 KPI globales y 45 departamentales',
               f"Filas BSC: {seen['bsc']}")
    for name,expected in [('etl_proyectos',17),('etl_tareas',85),('etl_recursos',110),('etl_contratos',3),('etl_cierres_gmail',6)]:
        if name in seen:
            result(seen[name]>=expected,f'Streamlit recibe {name}',f'{seen[name]} filas (min {expected})')
    # La actualizacion visual en navegador depende de cache y de los permisos.
    line('NOTA: SELECT correcto no garantiza renderizado navegador/roles: comprobar pantalla.')


def main():
    parser=argparse.ArgumentParser(description='Auditoria MAAS 4: solo lectura SQL + codigo Streamlit')
    parser.add_argument('--servidor',default=SERVER_DEFAULT)
    parser.add_argument('--streamlit',default=None,help='Carpeta que contiene maas_datos.py')
    args=parser.parse_args()
    line('MAAS ECOLOGIA 4 | AUDITORIA FINAL | SOLO LECTURA')
    line('Base: '+DATABASE+' | Servidor: '+args.servidor)
    con=None
    try:
        import pyodbc
        driver=next((d for d in ('ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server') if d in pyodbc.drivers()),None)
        if not driver:raise RuntimeError('Falta ODBC Driver 17/18')
        con=pyodbc.connect(f'DRIVER={{{driver}}};SERVER={args.servidor};DATABASE={DATABASE};'
                             'Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;'
                             'Connection Timeout=10;Application Name=MAAS_AUDITORIA_SOLO_LECTURA;',
                             autocommit=True,timeout=25)
        cur=con.cursor()
        bsc_id=latest(cur,'BSC')
        sales_id=latest(cur,'VENTAS')
        line(f'Carga BSC vigente: {bsc_id} | Ventas vigente: {sales_id}')
        check_bsc(cur,bsc_id)
        check_sales(cur,sales_id)
        check_events(cur)
        check_streamlit(cur,args.streamlit)
    except Exception as exc:
        result(False,'No fue posible completar auditoria',f'{type(exc).__name__}: {exc}')
    finally:
        if con is not None:con.close()
    line('\n5. Pruebas que requieren observacion en el PC')
    line('- Programador: dejar ejecutando 09_programar_etl_maas.py y confirmar que detecta un cambio REAL en Drive/Gmail sin ejecutar el maestro manualmente.')
    line('- Interfaz: presionar Actualizar datos desde SQL; revisar los KPI y graficos por rol/area.')
    line('- KPI manual >1000MM: resultado es dato informado, NO adjudicacion comprobada.')
    line('- 11 KPI PRY_V12 historicos: NO se recalculan con el ETL de 22 fuentes.')
    line(f'\nRESUMEN: {FAILS} fallas | {WARNINGS} aspectos pendientes/advertencias')
    if FAILS:
        line('ESTADO: NO VALIDADO AL 100%. Corrige las fallas antes de modificar o redistribuir datos.')
    else:
        line('ESTADO: controles SQL superados; faltan las comprobaciones indicadas como pendientes.')
    outfile=Path(__file__).resolve().parent/'logs_etl'/'auditoria_final_maas4.txt'
    try:
        outfile.parent.mkdir(parents=True,exist_ok=True)
        outfile.write_text('\n'.join(R)+'\n',encoding='utf-8')
        line('Informe guardado: '+str(outfile))
    except OSError as e:
        line('No se pudo guardar TXT local: '+str(e))
    return 1 if FAILS else 0


if __name__=='__main__':
    sys.exit(main())
