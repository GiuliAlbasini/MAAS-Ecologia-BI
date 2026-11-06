# -*- coding: ascii -*-
"""Pruebas locales de identidad estable: NO conecta SQL ni lee Drive."""
from bsc_identidades_estables import construir_mapa, codigo_para_fila, codigo_para_departamento

def g(n, nombre, cat='Control'):
    return {'FilaExcel':n, 'NombreKPI':nombre, 'Categoria':cat}

def d(n, nombre, hoja='INGENIERIA'):
    return {'FilaExcel':n,'NombreHoja':hoja,'Departamento':hoja,'NombreKPI':nombre,'Categoria':'Control'}

def debe_fallar(f):
    try:
        f()
    except RuntimeError:
        return
    raise AssertionError('Se acepto un cambio de identidad no permitido')

def run():
    prev=[g(i,f'Indicador {i}') for i in range(10,25)]
    ahora=[dict(x) for x in prev]
    ahora[0]['NombreKPI']='Porcentaje nuevo de capacitacion'
    ahora[3]['NombreKPI']='Encuestas de calidad corregidas'
    dp=[d(8,'Indicador 10'),d(9,'Indicador 11'),d(10,'Alias externo')]
    dn=[dict(x) for x in dp]
    dn[0]['NombreKPI']='Porcentaje nuevo de capacitacion'
    dims=[{'CodigoKPI':f'BSC_COD_{x["FilaExcel"]}','NombreKPI':x['NombreKPI'],
           'TipoIndicador':'OFICIAL_BSC'} for x in prev]
    mapa=construir_mapa(prev,ahora,dp,dn,dims)
    assert len(mapa['global'])==15
    assert codigo_para_fila(mapa,10,'Porcentaje nuevo de capacitacion')=='BSC_COD_10'
    assert codigo_para_fila(mapa,13,'Encuestas de calidad corregidas')=='BSC_COD_13'
    assert codigo_para_departamento(mapa,'INGENIERIA',8,'Porcentaje nuevo de capacitacion')=='BSC_COD_10'
    assert codigo_para_departamento(mapa,'INGENIERIA',10,'Alias externo') is None
    assert len({r['codigo'] for r in mapa['global'].values()})==15
    # Un siguiente renombre conserva el MISMO codigo a traves del registro local.
    ultimos=[dict(x) for x in ahora]
    ultimos[0]['NombreKPI']='Capacitacion trimestral'
    dims_actual=[dict(x,CodigoKPI=f'BSC_COD_{x["FilaExcel"]}') for x in []]
    dims_actual=[{'CodigoKPI':f'BSC_COD_{x["FilaExcel"]}', 'NombreKPI':x['NombreKPI'],
                  'TipoIndicador':'OFICIAL_BSC'} for x in ahora]
    mapa2=construir_mapa(ahora,ultimos,dn,dn,dims_actual,{'global':mapa['global']})
    assert codigo_para_fila(mapa2,10,'Capacitacion trimestral')=='BSC_COD_10'
    # Cambiar la categoria, mover/insertar y borrar filas se rechaza.
    altered=[dict(x) for x in ahora]
    altered[0]['Categoria']='Otra categoria'
    debe_fallar(lambda: construir_mapa(prev,altered,dp,dn,dims))
    altered=[dict(x) for x in ahora]
    altered[0]['FilaExcel']=100
    debe_fallar(lambda: construir_mapa(prev,altered,dp,dn,dims))
    altered=[dict(x) for x in ahora]
    altered[0]['NombreKPI']='Indicador 11'  # otro KPI historico en otra fila
    debe_fallar(lambda: construir_mapa(prev,altered,dp,dn,dims))
    altered=ahora[:-1]
    debe_fallar(lambda: construir_mapa(prev,altered,dp,dn,dims))
    print('PRUEBAS OK: cambios de nombre, identidad historica, departamentos y protecciones.')

if __name__=='__main__':
    run()
