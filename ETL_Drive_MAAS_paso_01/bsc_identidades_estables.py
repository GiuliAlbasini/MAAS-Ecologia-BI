# -*- coding: utf-8 -*-
"""Identidad estable de KPI del BSC sin cambiar el Excel ni la base.

La identidad fisica es (hoja, FilaExcel) y se enlaza al CodigoKPI
historico de DIM_KPI a traves del lote BSC PREVIAMENTE confirmado.
Permite editar NOMBRES, pero nunca reubicar, borrar o agregar filas de KPI
sin una migracion de identidad expresamente revisada.

EL MODULO NO HACE UPDATE A SQL; solamente consulta datos y crea el
archivo efimero logs_etl/identidades_bsc_vigentes.json. Los pasos 05/06
revalidan la huella del CargaID antes de usarlo.
"""
from __future__ import annotations
import json
import hashlib
import os
import re
import unicodedata
from pathlib import Path

NOMBRE_REGISTRO = 'identidades_bsc_vigentes.json'
ID_BSC_HISTORICO = '1BwZDowASatFv_eFhG2XHGuSg2_6wdveY'
ID_BSC_ACTUAL = '1uvwp6qW35fw8-Eb8o4O4zp3umNeRFfpt'
NUEVA_FILA = 19
NUEVO_NOMBRE = 'Margen Operativo'
NUEVA_CATEGORIA = 'Finanzas'
# Excepcion explicita: KPI REAL del BSC departamental que no existe en el BSC global.
# Su resultado se toma del Excel MANUALMENTE, nunca se infiere de facturas.
CODIGO_1000MM = 'BSC_DEP_ING_13_CONTRATO_1000MM'
HOJA_FILA_1000MM = 'INGENIERIA|13'
NOMBRE_BASE_1000MM = 'Ganar 1 contrato sobre 1000MM'


def norm(v):
    v=unicodedata.normalize('NFKD', str(v or '').strip())
    return '_'.join(re.findall(r'[a-z0-9]+', v.encode('ascii','ignore').decode('ascii').lower()))


def _filas(datos, esquema, tabla):
    columnas=esquema[tabla]
    return [dict(zip(columnas,r)) for r in datos['bsc'][tabla]]


def _clave_dep(row):
    return str(row['NombreHoja'])+'|'+str(int(row['FilaExcel']))


def cotejar(previous_global, current_global, previous_dep, current_dep):
    """Exige mismas posiciones y categorias. Nunca infiere nombres por similitud."""
    a={int(r['FilaExcel']):r for r in previous_global}
    b={int(r['FilaExcel']):r for r in current_global}
    if (len(a)!=15 or len(a)!=len(previous_global) or len(b)!=16
            or len(b)!=len(current_global) or set(b)-set(a)!={NUEVA_FILA}):
        raise RuntimeError('BSC: se requieren 15 filas historicas intactas y solo la nueva fila 19.')
    extra=b[NUEVA_FILA]
    if norm(extra['NombreKPI'])!=norm(NUEVO_NOMBRE) or norm(extra['Categoria'])!=norm(NUEVA_CATEGORIA):
        raise RuntimeError('BSC fila 19: solo se autoriza Margen Operativo, categoria Finanzas.')
    if any(norm(r['NombreKPI'])==norm(NUEVO_NOMBRE) for r in a.values()):
        raise RuntimeError('Margen Operativo ya existia en el BSC historico; no se autoriza duplicado.')
    for fila,r in a.items():
        v=b[fila]
        if norm(r['Categoria'])!=norm(v['Categoria']):
            raise RuntimeError(f'BSC fila {fila}: categoria cambio; no es un simple renombre.')
        if not norm(v['NombreKPI']):
            raise RuntimeError(f'BSC fila {fila}: nombre vacio.')
    p={_clave_dep(r):r for r in previous_dep}
    q={_clave_dep(r):r for r in current_dep}
    if len(p)!=len(previous_dep) or len(q)!=len(current_dep) or set(p)!=set(q):
        raise RuntimeError('BSC departamental: cambian hojas/filas; no se puede asumir misma identidad.')
    for key,r in p.items():
        v=q[key]
        if norm(r['Departamento'])!=norm(v['Departamento']) or norm(r['Categoria'])!=norm(v['Categoria']):
            raise RuntimeError(f'BSC departamental {key}: categoria o departamento cambiaron.')
        if not norm(v['NombreKPI']):
            raise RuntimeError(f'BSC departamental {key}: nombre vacio.')
    # Bloquear intercambio detectado (A renombrado igual al antiguo B, B movido).
    old_to_row={norm(r['NombreKPI']):fila for fila,r in a.items()}
    for fila, v in b.items():
        old_fila=old_to_row.get(norm(v['NombreKPI']))
        if old_fila is not None and old_fila!=fila:
            raise RuntimeError(f'BSC: indicador de la fila {old_fila} aparece en la {fila}. Reordenar requiere migracion.')
    return a,b,p,q


