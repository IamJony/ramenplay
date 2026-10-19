# -*- coding: utf-8 -*-
"""RamenPlayer by IamJony"""
import base64
import re

from .kodi_utils import log, get_timeout, log_debug
from .http_utils import nueva_session, UA


PATRONES_RAMENPLAYER = (
    "jkanime.net/jkplayer/um?",
    "jkanime.net/jkplayer/umv?",
    "jkanime.net/jkplayer/um/",
    "jkanime.net/jkplayer/umv/",
)


def es_ramenplayer(url):
    return any(p in url for p in PATRONES_RAMENPLAYER)


class RamenPlayerExtractor:
    def __init__(self, session=None, debug=False):
        self.session = session or nueva_session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.5",
        })
        self.session.trust_env = False
        self.session.proxies = {}
        self.debug = debug
        self._headers = None
        self.timeout = get_timeout()

    def soporta(self, url):
        return es_ramenplayer(url)

    def extraer(self, url):
        if self.debug:
            log(f"[RamenPlayer] GET {url[:100]}")

        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        html = r.text

        self._headers = {
            "User-Agent": self.session.headers.get("User-Agent"),
            "Referer": r.url,
        }

        m3u8 = self._extraer_m3u8(html)
        if not m3u8:
            raise RuntimeError("RamenPlayer: no se encontro M3U8")

        if self.debug:
            log(f"[RamenPlayer] OK {m3u8[:100]}")
        return m3u8

    def obtener_headers(self):
        return self._headers

    def _extraer_m3u8(self, html):
        m = re.search(r"atob\(['\"]([A-Za-z0-9+/=]+)['\"]\)", html)
        if m:
            try:
                dec = base64.b64decode(m.group(1)).decode("utf-8", "ignore")
                u = self._find_m3u8(dec)
                if u:
                    return u
            except Exception as e:
                log_debug(f"[RamenPlayer] atob fallo: {e}")

        for patron in [
            r"loadSource\(\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]",
            r"url:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]",
            r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'"hls"\s*:\s*"([^"]+)"',
        ]:
            m = re.search(patron, html)
            if m:
                link = m.group(1).replace("\\/", "/")
                if ".m3u8" in link or ".mp4" in link:
                    return link

        return self._find_m3u8(html)

    @staticmethod
    def _find_m3u8(text):
        m = re.search(
            r"https?://[^\s'\"<>]+\.m3u8[^\s'\"<>]*",
            text, re.IGNORECASE,
        )
        return m.group(0) if m else None


RamenPlayPlayerExtractor = RamenPlayerExtractor
