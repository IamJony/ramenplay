# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import xbmcaddon

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")


def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID}] {msg}", level)


def log_debug(msg):
    """Solo loguea si el usuario activó modo debug."""
    try:
        if ADDON.getSetting("debug") == "true":
            xbmc.log(f"[{ADDON_ID}][DEBUG] {msg}", xbmc.LOGDEBUG)
    except Exception:
        pass


def notificar(msg, tiempo=3000, icono=xbmcgui.NOTIFICATION_INFO):
    xbmcgui.Dialog().notification(ADDON_NAME, msg, icono, tiempo)


def pedir_texto(titulo, valor_inicial=""):
    kb = xbmc.Keyboard(valor_inicial, titulo)
    kb.doModal()
    if kb.isConfirmed():
        return kb.getText().strip()
    return None


def get_timeout():
    try:
        return int(ADDON.getSetting("timeout") or "8")
    except Exception:
        return 8


def get_health_check():
    try:
        return ADDON.getSetting("health_check") == "true"
    except Exception:
        return True


def get_health_check_timeout():
    try:
        return int(ADDON.getSetting("health_check_timeout") or "5")
    except Exception:
        return 5


def get_player_proxy():
    try:
        if ADDON.getSetting("proxy_player_enabled") != "true":
            return None
        host = ADDON.getSetting("proxy_host") or "127.0.0.1"
        port = ADDON.getSetting("proxy_port") or "8080"
        tipo = ADDON.getSetting("proxy_type") or "http"
        return f"{tipo}://{host}:{port}"
    except Exception as e:
        log(f"Error leyendo config proxy: {e}")
        return None


def tiene_inputstream_adaptive():
    try:
        xbmcaddon.Addon("inputstream.adaptive")
        return True
    except Exception:
        return False
