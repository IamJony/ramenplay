# -*- coding: utf-8 -*-
import os
import sys
from urllib.parse import urlparse, quote

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(_HERE, "resources", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import urllib.parse
import xbmc
import xbmcgui
import xbmcplugin

from resources.lib.api import RamenPlayAPI
from resources.lib.extractor import (
    extraer_de_lista, extraer_hls, clasificar_servidores
)
from resources.lib.health_check import filtrar_vivos
from resources.lib.ramenplayer import es_ramenplayer
from resources.lib.kodi_utils import (
    log, log_debug, notificar, pedir_texto, get_player_proxy,
    get_health_check, tiene_inputstream_adaptive
)

ADDON_HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]
PARAMS = {
    k: v[0]
    for k, v in urllib.parse.parse_qs(
        sys.argv[2][1:] if len(sys.argv) > 2 else "",
        keep_blank_values=False,
    ).items()
}
API = RamenPlayAPI()


def build_url(**kwargs):
    return BASE_URL + "?" + urllib.parse.urlencode(kwargs)


def add_dir(label, params, is_folder=True, icon="DefaultFolder.png"):
    li = xbmcgui.ListItem(label=label)
    li.setArt({"icon": icon, "thumb": icon})
    xbmcplugin.addDirectoryItem(
        handle=ADDON_HANDLE,
        url=build_url(**params),
        listitem=li,
        isFolder=is_folder,
    )


def _url_con_headers_kodi(url, headers):
    """Añade |Header=value a la URL para VideoPlayer nativo.

    Kodi NO decodifica los valores, por lo que NO hay que quotear el nombre
    ni el valor (solo evitamos caracteres problemáticos | & =).
    """
    if not headers:
        return url
    pares = []
    for k, v in headers.items():
        if not v:
            continue
        # Solo escapamos caracteres reservados por Kodi (| & =)
        v_seg = str(v).replace("|", "%7C").replace("&", "%26").replace("=", "%3D")
        pares.append(f"{k}={v_seg}")
    return url + "|" + "&".join(pares)


def _nombre_servidor(url):
    # Fragmentos REALES de URL para etiquetar (NO tocar)
    if "jkplayer/um?" in url or "jkplayer/um/" in url:
        return "RamenPlayer #1"
    if "jkplayer/umv?" in url or "jkplayer/umv/" in url:
        return "RamenPlayer #2"
    try:
        p = urlparse(url)
        return (p.netloc or url[:40]).replace("www.", "")
    except Exception:
        return url[:40]


def _sufijo_estado(estado, ms):
    if estado == "vivo":
        return f" LIVE {ms}ms" if ms else " LIVE"
    if estado == "sospechoso":
        return f" WARNING {ms}ms" if ms else " WARNING"
    if estado == "skip":
        return " (no verificado)"
    return ""


