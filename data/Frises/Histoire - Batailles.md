```dataview
table debut, fin, indice_1, indice_2, indice_3
from "Histoire"
where debut and contains(lower(file.name), "bataille")
sort debut asc
```
