# -*- coding: utf-8 -*-
"""MAAS ECOLOGÍA 4 | PASO 02: transformar y validar Drive + Gmail separado.

Compatible con el manifiesto del extractor de 20 fuentes (BSC + ventas + caja +
archivos proyecto_XX con Carta Gantt, Tareas y Recursos).

    py .\02_transformar_y_validar.py --probar     # valida sin publicar CSV
    py .\02_transformar_y_validar.py --ejecutar  # publica CSV y reporte
    py .\02_transformar_y_validar.py            # igual que --ejecutar

Lee CSV locales preparados por 01_extraer_desde_gmail.py (no conecta a Gmail).
NO modifica Drive, Gmail, SQL Server ni Streamlit.
IMPORTANTE: paso 04 actual (20 Drive) debe adaptarse para las fuentes Gmail;
no ejecutarlo después de publicar un reporte con Gmail, hasta actualizarlo.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import tempfile
import unicodedata
import warnings as python_warnings
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("Faltan librerías. Ejecuta: py -m pip install pandas openpyxl")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "datos_fuente" / "ultima_extraccion.json"
DEST = ROOT / "datos_transformados"
EXPECTED_STATIC = {"bsc", "ventas", "caja"}
EXPECTED_MIN_PROJECTS = 17
GMAIL_DIR = ROOT / "datos_fuente" / "gmail"
GMAIL_FILES = ("cierres_facturacion.csv", "contratos_pdf.csv", "auditoria_gmail.json")


def vacio(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip().lower() in ("", "nan", "nat", "none")
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def texto(v) -> str:
    if vacio(v):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def key(v) -> str:
    s = unicodedata.normalize("NFKD", texto(v))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def monto(v) -> int | None:
    if vacio(v):
        return None
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        n = Decimal(str(v))
    else:
        s = re.sub(r"[\s$]", "", texto(v))
        if re.fullmatch(r"-?\d{1,3}(?:[.,]\d{3})+", s):
            s = re.sub(r"[.,]", "", s)
        elif "," in s and "." not in s:
            s = s.replace(",", ".")
        try:
            n = Decimal(s)
        except InvalidOperation as exc:
            raise ValueError(f"Monto no numérico: {v!r}") from exc
    if not n.is_finite() or n != n.to_integral_value():
        raise ValueError(f"Monto CLP inválido: {v!r}")
    return int(n)


def numero(v) -> float | None:
    if vacio(v):
        return None
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        return float(v)
    s = texto(v).strip().replace("%", "").replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        n = float(s)
    except ValueError as exc:
        raise ValueError(f"Valor numérico inválido: {v!r}") from exc
    return n / 100 if texto(v).endswith("%") else n


def _letra_excel(columna: int) -> str:
    """Convierte columna 1-based a referencia A1, sin depender de Excel instalado."""
    letras = ""
    while columna:
        columna, resto = divmod(columna - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def numero_bsc(fila, campo: str, archivo: Path, hoja_excel: str):
    """Valida el KPI original e identifica su celda si Excel entrega #VALUE!."""
    try:
        return numero(fila.get(campo))
    except ValueError as exc:
        pos = fila.index.get_loc(campo)
        coordenada = f"{_letra_excel(int(pos) + 1)}{int(fila['fila_excel'])}"
        nombre = texto(fila.get('kpi'))
        raise ValueError(
            f"{archivo.name}, hoja {hoja_excel}, celda {coordenada}, "
            f"KPI {nombre!r}, campo {campo}: {exc}. "
            "Revisar la formula en Google Drive; no asignar cero automaticamente."
        ) from exc


def fecha(v) -> str:
    if vacio(v):
        return ""
    try:
        if isinstance(v, (int, float)):
            dt = pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))
        elif isinstance(v, (datetime, date, pd.Timestamp)):
            dt = pd.Timestamp(v)
        else:
            s = texto(v)
            dt = pd.to_datetime(s, errors="raise", dayfirst=not bool(re.match(r"^\d{4}-", s)))
        if pd.isna(dt):
            raise ValueError("fecha vacía")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"Fecha inválida: {v!r}") from exc


def entero(v) -> int | None:
    n = numero(v)
    if n is None:
        return None
    if not float(n).is_integer():
        raise ValueError(f"Se esperaba un entero: {v!r}")
    return int(n)


def pct(v, descripcion="porcentaje") -> float | None:
    n = numero(v)
    if n is not None and not 0 <= n <= 1:
        raise ValueError(f"{descripcion}: fuera de rango 0–100 %: {v!r}")
    return n


def hoja(path: Path, nombre: str, obligatorias: tuple[str, ...], max_fila: int = 14):
    raw = pd.read_excel(path, sheet_name=nombre, header=None, dtype=object)
    for i in range(min(len(raw), max_fila)):
        cabecera = [key(x) for x in raw.iloc[i]]
        if set(obligatorias).issubset(cabecera):
            apariciones = {}
            encabezados = []
            for j, nombre_campo in enumerate(cabecera):
                campo = nombre_campo or f"sin_nombre_{j}"
                apariciones[campo] = apariciones.get(campo, 0) + 1
                encabezados.append(campo if apariciones[campo] == 1 else f"{campo}_{apariciones[campo]}")
            df = raw.iloc[i + 1:].copy()
            df.columns = encabezados
            df = df.dropna(how="all").reset_index(drop=True)
            df["fila_excel"] = range(i + 2, i + 2 + len(df))
            return df, i, raw
    raise ValueError(f"{path.name}/{nombre}: no aparece la cabecera {obligatorias}")


def c(raw: pd.DataFrame, fila_1: int, col_1: int):
    return raw.iat[fila_1 - 1, col_1 - 1] if raw.shape[0] >= fila_1 and raw.shape[1] >= col_1 else None


def filas_tabla(raw: pd.DataFrame, inicio_1: int, columnas: int, cortar=None):
    for ix in range(inicio_1 - 1, len(raw)):
        vals = [c(raw, ix + 1, j) for j in range(1, columnas + 1)]
        if cortar and cortar(vals):
            break
        if not any(not vacio(x) for x in vals):
            # Podría ser un hueco entre varias propuestas: no detenemos aquí.
            continue
        yield ix + 1, vals


