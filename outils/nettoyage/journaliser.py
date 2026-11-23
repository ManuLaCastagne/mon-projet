"""Ajoute un lot appliqué au journal (questions traitées + résumé).

Usage : python3 -I journaliser.py <journal.json> <lot.json> <numero_lot> <qa_resume>
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_qualite as aq  # noqa: E402

j = json.load(open(sys.argv[1], encoding="utf-8")) if os.path.exists(sys.argv[1]) else {"traitees": [], "lots": []}
lot = json.load(open(sys.argv[2], encoding="utf-8"))
for o in lot:
    j["traitees"].append(f"{o['fichier']}::{aq.normaliser(o['question_actuelle'])}")
    if o.get("proposition"):
        j["traitees"].append(f"{o['fichier']}::{aq.normaliser(o['proposition'])}")
j["traitees"] = sorted(set(j["traitees"]))
j["lots"].append({"lot": sys.argv[3], "questions": len(lot),
                  "verdicts": dict(Counter(o["verdict"] for o in lot)), "qa": sys.argv[4]})
json.dump(j, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("journal :", len(j["lots"]), "lots,", len(j["traitees"]), "questions traitées")
