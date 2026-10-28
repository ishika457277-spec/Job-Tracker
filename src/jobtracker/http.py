from __future__ import annotations

import time

import requests

UA = "job-tracker/1.0 (personal job search script)"


def fetch(
    url: str,
    *,
    params=None,
    headers=None,
    method: str = "GET",
    json=None,
    retries: int = 2,
    timeout: int = 25,
) -> requests.Response:
    """GET/POST with small retry. Retries 429/5xx and network errors, not other 4xx."""
    hdrs = {"User-Agent": UA, "Accept": "application/json, text/xml, text/html;q=0.9, */*;q=0.5"}
    hdrs.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(
                method, url, params=params, headers=hdrs, json=json, timeout=timeout
            )
        except requests.RequestException as exc:
            last = exc
        else:
            if r.status_code == 429 or r.status_code >= 500:
                last = RuntimeError(f"HTTP {r.status_code} from {url}")
            elif r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code} from {url}")
            else:
                return r
        time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]