def tomar_manifest():
    if not MANIFEST.is_file():
        raise FileNotFoundError("Falta ultima_extraccion.json. Ejecuta primero el paso 01.")
    obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entradas = obj.get("archivos") if isinstance(obj, dict) else None
    if not isinstance(entradas, list):
        raise ValueError("Manifiesto no tiene 'archivos' con las 20 fuentes del nuevo extractor.")
    fuentes = {}
    for e in entradas:
        codigo = texto(e.get("fuente")).lower()
        if not codigo or codigo in fuentes:
            raise ValueError(f"Fuente duplicada o sin código en manifiesto: {codigo!r}")
        if codigo not in EXPECTED_STATIC and not re.fullmatch(r"proyecto_\d{2,}", codigo):
            raise ValueError(f"Fuente inesperada: {codigo!r}. Revisa el paso 01.")
        relativa = e.get("ruta_local")
        if not relativa:
            raise ValueError(f"La fuente {codigo} no tiene ruta local. Ejecuta paso 01 --ejecutar.")
        p = (ROOT / str(relativa)).resolve()
        if not p.is_relative_to(ROOT.resolve()) or not p.is_file():
            raise ValueError(f"Ruta fuera de la carpeta o inexistente: {codigo}")
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        if sha != e.get("version_sha256"):
            raise ValueError(f"La versión de {codigo} no coincide con el manifiesto. Repite paso 01.")
        fuentes[codigo] = {"ruta": p, "entrada": e, "sha256": sha}
    if not EXPECTED_STATIC.issubset(fuentes):
        raise ValueError(f"Faltan fuentes base: {sorted(EXPECTED_STATIC - set(fuentes))}")
    nums = sorted(int(k.split("_")[1]) for k in fuentes if k.startswith("proyecto_"))
    if not set(range(1, EXPECTED_MIN_PROJECTS + 1)).issubset(nums):
        raise ValueError("Faltan uno o más de los 17 proyectos iniciales")
    if nums != list(range(1, max(nums) + 1)):
        raise ValueError("Numeración de proyectos con huecos")
    return fuentes


def procesar_bsc(p, salida, conteos, adv):
    bsc, ind, raw = hoja(p, "BSC KPIs", ("categoria", "kpi", "meta_anual", "acumulado"))
    fecha_corte = ""
    for v in raw.iloc[:ind + 1].to_numpy().ravel():
        if isinstance(v, (date, datetime, pd.Timestamp)):
            fecha_corte = fecha(v)
            break
    if not fecha_corte:
        adv.append("BSC: no se reconoció fecha de referencia.")
    global_rows = []
    for _, r in bsc.iterrows():
        nombre = texto(r.get("kpi"))
        if not nombre:
            continue
        observacion = "SACAR" if any(texto(v).upper() == "SACAR" for v in r.tolist() if isinstance(v, str)) else ""
        global_rows.append({
            "fila_excel": int(r["fila_excel"]), "fecha_referencia": fecha_corte,
            "categoria": texto(r.get("categoria")), "nombre_kpi": nombre,
            "detalle": texto(r.get("detalle")), "meta_original": texto(r.get("meta_anual")),
            "meta_numerica": numero_bsc(r, "meta_anual", p, "BSC KPIs") if key(r.get("meta_anual")) != "b" else None,
            "acumulado_original": texto(r.get("acumulado")), "acumulado_numerico": numero_bsc(r, "acumulado", p, "BSC KPIs"),
            "avance_acumulado": numero_bsc(r, "avance_acumulado", p, "BSC KPIs"),
            "avance_proyectado": numero_bsc(r, "avance_proyectado_al_dia", p, "BSC KPIs"),
            "cumplimiento": numero_bsc(r, "cumplimiento", p, "BSC KPIs"),
            "responsable": texto(r.get("resp")), "peso": numero_bsc(r, "peso", p, "BSC KPIs"),
            "anotacion": observacion, "pendiente_validacion": bool(observacion),
        })
    if len(global_rows) != 15:
        adv.append(f"BSC: {len(global_rows)} KPI manuales (esperados 15, revisar si fue intencional).")
    salida["bsc_global.csv"] = pd.DataFrame(global_rows)
    conteos["kpi_global"] = len(global_rows)
    conteos["kpi_marcados_sacar"] = sum(int(r["pendiente_validacion"]) for r in global_rows)

    deps = []
    for nom in ("CONTRATOS", "ADMINISTRACION", "INGENIERIA", "OPERACIONES"):
        df, _, _ = hoja(p, nom, ("categoria", "kpi", "meta_anual", "acumulado"))
        if "peso" not in df.columns and "sin_nombre_7" in df.columns:
            df = df.rename(columns={"sin_nombre_7": "peso"})
        for _, r in df.iterrows():
            nombre = texto(r.get("kpi"))
            if not nombre:
                continue
            deps.append({
                "hoja": nom, "fila_excel": int(r["fila_excel"]),
                "categoria": texto(r.get("categoria")), "nombre_kpi": nombre,
                "meta_original": texto(r.get("meta_anual")),
                "meta_numerica": None if key(r.get("meta_anual")) == "b" else numero_bsc(r, "meta_anual", p, nom),
                "acumulado_original": texto(r.get("acumulado")),
                "acumulado_numerico": numero_bsc(r, "acumulado", p, nom),
                "avance_acumulado": numero_bsc(r, "avance_acumulado", p, nom),
                "cumplimiento": numero_bsc(r, "cumplimiento", p, nom),
                "peso": numero_bsc(r, "peso", p, nom),
            })
    salida["bsc_departamentos.csv"] = pd.DataFrame(deps)
    conteos["kpi_departamentales_filas"] = len(deps)

    # Hoja PROYECTOS permanece como fuente de verdad comercial; orden 1..17.
    pr = pd.read_excel(p, sheet_name="PROYECTOS", header=None, dtype=object)
    rows = []
    for i in range(3, len(pr)):
        nombre = texto(c(pr, i + 1, 1))
        if not nombre or key(nombre) in ("productos", "producto"):
            continue
        valor = monto(c(pr, i + 1, 2))
        if valor is None:
            continue  # No tratar subtítulos o totales como proyectos.
        obj = pct(c(pr, i + 1, 3), f"{nombre}: margen objetivo")
        act = pct(c(pr, i + 1, 4), f"{nombre}: margen actual")
        proy = pct(c(pr, i + 1, 6), f"{nombre}: margen proyectado")
        if any(x is None for x in (obj, act, proy)):
            raise ValueError(f"PROYECTOS fila {i+1}: faltan márgenes")
        rows.append({
            "numero_proyecto": len(rows) + 1,
            "codigo_proyecto": f"PRY-2026-{len(rows) + 1:03d}",
            "fila_excel": i + 1, "nombre_proyecto": nombre,
            "proyecto_normalizado": key(nombre), "venta_oc_clp": valor,
            "margen_objetivo": obj, "margen_actual": act,
            "avance_bsc": texto(c(pr, i + 1, 5)), "margen_proyectado": proy,
            "tipo_proyecto": texto(c(pr, i + 1, 7)),
            "no_cumple_original": entero(c(pr, i + 1, 8)),
            "cumple_margen_calculado": bool(act >= obj),
            "origen_comercial": "BSC", "origen_seguimiento": "SIMULADO",
        })
        if act < obj and entero(c(pr, i + 1, 8)) == 0:
            adv.append(f"BSC {nombre}: margen actual menor al objetivo, pero bandera No Cumple = 0 (no se corrigió).")
    if len(set(r["proyecto_normalizado"] for r in rows)) != len(rows):
        raise ValueError("Hoja PROYECTOS: nombres de proyecto duplicados")
    if len(rows) < EXPECTED_MIN_PROJECTS:
        raise ValueError(f"BSC: se encontraron solo {len(rows)} proyectos")
    salida["proyectos_bsc.csv"] = pd.DataFrame(rows)
    conteos["proyectos_bsc"] = len(rows)
    return rows


