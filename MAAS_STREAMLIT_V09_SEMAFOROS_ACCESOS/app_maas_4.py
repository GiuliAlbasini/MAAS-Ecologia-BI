# -*- coding: utf-8 -*-
"""Portal MAAS Ecologia: acceso por rol y menu restringido segun permisos.

Conserva la estructura original del proyecto (pages_v08, maas_ui y logo_maas.png).
IMPORTANTE: para una aplicacion publica utiliza autenticacion segura y secretos externos.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hmac
import streamlit as st

BASE = Path(__file__).resolve().parent
PAGINAS = {
    'inicio': ('Inicio', '🏠', 'pages_v08/inicio.py'),
    'gerencia': ('Gerencia General', '👥', 'pages_v08/gerencia.py'),
    'administracion': ('Administración', '📁', 'pages_v08/administracion.py'),
    'ingenieria': ('Ingeniería', '📐', 'pages_v08/ingenieria.py'),
    'operaciones': ('Operación', '⚙️', 'pages_v08/operaciones.py'),
    'proyectos': ('Proyectos', '🧱', 'pages_v08/proyectos.py'),
    'contratos': ('Contratos', '📋', 'pages_v08/contratos.py'),
    'ventas': ('Ventas', '💰', 'pages_v08/ventas.py'),
}

# =====================================================================
# CONTRASEÑAS: EDITAR AQUÍ EN VISUAL STUDIO CODE (NO EN STREAMLIT)
# Para un despliegue público es preferible utilizar st.secrets y autenticación robusta.
# =====================================================================
CONTRASENAS = {
    'gerencia': 'gere123',
    'administracion': 'admin123',
    'ingenieria': 'ing123',
    'operaciones': 'ope123',
}

# El selector de ingreso incluye SOLO estos cuatro roles.
ROLES = {
    'gerencia': 'Gerencia General',
    'operaciones': 'Operaciones',
    'administracion': 'Administración',
    'ingenieria': 'Ingeniería',
}

# Páginas visibles según el área. Inicio es la primera para todos.
MENU = {
    'gerencia': ['inicio', 'gerencia', 'ventas', 'contratos', 'proyectos'],
    'operaciones': ['inicio', 'operaciones', 'proyectos', 'contratos'],
    'administracion': ['inicio', 'administracion', 'ventas', 'proyectos', 'contratos'],
    'ingenieria': ['inicio', 'ingenieria', 'proyectos'],
}

st.set_page_config(page_title='MAAS Ecología | Acceso', page_icon='🌿',
                   layout='wide', initial_sidebar_state='collapsed')

# Invalida el estado de la versión antigua, que permitía entrar sin clave.
VERSION_ACCESO = 'MAAS-ROLES-CUATRO-PERFILES-V4'
if st.session_state.get('maas_version_acceso') != VERSION_ACCESO:
    for _k in list(st.session_state):
        if _k.startswith(('maas_portal_', 'maas_acceso_simple_',
                          'maas_modulos_abiertos', 'maas_login_', 'maas_fallos_',
                           'maas_export_')):
            del st.session_state[_k]
    st.session_state['maas_version_acceso'] = VERSION_ACCESO


def cerrar_sesion():
    for k in list(st.session_state):
        if k.startswith(('maas_portal_', 'maas_acceso_simple_',
                         'maas_modulos_abiertos', 'maas_login_', 'maas_fallos_',
                           'maas_export_')):
            del st.session_state[k]
    st.rerun()


def pantalla_inicial():
    """Vista del ingreso. No cambia la autenticación ni los permisos de los roles."""
    st.markdown('''<style>
    section[data-testid="stSidebar"]{display:none!important}
    [data-testid="collapsedControl"]{display:none!important}
    .stApp, [data-testid="stAppViewContainer"]{background:#f3f6fa!important}
    .block-container{max-width:710px!important;padding-top:clamp(25px,6vh,55px)!important;
      padding-bottom:90px!important}
    .st-key-maas_portada{
      background:#ffffff!important;border:1px solid #e2eaf4!important;
      border-radius:30px!important;padding:37px 44px 26px!important;
      box-shadow:0 18px 50px rgba(22,45,79,.09)!important}
    .maas-login-icon{width:86px;height:86px;margin:0 auto 24px;
      border-radius:50%;background:#e1ebfb;display:flex;align-items:center;
      justify-content:center;font-size:40px;line-height:1}
    .maas-login-title{text-align:center;color:#142747;font-size:29px;
      font-weight:800;line-height:1.25;letter-spacing:-.5px;margin:0}
    .maas-login-sub{text-align:center;color:#8394b1;font-size:15px;
      margin:12px 0 26px}
    .st-key-maas_portada [data-testid="stForm"]{
      border:none!important;padding:0!important;background:transparent!important}
    .st-key-maas_portada label p{color:#162747!important;font-weight:650!important;
      font-size:15px!important}
    .st-key-maas_portada [data-testid="stSelectbox"] [data-baseweb="select"]>div{
      background:#eaf0f8!important;border-radius:11px!important;
      min-height:50px!important;border:1px solid transparent!important}
    .st-key-maas_portada [data-testid="stTextInput"] [data-baseweb="input"]{
      border-radius:11px!important;min-height:50px!important;
      border:1px solid #98add0!important;background:white!important}
    .st-key-maas_portada [data-testid="stTextInput"] input{
      font-size:16px!important;color:#172b4a!important}
    .st-key-maas_portada [data-testid="stTextInput"] input::placeholder{
      color:#899bb7!important}
    .st-key-maas_portada [data-testid="stFormSubmitButton"] button{
      background:#17294b!important;color:white!important;
      border:none!important;border-radius:28px!important;
      min-height:50px!important;font-size:17px!important;font-weight:700!important;
      box-shadow:none!important;margin-top:4px!important}
    .st-key-maas_portada [data-testid="stFormSubmitButton"] button:hover{
      background:#243e67!important;color:white!important}
    .st-key-maas_portada [data-testid="stFormSubmitButton"] button:focus{
      color:white!important}
    @media(max-width:620px){
      .block-container{padding-top:20px!important;padding-left:12px!important;
        padding-right:12px!important}
      .st-key-maas_portada{padding:28px 22px 23px!important;border-radius:23px!important}
      .maas-login-title{font-size:25px}
      .maas-login-sub{font-size:13px}
      .maas-login-icon{width:75px;height:75px;font-size:35px}}
    </style>''', unsafe_allow_html=True)

    with st.container(key='maas_portada'):
        st.markdown('''<div class="maas-login-icon" aria-hidden="true">🔐</div>
            <h1 class="maas-login-title">Tablero de KPI</h1>
            <p class="maas-login-sub">MaasEcología · elige tu área e ingresa tu contraseña</p>''',
            unsafe_allow_html=True)

        # Selector fuera del formulario, como en la versión original.
        elegido = st.selectbox('Área', list(ROLES),
                               format_func=lambda a: ROLES[a],
                               key='maas_seleccion_perfil')
        with st.form('maas_form_ingreso', clear_on_submit=False):
            clave = st.text_input('Contraseña', type='password',
                                  placeholder='Escribe tu contraseña')
            ingresar = st.form_submit_button('Ingresar', use_container_width=True,
                                              type='primary')

        if ingresar:
            esperada = CONTRASENAS.get(elegido, '')
            if not esperada or esperada.startswith('CAMBIAR_'):
                st.error('Esta área no tiene una contraseña configurada en app_maas_4.py.')
            elif hmac.compare_digest(clave.encode('utf-8'), esperada.encode('utf-8')):
                st.session_state['maas_portal_autorizado'] = True
                st.session_state['maas_portal_perfil'] = elegido
                st.rerun()
            else:
                st.error('Contraseña incorrecta. Inténtalo nuevamente.')


perfil = st.session_state.get('maas_portal_perfil')
if not st.session_state.get('maas_portal_autorizado') or perfil not in MENU:
    pantalla_inicial()
    st.stop()

# Registrar SOLO las páginas autorizadas para este rol.
# Streamlit impide resolver rutas de páginas no incluidas en st.navigation.
paginas_autorizadas = []
for clave_pagina in MENU[perfil]:
    nombre_pagina, icono_pagina, ruta_pagina = PAGINAS[clave_pagina]
    if not (BASE / ruta_pagina).is_file():
        st.error(f'Falta la página autorizada: {ruta_pagina}')
        st.stop()
    paginas_autorizadas.append(
        st.Page(ruta_pagina, title=nombre_pagina, icon=icono_pagina,
                url_path=clave_pagina, default=(clave_pagina == 'inicio'))
    )
navegacion = st.navigation(paginas_autorizadas, position='sidebar')
pagina_actual = (navegacion.url_path or 'inicio').strip('/')
# En versiones donde el path inicial es vacío, se trata de Inicio.
if pagina_actual not in MENU[perfil]:
    st.error('No tienes acceso a esta página.')
    st.stop()
nombre_rol = ROLES[perfil]

try:
    from maas_ui import estilo
    estilo()
except (ImportError, AttributeError):
    pass

with st.sidebar:
    logo = BASE / 'logo_maas.png'
    if logo.is_file():
        st.image(str(logo), width=185)
    else:
        st.markdown('### MAAS Ecología')
    st.divider()
    st.caption(f'👤 Sesión: {nombre_rol}')
    if st.button('🔄 Actualizar datos', use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    if st.button('↩ Cambiar perfil / Cerrar sesión', use_container_width=True):
        cerrar_sesion()
    st.divider()
    st.caption('Para guardar esta vista:')
    if st.button('📸 Capturar imagen (PNG)', use_container_width=True):
        try:
            from maas_exportacion import exportar_vista
            with st.spinner('Generando imagen PNG...'):
                st.session_state['maas_export_png'] = exportar_vista(
                    perfil=perfil, nombre_perfil=nombre_rol, perfiles=ROLES,
                    contrasenas=CONTRASENAS, formato='png', pagina_destino=pagina_actual)
                st.session_state['maas_export_png_perfil'] = (perfil, pagina_actual)
        except Exception as exc:
            st.error(f'No se pudo generar la imagen: {exc}')

    if (st.session_state.get('maas_export_png') is not None
            and st.session_state.get('maas_export_png_perfil') == (perfil, pagina_actual)):
        st.download_button('⬇️ Descargar PNG',
            data=st.session_state['maas_export_png'],
            file_name=f'MAAS_{perfil}_{pagina_actual}_{datetime.now(ZoneInfo("America/Santiago")):%Y%m%d_%H%M}.png',
            mime='image/png', use_container_width=True, key='maas_descargar_png')


    # PDF de toda la pagina: captura completa en nueva sesion autorizada,
    # repartida en hojas A4 apaisadas, sin cambiar los dashboards ni SQL.
    if st.button('📄 Crear PDF de esta página', use_container_width=True):
        try:
            from maas_pdf_exportacion import exportar_pdf
            with st.spinner('Generando PDF de la página completa...'):
                st.session_state['maas_export_pdf'] = exportar_pdf(
                    perfil=perfil, nombre_perfil=nombre_rol, perfiles=ROLES,
                    contrasenas=CONTRASENAS, pagina_destino=pagina_actual)
                st.session_state['maas_export_pdf_perfil'] = (perfil, pagina_actual)
        except Exception as exc:
            st.session_state.pop('maas_export_pdf', None)
            st.session_state.pop('maas_export_pdf_perfil', None)
            st.error(f'No se pudo generar el PDF: {exc}')

    if (st.session_state.get('maas_export_pdf') is not None
            and st.session_state.get('maas_export_pdf_perfil') == (perfil, pagina_actual)):
        st.download_button('⬇️ Descargar PDF',
            data=st.session_state['maas_export_pdf'],
            file_name=f'MAAS_{perfil}_{pagina_actual}_{datetime.now(ZoneInfo("America/Santiago")):%Y%m%d_%H%M}.pdf',
            mime='application/pdf', use_container_width=True,
            key='maas_descargar_pdf')


navegacion.run()
