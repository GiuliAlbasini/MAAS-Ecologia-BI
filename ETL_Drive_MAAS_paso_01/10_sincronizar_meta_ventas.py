# -*- coding: utf-8 -*-
"""Meta anual de ventas desde la hoja METAS_VENTAS del BSC Drive.

--probar: verifica Excel y presencia de tabla SQL, no modifica SQL.
--cargar: actualiza solo dbo.CFG_META_VENTAS_ANUAL; jamás hechos/dimensiones.

El BSC físico se lee desde la copia XLSM descargada por PASO 01,
no se abre por Excel ni se escribe el archivo original.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import posixpath
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "datos_fuente" / "ultima_extraccion.json"
DB = "MAAS_ECOLOGIA_4"
SERVER = r"Giuli\GIULIANA"
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOCREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).strip().casefold().replace(" ", "_")


def leer_bsc_local() -> Path:
    if not MANIFEST.is_file():
        raise RuntimeError("Falta ultima_extraccion.json. Ejecutar PASO 01 o el maestro primero.")
    data = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    matches = [f for f in data.get("archivos", []) if f.get("fuente") == "bsc"]
    if len(matches) != 1:
        raise RuntimeError("BSC no aparece exactamente una vez en el manifiesto Drive")
    relativo = matches[0].get("ruta_local")
    if not relativo:
        raise RuntimeError("El BSC del manifiesto no tiene ruta local")
    path = (ROOT / relativo).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise RuntimeError("Ruta de BSC no válida o archivo no encontrado")
    return path


def extraer_valores_bsc(path: Path) -> dict[int, Decimal]:
    with ZipFile(path, "r") as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheet = next((x for x in wb.findall(f".//{{{MAIN}}}sheet")
                      if x.attrib.get("name") == "METAS_VENTAS"), None)
        if sheet is None:
            raise RuntimeError("Falta la hoja METAS_VENTAS en el Excel BSC. No insertar filas en BSC KPIs.")
        rid = sheet.attrib.get(f"{{{DOCREL}}}id")
        relroot = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel = next((x for x in relroot.findall(f"{{{PACKAGE_REL}}}Relationship")
                    if x.attrib.get("Id") == rid), None)
        if rel is None:
            raise RuntimeError("No se puede encontrar la hoja METAS_VENTAS dentro del Excel")
        target = rel.attrib.get("Target", "")
        if target.startswith("/"):
            member = target.lstrip("/")
        elif target.startswith("xl/"):
            member = posixpath.normpath(target)
        else:
            member = posixpath.normpath(posixpath.join("xl", target))
        root = ET.fromstring(z.read(member))
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for item in strings.findall(f"{{{MAIN}}}si"):
                shared.append("".join((t.text or "") for t in item.findall(f".//{{{MAIN}}}t")))
        rows: dict[int, dict[str, tuple[str, bool]]] = {}
        for cell in root.findall(f".//{{{MAIN}}}sheetData/{{{MAIN}}}row/{{{MAIN}}}c"):
            ref = cell.attrib.get("r", "")
            m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
            if not m or m.group(1) not in ("A", "B", "C"):
                continue
            col, row = m.group(1), int(m.group(2))
            v = cell.find(f"{{{MAIN}}}v")
            formula = cell.find(f"{{{MAIN}}}f") is not None
            inline = cell.find(f"{{{MAIN}}}is")
            value = v.text if v is not None and v.text is not None else ""
            if cell.attrib.get("t") == "s" and value:
                value = shared[int(value)]
            if inline is not None:
                value = "".join((t.text or "") for t in inline.findall(f".//{{{MAIN}}}t"))
            rows.setdefault(row, {})[col] = (value.strip(), formula)
    header = rows.get(1, {})
    target_headers = {"A": "anio", "B": "kpi", "C": "meta_anual_clp"}
    for col, expected in target_headers.items():
        actual = normalizar(header.get(col, ("", False))[0])
        if actual != expected:
            raise RuntimeError(f"METAS_VENTAS!{col}1 debe decir {expected}; aparece {actual or '[vacío]'}")
    goals: dict[int, Decimal] = {}
    for row, cells in sorted(rows.items()):
        if row == 1:
            continue
        values = [cells.get(c, ("", False))[0] for c in ("A", "B", "C")]
        if not any(values):
            continue
        if not all(values):
            raise RuntimeError(f"METAS_VENTAS fila {row}: se requieren Año, KPI y Meta anual CLP")
        if cells.get("C", ("", False))[1]:
            raise RuntimeError(f"METAS_VENTAS!C{row}: ingresar monto numérico, no fórmula")
        try:
            ano_decimal = Decimal(values[0])
            ano = int(ano_decimal)
            monto = Decimal(values[2])
        except (InvalidOperation, ValueError) as e:
            raise RuntimeError(f"METAS_VENTAS fila {row}: año y monto deben ser números (sin $ ni puntos de miles)") from e
        if ano_decimal != ano_decimal.to_integral_value() or not 2020 <= ano <= 2100:
            raise RuntimeError(f"METAS_VENTAS fila {row}: año inválido")
        if normalizar(values[1]) != f"ventas_{ano}":
            raise RuntimeError(f"METAS_VENTAS fila {row}: KPI debe decir Ventas {ano}")
        if monto <= 0 or monto != monto.to_integral_value() or monto > Decimal("999999999999999"):
            raise RuntimeError(f"METAS_VENTAS fila {row}: meta CLP inválida")
        if ano in goals:
            raise RuntimeError(f"METAS_VENTAS: año {ano} duplicado")
        goals[ano] = monto
    if 2026 not in goals:
        raise RuntimeError("METAS_VENTAS: falta la meta de ventas 2026")
    return goals


def conectar(servidor):
    import pyodbc
    d = next((v for v in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server")
              if v in pyodbc.drivers()), None)
    if not d:
        raise RuntimeError("Falta driver ODBC 17/18 de SQL Server")
    return pyodbc.connect(
        f"DRIVER={{{d}}};SERVER={servidor};DATABASE={DB};Trusted_Connection=yes;"
        "TrustServerCertificate=yes;Encrypt=yes;", autocommit=False, timeout=10)


def main():
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probar", action="store_true")
    mode.add_argument("--cargar", action="store_true")
    p.add_argument("--servidor", default=SERVER)
    args = p.parse_args()
    datos = extraer_valores_bsc(leer_bsc_local())
    print("META VENTAS BSC:", "; ".join(f"{y}: ${int(g):,} CLP" for y,g in sorted(datos.items())))
    with conectar(args.servidor) as con:
        cur = con.cursor()
        cur.execute("SELECT OBJECT_ID('dbo.CFG_META_VENTAS_ANUAL', 'U')")
        if cur.fetchone()[0] is None:
            raise RuntimeError("Falta tabla CFG_META_VENTAS_ANUAL. Ejecuta primero 01_crear_tabla_meta_ventas.sql en SSMS")
        if args.probar:
            print("PRUEBA OK: Excel METAS_VENTAS y tabla SQL validados, sin escrituras")
            con.rollback()
            return
        try:
            for year, amount in sorted(datos.items()):
                cur.execute("SELECT MetaAnualCLP FROM dbo.CFG_META_VENTAS_ANUAL WITH (UPDLOCK,HOLDLOCK) WHERE Anio=?", year)
                old = cur.fetchone()
                if old is None:
                    cur.execute("INSERT INTO dbo.CFG_META_VENTAS_ANUAL (Anio,MetaAnualCLP,Fuente) VALUES (?,?,?)",
                                year, amount, "BSC/METAS_VENTAS")
                    print(f"  {year}: INSERTADA")
                elif Decimal(str(old[0])) != amount:
                    cur.execute("UPDATE dbo.CFG_META_VENTAS_ANUAL SET MetaAnualCLP=?,Fuente=?,ActualizadoUTC=SYSUTCDATETIME() WHERE Anio=?",
                                amount, "BSC/METAS_VENTAS", year)
                    print(f"  {year}: ACTUALIZADA")
                else:
                    print(f"  {year}: SIN CAMBIOS")
            con.commit()
            print("META VENTAS: COMMIT OK (solo tabla CFG_META_VENTAS_ANUAL)")
        except Exception:
            con.rollback()
            raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR META VENTAS:", str(exc), file=sys.stderr)
        sys.exit(1)
