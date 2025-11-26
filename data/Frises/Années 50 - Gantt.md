```dataviewjs
const personnages = dv.pages()
	.where(p => p.debut && p.debut >= 1950 && p.debut <= 1960)
    .sort(p => p.debut);

let ganttCode = "```mermaid\ngantt\n    title Durée de vie des personnages\n    dateFormat YYYY\n    axisFormat %Y\n\n";

personnages.forEach((perso, index) => {
    let nom = perso.file.name;
    let debut = perso.debut;
    let fin = perso.fin ?? 2026; // si fin est indéfini, on prend debut
    let duree = fin - debut + 1;
    let label = `${debut}–${fin}`;

    ganttCode += `    section ${nom}\n    ${label} : ${index+1}, ${debut}, ${duree}y\n`;
});

ganttCode += "```";

dv.paragraph(ganttCode);
```
