def procesar_ventas(p, salida, conteos, adv):
    sales, _, _ = hoja(p, "DETALLE", ("documento", "folio", "fecha", "rut", "neto"))
    facturas = []
    for _, r in sales.iterrows():
        tipo, folio = texto(r.get("documento")), texto(r.get("folio"))
        if not tipo or not folio:
            continue
        facturas.append({
            "fila_excel": int(r["fila_excel"]), "tipo_documento": tipo,
            "folio": folio, "fecha_documento": fecha(r.get("fecha")),
            "rut_cliente": texto(r.get("rut")), "razon_social": texto(r.get("razon_social")),
            "ciudad_cliente": texto(r.get("ciudad_cliente")), "comuna_cliente": texto(r.get("comunacliente")),
            "neto_clp": monto(r.get("neto")), "iva_clp": monto(r.get("iva")),
            "total_clp": monto(r.get("total")),
        })
    df = pd.DataFrame(facturas)
    if df.empty:
        raise ValueError("Reporte ventas: sin documentos válidos")
    df["clave_documento"] = df["tipo_documento"].map(key) + "|" + df["folio"].astype(str)
    df["documento_duplicado"] = df.duplicated("clave_documento", keep=False)
    if df["documento_duplicado"].any():
        raise ValueError(f"Ventas: {int(df['documento_duplicado'].sum())} documentos duplicados")
    if df["fecha_documento"].eq("").any() or df["neto_clp"].isna().any():
        raise ValueError("Ventas: existen facturas sin fecha o sin importe neto")
    salida["ventas_detalle.csv"] = df
    conteos["documentos_ventas"] = len(df)
    df["mes"] = df["fecha_documento"].str[:7]
    mensuales = df.groupby("mes", as_index=False).agg(
        ventas_netas_clp=("neto_clp", "sum"), documentos=("folio", "count"),
        clientes_distintos=("rut_cliente", "nunique"),
    )
    salida["ventas_mensuales_preliminares.csv"] = mensuales
    total_neto = int(df["neto_clp"].sum())
    resumen, _, _ = hoja(p, "RESUMEN", ("documento", "cantidad", "neto"))
    filas_total = resumen.loc[resumen["documento"].map(key).eq("total")]
    if len(filas_total) != 1:
        raise ValueError("Ventas: RESUMEN sin exactamente una fila TOTAL")
    neto_resumen = monto(filas_total.iloc[0].get("neto"))
    conteos["ventas_netas_clp"] = total_neto
    if total_neto != neto_resumen:
        raise ValueError(f"Ventas DETALLE vs RESUMEN no concilian: {total_neto:,} vs {neto_resumen:,} CLP")


def procesar_caja(p, salida, conteos, adv):
    raw = pd.read_excel(p, sheet_name="CONTROL_CAJA_MENSUAL", header=None, dtype=object)
    if key(c(raw, 6, 1)) != "periodo" or key(c(raw, 6, 7)) != "hubo_quiebre":
        raise ValueError("Control caja: encabezados diferentes a los esperados en la fila 6")
    registros = []
    for n_fila, vals in filas_tabla(raw, 7, 9, cortar=lambda x: not bool(re.fullmatch(r"20\d\d-\d\d", texto(x[0])))):
        mes = texto(vals[0])
        if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", mes):
            raise ValueError(f"Caja: período inválido en fila {n_fila}")
        inicial, ing, egr = (monto(vals[j]) for j in (1, 2, 3))
        if any(x is None for x in (inicial, ing, egr)) or ing < 0 or egr < 0:
            raise ValueError(f"Caja {mes}: faltan importes o entradas/salidas negativas")
        saldo_calculado = inicial + ing - egr
        brecha_calculada = max(-saldo_calculado, 0)
        hay_quiebre = saldo_calculado < 0
        saldo_excel, brecha_excel = monto(vals[4]), monto(vals[5])
        marca = key(vals[6])
        if saldo_excel is not None and saldo_excel != saldo_calculado:
            raise ValueError(f"Caja {mes}: saldo de Excel y cálculo no coinciden")
        if brecha_excel is not None and brecha_excel != brecha_calculada:
            raise ValueError(f"Caja {mes}: brecha de Excel y cálculo no coinciden")
        if marca and marca not in ({"si", "sí"} if hay_quiebre else {"no"}):
            raise ValueError(f"Caja {mes}: la marca de quiebre contradice el saldo")
        if registros and inicial != registros[-1]["saldo_final_clp"]:
            raise ValueError(f"Caja {mes}: saldo inicial no concilia con mes anterior")
        if mes in {r["mes"] for r in registros}:
            raise ValueError(f"Caja: período duplicado {mes}")
        if texto(vals[7]).upper() != "SIMULADO":
            raise ValueError(f"Caja {mes}: se esperaba origen SIMULADO")
        registros.append({
            "fila_excel": n_fila, "mes": mes, "saldo_inicial_clp": inicial,
            "ingresos_cobrados_clp": ing, "egresos_pagados_clp": egr,
            "saldo_final_clp": saldo_calculado, "brecha_caja_clp": brecha_calculada,
            "hubo_quiebre": hay_quiebre, "origen_datos": "SIMULADO",
            "observacion": texto(vals[8]),
        })
    if not registros:
        raise ValueError("Caja: no hay meses para procesar")
    salida["caja_mensual.csv"] = pd.DataFrame(registros)
    conteos["meses_caja"] = len(registros)
    conteos["meses_con_quiebre"] = sum(r["hubo_quiebre"] for r in registros)
    conteos["brecha_caja_acumulada_clp"] = sum(r["brecha_caja_clp"] for r in registros)
    adv.append("Caja: los saldos y quiebres son SIMULADOS, no datos financieros reales de MAAS.")


