# -*- coding: utf-8 -*-
"""MAAS_ECOLOGIA_4 | Paso 03: prueba de conexion SQL Server (SOLO LECTURA).

Coloca este archivo junto a 01_extraer_desde_drive.py y
02_transformar_y_validar.py. Ejecuta:
    py -m pip install pyodbc
    py .\03_probar_conexion_sql.py

El script NO crea ni modifica tablas, ni lee credenciales de Google Drive.
Utiliza autenticacion integrada de Windows (la misma de SSMS si esa es tu conexion).
"""

from __future__ import annotations

import sys

try:
    import pyodbc
except ImportError:
    print("Falta pyodbc. Ejecuta: py -m pip install pyodbc")
    sys.exit(1)

BASE = "MAAS_ECOLOGIA_4"
TABLAS_REQUERIDAS = [
    "ETL_CARGA", "STG_BSC_KPI", "STG_KPI_DEPARTAMENTO", "STG_BD_KPI",
    "STG_PROYECTO", "STG_VENTA_DETALLE", "STG_VENTA_RESUMEN",
    "STG_SEGUIMIENTO_PROYECTO", "STG_DETALLE_COSTOS",
    "DIM_FECHA", "DIM_KPI", "DIM_AREA", "DIM_RESPONSABLE",
    "DIM_CLIENTE", "DIM_PROYECTO", "DIM_COSTOS",
    "FACT_KPI_ESTRATEGICO", "FACT_SEGUIMIENTO_OPERACIONAL",
]


def main() -> int:
    disponibles = pyodbc.drivers()
    driver = next((x for x in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server")
                   if x in disponibles), None)
    if not driver:
        print("ERROR: no se detecto ODBC Driver 17/18 for SQL Server.")
        print("Controladores instalados:", disponibles)
        print("Instala el controlador ODBC oficial de Microsoft y vuelve a intentar.")
        return 1

    print("MAAS 4 | PRUEBA DE SQL SERVER (SOLO LECTURA)")
    print("En SSMS, mira el campo 'Nombre del servidor' de la ventana Conectar.")
    server = input("Escribe el nombre del servidor (por ejemplo, .\\SQLEXPRESS): ").strip()
    if not server:
        print("ERROR: falta el nombre del servidor. No se intento ninguna conexion.")
        return 1

    # Solo para entorno SQL Server local de tesis. El certificado no se valida;
    # usar certificado valido en un servidor corporativo o remoto.
    conn_string = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={BASE};"
        "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
        "Connection Timeout=10;Application Name=MAAS_ETL_prueba_lectura;"
    )
    try:
        with pyodbc.connect(conn_string, timeout=10, autocommit=False) as conn:
            cur = conn.cursor()
            bd, servidor = cur.execute("SELECT DB_NAME(), @@SERVERNAME").fetchone()
            print("CONEXION OK | Base:", bd, "| Servidor:", servidor)
            rows = cur.execute(
                "SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('dbo')"
            ).fetchall()
            existentes = {r[0] for r in rows}
            faltan = [nombre for nombre in TABLAS_REQUERIDAS if nombre not in existentes]
            print(f"Tablas esperadas: {len(TABLAS_REQUERIDAS)} | Encontradas: {len(TABLAS_REQUERIDAS)-len(faltan)}")
            if faltan:
                print("FALTAN estas tablas en la base MAAS_ECOLOGIA_4:")
                for nombre in faltan:
                    print(" -", nombre)
                print("Revisar el script SQL del modelo antes de cargar datos.")
                conn.rollback()
                return 2
            print("MODELO OK: todas las tablas esperadas existen.")
            print("PRUEBA FINALIZADA: no se insertaron ni modificaron registros.")
            conn.rollback()
            return 0
    except pyodbc.Error as exc:
        print("ERROR DE CONEXION: no se pudo consultar MAAS_ECOLOGIA_4.")
        print(str(exc))
        print("Comprueba servidor, instancia, autenticacion de Windows y nombre de base.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
