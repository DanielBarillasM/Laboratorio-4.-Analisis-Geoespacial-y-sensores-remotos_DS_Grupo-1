"""Solicita autorización OIDC y deja un token efímero para el descargador.

No recibe usuario ni contraseña. El archivo resultante está ignorado por Git y
el descargador lo elimina inmediatamente después de leerlo.
"""

from pathlib import Path

import openeo


ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / "data" / "jobs" / "access_token.txt"


def show(message: str) -> None:
    print(message, flush=True)


connection = openeo.connect("https://openeo.dataspace.copernicus.eu")
show("Conexión preparada; solicitando código de Copernicus…")
connection.authenticate_oidc_device(
    provider_id="CDSE",
    store_refresh_token=False,
    use_pkce=True,
    max_poll_time=600,
    display=show,
)
bearer = connection.auth.bearer
prefix = "oidc/CDSE/"
if not bearer.startswith(prefix):
    raise RuntimeError("El backend devolvió un tipo de token inesperado")
TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
TOKEN_PATH.write_text(bearer.removeprefix(prefix), encoding="utf-8")
show("Autorización completada. Token temporal listo para el descargador.")
