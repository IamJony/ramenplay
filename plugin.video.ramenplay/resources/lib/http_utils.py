# -*- coding: utf-8 -*-
"""Utilidades HTTP compartidas: headers, sesiones, referers."""
import threading
from urllib.parse import urlparse

import requests

UA = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) "
    "Gecko/20100101 Firefox/146.0"
)

BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "DNT": "1",
}

_tls = threading.local()


def nueva_session():
    """Crea una Session limpia sin proxies del entorno."""
    s = requests.Session()
    s.trust_env = False
    s.proxies = {}
    s.headers.update(BASE_HEADERS)
    return s


def session_tls():
    """Session thread-local para health check (reutiliza conexiones)."""
    if not hasattr(_tls, "s") or _tls.s is None:
        _tls.s = nueva_session()
    return _tls.s


def referer_de_url(url):
    if not url or "://" not in url:
        return "https://www.google.com/"
    # Condicion de scraping: si es el player interno, usar el host raiz como referer
    if "jkanime.net/jkplayer" in url:
        return "https://jkanime.net/"
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}/"
    except Exception:
        pass
    return "https://www.google.com/"


def headers_para(url):
    h = dict(BASE_HEADERS)
    ref = referer_de_url(url)
    h["Referer"] = ref
    h["Origin"] = ref.rstrip("/")
    return h


def urlparse_seguro(url):
    try:
        return urlparse(url)
    except Exception:
        return None
