# -*- coding: utf-8 -*-
import base64
import re
import time
from urllib.parse import urlparse, urlunparse

import requests

from .kodi_utils import log, get_timeout, log_debug
from .http_utils import nueva_session

# Host real ofuscado en base64 (scraping: NO tocar)
BASE64_BASE_URL = "aHR0cHM6Ly9qa2FuaW1lLm5ldA=="
BASE_URL = base64.b64decode(BASE64_BASE_URL).decode()

DOMINIOS_NORMALIZAR = {
    "sfastwish.com": "streamwish.top",
    "sfastwish.to": "streamwish.top",
    "sfastwish.net": "streamwish.top",
    "streamwish.com": "streamwish.top",
    "streamwish.to": "streamwish.top",
    "streamwish.net": "streamwish.top",
}

_CACHE_SERVIDORES = {}
CACHE_TTL = 300  # 5 min


class RamenPlayAPI:
    def __init__(self):
        self.session = nueva_session()
        self.base_url = BASE_URL  # host real (scraping)
        self.csrf_token = None
        self.timeout = get_timeout()
        log("[RamenPlay][API] v1.8.0")

    def _obtener_csrf(self):
        r = self.session.get(self.base_url, timeout=self.timeout)
        r.raise_for_status()
        m = re.search(r'name="csrf-token" content="([^"]+)"', r.text)
        if not m:
            raise RuntimeError("RamenPlay: no CSRF")
        self.csrf_token = m.group(1)
        return self.csrf_token

    def _asegurar_token(self):
        if not self.csrf_token:
            self._obtener_csrf()

    def _post_con_reintento(self, url, data, extra_headers):
        for intento in (1, 2):
            self._asegurar_token()
            data["_token"] = self.csrf_token
            try:
                r = self.session.post(
                    url, data=data, headers=extra_headers,
                    timeout=self.timeout,
                )
                if r.status_code == 419 and intento == 1:
                    self.csrf_token = None
                    continue
                r.raise_for_status()
                return r
            except requests.HTTPError:
                if intento == 2:
                    raise
                self.csrf_token = None

    def buscar(self, termino):
        r = self._post_con_reintento(
            f"{self.base_url}/ajax_search",
            {"q": termino},
            {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/buscar/{termino.replace(' ', '+')}",
                "Origin": self.base_url,
            },
        )
        try:
            data = r.json()
        except ValueError:
            return []
        if not isinstance(data, list):
            return []

        # Miniaturas: el CDN sirve la version nitida en /image/ en lugar
        # de /thumbnail/. Reescribimos antes de devolver.
        for anime in data:
            if isinstance(anime, dict):
                thumb = anime.get("thumbnail")
                if thumb and "/assets/images/animes/thumbnail/" in thumb:
                    anime["thumbnail"] = thumb.replace(
                        "/assets/images/animes/thumbnail/",
                        "/assets/images/animes/image/",
                        1,
                    )
        return data

    def total_capitulos(self, anime_id, chapter_num=1):
        r = self._post_con_reintento(
            f"{self.base_url}/ajax/episodes/{anime_id}/{chapter_num}",
            {},
            {"X-Requested-With": "XMLHttpRequest", "Origin": self.base_url},
        )
        try:
            return max(0, int(r.json().get("total") or 0))
        except (ValueError, TypeError, AttributeError):
            return 0

    @staticmethod
    def _normalizar_url(url):
        if not url:
            return url
        p = urlparse(url)
        host = (p.netloc or "").lower()
        for viejo, nuevo in DOMINIOS_NORMALIZAR.items():
            if host == viejo or host.endswith("." + viejo):
                p = p._replace(netloc=nuevo)
                break
        url = urlunparse(p)
        if "streamtape.com" in url or "strtape." in url:
            m = re.match(r"(https?://[^/]+/e/[^/]+)", url)
            if m:
                url = m.group(1)
        return url

    def servidores(self, slug, capitulo):
        key = (slug, capitulo)
        if key in _CACHE_SERVIDORES:
            data, ts = _CACHE_SERVIDORES[key]
            if time.time() - ts < CACHE_TTL:
                log_debug(f"[API] Cache HIT {key}")
                return data

        # Path real del sitio scrapeado (NO tocar)
        url = f"{self.base_url}/{slug}/{capitulo}/"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        html = r.text

        servidores = []
        plantillas_ignoradas = 0

        # Patron de scraping: iframes del player (jkplayer) — NO tocar el literal
        for s in re.findall(
            r'<iframe[^>]*src="([^"]*(?:jkplayer)[^"]*)"', html
        ):
            if "'+" in s or "val." in s or "location." in s or "${" in s:
                plantillas_ignoradas += 1
                continue
            if s.startswith("/"):
                s = self.base_url + s
            servidores.append(s)

        for raw in re.findall(r'"remote":"([^"]+)"', html):
            try:
                dec = base64.b64decode(raw).decode("utf-8", "ignore").strip()
                if not dec or not dec.startswith("http"):
                    continue
                if "'+" in dec or "val." in dec:
                    plantillas_ignoradas += 1
                    continue
                servidores.append(dec)
            except Exception:
                continue

        vistos = set()
        unicos = []
        for s in servidores:
            s_norm = self._normalizar_url(s)
            if s_norm not in vistos:
                vistos.add(s_norm)
                unicos.append(s_norm)

        log(f"[API] Plantillas JS ignoradas: {plantillas_ignoradas}")
        log(f"[API] Servidores únicos: {len(unicos)}")
        for i, s in enumerate(unicos):
            log_debug(f"[API]   [{i}] {s[:120]}")

        data = (unicos, html)
        _CACHE_SERVIDORES[key] = (data, time.time())
        return data
