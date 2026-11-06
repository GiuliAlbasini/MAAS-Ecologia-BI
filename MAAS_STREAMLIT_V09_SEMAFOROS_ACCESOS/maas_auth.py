# -*- coding: utf-8 -*-
"""Compatibilidad con páginas antiguas: acceso por selector, sin contraseñas."""
import streamlit as st


def exigir_acceso(modulo):
    if (st.session_state.get('maas_portal_autorizado') is not True
            or st.session_state.get('maas_portal_perfil') != modulo):
        st.error('Selecciona este perfil en la pantalla inicial.')
        st.stop()
    return True
