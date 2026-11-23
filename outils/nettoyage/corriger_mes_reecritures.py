"""Remplace en place des réécritures écrites par Claude (pas le texte d'origine, déjà archivé).
Usage : python3 -I corriger_mes_reecritures.py <fix.json> <pilote.json> <dossier_data>"""
import json, os, sys
fix = json.load(open(sys.argv[1], encoding="utf-8"))
lot = {str(o["n"]): o for o in json.load(open(sys.argv[2], encoding="utf-8"))}
data = sys.argv[3]
for k, ancien in fix["old"].items():
    o = lot[k]; p = os.path.join(data, o["fichier"])
    t = open(p, encoding="utf-8", newline="").read()
    assert t.count(ancien) == 1, (k, t.count(ancien))
    if k in fix["new"]:
        t = t.replace(ancien, fix["new"][k])
    else:  # retrait de ma réécriture fautive (l'original est déjà dans les archives)
        nl = "\r\n" if "\r\n" in t else "\n"
        t = t.replace(ancien + nl + nl, "") if (ancien + nl + nl) in t else t.replace(nl + nl + ancien, "")
        assert ancien not in t
    open(p, "w", encoding="utf-8", newline="").write(t)
    print("ok", k, o["fiche"])
