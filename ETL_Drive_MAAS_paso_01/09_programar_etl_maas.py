# -*- coding: utf-8 -*-
"""Vigilancia local cada 1 minuto, sin instalar librerias adicionales.

Desde la carpeta ETL actual:
  py .\09_programar_etl_maas.py --ahora

El programa sigue ejecutandose mientras esta ventana permanezca abierta,
Windows no este suspendido y SQL Server este disponible. Detener: Ctrl+C.
Ejecuta el maestro 08_ejecutar_etl_maas.py (nombre real en esta carpeta).
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
MAESTRO = ROOT / '08_ejecutar_etl_maas.py'


def ejecutar_una_vez():
    print('\n[' + datetime.now().strftime('%d/%m/%Y %H:%M:%S') + '] Verificando Drive y Gmail...', flush=True)
    try:
        code = subprocess.run([sys.executable, '-u', str(MAESTRO), '--ejecutar'], cwd=ROOT).returncode
    except OSError as exc:
        print('ERROR al iniciar el ETL:', exc, flush=True)
        return
    print('Resultado:', 'OK' if code == 0 else f'ERROR codigo {code}', flush=True)
    if code:
        print('Revisa logs_etl/ultimo_resultado.json. La siguiente ejecucion intentara de nuevo.', flush=True)


def main():
    p = argparse.ArgumentParser(description='ETL MAAS periodico; terminal abierta')
    p.add_argument('--cada-minutos', type=int, default=1)
    p.add_argument('--ahora', action='store_true')
    a = p.parse_args()
    if not 1 <= a.cada_minutos <= 1440:
        p.error('--cada-minutos debe estar entre 1 y 1440')
    if not MAESTRO.is_file():
        p.error('Falta 08_ejecutar_etl_maas.py en la misma carpeta')
    print('MAAS 4 | ETL CADA ' + str(a.cada_minutos) + ' MINUTOS')
    print('Ventana abierta y equipo activo requeridos. Detener: Ctrl+C.')
    try:
        if a.ahora:
            ejecutar_una_vez()
        while True:
            print('Proximo control dentro de ' + str(a.cada_minutos) + ' minutos.', flush=True)
            time.sleep(a.cada_minutos * 60)
            ejecutar_una_vez()
    except KeyboardInterrupt:
        print('\nMonitor detenido por la usuaria.')


if __name__ == '__main__':
    main()