def procesar_proyecto(nro: int, p: Path, bsc: dict, items: dict, adv):
    prefijo = f"PRY-2026-{nro:03d}"
    gw = pd.read_excel(p, sheet_name="Carta Gantt", header=None, dtype=object)
    tw = pd.read_excel(p, sheet_name="Tareas", header=None, dtype=object)
    rw = pd.read_excel(p, sheet_name="Recursos", header=None, dtype=object)
    if key(c(gw, 8, 1)) != "codigo" or key(c(tw, 5, 1)) != "codigo" or key(c(rw, 5, 1)) != "recurso":
        raise ValueError(f"{p.name}: encabezados incorrectos de Carta Gantt/Tareas/Recursos")
    m = re.match(r"^\s*(\d{2,})\s*·\s*(.*?)\s*\|", texto(c(gw, 2, 1)))
    if not m or int(m.group(1)) != nro or key(m.group(2)) != bsc["proyecto_normalizado"]:
        raise ValueError(f"{p.name}: nombre/código del proyecto no corresponde con el seguimiento")
    if monto(c(gw, 5, 2)) != bsc["venta_oc_clp"]:
        raise ValueError(f"{p.name}: Venta/OC difiere del valor comercial de referencia")
    # Las comparaciones comerciales contra BSC solo aplican a proyectos incluidos allí.
    # Si el proyecto es nuevo, sus datos proceden del Excel de seguimiento.
    tiene_bsc = bsc.get("origen_comercial") == "BSC"
    if tiene_bsc:
        for pos, campo in ((4, "margen_objetivo"), (8, "margen_proyectado")):
            val = pct(c(gw, 5, pos))
            if val is None or abs(val - bsc[campo]) > 1e-8:
                raise ValueError(f"{p.name}: {campo} difiere del BSC")
    # El margen actual de Carta Gantt sigue siendo un cálculo independiente.
    margen_gantt = numero(c(gw, 5, 6))
    if margen_gantt is not None:
        if not math.isfinite(margen_gantt) or margen_gantt > 1:
            raise ValueError(f"{p.name}: margen actual de Carta Gantt invalido (F5)")
        if tiene_bsc and abs(margen_gantt - bsc["margen_actual"]) > 1e-8:
            adv.append(
                f"{p.name}: margen actual Gantt ({margen_gantt:.2%}) distinto del BSC "
                f"({bsc['margen_actual']:.2%}); se conserva el BSC como fuente comercial."
            )
    gantt = {}
    for fila, x in filas_tabla(gw, 9, 9, cortar=lambda r: key(r[0]) in ("total", "adjucacion_de_propuestas", "adjudicacion_de_propuestas")):
        cod = texto(x[0])
        if not re.fullmatch(r"T\d{2,4}", cod, flags=re.I):
            raise ValueError(f"{p.name} Carta Gantt fila {fila}: código de tarea inválido")
        if cod in gantt:
            raise ValueError(f"{p.name}: tarea Gantt duplicada: {cod}")
        f_ini, f_fin = fecha(x[2]), fecha(x[3])
        dur, hh, costo_plan = entero(x[4]), numero(x[5]), monto(x[6])
        if not f_ini or not f_fin or f_ini > f_fin:
            raise ValueError(f"{p.name} Gantt {cod}: fechas inválidas")
        if dur is None or hh is None or costo_plan is None or min(dur, hh, costo_plan) < 0:
            raise ValueError(f"{p.name} Gantt {cod}: horas/duración/costo inválidos")
        if dur != (date.fromisoformat(f_fin) - date.fromisoformat(f_ini)).days + 1:
            raise ValueError(f"{p.name} Gantt {cod}: duración no coincide con fechas")
        anterior = texto(x[7]); estado = texto(x[8])
        gantt[cod] = {
            "codigo_proyecto": prefijo, "numero_proyecto": nro, "nombre_proyecto": bsc["nombre_proyecto"],
            "fila_excel": fila, "codigo_tarea": cod, "nombre_tarea": texto(x[1]),
            "fecha_inicio_plan": f_ini, "fecha_termino_plan": f_fin,
            "duracion_dias": dur, "hh_planificadas": hh, "costo_planificado_clp": costo_plan,
            "tarea_predecesora": "" if anterior in ("—", "-") else anterior,
            "estado_tarea": estado, "origen_datos": "SIMULADO",
        }
    if not gantt:
        raise ValueError(f"{p.name}: Carta Gantt sin tareas")
    for cod, g in gantt.items():
        dep = g["tarea_predecesora"]
        if dep and (dep not in gantt or dep == cod):
            raise ValueError(f"{p.name}: predecesora inválida para {cod}: {dep}")
    tareas = {}
    for fila, x in filas_tabla(tw, 6, 10, cortar=lambda r: key(r[0]) == "total"):
        cod = texto(x[0])
        if not re.fullmatch(r"T\d{2,4}", cod, flags=re.I):
            raise ValueError(f"{p.name} Tareas fila {fila}: código inválido")
        if cod in tareas or cod not in gantt:
            raise ValueError(f"{p.name}: tarea {cod} repetida o inexistente en Carta Gantt")
        hh_plan, hh_real = numero(x[5]), numero(x[6])
        cp, cr = monto(x[7]), monto(x[8])
        if any(v is None for v in (hh_plan, hh_real, cp, cr)) or min(hh_plan, hh_real, cp, cr) < 0:
            raise ValueError(f"{p.name} Tareas {cod}: horas/costos inválidos")
        if abs(hh_plan - gantt[cod]["hh_planificadas"]) > 1e-8 or cp != gantt[cod]["costo_planificado_clp"]:
            raise ValueError(f"{p.name}: planificación distinta entre Carta Gantt y Tareas para {cod}")
        if fecha(x[3]) != gantt[cod]["fecha_inicio_plan"] or fecha(x[4]) != gantt[cod]["fecha_termino_plan"]:
            raise ValueError(f"{p.name}: fechas de {cod} distintas entre hojas")
        a = pct(x[9], f"{p.name} avance {cod}")
        # Regla SIMULADA acordada: HH reales > 0 implica tarea finalizada.
        # HH reales / HH planificadas se reserva para medir consumo, NO avance.
        avance_esperado = 1.0 if hh_real > 0 else 0.0
        if a is None or abs(a - avance_esperado) > 1e-5:
            adv.append(
                f"{p.name} {cod}: avance {a!r} no sigue la regla simulada "
                "(100% si HH reales > 0; 0% en otro caso). Revisar formula."
            )
        tareas[cod] = {
            "codigo_proyecto": prefijo, "numero_proyecto": nro, "nombre_proyecto": bsc["nombre_proyecto"],
            "fila_excel": fila, "codigo_tarea": cod, "nombre_tarea": texto(x[1]),
            "recurso_principal": texto(x[2]), "fecha_inicio_plan": fecha(x[3]),
            "fecha_termino_plan": fecha(x[4]), "hh_planificadas": hh_plan,
            "hh_reales": hh_real, "costo_planificado_clp": cp,
            "costo_real_clp": cr, "avance_tarea": a,
            "estado_tarea": gantt[cod]["estado_tarea"], "origen_datos": "SIMULADO",
        }
    if set(tareas) != set(gantt):
        raise ValueError(f"{p.name}: las tareas del Gantt y de Tareas no coinciden")

    # Conciliar la formula nueva de F5 con venta y costos reales de Tareas.
    # La hoja puede dejar F5 vacia hasta que todos los costos esten completos.
    # Una discrepancia se informa, pero nunca se reemplaza ni se inventa el margen.
    costos_reales = [t["costo_real_clp"] for t in tareas.values()]
    if all(costo > 0 for costo in costos_reales) and bsc["venta_oc_clp"] > 0:
        calculado = (bsc["venta_oc_clp"] - sum(costos_reales)) / bsc["venta_oc_clp"]
        if margen_gantt is None:
            adv.append(
                f"{p.name}: F5 sin resultado aunque todas las tareas tienen costos reales; "
                "revisar recálculo de la formula en Google Drive."
            )
        elif abs(margen_gantt - calculado) > 0.0001:
            adv.append(
                f"{p.name}: margen actual de F5 ({margen_gantt:.2%}) difiere "
                f"del calculado por Venta/OC y costos reales ({calculado:.2%}); "
                "revisar formula y valores almacenados."
            )
    elif margen_gantt is not None:
        adv.append(
            f"{p.name}: F5 tiene margen actual, pero alguna tarea no tiene "
            "costo real mayor que cero; revisar si el margen es preliminar."
        )
    for t in gantt.values():
        items["proyectos_gantt.csv"].append(t)
    for t in tareas.values():
        items["proyectos_tareas.csv"].append(t)

    recursos = []
    for fila, x in filas_tabla(rw, 6, 6, cortar=lambda r: key(r[0]).startswith("datos_simulados")):
        nombre = texto(x[0])
        if not nombre:
            continue
        plan, utilizado = numero(x[2]), numero(x[3])
        if plan is None or utilizado is None or plan < 0 or utilizado < 0:
            raise ValueError(f"{p.name} Recurso fila {fila}: cantidades inválidas")
        restante = plan - utilizado
        uso = utilizado / plan if plan else 0
        rr, ur = numero(x[4]), numero(x[5])
        if rr is not None and abs(rr - restante) > 1e-5:
            raise ValueError(f"{p.name} recurso {nombre}: restante no concilia")
        if ur is not None and abs(ur - uso) > 1e-5:
            raise ValueError(f"{p.name} recurso {nombre}: utilización no concilia")
        recursos.append({
            "codigo_proyecto": prefijo, "numero_proyecto": nro,
            "nombre_proyecto": bsc["nombre_proyecto"], "fila_excel": fila,
            "nombre_recurso": nombre, "unidad": texto(x[1]),
            "cantidad_planificada": plan, "cantidad_utilizada": utilizado,
            "cantidad_restante": restante, "porcentaje_utilizacion": uso,
            "origen_datos": "SIMULADO",
        })
    if not recursos:
        raise ValueError(f"{p.name}: no hay recursos")
    items["proyectos_recursos.csv"].extend(recursos)

    if key(c(gw, 19, 1)) != "n_propuesta" or key(c(gw, 19, 4)) != "estado":
        raise ValueError(f"{p.name}: encabezados de adjudicaciones en fila 19 no coinciden")
    for fila, x in filas_tabla(gw, 20, 9, cortar=lambda r: key(r[0]).startswith("nota")):
        propuesta = texto(x[0])
        if not propuesta:
            continue
        estado = key(x[3]); fecha_adj = fecha(x[4])
        if estado in ("adjudicada", "adjudicado") and not fecha_adj:
            raise ValueError(f"{p.name}: adjudicación {propuesta} sin fecha")
        if texto(x[5]) != prefijo:
            raise ValueError(f"{p.name}: ID de proyecto de propuesta no coincide")
        if texto(x[8]).upper() != "SIMULADO":
            raise ValueError(f"{p.name}: propuesta no marcada como SIMULADO")
        if monto(x[7]) != bsc["venta_oc_clp"]:
            raise ValueError(f"{p.name}: propuesta {propuesta} con monto distinto de BSC")
        cat = key(x[2])
        tipos = {"andina_externos": "ANDINA EXTERNOS", "doh": "DOH", "fundacion_mlp": "FUNDACIÓN MLP", "andina_faena": "ANDINA FAENA", "mlp_faena": "MLP-FAENA", "otras": "OTRAS"}
        if cat not in tipos:
            raise ValueError(f"{p.name}: categoría de propuesta desconocida: {x[2]!r}")
        items["proyectos_adjudicaciones.csv"].append({
            "codigo_proyecto": prefijo, "numero_proyecto": nro,
            "nombre_proyecto": bsc["nombre_proyecto"], "fila_excel": fila,
            "numero_propuesta": propuesta, "cliente": texto(x[1]),
            "categoria_kpi": tipos[cat], "estado_adjudicacion": texto(x[3]),
            "fecha_adjudicacion": fecha_adj, "anio": entero(x[6]),
            "monto_clp": monto(x[7]), "origen_datos": "SIMULADO",
        })
    return {
        "codigo_proyecto": prefijo, "numero_proyecto": nro,
        "nombre_proyecto": bsc["nombre_proyecto"],
        "fecha_inicio_plan": min(t["fecha_inicio_plan"] for t in gantt.values()),
        "fecha_termino_plan": max(t["fecha_termino_plan"] for t in gantt.values()),
        "hh_planificadas": sum(t["hh_planificadas"] for t in tareas.values()),
        "hh_reales": sum(t["hh_reales"] for t in tareas.values()),
        "costo_planificado_clp": sum(t["costo_planificado_clp"] for t in tareas.values()),
        "costo_real_clp": sum(t["costo_real_clp"] for t in tareas.values()),
        "tareas_total": len(tareas),
        "tareas_finalizadas": sum(key(t["estado_tarea"]) in ("finalizada", "finalizado", "terminada") for t in tareas.values()),
        "origen_datos": "SIMULADO",
    }