def construir_mapa(previous_global,current_global,previous_dep,current_dep,dimensiones, respaldo=None):
    """Funcion pura, puede probarse sin SQL. Dimensiones incluye (CodigoKPI,NombreKPI,TipoIndicador)."""
    a,b,p,q=cotejar(previous_global,current_global,previous_dep,current_dep)
    reg_prev=(respaldo or {}).get('global',{})
    prev_by_name={}
    prev_by_code={}
    for row in dimensiones:
        code=str(row['CodigoKPI'])
        if norm(row.get('TipoIndicador'))=='oficial_bsc':
            prev_by_code[code]=row
            name_key=norm(row['NombreKPI'])
            if name_key in prev_by_name:
                raise RuntimeError('DIM_KPI: nombre BSC duplicado.')
            prev_by_name[name_key]=code
    if len(prev_by_code)<15:
        raise RuntimeError('DIM_KPI: faltan KPI BSC historicos. No crear nuevos de forma automatica.')
    nuevos={}
    codigos=set()
    antiguas_alias={}
    for fila in sorted(a):
        viejo=str(a[fila]['NombreKPI'])
        nuevo=str(b[fila]['NombreKPI'])
        codigo=reg_prev.get(str(fila),{}).get('codigo')
        if not codigo:
            codigo=prev_by_name.get(norm(viejo))
        if not codigo or codigo not in prev_by_code or codigo in codigos:
            raise RuntimeError(f'BSC fila {fila}: no se puede reconciliar CodigoKPI existente de {viejo!r}.')
        codigos.add(codigo)
        antiguos_norm=norm(viejo)
        nuevos[str(fila)]={'codigo':codigo,'nombre':nuevo,'anterior':viejo,'categoria':str(b[fila]['Categoria'] or '')}
        antiguas_alias[antiguos_norm]=codigo
        antiguas_alias[norm(nuevo)]=codigo
    if len(nuevos)!=15:
        raise RuntimeError('BSC: deben conservarse las 15 identidades estables historicas.')
    extra=b[NUEVA_FILA]
    clave_nueva=norm(extra['NombreKPI'])
    codigo_nuevo='BSC_'+hashlib.sha256(clave_nueva.encode('utf-8')).hexdigest()[:16].upper()
    if codigo_nuevo in codigos or clave_nueva in prev_by_name:
        raise RuntimeError('El CodigoKPI nuevo ya existe; revisar antes de insertar.')
    nuevos[str(NUEVA_FILA)]={'codigo':codigo_nuevo,'nombre':str(extra['NombreKPI']),
                             'anterior':'','categoria':str(extra['Categoria'])}
    antiguas_alias[clave_nueva]=codigo_nuevo
    dept_map={}
    for key,old in p.items():
        # Los que originalmente no conciliaban con KPI global quedan SIN ASOCIAR;
        # renombrar un alias no lo convierte silenciosamente en un hecho nuevo.
        prev_code=antiguas_alias.get(norm(old['NombreKPI']))
        if key == HOJA_FILA_1000MM:
            anterior_dep=(respaldo or {}).get('departamentos',{}).get(key,{})
            tiene_identidad_prev=(anterior_dep.get('codigo') == CODIGO_1000MM)
            if (norm(old['NombreKPI']) != norm(NOMBRE_BASE_1000MM)
                    and not tiene_identidad_prev):
                raise RuntimeError('El KPI de 1000MM no tiene identidad previa comprobable.')
            if norm(old['Categoria']) != 'licitaciones':
                raise RuntimeError('KPI de 1000MM: categoria de origen inesperada.')
            if prev_code not in (None, CODIGO_1000MM):
                raise RuntimeError('KPI de 1000MM: colision con KPI global.')
            # Su nombre podra editarse, pero su codigo queda anclado a hoja/fila.
            prev_code=CODIGO_1000MM
        dept_map[key]={'codigo':prev_code,'nombre':str(q[key]['NombreKPI'])}
    return {'global':nuevos,'departamentos':dept_map}


