# -*- coding: utf-8 -*-
"""MAAS ECOLOGIA 4 | Maestro seguro: 20+ Drive + 2 Gmail -> SQL Server.

Instalar junto a los scripts 01, 02, 04, 05 y 06 ACTUALES.

  py .\08_ejecutar_etl_maas.py --probar     # sincroniza copias locales; SQL solo lectura
  py .\08_ejecutar_etl_maas.py --ejecutar  # actualiza ETL / SQL

Avisos de compatibilidad:
* Requiere Drive/Gmail OAuth previamente autorizados con la MISMA cuenta de Windows.
* Solo procesa mensajes de Gmail etiquetados MAAS-ETL.
* Detecta eliminacion/cambio de clave de registros entre cargas confirmadas y
  detiene automaticamente; los pasos 05/06 actuales no hacen bajas historicas.
* --probar DESCARGA Y TRANSFORMA copias locales actuales, pero NO escribe SQL.
  Si hay una fuente nueva en STAGING, reserva los chequeos 05/06 para --ejecutar.
* Las descripciones de dimensiones existentes NO se reescriben en el paso 05.
* 11 KPI operacionales V12 siguen historicos, NO se recalculan.
* No realiza un 'refresh' directo en el navegador; Streamlit lee SQL al actualizar.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from bsc_identidades_estables import preparar_desde_maestro

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / 'logs_etl'
LAST = LOG_DIR / 'ultimo_snapshot_confirmado.json'
STATUS = LOG_DIR / 'ultimo_resultado.json'
SCRIPT = {
    'drive': '01_extraer_desde_drive.py',
    'gmail': '01_extraer_desde_gmail.py',
    'transformar': '02_transformar_y_validar.py',
    'staging': '04_cargar_staging.py',
    'dimensiones': '05_cargar_dimensiones.py',
    'hechos': '06_verificar_y_cargar_hechos.py',
    'metas_ventas': '10_sincronizar_meta_ventas.py',
}

# Claves de negocio presentes en cada tabla convertida por el paso 04.
# Si desaparece una clave previamente publicada NO se permite una
# sincronizacion automatica con hechos historicos potencialmente obsoletos.
# Atributos descriptivos que el PASO 05 actual solo inserta una vez.
# Si cambian, exigir revisar la dimension antes de usar un valor obsoleto.
ATRIBUTOS_DIMENSIONES = {
    'STG_BSC_KPI': ('Categoria',),
    'STG_PROYECTO': ('TipoProyecto',),
    'STG_VENTA_DETALLE': ('RutCliente', 'RazonSocial', 'CiudadCliente', 'ComunaCliente'),
    'STG_PROYECTO_GANTT': ('NombreTarea', 'TareaPredecesora'),
    'STG_TAREA': ('NombreTarea', 'RecursoPrincipal', 'OrigenDatos'),
}

CLAVES = {
    'STG_BSC_KPI': ('FilaExcel',),
    'STG_KPI_DEPARTAMENTO': ('NombreHoja', 'FilaExcel'),
    'STG_PROYECTO': ('NombreProyecto',),
    'STG_VENTA_DETALLE': ('TipoDocumento', 'Folio'),
    'STG_CAJA_MENSUAL': ('Mes',),
    'STG_PROYECTO_RESUMEN': ('CodigoProyecto',),
    'STG_PROYECTO_GANTT': ('CodigoProyecto', 'CodigoTarea'),
    'STG_TAREA': ('CodigoProyecto', 'CodigoTarea'),
    'STG_RECURSO': ('CodigoProyecto', 'FilaExcel'),
    'STG_ADJUDICACION': ('CodigoProyecto', 'NumeroPropuesta'),
    'STG_GMAIL_CIERRE_MENSUAL': ('GmailMessageID', 'Periodo'),
    'STG_GMAIL_CONTRATO': ('GmailMessageID', 'SHA256PDF'),
}


def fecha_actual() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


class Bitacora:
    def __init__(self, modo):
        LOG_DIR.mkdir(exist_ok=True)
        self.modo = modo
        self.inicio = fecha_actual()
        self.ruta = LOG_DIR / ('etl_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.log')
        self.f = self.ruta.open('w', encoding='utf-8', buffering=1)

    def escribir(self, linea):
        print(linea, flush=True)
        self.f.write(linea + '\n')

    def cerrar(self, correcto, error=None):
        self.f.close()
        resultado = {
            'inicio': self.inicio,
            'fin': fecha_actual(),
            'modo': self.modo,
            'estado': 'OK' if correcto else 'ERROR',
            'error': error,
            'log': str(self.ruta),
        }
        temporal = STATUS.with_suffix('.tmp')
        temporal.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
        temporal.replace(STATUS)


@contextlib.contextmanager
def bloqueo():
    ruta = ROOT / '.maas_etl_en_ejecucion.lock'
    with ruta.open('a+b') as f:
        f.seek(0)
        f.write(b'1')
        f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise RuntimeError('Ya hay otro ETL en ejecucion: no se permite superponer cargas') from e
        try:
            yield
        finally:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def ejecutar_paso(log, nombre, opcion):
    archivo = ROOT / SCRIPT[nombre]
    comando = [sys.executable, '-u', str(archivo), opcion]
    log.escribir('\n=== ' + archivo.name + ' ' + opcion + ' ===')
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    with subprocess.Popen(
        comando, cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding='utf-8', errors='replace', text=True, bufsize=1,
    ) as p:
        assert p.stdout is not None
        for linea in p.stdout:
            linea = linea.rstrip('\r\n')
            log.escribir(linea)
            if nombre == 'gmail' and opcion == '--ejecutar' and 'SIN MENSAJES:' in linea:
                # El extractor original conserva el CSV anterior cuando no hay
                # mensajes; no permitir publicarlo como si fuera nuevo.
                p.wait()
                raise RuntimeError('Gmail MAAS-ETL sin mensajes; se conserva CSV anterior, no se actualiza SQL')
        rc = p.wait()
    if rc:
        raise RuntimeError(f'Fallo {archivo.name} {opcion} (codigo {rc}); se detuvo el maestro')
    log.escribir('PASO OK: ' + archivo.name)


def verificar_archivos():
    faltan = [name for name in SCRIPT.values() if not (ROOT / name).is_file()]
    if faltan:
        raise FileNotFoundError('Faltan scripts en esta carpeta ETL: ' + ', '.join(faltan))
    # Distinguir el paso 06 nuevo de 22 fuentes del ejecutor historico V12.
    s6 = (ROOT / SCRIPT['hechos']).read_text(encoding='utf-8-sig')
    s5 = (ROOT / SCRIPT['dimensiones']).read_text(encoding='utf-8-sig')
    s4 = (ROOT / SCRIPT['staging']).read_text(encoding='utf-8-sig')
    s2 = (ROOT / SCRIPT['transformar']).read_text(encoding='utf-8-sig')
    if not all(x in s6 for x in ('NEW_TYPES', 'GMAIL_FACTURADO_MES', 'CONTRATO', '--cargar')):
        raise RuntimeError('El PASO 06 no es el actualizado de Drive + Gmail. No ejecutar maestro V12.')
    if 'DIM_TAREA' not in s5 or 'gmail_contratos' not in s5:
        raise RuntimeError('El PASO 05 debe ser la version actualizada con Gmail y DIM_TAREA.')
    if 'GMAIL_SOURCES' not in s4 or 'STG_TAREA' not in s4:
        raise RuntimeError('El PASO 04 debe ser la version actualizada con 22 fuentes.')
    if 'gmail' not in s2.lower():
        raise RuntimeError('El PASO 02 no incorpora Gmail.')


def cargar_modulo_paso04():
    path = ROOT / SCRIPT['staging']
    spec = importlib.util.spec_from_file_location('maas_stage04_maestro', path)
    if not spec or not spec.loader:
        raise RuntimeError('No se puede leer el paso 04')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def snapshot_transformado():
    """Lee solamente CSV validados por paso 02. No escribe SQL."""
    mod = cargar_modulo_paso04()
    fuentes, datos = mod.build_dataset()
    versiones = {fuente: mod.fingerprint(tablas) for fuente, tablas in sorted(datos.items())}
    claves_por_tabla = {}
    atributos_por_tabla = {}
    for codigo, tablas in sorted(datos.items()):
        for tabla, registros in sorted(tablas.items()):
            if tabla not in CLAVES:
                continue
            indices = tuple(mod.SCHEMA[tabla].index(col) for col in CLAVES[tabla])
            claves = [json.dumps([str(registro[i]) for i in indices], ensure_ascii=False)
                      for registro in registros]
            if len(claves) != len(set(claves)):
                raise RuntimeError(f'Clave de negocio duplicada: {codigo}/{tabla}')
            claves_por_tabla[codigo + '/' + tabla] = sorted(claves)
            if tabla in ATRIBUTOS_DIMENSIONES:
                atr_indices = tuple(mod.SCHEMA[tabla].index(c) for c in ATRIBUTOS_DIMENSIONES[tabla])
                atributos_por_tabla[codigo + '/' + tabla] = {
                    clave: [str(registro[i]) for i in atr_indices]
                    for clave, registro in zip(claves, registros)
                }
    resumen = json.dumps(versiones, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return {
        'versiones': versiones,
        'sha256_conjunto': hashlib.sha256(resumen.encode('utf-8')).hexdigest(),
        'claves': claves_por_tabla,
        'atributos_dimension': atributos_por_tabla,
        'numero_fuentes': len(fuentes),
    }


def comprobar_no_bajas(anterior, actual):
    """Previene eliminaciones/cambios de clave sin conciliacion FACT."""
    if anterior is None:
        return
    removed_sources = set(anterior.get('versiones', {})) - set(actual['versiones'])
    if removed_sources:
        raise RuntimeError('Se quitaron fuentes: ' + ', '.join(sorted(removed_sources)) +
                           '. NO sincronizar sin revisar hechos historicos.')
    for tabla, claves_anteriores in anterior.get('claves', {}).items():
        claves_actuales = set(actual['claves'].get(tabla, []))
        faltantes = set(claves_anteriores) - claves_actuales
        if tabla in ('bsc/STG_BSC_KPI', 'bsc/STG_KPI_DEPARTAMENTO'):
            # La comprobacion de fila/hoja, categoria e identidad SQL ocurre
            # en preparar_desde_maestro; compatibilidad con snapshot anterior
            # basado en nombre se conserva para esta primera migracion.
            continue
        if faltantes:
            ejemplo = sorted(faltantes)[:3]
            raise RuntimeError(
                f'Cambios de identidad/eliminaciones en {tabla}: {len(faltantes)} claves faltantes; '
                f'ejemplos={ejemplo}. Se detuvo ANTES de escribir SQL. '
                'Para eliminar/renombrar registros se requiere reconciliacion autorizada.'
            )
    for tabla, atributos_previos in anterior.get('atributos_dimension', {}).items():
        atributos_nuevos = actual['atributos_dimension'].get(tabla, {})
        cambios = [clave for clave, anterior_valor in atributos_previos.items()
                   if clave in atributos_nuevos and atributos_nuevos[clave] != anterior_valor]
        if cambios:
            raise RuntimeError(
                f'Cambios descriptivos en {tabla}: {len(cambios)} registros; '
                'paso 05 no hace UPDATE de dimensiones existentes. '
                'Detenido antes de SQL para no mostrar nombres/categorias obsoletos.'
            )


def anterior_confirmado():
    if not LAST.is_file():
        return None
    return json.loads(LAST.read_text(encoding='utf-8'))


def guardar_confirmado(actual):
    dato = dict(actual)
    dato['confirmado_local'] = fecha_actual()
    tmp = LAST.with_suffix('.tmp')
    tmp.write_text(json.dumps(dato, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(LAST)


def ciclo(modo: str, forzar=False):
    verificar_archivos()
    with bloqueo():
        log = Bitacora(modo)
        correcto = False
        error = None
        try:
            log.escribir('MAAS ECOLOGIA 4 | MAESTRO 22 FUENTES | ' + modo.upper())
            log.escribir('Python: ' + sys.executable)
            log.escribir('Carpeta ETL: ' + str(ROOT))
            if modo == 'probar':
                # La validacion de STAGING compara hashes del manifiesto publicado
                # por 01 con el reporte publicado por 02. Un --probar aislado de
                # Drive/Gmail no actualiza esas copias y produce un falso desfase.
                # Se sincronizan SOLO archivos locales para validar el lote vigente.
                log.escribir('PRUEBA: se actualizaran copias/manifiestos/CSV LOCALES; SQL queda en solo lectura.')
                ejecutar_paso(log, 'drive', '--ejecutar')
                ejecutar_paso(log, 'gmail', '--ejecutar')
                ejecutar_paso(log, 'transformar', '--ejecutar')
                ejecutar_paso(log, 'staging', '--verificar')
                ejecutar_paso(log, 'staging', '--comprobar-sql')
                ejecutar_paso(log, 'metas_ventas', '--probar')
                actual = snapshot_transformado()
                if actual['numero_fuentes'] < 22:
                    raise RuntimeError('Menos de 22 fuentes transformadas. Se cancela la prueba.')
                previo = anterior_confirmado()
                comprobar_no_bajas(previo, actual)
                preparar_desde_maestro(ROOT,previo,actual,cargar_modulo_paso04())
                log.escribir(f'LOTE VALIDADO: {actual["numero_fuentes"]} fuentes | SHA: {actual["sha256_conjunto"][:14]}')
                if previo and previo.get('sha256_conjunto') == actual['sha256_conjunto']:
                    # Solo si es el lote previamente confirmado contra SQL.
                    ejecutar_paso(log, 'dimensiones', '--verificar')
                    ejecutar_paso(log, 'hechos', '--verificar')
                    log.escribir('DIM/FACT: verificadas contra el lote previamente cargado.')
                else:
                    log.escribir('DIM/FACT: aun NO verificables contra el lote nuevo hasta cargar STAGING.')
                    log.escribir('No se han cambiado tablas SQL. Para actualizar, ejecutar --ejecutar.')
                log.escribir('\nPRUEBA PREVIA OK: 22 fuentes, validacion y estructura SQL comprobadas; sin escrituras SQL.')
            else:
                ejecutar_paso(log, 'drive', '--ejecutar')
                ejecutar_paso(log, 'gmail', '--ejecutar')
                ejecutar_paso(log, 'transformar', '--ejecutar')
                ejecutar_paso(log, 'staging', '--verificar')
                ejecutar_paso(log, 'staging', '--comprobar-sql')
                ejecutar_paso(log, 'metas_ventas', '--probar')
                actual = snapshot_transformado()
                if actual['numero_fuentes'] < 22:
                    raise RuntimeError('Menos de 22 fuentes encontradas. Se cancela carga.')
                previo = anterior_confirmado()
                comprobar_no_bajas(previo, actual)
                preparar_desde_maestro(ROOT,previo,actual,cargar_modulo_paso04())
                log.escribir(f'FUENTES: {actual["numero_fuentes"]} | SHA: {actual["sha256_conjunto"][:14]}')
                if not forzar and previo and previo.get('sha256_conjunto') == actual['sha256_conjunto']:
                    # Evita UPDATE de 333 KPI cada 15 minutos cuando nada cambio.
                    ejecutar_paso(log, 'dimensiones', '--verificar')
                    ejecutar_paso(log, 'hechos', '--verificar')
                    log.escribir('SIN CAMBIOS en las fuentes: no se reescribieron las FACT.')
                else:
                    ejecutar_paso(log, 'staging', '--cargar')
                    ejecutar_paso(log, 'dimensiones', '--verificar')
                    ejecutar_paso(log, 'dimensiones', '--cargar')
                    ejecutar_paso(log, 'hechos', '--verificar')
                    ejecutar_paso(log, 'hechos', '--cargar')
                    guardar_confirmado(actual)
                    log.escribir('\nCARGA COMPLETADA: fuentes validadas, STAGING + DIM + FACT confirmadas.')
                ejecutar_paso(log, 'metas_ventas', '--cargar')
                log.escribir('Streamlit leera SQL al recargar la pagina o vencer su cache.')
                log.escribir('Recordatorio: los 11 KPI PRY_V12 NO se recalculan con este maestro.')
            correcto = True
            return 0
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            log.escribir('\nERROR: ' + error)
            log.escribir('No ejecutes manualmente pasos posteriores sin revisar el error.')
            return 1
        finally:
            log.cerrar(correcto, error)
            print('Bitacora: ' + str(log.ruta), flush=True)


def main():
    p = argparse.ArgumentParser(description='Maestro ETL 22 fuentes MAAS_ECOLOGIA_4; no programa tareas.')
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--probar', action='store_true', help='Actualiza copias locales y valida; no escribe SQL')
    modes.add_argument('--ejecutar', action='store_true', help='Extraer, transformar, STAGING, dimensiones y hechos')
    p.add_argument('--forzar', action='store_true', help='Recargar incluso si las huellas no cambiaron')
    a = p.parse_args()
    if a.forzar and not a.ejecutar:
        p.error('--forzar requiere --ejecutar')
    return ciclo('probar' if a.probar else 'ejecutar', forzar=a.forzar)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('ERROR INICIAL:', str(e), file=sys.stderr)
        sys.exit(1)