def procesar_proyectos(fuentes, bsc, salida, conteos, adv):
    por_num = {r["numero_proyecto"]: r for r in bsc}
    items = {n: [] for n in ("proyectos_gantt.csv", "proyectos_tareas.csv", "proyectos_recursos.csv", "proyectos_adjudicaciones.csv")}
    res = []
    numeros = sorted(int(k.split("_")[1]) for k in fuentes if k.startswith("proyecto_"))
    # El BSC es fuente comercial, pero NO un catálogo obligatorio de proyectos.
    # Una fuente de seguimiento nueva puede existir sin fila equivalente en BSC.
    faltan_archivos = sorted(set(por_num) - set(numeros))
    if faltan_archivos:
        adv.append(f"BSC: {len(faltan_archivos)} proyectos sin Excel de seguimiento: {faltan_archivos}. No se crea información operacional.")
    sin_bsc = []
    for nro in numeros:
        file = fuentes[f"proyecto_{nro:02d}"]["ruta"]
        if nro in por_num:
            ref = por_num[nro]
        else:
            gw = pd.read_excel(file, sheet_name="Carta Gantt", header=None, dtype=object)
            cabecera = texto(c(gw, 2, 1))
            match = re.match(r"^\s*(\d{2,})\s*·\s*(.*?)\s*\|", cabecera)
            if not match or int(match.group(1)) != nro or not texto(match.group(2)):
                raise ValueError(f"{file.name}: encabezado de proyecto sin nombre o número correcto")
            nombre = texto(match.group(2))
            venta = monto(c(gw, 5, 2))
            if venta is None or venta < 0:
                raise ValueError(f"{file.name}: Venta/OC faltante o inválida en Carta Gantt B5")
            ref = {"numero_proyecto": nro, "codigo_proyecto": f"PRY-2026-{nro:03d}",
                   "nombre_proyecto": nombre, "proyecto_normalizado": key(nombre),
                   "venta_oc_clp": venta, "margen_objetivo": None,
                   "margen_actual": None, "margen_proyectado": None,
                   "origen_comercial": "SEGUIMIENTO"}
            sin_bsc.append(nombre)
        res.append(procesar_proyecto(nro, file, ref, items, adv))
    # Rechazar nombres repetidos incluso si uno no aparece en el BSC.
    nombres = [key(x['nombre_proyecto']) for x in res]
    if len(nombres) != len(set(nombres)):
        raise ValueError("Seguimiento: proyectos con nombres normalizados duplicados")
    if sin_bsc:
        adv.append(f"{len(sin_bsc)} proyecto(s) nuevos sin BSC: " + ", ".join(sin_bsc) + ". Se conserva su origen seguimiento, sin inventar KPI comerciales.")
    salida["proyectos_seguimiento_resumen.csv"] = pd.DataFrame(res)
    conteos["proyectos_con_seguimiento"] = len(res)
    for nombre, rows in items.items():
        if not rows:
            raise ValueError(f"Sin datos: {nombre}")
        df = pd.DataFrame(rows)
        if nombre == "proyectos_adjudicaciones.csv":
            if df["numero_propuesta"].duplicated().any():
                raise ValueError("Propuestas repetidas entre proyectos")
            df["adjudicada"] = df["estado_adjudicacion"].map(key).isin(("adjudicada", "adjudicado"))
        salida[nombre] = df
        conteos[nombre.replace(".csv", "")] = len(df)
    cats = ["ANDINA EXTERNOS", "DOH", "FUNDACIÓN MLP", "ANDINA FAENA", "MLP-FAENA"]
    df = salida["proyectos_adjudicaciones.csv"]
    indicadores = [{"categoria_kpi": cat, "propuestas_registradas": int((df["categoria_kpi"] == cat).sum()),
                    "propuestas_adjudicadas": int(((df["categoria_kpi"] == cat) & df["adjudicada"]).sum()),
                    "origen_datos": "SIMULADO"} for cat in cats]
    salida["kpi_adjudicaciones_preliminares.csv"] = pd.DataFrame(indicadores)
    conteos["propuestas_adjudicadas"] = int(df["adjudicada"].sum())
    adv.append("Adjudicaciones: información SIMULADA; no equivale a todas las ofertas históricas de MAAS.")
    adv.append("Plazos del Gantt: SIMULADOS; sin contrato y fecha de cierre real no se concluyen atrasos definitivos.")




