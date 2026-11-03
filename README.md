# Atleti TV

Calendario del primer equipo masculino del Atlético de Madrid, publicado en [GitHub Pages](https://nowindi.github.io/atleti-tv/). Distingue DAZN, Movistar Plus+ Plan Libre, Movistar LaLiga y Movistar Champions. TV/iPad refleja la configuración personal del usuario; no garantiza la compatibilidad de dispositivos ni una suscripción.

## Fuentes y evidencia

- [Calendario oficial del club](https://www.atleticodemadrid.com/calendario-completo-primer-equipo/): descubre encuentros, competición, jornada, local/visitante, fechas posibles y hora. Se usa el texto visible; las URLs de entradas/resúmenes pueden contener fechas antiguas. Una fecha con alternativas se guarda en `dateCandidates`, con `date: null`; la hora queda pendiente. No se convierte el domingo o una hora orientativa de la guía en confirmación oficial.
- [Fútbol en la TV](https://www.futbolenlatv.es/equipo/at-madrid): operadores exclusivamente de la fila del partido, con ambos equipos, competición y fecha compatible. Una hora incompatible con el club o filas ambiguas impiden confirmar canales. Se ignoran menús, publicidad, texto histórico y partidos vecinos. Los canales numerados/HDR se agrupan en su familia; no se asignan por los derechos generales de la competición.
- [Movistar Plan Libre](https://www.movistarplus.es/deportes/futbol/horarios): `M_PLUS` exige además una ficha del mismo partido, competición, fecha y jornada si está publicada. Se excluyen femenino y filial. La hora del programa (p. ej. 20:53) nunca sustituye el inicio del partido (21:00). Una mención genérica al rival no vale.

Cada operador publicado tiene `channelEvidence` con URL, texto del encuentro y `checkedAt`. La fecha/hora tiene su evidencia oficial. Los operadores se recalculan: pueden añadirse, retirarse o quedar pendientes. En la interfaz se pueden desplegar las fuentes de cada encuentro.

## Datos e histórico

`data/matches.json` usa esquema 2. Las identidades nuevas dependen de temporada, competición, jornada y ambos equipos, sin fecha/hora. Los IDs originales se mantienen al migrar para conservar sus referencias. Los encuentros ausentes se conservan como no verificados, con operadores pendientes; la ausencia no se interpreta como cancelación.

`data/history.json` es acumulativo, con altas y cambios, valores antes/después y evidencia. Acepta las entradas antiguas con arrays de canales. La migración registra también la retirada de afirmaciones iniciales sin evidencia. Un sondeo idéntico actualiza la fecha de consulta, sin duplicar cambios. `updatedAt` indica el último cambio; `checkedAt`, la última consulta completa. La web avisa si la consulta supera 48 horas.

## Actualización y publicación

Pages debe tener **Settings → Pages → Build and deployment → GitHub Actions**.

- **Update TV schedule**: conserva el horario `17 7,17 * * *` (07:17 y 17:17 UTC; 08:17/18:17 en invierno, 09:17/19:17 en verano de Madrid). También se puede lanzar manualmente. Ejecuta pruebas, consulta las tres fuentes, valida evidencias y guarda datos e histórico con `GITHUB_TOKEN` (`contents: write`). Las actualizaciones se serializan y un push concurrente provoca fallo, sin sobrescribir trabajo ajeno.
- Tras guardar, llama explícitamente al workflow reutilizable **Deploy GitHub Pages**. Un push con `GITHUB_TOKEN` no desencadena por sí solo otro workflow de push: [documentación de GitHub](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow).
- **Deploy GitHub Pages**: pruebas y validación, empaquetado de HTML/CSS/JS y los dos JSON únicamente; publicación con `pages: write` e `id-token: write`. También se lanza en pushes a main y manualmente. Nunca se publican scripts, tests ni archivos del checkout.
- **Tests**: en pushes y PR, sin consultar webs ni modificar datos.

## Desarrollo y verificación

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node --test tests/app.test.cjs
python scripts/update.py --dry-run
python scripts/update.py
python scripts/update.py --validate
```

`--data-dir` permite actualizar una copia de datos en otro directorio. Las pruebas usan fragmentos HTML capturados el 3 de noviembre de 2026 y casos sintéticos para altas, cambios de fecha/hora, retirada de canales, alias, rangos, cambio de año, fuentes rotas, aislamiento de filas, evidencias e idempotencia. Las pruebas del workflow comprueban también la sintaxis de todos los pasos de shell.

## Límites

Las fuentes son HTML público, sin API contratada: pueden bloquear peticiones, cambiar formato, contener errores o discrepar. Si una descarga o un parser falla, no se escribe ninguno de los dos JSON y Actions falla visiblemente; la web conserva la última consulta. Un nombre no reconocido, una fecha desconocida o una discrepancia pueden dejar operadores pendientes aunque se emita el partido. Las nuevas competiciones o formatos pueden necesitar adaptar el extractor; no se inventan futuros cruces de eliminatorias.

La guía no equivale a confirmación directa de DAZN/Movistar sobre todos sus canales: la interfaz lo describe como operadores publicados y enlaza su evidencia. Plan Libre requiere doble coincidencia, pero tampoco acredita una suscripción del usuario. No se anuncia cancelación por desaparecer un partido de una fuente. El parser de fechas admite los formatos observados del club y de Movistar; ante uno desconocido se debe revisar el fallo en Actions. GitHub puede retrasar cron y entrega por caché de Pages; no es un servicio en tiempo real.
