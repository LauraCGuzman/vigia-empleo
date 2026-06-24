"""
🌱 Climatebase scraper

Climatebase usa Algolia como motor de búsqueda. Replicamos su llamada interna
desde Python con `requests`. Sin navegador, sin Playwright, sin login.

Credenciales públicas (search-only, las expone el frontend de Climatebase
en cualquier request — no son secretas):
- App ID:  8PSNFFQTXQ
- API Key: d2ebe27d3cc3d35fea04da7b1b0718a8
- Index:   Job_production

Si Climatebase rota estas credenciales, basta con abrir DevTools en su web,
mirar una request a *.algolia.net y copiar los nuevos valores aquí.

Devuelve ofertas con el mismo schema que JobSpy para integrarse sin fricción
en buscar_ofertas() de job_alert.py.
"""

import time
import requests
from typing import Optional

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

ALGOLIA_APP_ID = "8PSNFFQTXQ"
ALGOLIA_API_KEY = "d2ebe27d3cc3d35fea04da7b1b0718a8"
ALGOLIA_INDEX = "Job_production"
ALGOLIA_URL = (
    f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net"
    f"/1/indexes/{ALGOLIA_INDEX}/query"
    f"?x-algolia-agent=Algolia%20for%20JavaScript%20(4.26.0)%3B%20Browser"
)

HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://climatebase.org",
    "Referer": "https://climatebase.org/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "x-algolia-api-key": ALGOLIA_API_KEY,
    "x-algolia-application-id": ALGOLIA_APP_ID,
}

# Atributos que pedimos a Algolia. Mismos que la UI de Climatebase + algunos
# extra que pueden ser útiles para el scoring.
ATTRIBUTES_TO_RETRIEVE = [
    "id", "source", "title", "name_of_employer", "employer_name",
    "locations", "job_types", "remote_preferences",
    "salary_from", "salary_to", "salary_period",
    "sectors", "employer_short_description",
    "employer_id", "activation_date",
    "description",  # crítico para el scoring de Claude
]


# ─────────────────────────────────────────────
# UTILIDADES INTERNAS
# ─────────────────────────────────────────────

def _format_locations(locations) -> str:
    """Climatebase devuelve locations como lista de strings o lista de dicts.
    Normaliza a string legible separado por ' / '."""
    if not locations:
        return "Remote / Not specified"
    if isinstance(locations, list):
        result = []
        for loc in locations:
            if isinstance(loc, dict):
                # Posibles campos: city, country, name, location
                parts = [loc.get(k) for k in ("city", "country", "name", "location")]
                parts = [p for p in parts if p]
                if parts:
                    result.append(", ".join(parts))
            elif isinstance(loc, str):
                result.append(loc)
        return " / ".join(result) if result else "Remote / Not specified"
    return str(locations)


def _is_remote(remote_preferences) -> bool:
    """Detecta si la oferta es remota a partir del campo remote_preferences."""
    if not remote_preferences:
        return False
    if isinstance(remote_preferences, list):
        joined = " ".join(str(x).lower() for x in remote_preferences)
    else:
        joined = str(remote_preferences).lower()
    return "remote" in joined or "hybrid" in joined


def _build_job_url(job_id, source: Optional[str] = None) -> str:
    """Construye la URL pública de la oferta. Climatebase usa /job/<id>."""
    if not job_id:
        return "https://climatebase.org/jobs"
    return f"https://climatebase.org/job/{job_id}"


import re as _re
import html as _html


def _strip_html(text: str) -> str:
    """Limpia HTML embebido y entidades. Climatebase devuelve descripciones con
    mucho <span style="..."> que es ruido puro para el scoring de Claude.
    """
    if not text:
        return ""
    # Eliminar tags HTML
    cleaned = _re.sub(r'<[^>]+>', ' ', text)
    # Decodificar entidades (&amp; → &, &nbsp; → espacio, etc.)
    cleaned = _html.unescape(cleaned)
    # Colapsar espacios múltiples y saltos de línea redundantes
    cleaned = _re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def _format_salary(salary_from, salary_to, period) -> str:
    """Formatea el rango salarial si está disponible.
    Acepta valores como int, float o str numérico (Algolia los devuelve de ambas formas)."""
    def _to_num(v):
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            return v
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    sf = _to_num(salary_from)
    st = _to_num(salary_to)
    # Tratar 0 como "no especificado" (algunas ofertas envían 0/0)
    if not sf:
        sf = None
    if not st:
        st = None
    if sf is None and st is None:
        return ""
    parts = []
    if sf is not None:
        parts.append(f"{int(sf):,}")
    if st is not None:
        parts.append(f"{int(st):,}")
    rango = "-".join(parts) if parts else ""
    p = f" {period}" if period else ""
    return f"{rango}{p}" if rango else ""