def procesar_gmail(salida: dict, conteos: dict, adv: list) -> dict:
    """Valida Gmail local y lo publica en CSV DISTINTOS de los de Drive.

    Nunca fusiona total de correo con facturas de Excel, ni modifica tareas/Gantt.
    Un contrato sin coincidencia exacta en BSC queda pendiente de vinculación.
    """
    archivos = {nombre: GMAIL_DIR / nombre for nombre in GMAIL_FILES}
    existentes = [n for n, p in archivos.items() if p.is_file()]
    if not existentes:
        adv.append("Gmail: no se encontraron exportaciones; solo se validaron las fuentes Drive.")
        return {}
    if len(existentes) != len(GMAIL_FILES):
        raise FileNotFoundError(
            "Gmail incompleto: faltan " + ", ".join(sorted(set(GMAIL_FILES) - set(existentes)))
            + ". Ejecuta 01_extraer_desde_gmail.py --ejecutar"
        )

    versiones_antes = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in archivos.items()}
    def leer_csv(nombre, requeridas):
        with archivos[nombre].open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            campos = set(reader.fieldnames or [])
            if not set(requeridas).issubset(campos):
                raise ValueError(f"Gmail {nombre}: columnas faltantes: {sorted(set(requeridas)-campos)}")
            return list(reader)

    cierres = leer_csv("cierres_facturacion.csv", (
        "periodo", "facturado_clp", "pendiente_clp", "criterio_facturacion",
        "gmail_message_id", "fecha_correo_utc", "origen_datos", "estado_validacion"
    ))
    contratos = leer_csv("contratos_pdf.csv", (
        "nombre_proyecto", "proyecto_normalizado", "fecha_inicio", "fecha_termino",
        "monto_contractual_clp", "gmail_message_id", "fecha_correo_utc",
        "archivo_pdf", "sha256_pdf", "origen_datos", "estado_validacion", "coincide_bsc"
    ))
    auditoria = json.loads(archivos["auditoria_gmail.json"].read_text(encoding="utf-8-sig"))
    if not isinstance(auditoria, dict) or not isinstance(auditoria.get("auditoria"), list):
        raise ValueError("Gmail: auditoria_gmail.json con estructura inválida")
    if auditoria.get("cierres") != len(cierres) or auditoria.get("contratos") != len(contratos):
        raise ValueError("Gmail: conteos de auditoría y CSV no coinciden")
    if auditoria.get("consulta") != "label:MAAS-ETL":
        raise ValueError("Gmail: la consulta no corresponde a la etiqueta MAAS-ETL")
    aprobados_auditoria = {
        (str(a.get("gmail_message_id", "")), str(a.get("tipo", "")))
        for a in auditoria["auditoria"] if a.get("estado") == "EXTRAIDO"
    }

    # Coincidencia exacta: primero BSC; los nuevos sin BSC pueden vincularse
    # con el seguimiento. Se mantiene el campo legacy CodigoProyectoBSC para SQL.
    catalogo = {}
    for r in salida["proyectos_bsc.csv"].to_dict("records"):
        nombre = texto(r["nombre_proyecto"])
        k = key(nombre)
        if k in catalogo:
            raise ValueError(f"BSC: dos proyectos tienen nombre normalizado idéntico: {nombre}")
        catalogo[k] = (texto(r["codigo_proyecto"]), nombre)

    for r in salida["proyectos_seguimiento_resumen.csv"].to_dict("records"):
        nombre = texto(r["nombre_proyecto"])
        clave = key(nombre)
        codigo = texto(r["codigo_proyecto"])
        if clave not in catalogo:
            catalogo[clave] = (codigo, nombre)

    def validar_fecha_utc(valor: str, desc: str):
        if not valor:
            raise ValueError(f"{desc}: falta fecha de correo")
        try:
            d = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"{desc}: fecha de correo inválida") from e
        if d.tzinfo is None:
            raise ValueError(f"{desc}: fecha de correo sin zona horaria")

    crows = []
    seen_c = set()
    for x in cierres:
        mid = texto(x["gmail_message_id"])
        mes = texto(x["periodo"])
        if (mid, "CIERRE") not in aprobados_auditoria:
            raise ValueError(f"Gmail cierre {mid}: no figura como EXTRAIDO en auditoría")
        if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", mes):
            raise ValueError(f"Gmail cierre {mid}: período inválido {mes!r}")
        if (mid, mes) in seen_c:
            raise ValueError(f"Gmail: cierre duplicado de mensaje {mid} para {mes}")
        seen_c.add((mid, mes))
        a, b = monto(x["facturado_clp"]), monto(x["pendiente_clp"])
        if a is None or b is None or a < 0 or b < 0:
            raise ValueError(f"Gmail cierre {mes}: montos vacíos o negativos")
        origen, estado = texto(x["origen_datos"]), texto(x["estado_validacion"])
        if origen not in ("SIMULADO", "REAL") or not estado:
            raise ValueError(f"Gmail cierre {mes}: origen/estado incompleto")
        validar_fecha_utc(texto(x["fecha_correo_utc"]), f"Gmail cierre {mes}")
        crows.append({
            "periodo": mes, "facturado_clp": a, "pendiente_clp": b,
            "criterio_facturacion": texto(x["criterio_facturacion"]),
            "gmail_message_id": mid, "fecha_correo_utc": x["fecha_correo_utc"],
            "origen_datos": origen, "estado_validacion": estado,
        })
    # No se elige arbitrariamente un mes si existen versiones diferentes.
    por_mes = {}
    for r in crows:
        por_mes.setdefault(r["periodo"], set()).add((r["facturado_clp"], r["pendiente_clp"]))
    conflictivos = [p for p, xs in por_mes.items() if len(xs) > 1]
    if conflictivos:
        for r in crows:
            if r["periodo"] in conflictivos:
                r["estado_validacion"] = "CONFLICTO_MISMO_MES"
        adv.append("Gmail: cierres con valores contradictorios, revisar: " + ", ".join(sorted(conflictivos)))

    prows = []
    seen_sha = set()
    for x in contratos:
        mid = texto(x["gmail_message_id"])
        if (mid, "CONTRATO") not in aprobados_auditoria:
            raise ValueError(f"Gmail contrato {mid}: no figura como EXTRAIDO en auditoría")
        nombre = texto(x["nombre_proyecto"])
        clave = key(nombre)
        if not nombre or clave != texto(x["proyecto_normalizado"]):
            raise ValueError(f"Gmail contrato {mid}: normalización de proyecto no coincide")
        fi, ff = texto(x["fecha_inicio"]), texto(x["fecha_termino"])
        try:
            if fi != date.fromisoformat(fi).isoformat() or ff != date.fromisoformat(ff).isoformat():
                raise ValueError("Fecha no ISO")
        except ValueError as e:
            raise ValueError(f"Gmail contrato {nombre}: fechas no válidas") from e
        if ff < fi:
            raise ValueError(f"Gmail contrato {nombre}: fin anterior a inicio")
        valor = monto(x["monto_contractual_clp"])
        if valor is None or valor < 0:
            raise ValueError(f"Gmail contrato {nombre}: monto faltante o negativo")
        sha = texto(x["sha256_pdf"]).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", sha) or sha in seen_sha:
            raise ValueError(f"Gmail contrato {nombre}: hash de PDF inválido o duplicado")
        seen_sha.add(sha)
        origen, estado = texto(x["origen_datos"]), texto(x["estado_validacion"])
        if origen not in ("SIMULADO", "REAL") or not estado:
            raise ValueError(f"Gmail contrato {nombre}: origen/estado incompleto")
        validar_fecha_utc(texto(x["fecha_correo_utc"]), f"Gmail contrato {nombre}")
        codigo, bsc_nombre = catalogo.get(clave, ("", ""))
        nombres_bsc = {key(r["nombre_proyecto"]) for r in salida["proyectos_bsc.csv"].to_dict("records")}
        es_bsc = "SI" if clave in nombres_bsc else "NO"
        if texto(x["coincide_bsc"]) != es_bsc:
            adv.append(f"Gmail contrato {nombre}: coincidencia BSC fue recalculada; comprobar fuente.")
        prows.append({
            "nombre_proyecto": nombre, "proyecto_normalizado": clave,
            "codigo_proyecto_bsc": codigo, "nombre_proyecto_bsc": bsc_nombre,
            "estado_vinculacion": ("VINCULADO_BSC" if es_bsc == "SI" else
                                   "VINCULADO_SEGUIMIENTO" if codigo else "PENDIENTE_VINCULACION"),
            "fecha_inicio": fi, "fecha_termino": ff, "monto_contractual_clp": valor,
            "gmail_message_id": mid, "fecha_correo_utc": x["fecha_correo_utc"],
            "archivo_pdf": texto(x["archivo_pdf"]), "sha256_pdf": sha,
            "origen_datos": origen, "estado_validacion": estado,
            "coincide_bsc": es_bsc,
        })
    por_proyecto = {}
    for r in prows:
        por_proyecto.setdefault(r["proyecto_normalizado"], set()).add(
            (r["fecha_inicio"], r["fecha_termino"], r["monto_contractual_clp"]))
    conflictos = [p for p, xs in por_proyecto.items() if len(xs) > 1]
    if conflictos:
        for r in prows:
            if r["proyecto_normalizado"] in conflictos:
                r["estado_validacion"] = "CONFLICTO_CONTRATOS"
        adv.append("Gmail: contratos contradictorios para " + ", ".join(sorted(conflictos)))

    versiones_despues = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in archivos.items()}
    if versiones_antes != versiones_despues:
        raise RuntimeError("Gmail: archivos cambiaron durante validación; repite el paso 02")
    campos_c = ("periodo", "facturado_clp", "pendiente_clp", "criterio_facturacion",
                "gmail_message_id", "fecha_correo_utc", "origen_datos", "estado_validacion")
    campos_p = ("nombre_proyecto", "proyecto_normalizado", "codigo_proyecto_bsc",
                "nombre_proyecto_bsc", "estado_vinculacion", "fecha_inicio", "fecha_termino",
                "monto_contractual_clp", "gmail_message_id", "fecha_correo_utc", "archivo_pdf",
                "sha256_pdf", "origen_datos", "estado_validacion", "coincide_bsc")
    salida["gmail_cierres_facturacion.csv"] = pd.DataFrame(crows, columns=campos_c)
    salida["gmail_contratos_pdf.csv"] = pd.DataFrame(prows, columns=campos_p)
    conteos["gmail_cierres"] = len(crows)
    conteos["gmail_contratos"] = len(prows)
    conteos["gmail_contratos_vinculados_bsc"] = sum(bool(x["codigo_proyecto_bsc"]) for x in prows)
    conteos["gmail_contratos_pendientes_vinculacion"] = sum(not x["codigo_proyecto_bsc"] for x in prows)
    adv.append("Gmail: los cierres NO se concilian automáticamente con ventas Excel y NO se suman a ventas.")
    adv.append("Gmail: contratos extraídos SIN APROBACIÓN; fechas y montos NO sustituyen automáticamente datos BSC/Gantt.")
    if any(x["origen_datos"] == "SIMULADO" for x in crows + prows):
        adv.append("Gmail: incluye datos SIMULADOS de prueba; no utilizarlos como resultados reales.")
    return {
        "archivos": {n: str(p.resolve()) for n, p in archivos.items()},
        "sha256": versiones_antes,
        "consulta": auditoria["consulta"],
    }


