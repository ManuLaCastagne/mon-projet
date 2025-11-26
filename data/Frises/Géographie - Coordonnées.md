```dataviewjs
const fiches = dv.pages('"Géographie"')
    .where(p => p.latitude !== undefined && p.longitude !== undefined)
    .sort(p => p.latitude);

const mapId = "geo-map";

let map = `\`\`\`leaflet
id: ${mapId}
`;

for (let fiche of fiches) {
    const lat = fiche.latitude;
    const lon = fiche.longitude;
    const nom = fiche.file.name;
    const superficie = fiche.superficie ? `Superficie : ${fiche.superficie} km²` : "";
    const popup = `${nom}<br>${superficie}`;

    map += `- Latitude: ${lat}\n  Longitude: ${lon}\n  Popup: ${popup}\n`;
}

map += "```";

dv.paragraph(map);
```





