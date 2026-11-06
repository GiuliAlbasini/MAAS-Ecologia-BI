# -*- coding: utf-8 -*-
"""Prueba sin SQL ni red de identidad de KPI departamental manual > 1000MM."""
from bsc_identidades_estables import construir_mapa, codigo_para_departamento, CODIGO_1000MM

def main():
    prev = [{'FilaExcel': i, 'NombreKPI': f'Indicador global {i}', 'Categoria':'Operaciones'} for i in range(4,19)]
    curr = [dict(x) for x in prev]
    old = [{'NombreHoja':'INGENIERIA', 'FilaExcel':13, 'Departamento':'INGENIERIA Y PROPUESTAS',
            'Categoria':'Licitaciones', 'NombreKPI':'Ganar 1 contrato sobre 1000MM'},
           {'NombreHoja':'OPERACIONES','FilaExcel':3,'Departamento':'OPERACIONES',
            'Categoria':'Operaciones','NombreKPI':'Indicador global 4'}]
    new = [dict(x) for x in old]
    dims = [{'CodigoKPI':f'BSC_ID_{x["FilaExcel"]}', 'NombreKPI':x['NombreKPI'],
             'TipoIndicador':'OFICIAL_BSC'} for x in prev]
    mapping = construir_mapa(prev,curr,old,new,dims)
    assert codigo_para_departamento(mapping, 'INGENIERIA',13,'Ganar 1 contrato sobre 1000MM') == CODIGO_1000MM
    assert codigo_para_departamento(mapping,'OPERACIONES',3,'Indicador global 4') == 'BSC_ID_4'
    changed = [dict(x) for x in new]
    changed[0]['NombreKPI'] = 'Contrato adjudicado superior a mil millones'
    mapping2 = construir_mapa(prev,curr,old,changed,dims,{'departamentos':mapping['departamentos']})
    assert codigo_para_departamento(mapping2,'INGENIERIA',13,changed[0]['NombreKPI']) == CODIGO_1000MM
    bad = [dict(x) for x in old]
    bad[0]['Categoria'] = 'Otra categoria'
    try:
        construir_mapa(prev,curr,bad,bad,dims)
    except RuntimeError:pass
    else:raise AssertionError('Debe bloquear cambios de categoria')
    print('PRUEBAS OK: KPI manual 1000MM incluido una sola vez, clave estable, bloqueo de categoria.')

if __name__=='__main__':main()
