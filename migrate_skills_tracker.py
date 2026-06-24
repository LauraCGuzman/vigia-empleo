"""
🔄 Migración one-shot de skills_tracker.json

Re-canonicaliza todas las claves del histórico contra las habilidades
definidas en habilidades.yaml. Skills que canonicalizan al mismo nombre
se suman. Skills no reconocidos se preservan con su grafía original.

Uso:
    python migrate_skills_tracker.py <input.json> <output.json>

Genera además un informe en stdout con:
  - Skills que se han colapsado (origen → destino)
  - Skills sin match (candidatos a añadir a habilidades.yaml o descartar)
  - Conteos antes/después
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Importar la lógica de canonicalización del propio job_alert
sys.path.insert(0, str(Path(__file__).parent))
from job_alert import _canonical_name, CONFIG


def migrar_dict_skills(skills: dict) -> tuple[dict, list[tuple[str, str, int]], list[tuple[str, int]]]:
    """Canonicaliza un dict {skill: count} y devuelve:
    - dict canonicalizado con counts sumados
    - lista de colapsos (skill_original, canonical, count)
    - lista de no-matched (skill, count)
    """
    nuevo: dict[str, int] = {}
    colapsos = []
    sin_match = []

    for skill, count in skills.items():
        canonical = _canonical_name(skill)

        # ¿Es match contra habilidades.yaml o es passthrough?
        es_match = canonical in CONFIG["skills"]

        if es_match and canonical != skill:
            colapsos.append((skill, canonical, count))
        elif not es_match:
            sin_match.append((skill, count))

        nuevo[canonical] = nuevo.get(canonical, 0) + count

    return nuevo, colapsos, sin_match


def main():
    if len(sys.argv) != 3:
        print("Uso: python migrate_skills_tracker.py <input.json> <output.json>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"❌ No existe: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        tracker = json.load(f)

    print("=" * 70)
    print(f"🔄 MIGRACIÓN DE SKILLS TRACKER")
    print(f"   Input:  {input_path}")
    print(f"   Output: {output_path}")
    print("=" * 70)

    # ── Migrar cada semana ──
    print(f"\n📅 Procesando {len(tracker.get('semanas', []))} semana(s)...")
    todos_colapsos = []
    todos_sin_match = set()

    for semana in tracker.get("semanas", []):
        nuevos_skills, colapsos, sin_match = migrar_dict_skills(semana["skills"])
        semana["skills"] = nuevos_skills
        todos_colapsos.extend([(*c, semana["fecha"]) for c in colapsos])
        for skill, count in sin_match:
            todos_sin_match.add(skill)

    # ── Migrar acumulado ──
    print(f"📦 Recalculando acumulado total...")
    nuevo_acumulado, _, _ = migrar_dict_skills(tracker.get("acumulado", {}))
    n_antes = len(tracker.get("acumulado", {}))
    n_despues = len(nuevo_acumulado)
    tracker["acumulado"] = nuevo_acumulado

    # ── Metadata de migración ──
    tracker["_migration"] = {
        "migrated_at": datetime.now().isoformat(timespec="seconds"),
        "tool": "migrate_skills_tracker.py",
        "skills_count_before": n_antes,
        "skills_count_after": n_despues,
        "reduction": n_antes - n_despues,
        "note": "Canonicalización contra habilidades.yaml. Aliases ES/EN y variantes de capitalización colapsadas a la clave canónica."
    }

    # ── Guardar ──
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)

    # ── Informe ──
    print(f"\n{'─' * 70}")
    print(f"📊 RESUMEN")
    print(f"{'─' * 70}")
    print(f"  Skills únicos antes:    {n_antes}")
    print(f"  Skills únicos después:  {n_despues}")
    print(f"  Reducción:              {n_antes - n_despues} ({100*(n_antes-n_despues)//n_antes if n_antes else 0}%)")
    print(f"  Colapsos totales:       {len(todos_colapsos)}")
    print(f"  Sin match (preservados): {len(todos_sin_match)}")

    if todos_colapsos:
        print(f"\n{'─' * 70}")
        print(f"✅ COLAPSOS (origen → canónico)")
        print(f"{'─' * 70}")
        por_canonical = {}
        for orig, canonical, count, fecha in todos_colapsos:
            por_canonical.setdefault(canonical, []).append((orig, count, fecha))
        for canonical in sorted(por_canonical):
            origenes = por_canonical[canonical]
            total_count = sum(c for _, c, _ in origenes)
            origenes_str = ", ".join(sorted(set(o for o, _, _ in origenes)))
            print(f"  → {canonical} ({total_count} apariciones desde: {origenes_str})")

    if todos_sin_match:
        print(f"\n{'─' * 70}")
        print(f"⚠️  SIN MATCH (preservados con grafía original)")
        print(f"{'─' * 70}")
        print(f"  Estos skills no están en habilidades.yaml. Posibles acciones:")
        print(f"  - Añadir a habilidades.yaml si son relevantes para ti")
        print(f"  - Dejar como están si son ruido sectorial")
        for skill in sorted(todos_sin_match):
            count = tracker["acumulado"].get(skill, 0)
            print(f"  · {skill!r} (acumulado: {count})")

    print(f"\n✅ Archivo migrado: {output_path}")


if __name__ == "__main__":
    main()
