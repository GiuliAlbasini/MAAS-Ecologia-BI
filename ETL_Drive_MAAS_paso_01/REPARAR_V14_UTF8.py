# -*- coding: ascii -*-
"""Corrige SOLO la codificacion de los scripts V14 de MAAS.

No ejecuta ETL ni conecta con SQL Server.
Si un archivo ya es UTF-8, lo conserva intacto.
Para archivos ANSI/Windows-1252, guarda un respaldo y convierte a UTF-8.
"""
from pathlib import Path
import sys

CARPETA = Path(__file__).resolve().parent
ARCHIVOS = ('05_cargar_dimensiones.py', '06_verificar_y_cargar_hechos.py')


def preparar(ruta):
    original = ruta.read_bytes()
    try:
        texto = original.decode('utf-8-sig')
        codificacion = 'UTF-8'
    except UnicodeDecodeError:
        texto = original.decode('cp1252')
        codificacion = 'Windows-1252'
    # Check the Python code BEFORE writing over the original.
    compile(texto, str(ruta), 'exec')
    return original, texto.encode('utf-8'), codificacion


def main():
    print('MAAS V14 | REPARACION DE CODIFICACION | NO MODIFICA SQL')
    preparados = []
    for nombre in ARCHIVOS:
        ruta = CARPETA / nombre
        if not ruta.is_file():
            print('ERROR: No se encontro:', ruta)
            return 1
        try:
            original, convertido, origen = preparar(ruta)
        except (ValueError, UnicodeError, SyntaxError) as exc:
            print('ERROR de lectura o sintaxis en', nombre, ':', exc)
            return 1
        preparados.append((ruta, original, convertido, origen))

    for ruta, original, convertido, origen in preparados:
        if original == convertido:
            print('OK |', ruta.name, '| ya estaba en UTF-8 y es sintacticamente valido')
            continue
        respaldo = ruta.with_name(ruta.name + '.respaldo_antes_utf8.bak')
        if respaldo.exists():
            print('ERROR: Ya existe el respaldo; no se sobreescribira:', respaldo)
            return 1
        respaldo.write_bytes(original)
        ruta.write_bytes(convertido)
        print('CORREGIDO |', ruta.name, '| origen:', origen,
              '| respaldo:', respaldo.name)
    print('LISTO: ambos scripts tienen sintaxis valida y son legibles en UTF-8.')
    print('Siguiente paso: py .\\05_cargar_dimensiones.py --verificar')
    return 0


if __name__ == '__main__':
    sys.exit(main())
