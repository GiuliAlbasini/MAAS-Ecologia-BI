# -*- coding: ascii -*-
"""MAAS ECOLOGIA 4 - Diagnostico de renombres BSC (NO MODIFICA SQL).

Uso desde la carpeta ETL:
    python -u .\10_diagnosticar_renombres_bsc.py

Requisitos:
- Debe existir un ultimo_snapshot_confirmado.json generado por el maestro 08.
- Ejecutar 08 --probar primero (aunque se detenga por cambios de identidad).

Genera logs_etl/diagnostico_renombres_bsc.csv con CANDIDATOS, no cambios automaticos.
"""
from __future__ import annotations

import csv
from difflib import SequenceMatcher
import importlib.util
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parent
LAST = ROOT / 'logs_etl' / 'ultimo_snapshot_confirmado.json'
OUT = ROOT / 'logs_etl' / 'diagnostico_renombres_bsc.csv'
TABLAS = [
    'bsc/STG_BSC_KPI',
    'bsc/STG_KPI_DEPARTAMENTO',
    'bsc/STG_PROYECTO',
]


def normalizar(s: str) -> str:
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', errors='ignore').decode('ascii')
    return ' '.join(re.findall(r'[a-z0-9]+', s.lower()))


def nombre(clave: str) -> str:
    try:
        v = json.loads(clave)
        return str(v[-1]) if isinstance(v, list) and v else str(clave)
    except (TypeError, json.JSONDecodeError):
        return str(clave)


def particion(claves_previas, claves_actuales):
    p, n = set(claves_previas), set(claves_actuales)
    return sorted(p-n), sorted(n-p)


def sugerir(faltantes: list[str], nuevos: list[str], tabla: str):
    disponibles = list(nuevos)
    pares = []
    # Departamentales: misma hoja y fila sirve como referencia, NO como autorizacion.
    if tabla == 'bsc/STG_KPI_DEPARTAMENTO':
        por_posicion = {}
        for v in disponibles:
            try:
                a = json.loads(v)
            except json.JSONDecodeError:
                continue
            if len(a) == 3:
                por_posicion.setdefault((str(a[0]), str(a[1])), []).append(v)
        for old in faltantes:
            try:
                a = json.loads(old)
            except json.JSONDecodeError:
                a = []
            if len(a) == 3:
                pos = (str(a[0]), str(a[1]))
                matches = [v for v in por_posicion.get(pos, []) if v in disponibles]
                if len(matches) == 1:
                    new = matches[0]
                    disponibles.remove(new)
                    pares.append((old, new, 'MISMA_HOJA_Y_FILA', 1.0))
    usados_old = {v[0] for v in pares}
    for old in faltantes:
        if old in usados_old:
            continue
        if disponibles:
            scores = [(SequenceMatcher(None, normalizar(nombre(old)), normalizar(nombre(v))).ratio(), v)
                      for v in disponibles]
            similitud, new = max(scores, key=lambda x: x[0])
            # Puntaje BAJO significa que NO existe correspondencia confiable.
            pares.append((old, new, 'SUGERENCIA_POR_SIMILITUD', similitud))
            disponibles.remove(new)
        else:
            pares.append((old, '', 'SIN_CANDIDATO', 0.0))
    for new in disponibles:
        pares.append(('', new, 'SOLO_NUEVO', 0.0))
    return pares


def main():
    if not LAST.is_file():
        raise FileNotFoundError('Falta ' + str(LAST) + '. No borres ni recrees este archivo.')
    previa = json.loads(LAST.read_text(encoding='utf-8-sig'))
    ruta = ROOT / '08_ejecutar_etl_maas.py'
    if not ruta.is_file():
        raise FileNotFoundError('No existe 08_ejecutar_etl_maas.py en ' + str(ROOT))
    spec = importlib.util.spec_from_file_location('maas_maestro_solo_lectura', ruta)
    if spec is None or spec.loader is None:
        raise RuntimeError('No fue posible abrir el maestro 08')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    # NO ejecuta el ETL ni consulta ni actualiza SQL: usa CSV ya validados.
    actual = mod.snapshot_transformado()
    print('DIAGNOSTICO BSC - SOLO LECTURA - NO MODIFICA SQL')
    print('Ultimo lote confirmado:', previa.get('confirmado_local', 'sin fecha registrada'))
    print('Fuentes actuales:', actual.get('numero_fuentes'))
    if previa.get('sha256_conjunto') == actual.get('sha256_conjunto'):
        print('AVISO: el conjunto actual es IDENTICO al ultimo confirmado.')
    rows = []
    for tabla in TABLAS:
        old, new = particion(previa.get('claves', {}).get(tabla, []),
                             actual.get('claves', {}).get(tabla, []))
        print('\n' + tabla + ': anteriores ausentes=' + str(len(old)) +
              ', claves nuevas=' + str(len(new)))
        pares = sugerir(old, new, tabla)
        if not pares:
            print('  Sin cambios de identidad.')
        for i, (anterior, nuevo, regla, similitud) in enumerate(pares, 1):
            print(f' {i:02d}. ANTES: {nombre(anterior) if anterior else "(sin anterior)"}')
            print(f'     AHORA: {nombre(nuevo) if nuevo else "(sin candidato)"}')
            print(f'     TIPO:  {regla} | similitud {similitud:.0%} | POR VALIDAR')
            rows.append({'Tabla':tabla,
                         'ClaveAnterior':anterior,'ClaveNuevaSugerida':nuevo,
                         'NombreAnterior':nombre(anterior) if anterior else '',
                         'NombreNuevoSugerido':nombre(nuevo) if nuevo else '',
                         'Criterio':regla, 'Similitud':f'{similitud:.3f}',
                         'ConfirmacionManual':''})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'Tabla','ClaveAnterior','ClaveNuevaSugerida','NombreAnterior',
            'NombreNuevoSugerido','Criterio','Similitud','ConfirmacionManual'])
        writer.writeheader()
        writer.writerows(rows)
    print('\nREPORTE GENERADO:', OUT)
    print('IMPORTANTE: NO autorices renombres solo por similitud. Verifica cada pareja.')
    print('No se ha modificado SQL, el BSC, Gmail, el ETL ni Streamlit.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('ERROR DIAGNOSTICO:', type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        sys.exit(1)