def _leer_json(path):
    if not Path(path).is_file():
        return None
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _mapa_actualizacion(prev_g, curr_g, prev_d, curr_d, dim, respaldo):
    """Mantiene codigos ya confirmados por posicion; no rehace la migracion inicial."""
    if not respaldo or not isinstance(respaldo.get('global'), dict) or not isinstance(respaldo.get('departamentos'), dict):
        raise RuntimeError('BSC actual: falta mapa de identidades confirmado; no se pueden reconstruir codigos por nombre.')
    a = {int(r['FilaExcel']): r for r in prev_g}
    b = {int(r['FilaExcel']): r for r in curr_g}
    if len(a) != len(prev_g) or len(b) != len(curr_g) or set(a) != set(b) or len(a) != 16:
        raise RuntimeError('BSC actual: se agregaron, eliminaron o duplicaron filas KPI; requiere migracion revisada.')
    if set(respaldo['global']) != {str(k) for k in a}:
        raise RuntimeError('BSC actual: las filas del mapa vigente difieren del lote confirmado.')
    ap = {_clave_dep(r): r for r in prev_d}
    bp = {_clave_dep(r): r for r in curr_d}
    if (len(ap) != len(prev_d) or len(bp) != len(curr_d)
            or set(ap) != set(bp) or set(ap) != set(respaldo['departamentos'])):
        raise RuntimeError('BSC actual: hojas o filas departamentales cambiaron; requiere conciliacion.')
    codigo_dim = {str(row['CodigoKPI']) for row in dim}
    codes = set()
    resultado_g = {}
    nombres_anteriores = {norm(r['NombreKPI']): fila for fila, r in a.items()}
    for fila in sorted(a):
        old, new, saved = a[fila], b[fila], respaldo['global'][str(fila)]
        code = str(saved.get('codigo') or '')
        if (not code or code in codes or code not in codigo_dim
                or norm(saved.get('nombre')) != norm(old['NombreKPI'])
                or norm(saved.get('categoria')) != norm(old['Categoria'])):
            raise RuntimeError(f'BSC fila {fila}: mapa previo no coincide con STAGING/DIM_KPI confirmado.')
        if norm(old['Categoria']) != norm(new['Categoria']) or not norm(new['NombreKPI']):
            raise RuntimeError(f'BSC fila {fila}: cambio de categoria o nombre vacio.')
        otro = nombres_anteriores.get(norm(new['NombreKPI']))
        if otro is not None and otro != fila:
            raise RuntimeError(f'BSC fila {fila}: nombre pertenecia a fila {otro}; no se permite intercambio.')
        codes.add(code)
        resultado_g[str(fila)] = {
            'codigo': code, 'nombre': str(new['NombreKPI']),
            'anterior': str(old['NombreKPI']), 'categoria': str(new['Categoria'] or '')
        }
    if (norm(resultado_g[str(NUEVA_FILA)]['nombre']) != norm(NUEVO_NOMBRE)
            or norm(resultado_g[str(NUEVA_FILA)]['categoria']) != norm(NUEVA_CATEGORIA)):
        raise RuntimeError('BSC fila 19: Margen Operativo y categoria Finanzas deben mantenerse.')
    resultado_d = {}
    for clave, old in ap.items():
        new, saved = bp[clave], respaldo['departamentos'][clave]
        if (norm(old['NombreKPI']) != norm(saved.get('nombre'))
                or norm(old['Departamento']) != norm(new['Departamento'])
                or norm(old['Categoria']) != norm(new['Categoria'])
                or not norm(new['NombreKPI'])):
            raise RuntimeError(f'BSC departamental {clave}: cambia identidad, categoria o departamento.')
        code = saved.get('codigo')
        if code and code != CODIGO_1000MM and str(code) not in codes:
            raise RuntimeError(f'BSC departamental {clave}: codigo no corresponde a KPI global confirmado.')
        if clave == HOJA_FILA_1000MM and code != CODIGO_1000MM:
            raise RuntimeError('BSC departamental 1000MM: codigo estable no coincide.')
        resultado_d[clave] = {'codigo': code, 'nombre': str(new['NombreKPI'])}
    return {'global': resultado_g, 'departamentos': resultado_d}


