# -*- coding: utf-8 -*-
"""Exportación visual local de dashboards MAAS usando Chromium/Playwright.
No modifica SQL ni el ETL. Ejecuta un navegador aislado y temporal.
Instalación (una vez): python -m pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

from contextlib import suppress
import io
import os


def exportar_vista(*, perfil: str, nombre_perfil: str, perfiles: dict,
                   contrasenas: dict, formato: str, url: str = 'http://127.0.0.1:8501') -> bytes:
    """Devuelve un PNG de página completa o PDF impreso de la vista del perfil.

    Nota: Playwright usa su propia sesión local (no la sesión del usuario).
    Se autentica con la clave configurada en el código y cierra Chromium al terminar.
    """
    if formato not in ('png', 'pdf'):
        raise ValueError('Formato no permitido. Usa png o pdf.')
    if perfil not in perfiles:
        raise ValueError('Perfil no reconocido.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError('Falta Playwright. Instálalo con: python -m pip install playwright') from exc

    clave = contrasenas.get(perfil, '') if perfil != 'inicio' else ''
    if perfil != 'inicio' and (not clave or clave.startswith('CAMBIAR_')):
        raise RuntimeError('El perfil no tiene contraseña configurada en app_maas_4.py.')

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, args=['--disable-dev-shm-usage'])
        except Exception as exc:
            raise RuntimeError('Chromium de Playwright no está instalado. Ejecuta: python -m playwright install chromium') from exc
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 900},
                                    device_scale_factor=1, locale='es-CL',
                                    color_scheme='light')
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            # Entrar por la pantalla original, sin saltarse ninguna validación.
            # Esperar a que Streamlit termine de montar sus widgets.
            selector = page.get_by_role('combobox', name='Selecciona tu perfil')
            selector.wait_for(timeout=45000)
            if perfil != 'inicio':
                selector.click()
                page.get_by_role('option', name=nombre_perfil, exact=True).click(timeout=15000)
                page.get_by_role('textbox', name='Contraseña').fill(clave)
            page.get_by_role('button', name='Ingresar').click()
            # Esperar a que desaparezca el login y aparezca el botón del dashboard.
            page.get_by_role('button', name='Actualizar datos').wait_for(timeout=90000)
            page.locator('[data-testid="stAppViewContainer"] [data-testid="stMainBlockContainer"]').wait_for(timeout=60000)
            # Esperar a que terminen los indicadores/gráficos y la carga del dashboard.
            page.wait_for_function("""() =>
                !document.querySelector('[data-testid="stSpinner"]') &&
                !document.querySelector('[data-testid="stStatusWidget"] [role="progressbar"]')
            """, timeout=90000)
            with suppress(Exception):
                page.locator('.js-plotly-plot').first.wait_for(timeout=10000)
            page.wait_for_timeout(1100)
            # La vista se exporta sin la barra lateral ni la barra superior de Streamlit.
            page.add_style_tag(content='''
                header[data-testid="stHeader"],
                [data-testid="stSidebar"],
                [data-testid="collapsedControl"],
                [data-testid="stToolbar"],
                [data-testid="stDecoration"] {display:none!important}
                [data-testid="stAppViewContainer"] {margin-left:0!important}
                [data-testid="stMainBlockContainer"] {max-width:none!important;width:100%!important;
                    padding:18px 24px!important}
                body {background:#F4F7FB!important}
                @media print {
                  [data-testid="stMainBlockContainer"] {padding:12px 16px!important}
                  [data-testid="stPlotlyChart"] {break-inside:avoid}
                }
            ''')
            # Asegura que haya scroll real hasta el final, para activar lazy-load.
            page.evaluate('''async () => {
                const el = document.querySelector('[data-testid="stAppViewContainer"]') || document.scrollingElement;
                const distance = Math.max(el.scrollHeight, document.body.scrollHeight);
                for (let y = 0; y <= distance; y += 650) {
                  el.scrollTop = y;
                  window.scrollTo(0, y);
                  await new Promise(r => setTimeout(r, 55));
                }
                el.scrollTop = 0; window.scrollTo(0,0);
            }''')
            page.wait_for_timeout(900)
            if formato == 'png':
                return page.screenshot(type='png', full_page=True, animations='disabled', timeout=60000)
            return page.pdf(format='A4', landscape=True, print_background=True,
                            margin={'top':'10mm','bottom':'10mm','left':'9mm','right':'9mm'},
                            prefer_css_page_size=False)
        finally:
            browser.close()