# ─────────────────────────────────────────────
# API PÚBLICA DEL MÓDULO
# ─────────────────────────────────────────────

def scrape_climatebase(
    query: str,
    max_results: int = 50,
    only_remote: bool = True,
    timeout: int = 15,
) -> list[dict]:
    """Busca ofertas en Climatebase vía API Algolia.

    Args:
        query: término de búsqueda en inglés (ej. 'data scientist', 'mlrv analyst')
        max_results: máximo de resultados a devolver (Algolia tope ~1000 por query)
        only_remote: si True, filtra post-hoc por ofertas con remote/hybrid
        timeout: timeout en segundos para la petición HTTP

    Returns:
        Lista de dicts con schema compatible con JobSpy:
            {title, company, url, description, location, source}
        Devuelve [] en caso de error (logueado por stdout).
    """
    payload = {
        "query": query,
        "page": 0,
        "hitsPerPage": min(max_results, 100),
        "filters": "",
        "facets": [],
        # Solo filtramos por ofertas activas y aprobadas. NO replicamos los
        # facetFilters de exclusión por empleador-id que mete la UI de
        # Climatebase (probablemente empresas que pagan por no aparecer en free).
        "facetFilters": [
            "active:true",
            "employer_has_approval:true",
        ],
        "attributesToHighlight": [],
        "attributesToRetrieve": ATTRIBUTES_TO_RETRIEVE,
        "analytics": False,
        "getRankingInfo": False,
        "responseFields": ["hits", "page", "nbPages", "nbHits"],
        "enablePersonalization": False,
        "enableABTest": False,
    }

    try:
        import json as _json
        response = requests.post(
            ALGOLIA_URL,
            headers=HEADERS,
            data=_json.dumps(payload),
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"    ⚠️  Climatebase: error de red ({e})")
        return []
    except ValueError as e:
        print(f"    ⚠️  Climatebase: respuesta no es JSON válido ({e})")
        return []

    hits = data.get("hits", [])
    ofertas = []

    for hit in hits:
        company = (
            hit.get("employer_name")
            or hit.get("name_of_employer")
            or "Unknown"
        )
        location = _format_locations(hit.get("locations"))
        salary_str = _format_salary(
            hit.get("salary_from"),
            hit.get("salary_to"),
            hit.get("salary_period"),
        )

        # Construir descripción combinando lo que tengamos (limpiando HTML)
        desc_parts = []
        if hit.get("description"):
            desc_parts.append(_strip_html(hit["description"]))
        if hit.get("employer_short_description"):
            desc_parts.append(f"\n\nAbout the company: {_strip_html(hit['employer_short_description'])}")
        if salary_str:
            desc_parts.append(f"\n\nSalary: {salary_str}")
        if hit.get("remote_preferences"):
            rp = hit["remote_preferences"]
            rp_str = ", ".join(rp) if isinstance(rp, list) else str(rp)
            desc_parts.append(f"\nRemote: {rp_str}")
        description = "".join(desc_parts)[:2000].strip()

        # Filtrado opcional por remoto
        if only_remote and not _is_remote(hit.get("remote_preferences")):
            continue

        ofertas.append({
            "title":       (hit.get("title") or "").strip(),
            "company":     str(company).strip(),
            "url":         _build_job_url(hit.get("id"), hit.get("source")),
            "description": description,
            "location":    location,
            "source":      "climatebase",
        })

    return ofertas


# ─────────────────────────────────────────────
# CLI para testing manual
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys

    test_query = sys.argv[1] if len(sys.argv) > 1 else "data scientist"
    print(f"🌱 Climatebase scraper test — query: {test_query!r}")
    results = scrape_climatebase(test_query, max_results=20, only_remote=True)
    print(f"   {len(results)} ofertas remotas encontradas")
    print()
    for i, job in enumerate(results[:5], 1):
        print(f"[{i}] {job['title']}")
        print(f"    🏢 {job['company']}")
        print(f"    📍 {job['location']}")
        print(f"    🔗 {job['url']}")
        print(f"    📝 {job['description'][:200]}...")
        print()