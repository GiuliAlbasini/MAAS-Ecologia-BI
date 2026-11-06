# -*- coding: utf-8 -*-
"""Exporta una vista MAAS a PDF multipagina a partir de una captura completa.

No consulta ni modifica SQL. Usa Chromium/Playwright en sesion temporal y
mantiene el control de acceso del portal. Se capturan los filtros por defecto
porque se abre una sesion nueva, independiente de la ventana de la usuaria.
"""
from __future__ import annotations

from contextlib import suppress
from io import BytesIO
from urllib.parse import urlparse


def _pdf_desde_png(png: bytes) -> bytes:
    """Pagina A4 apaisada, con captura completa repartida sin omitir altura."""
    try:
        from PIL import Image
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.utils import ImageReader
    except ImportError as exc:
        raise RuntimeError(
            'Faltan dependencias para PDF. Ejecuta: python -m pip install pillow reportlab'
        ) from exc

    with Image.open(BytesIO(png)) as imagen:
        imagen = imagen.convert('RGB')
        ancho_px, alto_px = imagen.size
        if ancho_px < 10 or alto_px < 10:
            raise RuntimeError('La captura esta vacia; no se genero PDF.')

        ancho_hoja, alto_hoja = landscape(A4)
        margen = 22  # puntos (~7.8 mm)
        ancho_util = ancho_hoja - 2 * margen
        alto_util = alto_hoja - 2 * margen
        # Altura maxima en pixeles que cabe manteniendo el ancho completo.
        max_alto_fragmento = max(1, int(ancho_px * alto_util / ancho_util))
        salida = BytesIO()
        pdf = canvas.Canvas(salida, pagesize=(ancho_hoja, alto_hoja), pageCompression=1)
        offset = 0
        pagina = 0
        while offset < alto_px:
            limite = min(alto_px, offset + max_alto_fragmento)
            fragmento = imagen.crop((0, offset, ancho_px, limite))
            alto_dibujo = (limite - offset) * ancho_util / ancho_px
            pdf.drawImage(ImageReader(fragmento), margen,
                          alto_hoja - margen - alto_dibujo,
                          width=ancho_util, height=alto_dibujo,
                          preserveAspectRatio=True, mask='auto')
            pagina += 1
            pdf.setFont('Helvetica', 8)
            pdf.setFillColorRGB(0.45, 0.49, 0.56)
            pdf.drawRightString(ancho_hoja - margen, 10,
                                f'MAAS Ecologia | Pagina {pagina}')
            pdf.showPage()
            offset = limite
        pdf.save()
        return salida.getvalue()


def _seleccionar_rol(page, nombre_perfil: str) -> None:
    # Compatible con el login nuevo ('Area') y el login anterior.
    for nombre in ('\xc1rea', 'Area', 'Selecciona tu perfil'):
        selector = page.get_by_role('combobox', name=nombre, exact=True)
        if selector.count():
            selector.select_option(label=nombre_perfil) if selector.locator('option').count() else _elegir_lista_custom(selector, page, nombre_perfil)
            return
    raise RuntimeError('No se encontro el selector del area en el login MAAS.')


def _elegir_lista_custom(selector, page, nombre_perfil):
    selector.click()
    page.get_by_role('option', name=nombre_perfil, exact=True).click(timeout=15000)


def _abrir_pagina(page, destino: str) -> None:
    """Cambia la pagina usando st.navigation, sin reiniciar la sesion."""
    if destino == 'inicio':
        return
    # En Streamlit, los links de navegacion pueden estar dentro de un sidebar
    # inicialmente colapsado, pero click() en el DOM respeta el router de la app.
    enlaces = page.locator('[data-testid="stSidebarNav"] a')
    encontrados = enlaces.count()
    for i in range(encontrados):
        a = enlaces.nth(i)
        href = a.get_attribute('href') or ''
        if urlparse(href).path.rstrip('/').endswith('/' + destino):
            a.evaluate('(el) => el.click()')
            page.wait_for_function(
                '(path) => window.location.pathname.replace(/\\/$/, "").endsWith("/" + path)',
                arg=destino, timeout=20000)
            return
    # Respaldo para cambios de estructura interna del sidebar.
    titulos = {
        'gerencia': 'Gerencia General', 'administracion': 'Administraci\xf3n',
        'operaciones': 'Operaci\xf3n', 'ingenieria': 'Ingenier\xeda',
        'ventas': 'Ventas 2026', 'contratos': 'Contratos',
        'proyectos': 'Proyectos',
    }
    titulo = titulos.get(destino)
    if titulo:
        link = page.get_by_role('link', name=titulo, exact=True)
        if link.count():
            link.first.evaluate('(el) => el.click()')
            page.wait_for_function(
                '(path) => window.location.pathname.replace(/\\/$/, "").endsWith("/" + path)',
                arg=destino, timeout=20000)
            return
    raise RuntimeError(
        f'No se encontro la pagina {destino!r} en el menu autorizado. '
        'No se genero un PDF de una pagina distinta.'
    )