def vista_menu():
    add_dir("Buscar anime", {"action": "buscar"},
            icon="DefaultAddonsSearch.png")
    add_dir("Reproducir URL HLS directa", {"action": "url_directa"},
            is_folder=False, icon="DefaultVideo.png")
    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def vista_buscar():
    termino = pedir_texto("Buscar anime en RamenPlay")
    if not termino:
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    try:
        resultados = API.buscar(termino)
    except Exception as e:
        log(f"Error busqueda: {e}")
        notificar(f"Error: {e}", icono=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    if not resultados:
        notificar("Sin resultados")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    for anime in resultados:
        thumb = anime.get("thumbnail") or "DefaultTVShows.png"
        li = xbmcgui.ListItem(label=anime.get("title", "?"))
        li.setArt({"thumb": thumb, "icon": thumb, "poster": thumb})
        li.setInfo("video", {
            "title": anime.get("title"),
            "plot": f"{anime.get('type', '')} - {anime.get('status', '')}",
        })
        xbmcplugin.addDirectoryItem(
            handle=ADDON_HANDLE,
            url=build_url(
                action="capitulos",
                id=anime.get("id"),
                slug=anime.get("slug"),
                titulo=anime.get("title"),
            ),
            listitem=li,
            isFolder=True,
        )

    xbmcplugin.setContent(ADDON_HANDLE, "tvshows")
    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def vista_capitulos(anime_id, slug, titulo):
    if not all([anime_id, slug, titulo]):
        notificar("Parámetros incompletos", icono=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    try:
        total = API.total_capitulos(anime_id)
    except Exception as e:
        log(f"Error capitulos: {e}")
        notificar(f"No se pudo obtener capitulos: {e}",
                  icono=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    if total <= 0:
        notificar("Sin capitulos")
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    for cap in range(1, total + 1):
        li = xbmcgui.ListItem(label=f"Capitulo {cap}")
        li.setInfo("video", {
            "title": f"{titulo} - Cap {cap}",
            "episode": cap,
            "tvshowtitle": titulo,
        })
        xbmcplugin.addDirectoryItem(
            handle=ADDON_HANDLE,
            url=build_url(
                action="ver_capitulo",
                slug=slug,
                titulo=titulo,
                cap=cap,
            ),
            listitem=li,
            isFolder=True,
        )

    xbmcplugin.setContent(ADDON_HANDLE, "episodes")
    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def vista_ver_capitulo(slug, titulo, cap):
    log(f"[RamenPlay] ver_capitulo: {slug} cap {cap}")

    if not slug or not titulo or cap is None:
        notificar("Parámetros incompletos", icono=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    try:
        servidores, _ = API.servidores(slug, cap)
    except Exception as e:
        log(f"[RamenPlay] Error servidores: {e}")
        notificar(f"Error: {e}", icono=xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    if not servidores:
        notificar("Sin servidores", icono=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    if get_health_check():
        log("[RamenPlay] Ejecutando health check...")
        resultados = filtrar_vivos(servidores)
    else:
        resultados = [
            {"url": u, "estado": "skip", "status": None, "ms": 0}
            for u in servidores
        ]

    info_map = {r["url"]: r for r in resultados}
    clasif = clasificar_servidores(servidores)

    orden_estado = {"vivo": 0, "sospechoso": 1, "skip": 2, "muerto": 3}

    def _mostrar(url):
        info = info_map.get(url, {})
        return info.get("estado") != "muerto"

    def _orden(url):
        info = info_map.get(url, {})
        return (orden_estado.get(info.get("estado", "muerto"), 9),
                info.get("ms", 0))

    rp_visibles = sorted(
        [u for u in clasif["ramenplayer"] if _mostrar(u)], key=_orden
    )
    ext_visibles = sorted(
        [u for u in clasif["externos"] if _mostrar(u)], key=_orden
    )

    total_mostrados = 0

    for u in rp_visibles + ext_visibles:
        info = info_map.get(u, {})
        label = _nombre_servidor(u) + _sufijo_estado(
            info.get("estado"), info.get("ms", 0)
        )
        li = xbmcgui.ListItem(label=label)
        li.setArt({"icon": "DefaultVideo.png"})
        xbmcplugin.addDirectoryItem(
            handle=ADDON_HANDLE,
            url=build_url(action="reproducir", url=u, titulo=titulo, cap=cap),
            listitem=li,
            isFolder=False,
        )
        total_mostrados += 1

    muertos_ocultos = sum(1 for r in resultados if r.get("estado") == "muerto")

    if total_mostrados == 0:
        notificar("Todos los servidores estan caidos",
                  icono=xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        return

    if muertos_ocultos > 0:
        log(f"[RamenPlay] Ocultados {muertos_ocultos} servidores muertos")

    xbmcplugin.setContent(ADDON_HANDLE, "videos")
    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def _detectar_formato(link):
    """Devuelve 'm3u8', 'mp4' u 'otro' según el path (ignora query)."""
    try:
        path = urlparse(link).path.lower()
    except Exception:
        path = link.lower()
    if path.endswith(".m3u8"):
        return "m3u8"
    if path.endswith(".mp4"):
        return "mp4"
    if ".m3u8" in path:
        return "m3u8"
    if ".mp4" in path:
        return "mp4"
    return "otro"


def vista_reproducir(url_servidor, titulo, cap):
    log(f"[RamenPlay] reproducir: {url_servidor[:100]}")

    es_rp = es_ramenplayer(url_servidor)
    log(f"[RamenPlay] es_ramenplayer={es_rp}")

    # Pasamos la sesión de la API para reutilizar cookies en el player
    link, headers = extraer_hls(
        url_servidor, debug=True, session_http=API.session
    )
    if not link:
        notificar("No se pudo extraer el enlace",
                  icono=xbmcgui.NOTIFICATION_ERROR)
        return

    log(f"[RamenPlay] link={link[:150]}")

    formato = _detectar_formato(link)
    li = xbmcgui.ListItem(path=link)
    li.setContentLookup(False)
    li.setInfo("video", {
        "title": f"{titulo} - Cap {cap}",
        "plot": f"{titulo}, capitulo {cap} - RamenPlay",
    })

    if formato == "mp4":
        url_headers = _url_con_headers_kodi(link, headers)
        li.setPath(url_headers)
        li.setMimeType("video/mp4")
        log("[RamenPlay] MP4 via VideoPlayer nativo")
        xbmc.Player().play(url_headers, li)
        return

    if formato == "m3u8" and tiene_inputstream_adaptive():
        li.setMimeType("application/vnd.apple.mpegurl")
        li.setProperty("inputstream", "inputstream.adaptive")
        li.setProperty("inputstream.adaptive.manifest_type", "hls")
        if headers:
            hs = "&".join(f"{k}={v}" for k, v in headers.items() if v)
            li.setProperty("inputstream.adaptive.stream_headers", hs)
            li.setProperty("inputstream.adaptive.manifest_headers", hs)
        if not es_rp:
            proxy_url = get_player_proxy()
            if proxy_url:
                li.setProperty("inputstream.adaptive.proxy", proxy_url)
                li.setProperty("inputstream.adaptive.proxy_type", "http")
        log("[RamenPlay] HLS via inputstream.adaptive")
        xbmc.Player().play(link, li)
        return

    # Fallback: m3u8 sin ISA o formato desconocido → VideoPlayer nativo
    url_headers = _url_con_headers_kodi(link, headers)
    li.setPath(url_headers)
    log(f"[RamenPlay] Formato {formato} via VideoPlayer nativo")
    xbmc.Player().play(url_headers, li)


def vista_url_directa():
    url = pedir_texto("URL HLS (.m3u8) - RamenPlay")
    if not url:
        return
    vista_reproducir(url, "URL directa", 0)


def _get_int(key, default=None):
    v = PARAMS.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def router():
    action = PARAMS.get("action", "")
    try:
        if action == "":
            vista_menu()
        elif action == "buscar":
            vista_buscar()
        elif action == "capitulos":
            vista_capitulos(
                PARAMS.get("id"),
                PARAMS.get("slug"),
                PARAMS.get("titulo"),
            )
        elif action == "ver_capitulo":
            vista_ver_capitulo(
                PARAMS.get("slug"),
                PARAMS.get("titulo"),
                _get_int("cap", 1),
            )
        elif action == "reproducir":
            vista_reproducir(
                PARAMS.get("url", ""),
                PARAMS.get("titulo", "?"),
                _get_int("cap", 0),
            )
        elif action == "url_directa":
            vista_url_directa()
        else:
            vista_menu()
    except Exception as e:
        log(f"[RamenPlay] Error en router: {e}")
        notificar(f"Error: {e}", icono=xbmcgui.NOTIFICATION_ERROR)
        try:
            xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False)
        except Exception:
            pass


if __name__ == "__main__":
    router()
