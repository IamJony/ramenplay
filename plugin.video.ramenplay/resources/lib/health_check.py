# -*- coding: utf-8 -*-
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from .kodi_utils import log, get_health_check_timeout
from .http_utils import headers_para, session_tls

SKIP_CHECK = (
    "mediafire.com", "mega.nz", "mega.co.nz",
    "1fichier.com", "drive.google.com",
)

STATUS_SOSPECHOSOS_VIVO = (401, 403, 429, 503)

SOFT_BLOCK_SIGNATURES = (
    "please turn off adblock",
    "turn off your adblock",
    "cloudflare",
    "just a moment",
    "checking your browser",
    "captcha",
    "ddos protection",
    "attention required",
)


def _es_soft_block(texto):
    if not texto:
        return False
    bajo = texto[:4000].lower()
    return any(sig in bajo for sig in SOFT_BLOCK_SIGNATURES)


def _check_uno(url, timeout):
    t0 = time.time()
    headers = headers_para(url)
    # Solo pedimos los primeros 2 KB para detectar soft-block rápido
    headers["Range"] = "bytes=0-2047"

    try:
        session = session_tls()
        r = session.get(
            url, timeout=timeout, allow_redirects=True, stream=True,
            headers=headers,
        )
        status = r.status_code

        body_sample = b""
        ctype = r.headers.get("Content-Type", "").lower()

        if "text/html" in ctype:
            try:
                for chunk in r.iter_content(chunk_size=1024):
                    body_sample += chunk
                    if len(body_sample) >= 2048:
                        break
            except Exception:
                pass
        r.close()

        ms = int((time.time() - t0) * 1000)

        if 200 <= status < 300:
            texto = body_sample.decode("utf-8", "ignore")
            if _es_soft_block(texto):
                return url, "sospechoso", status, ms
            return url, "vivo", status, ms

        if 300 <= status < 400:
            return url, "vivo", status, ms

        if status in STATUS_SOSPECHOSOS_VIVO:
            return url, "sospechoso", status, ms

        if status in (404, 410):
            return url, "muerto", status, ms

        return url, "sospechoso", status, ms

    except requests.Timeout:
        return url, "muerto", None, int((time.time() - t0) * 1000)
    except requests.ConnectionError:
        return url, "muerto", None, int((time.time() - t0) * 1000)
    except Exception as e:
        log(f"[HealthCheck] {url[:60]}... ERROR {type(e).__name__}")
        return url, "muerto", None, int((time.time() - t0) * 1000)


def filtrar_vivos(servidores, max_workers=6):
    if not servidores:
        return []

    timeout = get_health_check_timeout()
    log(f"[HealthCheck] Verificando {len(servidores)} servidores (timeout={timeout}s)")

    resultados = []
    pendientes = []

    for url in servidores:
        if any(s in url for s in SKIP_CHECK):
            resultados.append({
                "url": url, "estado": "skip", "status": "skip", "ms": 0,
            })
        else:
            pendientes.append(url)

    if pendientes:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_check_uno, u, timeout): u for u in pendientes}
            for fut in as_completed(futures):
                try:
                    url, estado, status, ms = fut.result()
                    resultados.append({
                        "url": url, "estado": estado, "status": status, "ms": ms,
                    })
                except Exception as e:
                    log(f"[HealthCheck] futuro falló: {e}")

    orden = {"vivo": 0, "sospechoso": 1, "skip": 2, "muerto": 3}
    resultados.sort(key=lambda r: (orden.get(r["estado"], 9), r["ms"]))

    conteo = {}
    for r in resultados:
        conteo[r["estado"]] = conteo.get(r["estado"], 0) + 1
    log(f"[HealthCheck] Resultado: {conteo}")

    return resultados