def preparar_desde_maestro(root, anterior, actual, modulo_04, servidor=r'Giuli\GIULIANA'):
    """Reconcilia la primera migracion o una actualizacion posterior, sin escribir SQL."""
    if anterior is None or not anterior.get('versiones', {}).get('bsc'):
        raise RuntimeError('No hay snapshot BSC confirmado. Requiere inicializacion manual protegida.')
    root = Path(root)
    fuentes, datos = modulo_04.build_dataset()
    sha_act = modulo_04.fingerprint(datos['bsc'])
    if sha_act != actual['versiones']['bsc']:
        raise RuntimeError('Huella BSC diferente entre maestro y extractor.')
    prev_sha = anterior['versiones']['bsc']
    prev_file = _leer_json(root / 'logs_etl' / NOMBRE_REGISTRO)
    if fuentes['bsc']['meta'].get('id_drive') != ID_BSC_ACTUAL:
        raise RuntimeError('El BSC actual no corresponde al Excel nuevo autorizado.')

    con = modulo_04.conectar(servidor)
    try:
        cur = con.cursor()
        # El hash de un snapshot confirmado determina el lote. No se elige
        # el ultimo CargaID ni se acepta un hash en cualquier Drive.
        cargas = cur.execute('''SELECT CargaID, IdArchivoDrive FROM dbo.ETL_CARGA
            WHERE TipoFuente='BSC' AND IdArchivoDrive IN (?, ?)
              AND HashArchivoSHA256=? AND Estado='OK' ''',
            ID_BSC_HISTORICO, ID_BSC_ACTUAL, prev_sha).fetchall()
        if len(cargas) != 1:
            raise RuntimeError(
                f'BSC: se esperaban 1 lote previo confirmado y se encontraron {len(cargas)} '
                f'para hash {prev_sha[:12]} (Drive historico/actual). No cargar SQL.')
        carga_id, drive_anterior = int(cargas[0][0]), str(cargas[0][1])
        prev_g = [dict(FilaExcel=fila, Categoria=categoria, NombreKPI=nombre)
                  for fila, categoria, nombre in cur.execute('''SELECT FilaExcel,Categoria,NombreKPI
                  FROM dbo.STG_BSC_KPI WHERE CargaID=? ORDER BY FilaExcel''', carga_id).fetchall()]
        prev_d = [dict(NombreHoja=hoja, Departamento=dep, FilaExcel=fila,
                       Categoria=categoria, NombreKPI=nombre)
                  for hoja, dep, fila, categoria, nombre in cur.execute('''SELECT NombreHoja,Departamento,FilaExcel,Categoria,NombreKPI
                  FROM dbo.STG_KPI_DEPARTAMENTO WHERE CargaID=? ORDER BY NombreHoja,FilaExcel''', carga_id).fetchall()]
        dim = [dict(CodigoKPI=code, NombreKPI=name, TipoIndicador=tipo)
               for code, name, tipo in cur.execute('''SELECT CodigoKPI,NombreKPI,TipoIndicador FROM dbo.DIM_KPI''').fetchall()]
    finally:
        con.rollback()
        con.close()

    curr_g = _filas(datos, modulo_04.SCHEMA, 'STG_BSC_KPI')
    curr_d = _filas(datos, modulo_04.SCHEMA, 'STG_KPI_DEPARTAMENTO')
    if drive_anterior == ID_BSC_HISTORICO:
        # Primera migracion, 15 -> 16. El snapshot historico es la autoridad.
        respaldo = prev_file if prev_file and prev_sha in (
            prev_file.get('sha_activo'), prev_file.get('sha_anterior')) else None
        mapping = construir_mapa(prev_g, curr_g, prev_d, curr_d, dim, respaldo)
        fase = 'migracion inicial'
    else:
        # Las ejecuciones siguientes ya parten de 16 KPI. No volver a
        # ejecutar construir_mapa(), que exige 15 KPI historicos.
        if not prev_file:
            raise RuntimeError('BSC actual: no existe mapa de identidad previo. Reconciliar manualmente.')
        # Disponibles en ambas ramas: mapa del snapshot confirmado o
        # mapa preparado por --probar. No depender de una rama condicional.
        saved_g = prev_file.get('global', {})
        saved_d = prev_file.get('departamentos', {})
        if not isinstance(saved_g, dict) or not isinstance(saved_d, dict):
            raise RuntimeError('BSC actual: registro de identidades mal formado.')
        if prev_file.get('sha_activo') == prev_sha:
            # Mapa correspondiente al ultimo lote confirmado; caso habitual.
            respaldo_confirmado = prev_file
        elif (prev_file.get('sha_anterior') == prev_sha
              and prev_file.get('sha_activo') == sha_act):
            # --probar pudo preparar el mapa para el lote nuevo sin escribir SQL.
            # El snapshot confirmado sigue apuntando al lote antiguo. En vez
            # de rechazarlo, verificar el mapa preparado contra ambos lotes,
            # anclar sus codigos a DIM_KPI y recrear el respaldo del lote previo.
            prev_global = {int(r['FilaExcel']): r for r in prev_g}
            curr_global = {int(r['FilaExcel']): r for r in curr_g}
            prev_dep = {_clave_dep(r): r for r in prev_d}
            curr_dep = {_clave_dep(r): r for r in curr_d}
            if (len(prev_global) != len(prev_g) or len(curr_global) != len(curr_g)
                    or len(prev_dep) != len(prev_d) or len(curr_dep) != len(curr_d)
                    or len(prev_global) != 16 or len(prev_dep) != 45
                    or set(prev_global) != set(curr_global)
                    or set(saved_g) != {str(k) for k in prev_global}
                    or set(prev_dep) != set(curr_dep) or set(saved_d) != set(prev_dep)):
                raise RuntimeError('BSC: mapa preparado incompatible con el lote confirmado.')
            dim_codes = {str(r['CodigoKPI']) for r in dim}
            codigos = set()
            for fila, old in prev_global.items():
                new, saved = curr_global[fila], saved_g[str(fila)]
                code = str(saved.get('codigo') or '')
                if (not code or code in codigos or code not in dim_codes
                        or norm(saved.get('nombre')) != norm(new['NombreKPI'])
                        or norm(saved.get('categoria')) != norm(new['Categoria'])
                        or norm(old['Categoria']) != norm(new['Categoria'])):
                    raise RuntimeError(f'BSC fila {fila}: mapa preparado no conciliable con STAGING/DIM.')
                codigos.add(code)
            for clave, old in prev_dep.items():
                new, saved = curr_dep[clave], saved_d[clave]
                code = saved.get('codigo')
                if (norm(saved.get('nombre')) != norm(new['NombreKPI'])
                        or norm(old['Departamento']) != norm(new['Departamento'])
                        or norm(old['Categoria']) != norm(new['Categoria'])
                        or (code and code != CODIGO_1000MM and str(code) not in codigos)
                        or (clave == HOJA_FILA_1000MM and code != CODIGO_1000MM)):
                    raise RuntimeError(f'BSC departamental {clave}: mapa preparado incompatible.')
            respaldo_confirmado = {
                'global': {str(fila): dict(saved_g[str(fila)], nombre=str(old['NombreKPI']),
                                           categoria=str(old['Categoria']))
                           for fila, old in prev_global.items()},
                'departamentos': {clave: dict(saved_d[clave], nombre=str(old['NombreKPI']))
                                  for clave, old in prev_dep.items()},
            }
        else:
            raise RuntimeError('BSC actual: mapa vigente no corresponde al snapshot confirmado ni a una prueba del lote actual. Reconciliar manualmente.')
        mapping = _mapa_actualizacion(prev_g, curr_g, prev_d, curr_d, dim, respaldo_confirmado)
        # Nunca aceptar un mapa preparado que difiera de los codigos previamente verificados.
        if prev_file.get('sha_activo') == sha_act and prev_file.get('sha_anterior') == prev_sha:
            for clave, fila in mapping['global'].items():
                if fila['codigo'] != saved_g[clave]['codigo']:
                    raise RuntimeError('BSC: codigo global alterado entre prueba y ejecucion.')
            for clave, fila in mapping['departamentos'].items():
                if fila['codigo'] != saved_d[clave]['codigo']:
                    raise RuntimeError('BSC: codigo departamental alterado entre prueba y ejecucion.')
        fase = 'actualizacion con identidades conservadas'

    mapping.update({'sha_activo': sha_act, 'sha_anterior': prev_sha, 'version': 2})
    path = root / 'logs_etl' / NOMBRE_REGISTRO
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(mapping, ensure_ascii=True, indent=2), encoding='ascii')
    os.replace(temp, path)
    print(f'BSC IDENTIDAD ESTABLE: {fase}; {len(mapping["global"])} KPI globales '
          f'y {len(mapping["departamentos"])} departamentales, lote anterior {carga_id}.')
    return mapping


