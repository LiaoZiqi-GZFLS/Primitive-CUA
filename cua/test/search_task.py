import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

"""Test script: search across all vector indices for a given task.

Usage:
    python cua/test/search_task.py "your task description"
    python cua/test/search_task.py "打开微信" --top 5

Shows matching results from:
  - .cua scripts      (script index with embedding similarity)
  - Skills             (ChromaDB cua_skills_v2)
  - Knowledge base     (ChromaDB cua_knowledge_v2)
"""

import os

# Ensure project root is on path
_proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)


def _embed_task(task: str):
    """Embed a task description with the multilingual model."""
    import numpy as np
    from cua.recorder import _embed_text
    return _embed_text(task[:200])


def _search_scripts(task_vec, top_n: int = 5) -> list[tuple[str, float]]:
    """Search .cua script index by embedding similarity."""
    import numpy as np
    from cua.cli import _get_script_index, _calc_sim

    idx = _get_script_index()
    if not idx:
        return []

    scored = sorted(
        ((_calc_sim(task_vec, entry["vec"]), name) for name, entry in idx.items()),
        key=lambda x: -x[0],
    )
    return [(name, sim) for sim, name in scored[:top_n] if sim > 0.10]


def _search_skills(task: str, top_n: int = 5) -> list[tuple[str, float, str]]:
    """Search ChromaDB skills collection."""
    try:
        from cua.learning import _get_skills_collection
        col = _get_skills_collection()
        if col.count() == 0:
            return []
        results = col.query(query_texts=[task], n_results=top_n)
        if not results["ids"] or not results["ids"][0]:
            return []
        out = []
        for sid, dist, doc in zip(
            results["ids"][0], results["distances"][0],
            results.get("documents", [[]])[0]
        ):
            sim = 1.0 - dist  # cosine distance -> similarity
            if sim < 0.15:
                continue
            out.append((sid, sim, doc[:200] if doc else ""))
        return out
    except Exception as e:
        return [("(error)", 0.0, str(e))]


def _search_knowledge(task: str, top_n: int = 5) -> list[tuple[str, float, str]]:
    """Search ChromaDB knowledge base."""
    try:
        from cua.learning import _get_knowledge_collection
        col = _get_knowledge_collection()
        if col.count() == 0:
            return []
        results = col.query(query_texts=[task], n_results=top_n)
        if not results["ids"] or not results["ids"][0]:
            return []
        out = []
        for sid, dist, doc in zip(
            results["ids"][0], results["distances"][0],
            results.get("documents", [[]])[0]
        ):
            sim = 1.0 - dist
            if sim < 0.15:
                continue
            out.append((sid, sim, doc[:200] if doc else ""))
        return out
    except Exception as e:
        return [("(error)", 0.0, str(e))]


def _search_elements(task_vec, top_n: int = 5) -> list[tuple[str, float]]:
    """Search element library by embedding similarity."""
    import numpy as np
    from cua.recorder import list_templates, _embed_text

    tmpls = list_templates()
    if not tmpls:
        return []

    results = []
    for t in tmpls:
        ocr = t.get("ocr_text", "")
        if not ocr:
            continue
        ev = _embed_text(ocr[:200])
        s = float(np.dot(task_vec, ev) /
                  (np.linalg.norm(task_vec) * np.linalg.norm(ev) + 1e-8))
        results.append((ocr, s))
    results.sort(key=lambda x: -x[1])
    return [(name, sim) for name, sim in results[:top_n] if sim > 0.15]


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Search vector indices for a task match"
    )
    parser.add_argument(
        "task", nargs="+", help="Task description (can be Chinese or English)"
    )
    parser.add_argument(
        "--top", type=int, default=5, help="Number of results per category (default: 5)"
    )
    parser.add_argument(
        "--no-elements", action="store_true", help="Skip element library search"
    )
    args = parser.parse_args()

    task = " ".join(args.task)
    top_n = args.top

    print("=" * 60)
    print(f"Task: {task}")
    print("=" * 60)

    # Embed once
    task_vec = _embed_task(task)

    # ── Scripts ──
    print(f"\n{'=' * 60}")
    print(".cua Scripts")
    print("=" * 60)
    scripts = _search_scripts(task_vec, top_n)
    if scripts:
        for i, (name, sim) in enumerate(scripts, 1):
            bar = "#" * int(sim * 20) + "-" * (20 - int(sim * 20))
            print(f"  {i}. [{sim:.0%}] {bar} {name}")
    else:
        print("  (no matching scripts)")

    # ── Elements ──
    if not args.no_elements:
        print(f"\n{'=' * 60}")
        print("Elements (template library)")
        print("=" * 60)
        elements = _search_elements(task_vec, top_n)
        if elements:
            for i, (name, sim) in enumerate(elements, 1):
                bar = "█" * int(sim * 20) + "░" * (20 - int(sim * 20))
                print(f"  {i}. [{sim:.0%}] {bar} {name}")
        else:
            print("  (no matching elements)")

    # ── Skills ──
    print(f"\n{'=' * 60}")
    print("Skills (ChromaDB: cua_skills_v2)")
    print("=" * 60)
    skills = _search_skills(task, top_n)
    if skills:
        for i, (sid, sim, doc) in enumerate(skills, 1):
            bar = "█" * int(sim * 20) + "░" * (20 - int(sim * 20))
            print(f"  {i}. [{sim:.0%}] {bar} {sid}")
            if doc:
                print(f"     {doc[:120]}")
    else:
        print("  (no matching skills)")

    # ── Knowledge ──
    print(f"\n{'=' * 60}")
    print("Knowledge Base (ChromaDB: cua_knowledge_v2)")
    print("=" * 60)
    knowledge = _search_knowledge(task, top_n)
    if knowledge:
        for i, (sid, sim, doc) in enumerate(knowledge, 1):
            bar = "█" * int(sim * 20) + "░" * (20 - int(sim * 20))
            print(f"  {i}. [{sim:.0%}] {bar} {sid}")
            if doc:
                print(f"     {doc[:120]}")
    else:
        print("  (no matching knowledge entries)")

    print()


if __name__ == "__main__":
    main()
