"""CM-034 : choisit les prochaines fiches à vérifier (grand public, jamais vérifiées, score décroissant).

Usage : python3 -I selectionner.py <dossier mon-projet> <nombre> > liste.txt
"""
import glob, os, re, sys

racine, n = sys.argv[1], int(sys.argv[2])
cands = []
for p in glob.glob(os.path.join(racine, "data", "**", "*.md"), recursive=True):
    t = open(p, encoding="utf-8").read()
    entete = t.split("---", 2)[1] if t.startswith("---") else ""
    if re.search(r"^verifie_cm034:", entete, re.M):
        continue
    m = re.search(r"^culture_g_score:\s*(\d+)", entete, re.M)
    q = re.search(r"###### Questions\s*\n(.*?)(?=\n#|\Z)", t, re.S)
    if m and int(m.group(1)) >= 70 and q and q.group(1).strip():
        cands.append((-int(m.group(1)), os.path.relpath(p, racine)))
for _, p in sorted(cands)[:n]:
    print(p)
print(f"{len(cands)} fiches grand public restant à vérifier", file=sys.stderr)