def diagnosticar_errores_excel(fuentes, max_celdas: int = 15):
    """Inspecciona solo el contenido ZIP/XML de los Excel; no ejecuta macros.

    Detecta errores cacheados de formulas (t=e) y texto literal o compartido
    que contenga #VALUE!, #REF!, #DIV/0!, etc. No modifica ninguna fuente.
    """
    import posixpath
    from zipfile import ZipFile, BadZipFile
    from xml.etree import ElementTree as ET

    nsm = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    nsr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    nsrel = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    errores = {"#VALUE!", "#REF!", "#DIV/0!", "#NUM!", "#N/A", "#NAME?", "#NULL!"}
    total = 0
    for codigo, info in fuentes.items():
        archivo = info["ruta"]
        try:
            with ZipFile(archivo) as z:
                if "xl/workbook.xml" not in z.namelist():
                    continue
                libro = ET.fromstring(z.read("xl/workbook.xml"))
                rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
                targets = {}
                for rel in rels.findall(nsrel + "Relationship"):
                    target = rel.attrib.get("Target", "")
                    if target.startswith("/"):
                        target = target.lstrip("/")
                    else:
                        target = posixpath.normpath(posixpath.join("xl", target))
                    targets[rel.attrib.get("Id")] = target
                compartidas = []
                if "xl/sharedStrings.xml" in z.namelist():
                    ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
                    compartidas = ["".join(si.itertext()) for si in ss.findall(nsm + "si")]
                for sh in libro.findall(".//" + nsm + "sheet"):
                    nombre_hoja = sh.attrib.get("name", "?")
                    ruta_hoja = targets.get(sh.attrib.get(nsr + "id"), "")
                    if not ruta_hoja.startswith("xl/worksheets/") or ruta_hoja not in z.namelist():
                        continue
                    data = ET.fromstring(z.read(ruta_hoja))
                    for celda in data.iter(nsm + "c"):
                        typ = celda.attrib.get("t", "")
                        val = celda.findtext(nsm + "v", default="")
                        if typ == "s":
                            try:
                                val = compartidas[int(val)]
                            except (ValueError, IndexError):
                                continue
                        elif typ == "inlineStr":
                            val = "".join(celda.itertext())
                        if val.strip().upper() in errores:
                            total += 1
                            if total <= max_celdas:
                                print(
                                    f"  CELDA EXCEL CON ERROR: {codigo} / {archivo.name} / "
                                    f"{nombre_hoja}!{celda.attrib.get('r', '?')} = {val!r}",
                                    file=sys.stderr,
                                )
        except (BadZipFile, KeyError, ET.ParseError, OSError) as exc:
            print(f"  AVISO: no se pudo inspeccionar {codigo}: {exc}", file=sys.stderr)
    if total > max_celdas:
        print(f"  ...y otras {total - max_celdas} celdas con error Excel.", file=sys.stderr)
    if total:
        print(
            "ACCION: corregir en el archivo original de Google Drive la(s) formula(s) "
            "indicada(s), esperar el guardado y repetir el maestro. "
            "NO modificar SQL ni sustituir el error por 0.",
            file=sys.stderr,
        )
    return total


