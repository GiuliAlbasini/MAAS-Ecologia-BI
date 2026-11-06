# -*- coding: utf-8 -*-
"""Asistente local para credenciales de Streamlit con claves PBKDF2.
No se almacenan claves en texto plano. Nunca subir .streamlit/secrets.toml.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import tomllib

ROOT = Path(__file__).resolve().parent
DESTINO = ROOT / '.streamlit' / 'secrets.toml'
ROLES = ['gerencia','administracion','ingenieria','operaciones','contratos','ventas']


def quoted(v):
    return json.dumps(str(v), ensure_ascii=False)


def crear_hash(passwd: str):
    salt = secrets.token_bytes(24)
    rounds = 600_000
    digest = hashlib.pbkdf2_hmac('sha256', passwd.encode('utf-8'), salt, rounds)
    return '$'.join(['pbkdf2_sha256',str(rounds),base64.b64encode(salt).decode(),base64.b64encode(digest).decode()])


def main():
    print('MAAS 4 | CONFIGURAR USUARIOS PARA STREAMLIT (LOCAL)')
    if DESTINO.exists():
        try:
            content = tomllib.loads(DESTINO.read_text(encoding='utf-8'))
        except Exception as exc:
            raise SystemExit(f'El archivo de cuentas actual no se puede leer: {exc}')
    else:
        content = {'conexion': {'servidor': r'Giuli\GIULIANA'}, 'usuarios': []}
    usuario = input('Nuevo usuario (sin espacios): ').strip().lower()
    if not usuario or any(c.isspace() for c in usuario):
        raise SystemExit('Nombre de usuario invalido.')
    nombre = input('Nombre visible: ').strip() or usuario
    print('Roles: '+', '.join(ROLES))
    rol = input('Rol: ').strip().lower()
    if rol not in ROLES:
        raise SystemExit('Rol invalido.')
    p = getpass.getpass('Contraseña (minimo 12 caracteres): ')
    p2 = getpass.getpass('Repetir contraseña: ')
    if len(p) < 12 or p != p2:
        raise SystemExit('Contraseñas diferentes o demasiado cortas.')
    cuenta = {'usuario':usuario,'nombre':nombre,'rol':rol,'hash':crear_hash(p)}
    old = [dict(x) for x in content.get('usuarios',[]) if x.get('usuario') != usuario]
    old.append(cuenta)
    conn = content.get('conexion',{})
    server = conn.get('servidor') or r'Giuli\GIULIANA'
    lines = ['# CONFIDENCIAL: NO SUBIR ESTE ARCHIVO A DRIVE/GITHUB/CHATGPT', '[conexion]', 'servidor = '+quoted(server),'']
    for x in old:
        lines.extend(['[[usuarios]]', 'usuario = '+quoted(x['usuario']), 'nombre = '+quoted(x.get('nombre') or x['usuario']), 'rol = '+quoted(x['rol']), 'hash = '+quoted(x['hash']),''])
    DESTINO.parent.mkdir(parents=True,exist_ok=True)
    # Sustitucion atomica y escritura en UTF-8.
    temp = DESTINO.with_suffix('.toml.tmp')
    temp.write_text('\n'.join(lines),encoding='utf-8')
    os.replace(temp,DESTINO)
    print('Cuenta creada / actualizada. Cuentas configuradas:',len(old))
    print('El archivo .streamlit/secrets.toml debe permanecer privado.')

if __name__=='__main__':
    main()
