# Atleti TV
Calendario del Atlético de Madrid para GitHub Pages. Distingue DAZN, Movistar Plus+ Plan Libre, Movistar LaLiga y Movistar Liga de Campeones.

## Publicación
En Settings → Pages → Build and deployment, selecciona **GitHub Actions**. En Actions, ejecuta **Deploy GitHub Pages**. La web se publicará en https://nowindi.github.io/atleti-tv/.

## Actualización
El workflow Update TV schedule se ejecuta dos veces al día y guarda cambios en data/history.json. Necesita permiso Contents: write para GITHUB_TOKEN. Consulta fuentes públicas con un scraper conservador.

**Limitaciones:** Solo incorpora nuevos canales de encuentros ya incluidos en data/matches.json. No descubre nuevos partidos ni modifica fechas, horarios o canales retirados. Las fuentes pueden cambiar de formato y provocar fallos o falsos positivos. Verifica los canales antes de confiar en ellos. Los datos iniciales son históricos de la conversación y no se han contrastado de nuevo en este despliegue.
