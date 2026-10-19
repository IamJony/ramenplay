# -*- coding: utf-8 -*-
import re
import requests

from .kodi_utils import log, get_timeout, log_debug
from .ramenplayer import RamenPlayerExtractor, es_ramenplayer
from .http_utils import nueva_session, referer_de_url, UA

DOMINIOS_IGNORAR = (
    "mediafire.com", "mega.nz", "mega.co.nz",
    "1fichier.com", "drive.google.com",
)

DOMINIOS_STREAMWISH = (
    "streamwish.top", "streamwish.com",
    "streamwish.to", "sfastwish.com",
)

_STREAMVID_CACHE = None


def _get_streamvid_extractors():
    global _STREAMVID_CACHE
    if _STREAMVID_CACHE is not None:
        return _STREAMVID_CACHE
    try:
        from streamvid import EXTRACTORS
        _STREAMVID_CACHE = list(EXTRACTORS)
        log(f"[RamenPlay] streamvid: {len(_STREAMVID_CACHE)} extractores")
        return _STREAMVID_CACHE
    except Exception as e:
        log(f"[RamenPlay] streamvid NO disponible: {e}")
        _STREAMVID_CACHE = []
        return []


def _es_descarga(url):
    return any(d in url for d in DOMINIOS_IGNORAR)


def _es_streamwish(url):
    return any(d in url for d in DOMINIOS_STREAMWISH)


def _intento_streamwish(url):
    try:
        timeout = get_timeout()
        log(f"[RamenPlay] StreamWish directo: {url[:100]}")

        session = nueva_session()
        session.headers.update({
            "Referer": referer_de_url(url),
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        })

        r = session.get(url, timeout=timeout)
        r.raise_for_status()
        html = r.text
        headers = {"User-Agent": UA, "Referer": r.url}

        m = re.search(r'(https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*)', html)
        if m:
            return m.group(1), headers

        m = re.search(r'"hls"\s*:\s*"([^"]+)"', html)
        if m:
            link = m.group(1).replace("\\/", "/")
            if ".m3u8" in link:
                return link, headers

        for patron in [r'"file"\s*:\s*"([^"]+)"', r'"source"\s*:\s*"([^"]+)"']:
            m = re.search(patron, html)
            if m:
                link = m.group(1).replace("\\/", "/")
                if ".m3u8" in link or ".mp4" in link:
                    return link, headers

        return None, None
    except Exception as e:
        log(f"[RamenPlay] StreamWish fallo: {e}")
        return None, None


def clasificar_servidores(servers):
    out = {"ramenplayer": [], "externos": [], "ignorados": []}
    for s in servers:
        if _es_descarga(s):
            out["ignorados"].append(s)
        elif es_ramenplayer(s):
            out["ramenplayer"].append(s)
        else:
            out["externos"].append(s)
    return out


def extraer_hls(url, debug=False, session_http=None):
    """Extrae el link HLS.

    `session_http` permite pasar la Session de la API para reutilizar
    cookies (necesario en el player interno).
    """
    if _es_streamwish(url):
        link, headers = _intento_streamwish(url)
        if link:
            return link, headers
        log("[RamenPlay] StreamWish fallo, probando streamvid...")

    # Intentar RamenPlayer primero con la sesión que trae cookies
    if es_ramenplayer(url):
        try:
            ext = RamenPlayerExtractor(session=session_http, debug=debug)
            link = ext.extraer(url)
            if link:
                return link, ext.obtener_headers()
        except Exception as e:
            log(f"[RamenPlay] RamenPlayer fallo: {e}")

    extractores = _get_streamvid_extractors()
    for cls in extractores:
        try:
            ext = cls(debug=debug)
            if not ext.soporta(url):
                continue
            log(f"[RamenPlay] {cls.__name__} -> {url[:80]}")
            if hasattr(ext, "session"):
                ext.session.trust_env = False
                ext.session.proxies = {}
            link = ext.extraer(url)
            headers = ext.obtener_headers() if hasattr(ext, "obtener_headers") else None
            if link:
                return link, headers
        except Exception as e:
            log(f"[RamenPlay] FALLO {cls.__name__}: {e}")
            continue

    return None, None


def extraer_de_lista(servidores, debug=False, session_http=None):
    clasif = clasificar_servidores(servidores)
    log(f"[RamenPlay] Servidores: "
        f"{len(clasif['ramenplayer'])} rp, "
        f"{len(clasif['externos'])} ext, "
        f"{len(clasif['ignorados'])} ign")

    for srv in clasif["ramenplayer"]:
        link, headers = extraer_hls(srv, debug=debug, session_http=session_http)
        if link:
            return link, headers, srv

    for srv in clasif["externos"]:
        link, headers = extraer_hls(srv, debug=debug, session_http=session_http)
        if link:
            return link, headers, srv

    return None, None, None
