# -*- coding: utf-8 -*-
"""Compatibilidad para tableros anteriores: sin segundo inicio de sesión."""
import streamlit as st


def exigir_acceso_simple(area):
    if (st.session_state.get('maas_portal_autorizado') is not True
            or st.session_state.get('maas_portal_perfil') != area):
        st.error('Selecciona este perfil en la pantalla inicial.')
        st.stop()
    return True