def _reconciliar_lote_bsc(cur, carga_id, root, mapa, hash_actual):
    """Reconcilia un BSC actualizado sin generar ni reasignar CodigoKPI.

    Solo admite los mismos KPI fisicos (hoja y fila) y categorias que el
    ultimo lote referenciado por el mapa local. No necesita que la lista de
    proyectos del seguimiento coincida con la del BSC. Solo consulta SQL.
    """
    if (not isinstance(mapa.get('global'), dict)
            or not isinstance(mapa.get('departamentos'), dict)):
        raise RuntimeError('Mapa BSC incompleto: faltan las identidades globales/departamentales.')
    sha_previo = str(mapa.get('sha_activo') or '')
    if not sha_previo or sha_previo == hash_actual:
        raise RuntimeError('El mapa de identidad BSC no tiene una huella anterior valida.')

    # Un mapa previamente revisado es la autoridad; nunca elegir MAX(CargaID).
    # El lote historico se busca unicamente por su huella exacta confirmada.
    lotes = cur.execute("""SELECT CargaID, IdArchivoDrive FROM dbo.ETL_CARGA
        WHERE TipoFuente='BSC' AND HashArchivoSHA256=? AND Estado='OK' """,
        sha_previo).fetchall()
    permitidos = {ID_BSC_ACTUAL, ID_BSC_HISTORICO}
    lotes = [(int(r[0]), str(r[1])) for r in lotes if str(r[1]) in permitidos]
    if len(lotes) != 1:
        raise RuntimeError('No hay un unico lote BSC anterior confirmado con la huella del mapa. '
                           'Revisar el historial y las identidades antes de cargar FACT.')
    anterior_id = lotes[0][0]

    def globales(cid):
        filas = cur.execute("""SELECT FilaExcel, NombreKPI, Categoria
            FROM dbo.STG_BSC_KPI WHERE CargaID=?""", cid).fetchall()
        dic = {str(int(r[0])): {'nombre': str(r[1] or ''), 'categoria': str(r[2] or '')}
               for r in filas}
        if len(dic) != len(filas):
            raise RuntimeError('BSC: hay filas KPI globales duplicadas.')
        return dic

    def departamentos(cid):
        filas = cur.execute("""SELECT NombreHoja, FilaExcel, NombreKPI, Departamento, Categoria
            FROM dbo.STG_KPI_DEPARTAMENTO WHERE CargaID=?""", cid).fetchall()
        dic = {str(r[0]) + '|' + str(int(r[1])): {
            'nombre': str(r[2] or ''), 'departamento': str(r[3] or ''),
            'categoria': str(r[4] or '')} for r in filas}
        if len(dic) != len(filas):
            raise RuntimeError('BSC: hay filas KPI departamentales duplicadas.')
        return dic

    prev_g, nuevo_g = globales(anterior_id), globales(carga_id)
    prev_d, nuevo_d = departamentos(anterior_id), departamentos(carga_id)
    if (len(prev_g) != 16 or set(prev_g) != set(nuevo_g)
            or set(prev_g) != set(mapa['global'])):
        raise RuntimeError('BSC: cambiaron las filas de KPI globales. '
                           'Se requiere revision de identidades; no actualizar automaticamente.')
    if set(prev_d) != set(nuevo_d) or set(prev_d) != set(mapa['departamentos']):
        raise RuntimeError('BSC: cambiaron hojas o filas de KPI departamentales. '
                           'Se requiere revision de identidades.')

    codigos_dim = {str(x[0]) for x in cur.execute(
        'SELECT CodigoKPI FROM dbo.DIM_KPI').fetchall()}
    usados = set()
    resultado_g = {}
    nombres_previos = {norm(row['nombre']): k for k, row in prev_g.items()}
    for fila, old in prev_g.items():
        new, saved = nuevo_g[fila], mapa['global'][fila]
        codigo = str(saved.get('codigo') or '')
        if (not codigo or codigo not in codigos_dim or codigo in usados
                or norm(saved.get('nombre')) != norm(old['nombre'])
                or norm(saved.get('categoria')) != norm(old['categoria'])):
            raise RuntimeError(f'BSC fila {fila}: identidad anterior no concilia con DIM_KPI/STAGING.')
        if norm(new['categoria']) != norm(old['categoria']) or not norm(new['nombre']):
            raise RuntimeError(f'BSC fila {fila}: cambio de categoria o nombre vacio.')
        otra = nombres_previos.get(norm(new['nombre']))
        if otra is not None and otra != fila:
            raise RuntimeError(f'BSC fila {fila}: nombre pertenecia a la fila {otra}.')
        usados.add(codigo)
        resultado_g[fila] = dict(saved, codigo=codigo, nombre=new['nombre'],
                                 anterior=old['nombre'], categoria=new['categoria'])

    if (norm(resultado_g[str(NUEVA_FILA)]['nombre']) != norm(NUEVO_NOMBRE)
            or norm(resultado_g[str(NUEVA_FILA)]['categoria']) != norm(NUEVA_CATEGORIA)):
        raise RuntimeError('BSC fila 19: el KPI Margen Operativo cambio sin autorizacion.')
    resultado_d = {}
    for clave, old in prev_d.items():
        new, saved = nuevo_d[clave], mapa['departamentos'][clave]
        codigo = saved.get('codigo')
        if (norm(saved.get('nombre')) != norm(old['nombre'])
                or norm(old['departamento']) != norm(new['departamento'])
                or norm(old['categoria']) != norm(new['categoria'])
                or not norm(new['nombre'])):
            raise RuntimeError(f'BSC departamental {clave}: cambio de identidad o categoria.')
        if codigo and (codigo not in usados and codigo != CODIGO_1000MM):
            raise RuntimeError(f'BSC departamental {clave}: codigo no corresponde a KPI global.')
        if codigo and codigo not in codigos_dim:
            raise RuntimeError(f'BSC departamental {clave}: KPI no existe en DIM_KPI.')
        if clave == HOJA_FILA_1000MM and codigo != CODIGO_1000MM:
            raise RuntimeError('BSC departamental 1000MM: codigo historico incorrecto.')
        resultado_d[clave] = dict(saved, codigo=codigo, nombre=new['nombre'])

    resultado = dict(mapa, **{"global": resultado_g, "departamentos": resultado_d},
                     sha_anterior=sha_previo, sha_activo=hash_actual)
    print('BSC IDENTIDADES: nueva version conciliada automaticamente con '
          f'la carga anterior {anterior_id}; {len(resultado_g)} KPI globales y '
          f'{len(resultado_d)} departamentales. Codigos historicos intactos.')
    return resultado