def guardar_archivos(salida, reporte):
    DEST.mkdir(parents=True, exist_ok=True)
    # Escribir primero todos los CSV y el informe en un directorio temporal.
    with tempfile.TemporaryDirectory(prefix="maas_paso02_", dir=DEST.parent) as td:
        temp = Path(td)
        for nombre, df in salida.items():
            df.to_csv(temp / nombre, index=False, encoding="utf-8-sig", lineterminator="\n")
        (temp / "reporte_validacion.json").write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
        # Publicar el informe al final para que el paso siguiente lea la versión completa.
        for p in temp.iterdir():
            if p.name != "reporte_validacion.json":
                p.replace(DEST / p.name)
        (temp / "reporte_validacion.json").replace(DEST / "reporte_validacion.json")


def principal(publicar=True):
    fuentes = tomar_manifest()
    salida, conteos, advertencias = {}, {}, []
    with python_warnings.catch_warnings():
        python_warnings.filterwarnings("ignore", message="Unknown extension is not supported")
        python_warnings.filterwarnings("ignore", message="Conditional Formatting extension is not supported")
        bsc = procesar_bsc(fuentes["bsc"]["ruta"], salida, conteos, advertencias)
        procesar_ventas(fuentes["ventas"]["ruta"], salida, conteos, advertencias)
        procesar_caja(fuentes["caja"]["ruta"], salida, conteos, advertencias)
        procesar_proyectos(fuentes, bsc, salida, conteos, advertencias)
        datos_gmail = procesar_gmail(salida, conteos, advertencias)

    reporte = {
        "etapa": "02_transformar_y_validar",
        "version_estructura": "MAAS_20_FUENTES_GMAIL_V2" if datos_gmail else "MAAS_20_FUENTES_V1",
        "fuentes": {k: str(v["ruta"]) for k, v in fuentes.items()},
        "versiones_fuente_sha256": {k: v["sha256"] for k, v in fuentes.items()},
        "gmail": datos_gmail,
        "conteos": conteos, "advertencias": advertencias, "errores": [],
        "csv_generados": sorted(salida), "proyectos_simulados": True,
        "caja_simulada": True, "requiere_paso04_actualizado": True,
    }
    print("\nETL MAAS 4 | TRANSFORMACIÓN Y VALIDACIÓN (SIN SQL)")
    print(f"Fuentes validadas: {len(fuentes)}")
    for campo, valor in conteos.items():
        print(f"  {campo}: {valor}")
    print("ADVERTENCIAS:")
    for x in advertencias:
        print(f" - {x}")
    if publicar:
        guardar_archivos(salida, reporte)
        print("\nOK: CSV y reporte publicados en", DEST)
    else:
        print("\nPRUEBA OK: no se modificaron los CSV ni el reporte.")
    print("No se modificaron Drive, SQL Server ni Streamlit.")
    if datos_gmail:
        print("IMPORTANTE: NO ejecutes paso 04: ahora debe adaptarse para Gmail antes de cargar.")
    else:
        print("Gmail no encontrado: se conserva el reporte V1 solo Drive.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transformar 20 fuentes Drive + Gmail (si fue extraído)")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--probar", action="store_true", help="Validar sin publicar")
    g.add_argument("--ejecutar", action="store_true", help="Validar y publicar")
    a = parser.parse_args()
    try:
        sys.exit(principal(publicar=not a.probar))
    except Exception as exc:
        print(f"\nERROR PASO 02: {exc}", file=sys.stderr)
        if any(x in str(exc).upper() for x in ("#VALUE!", "#REF!", "#DIV/0!", "#NUM!", "#NAME?", "#NULL!", "#N/A")):
            print("DIAGNOSTICO DE FORMULAS / CELDAS EXCEL (solo lectura):", file=sys.stderr)
            try:
                diagnosticar_errores_excel(tomar_manifest())
            except Exception as error_diagnostico:
                print(f"No fue posible ubicar todas las celdas: {error_diagnostico}", file=sys.stderr)
        print("VALIDACIÓN FALLIDA. No ejecutes el paso 04.", file=sys.stderr)
        sys.exit(1)
