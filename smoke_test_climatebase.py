"""
🧪 Smoke-test del scraper de Climatebase

Ejecutar localmente para verificar que el scraper funciona correctamente.
Nota: requiere acceso a algolia.net (no funciona en entornos con proxy restrictivo).

Uso:
    cd <directorio_vigia>
    python smoke_test_climatebase.py

Output esperado: imprime las primeras ofertas reales para verificar parsing.
Si algo falla, imprime la respuesta cruda de Algolia para diagnóstico.
"""

import json
import sys
from pathlib import Path

# Permitir importar scrapers/climatebase.py desde este directorio
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.climatebase import scrape_climatebase, ALGOLIA_URL, HEADERS, ATTRIBUTES_TO_RETRIEVE
import requests


def raw_test():
    """Llamada raw a Algolia, sin parsing, para ver el JSON crudo de respuesta."""
    print("=" * 70)
    print("📡 TEST 1 — Respuesta cruda de Algolia")
    print("=" * 70)
    payload = {
        "query": "data scientist",
        "page": 0,
        "hitsPerPage": 3,
        "facetFilters": ["active:true", "employer_has_approval:true"],
        "attributesToRetrieve": ATTRIBUTES_TO_RETRIEVE,
        "responseFields": ["hits", "page", "nbPages", "nbHits"],
    }
    try:
        r = requests.post(ALGOLIA_URL, headers=HEADERS, data=json.dumps(payload), timeout=15)
        print(f"HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"❌ Body de error:\n{r.text[:1000]}")
            return False
        data = r.json()
        print(f"✅ Total ofertas en índice: {data.get('nbHits', 'N/A')}")
        print(f"✅ Páginas totales: {data.get('nbPages', 'N/A')}")
        print(f"✅ Hits en esta página: {len(data.get('hits', []))}")
        print()
        print("Primer hit (JSON crudo):")
        print(json.dumps(data["hits"][0] if data.get("hits") else {}, indent=2, ensure_ascii=False)[:2000])
        return True
    except Exception as e:
        print(f"❌ Excepción: {type(e).__name__}: {e}")
        return False


def parsed_test():
    """Test con el parser de nuestro módulo."""
    print()
    print("=" * 70)
    print("📋 TEST 2 — Output parseado por scrape_climatebase()")
    print("=" * 70)

    queries_test = [
        "data scientist",
        "climate data",
        "MRV analyst",
        "carbon analyst",
    ]

    for q in queries_test:
        results = scrape_climatebase(q, max_results=20, only_remote=True)
        print(f"\n🔍 Query: {q!r} → {len(results)} ofertas remotas")
        for job in results[:2]:
            print(f"   • {job['title']}")
            print(f"     🏢 {job['company']}  📍 {job['location']}")
            print(f"     🔗 {job['url']}")
            desc_preview = job['description'][:150].replace('\n', ' ')
            print(f"     📝 {desc_preview}...")


if __name__ == "__main__":
    print("🌱 SMOKE TEST — Climatebase scraper")
    print(f"   Endpoint: {ALGOLIA_URL[:80]}...")
    print()
    ok = raw_test()
    if ok:
        parsed_test()
    else:
        print("\n⚠️  Saltando tests parseados — el raw test falló.")
        print("   Si el código es 403, las credenciales pueden haber rotado.")
        print("   Re-abre DevTools en climatebase.org y verifica x-algolia-api-key.")