def registro_para_carga(cur, carga_id, root):
    """Obtiene identidades seguras para el lote BSC activo, sin escribir SQL/archivos.

    Nuevos proyectos del seguimiento NO alteran los CodigoKPI existentes.
    Cuando cambia el BSC, reconcilia con el ultimo mapa confirmado; si cambian
    identidades, se detiene. Funciona en --verificar y en --cargar.
    """
    v = _leer_json(Path(root) / 'logs_etl' / NOMBRE_REGISTRO)
    if not v:
        raise RuntimeError('No existe el mapa de identidades del BSC en logs_etl. '
                           'Restaurar el mapa confirmado o realizar conciliacion revisada; '
                           'no crear codigos KPI automaticamente.')
    fila = cur.execute("""SELECT HashArchivoSHA256, IdArchivoDrive
        FROM dbo.ETL_CARGA WHERE CargaID=? AND TipoFuente='BSC' AND Estado='OK' """,
        carga_id).fetchone()
    if not fila:
        raise RuntimeError('La version BSC del STAGING actual no esta confirmada.')
    sha_actual, id_drive = str(fila[0]), str(fila[1])
    if id_drive not in {ID_BSC_HISTORICO, ID_BSC_ACTUAL}:
        raise RuntimeError('El lote BSC activo tiene un identificador Drive no autorizado.')
    if sha_actual == v.get('sha_activo'):
        return v
    return _reconciliar_lote_bsc(cur, carga_id, root, v, sha_actual)


def codigo_para_fila(registro,fila,nombre):
    v=registro['global'].get(str(int(fila)))
    if not v or str(v['nombre']).strip()!=str(nombre).strip():
        raise RuntimeError(f'KPI BSC fila {fila}: nombre distinto de la identidad verificada.')
    return v['codigo']


def codigo_para_departamento(registro,hoja,fila,nombre):
    v=registro['departamentos'].get(str(hoja)+'|'+str(int(fila)))
    if not v or str(v['nombre']).strip()!=str(nombre).strip():
        raise RuntimeError(f'KPI departamental {hoja} fila {fila}: identidad no coincide.')
    return v.get('codigo')
