```dataviewjs
const personnages = dv.pages('"Histoire"')
    .where(p => p.debut && p.debut >= 1000 && p.debut <= 2000 && (p.file.name.toLowerCase().includes("bataille") || p.file.name.toLowerCase().includes("guerre")))
    .sort(p => p.debut);

let ganttCode = "```mermaid\ngantt\n    title Guerres et batailles\n    dateFormat YYYY\n    axisFormat %Y\n\n";

personnages.forEach((perso, index) => {
    let nom = perso.file.name;
    let debut = perso.debut;
    let fin = perso.fin ?? debut;
    let duree = fin - debut + 1;
    let label = `${debut}–${fin}`;

    ganttCode += `    section ${nom}\n    ${label} : ${index+1}, ${debut}, ${duree}y\n`;
});

ganttCode += "```";

dv.paragraph(ganttCode);
```