def exportar_pdf(*, perfil: str, nombre_perfil: str,
                 perfiles: dict, contrasenas: dict,
                 pagina_destino: str = 'inicio',
                 url: str = 'http://127.0.0.1:8501') -> bytes:
    """Genera un PDF de toda la altura de la pagina destino autorizada."""
    menu = {
        'gerencia': {'inicio', 'gerencia', 'ventas', 'contratos', 'proyectos'},
        'operaciones': {'inicio', 'operaciones', 'proyectos', 'contratos'},
        'administracion': {'inicio', 'administracion', 'ventas', 'proyectos', 'contratos'},
        'ingenieria': {'inicio', 'ingenieria', 'proyectos'},
    }
    if perfil not in perfiles or perfil not in menu:
        raise ValueError('Perfil no reconocido.')
    if pagina_destino not in menu[perfil]:
        raise ValueError('El perfil no tiene permiso para esta pagina.')
    clave = contrasenas.get(perfil, '')
    if not clave or str(clave).startswith('CAMBIAR_'):
        raise RuntimeError('La contrasena del perfil no esta configurada.')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            'Falta Playwright. Ejecuta: python -m pip install playwright'
        ) from exc

    with sync_playwright() as pw:
        try:
            navegador = pw.chromium.launch(headless=True)
        except Exception as exc:
            raise RuntimeError(
                'No se pudo iniciar Chromium. Ejecuta: python -m playwright install chromium'
            ) from exc
        try:
            contexto = navegador.new_context(
                viewport={'width': 1440, 'height': 900},
                device_scale_factor=1, locale='es-CL', color_scheme='light')
            page = contexto.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            page.get_by_role('button', name='Ingresar').wait_for(timeout=45000)
            _seleccionar_rol(page, nombre_perfil)
            page.get_by_label('Contrase\xf1a', exact=True).fill(str(clave))
            page.get_by_role('button', name='Ingresar').click()
            # El sidebar cambia despues de autenticar: confirma la entrada.
            page.get_by_role('button', name='Actualizar datos').wait_for(state='attached', timeout=60000)
            _abrir_pagina(page, pagina_destino)
            page.locator('[data-testid="stMainBlockContainer"]').wait_for(timeout=60000)
            with suppress(Exception):
                page.wait_for_function('''() =>
                    !document.querySelector('[data-testid="stSpinner"]') &&
                    !document.querySelector('[data-testid="stStatusWidget"] [role="progressbar"]')
                ''', timeout=30000)
            with suppress(Exception):
                page.locator('.js-plotly-plot').first.wait_for(timeout=10000)
            page.wait_for_timeout(1000)
            # Scroll previo para que Streamlit/Plotly monten componentes perezosos.
            page.evaluate('''async () => {
                const host = document.querySelector('[data-testid="stAppViewContainer"]');
                const scrollers = [document.scrollingElement, host].filter(Boolean);
                const maxH = Math.max(...scrollers.map(e=>e.scrollHeight), document.body.scrollHeight);
                for (let y=0; y<maxH; y+=600) {
                    for (const el of scrollers) el.scrollTop=y;
                    window.scrollTo(0,y);
                    await new Promise(r=>setTimeout(r,70));
                }
                for (const el of scrollers) el.scrollTop=0;
                window.scrollTo(0,0);
            }''')
            page.add_style_tag(content='''
                header[data-testid="stHeader"],
                [data-testid="stSidebar"],
                [data-testid="collapsedControl"],
                [data-testid="stToolbar"],
                [data-testid="stDecoration"],
                [data-testid="stStatusWidget"] {display:none!important}
                html,body,.stApp,
                [data-testid="stAppViewContainer"],
                [data-testid="stMain"],
                [data-testid="stMainBlockContainer"] {
                    overflow:visible!important;
                    height:auto!important;
                    max-height:none!important;
                }
                [data-testid="stMainBlockContainer"]{
                    max-width:1280px!important;width:100%!important;
                    margin:0 auto!important;padding:18px 24px!important;
                }
                [data-testid="stAppViewContainer"] {margin-left:0!important}
                body {background:#f4f7fb!important}
            ''')
            page.wait_for_timeout(650)
            png = page.screenshot(type='png', full_page=True,
                                  animations='disabled', timeout=90000)
            if len(png) < 5000:
                raise RuntimeError('La captura salio demasiado pequena; revisa el dashboard.')
            return _pdf_desde_png(png)
        finally:
            navegador.close()
