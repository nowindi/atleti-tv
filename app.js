const channelNames = {
  DAZN: 'DAZN', M_PLUS: 'Movistar Plus+ Plan Libre',
  M_LALIGA: 'Movistar LaLiga', M_CHAMPIONS: 'Movistar Champions'
};
const tvChannels = new Set(['DAZN', 'M_PLUS']);
let matches = [], currentFilter = 'all';

function effectiveChannels(match) {
  if (match.verificationStatus !== 'verified') return [];
  return (match.channels || []).filter(channel => (match.channelEvidence?.[channel] || []).length);
}
function getViewingMode(match) {
  const channels = effectiveChannels(match);
  return channels.some(channel => tvChannels.has(channel)) ? 'tv' : channels.length ? 'ipad' : 'pending';
}
function sortDate(match) { return match.date || match.dateCandidates?.[0] || '9999'; }
function isUpcoming(match, today) {
  const days = match.dateCandidates?.length ? match.dateCandidates : match.date ? [match.date] : [];
  return !days.length || days.some(day => day >= today);
}
function isPending(match) {
  return getViewingMode(match) === 'pending' || match.scheduleStatus !== 'confirmed';
}
function isStale(checkedAt, now = Date.now()) {
  const stamp = Date.parse(checkedAt);
  return !Number.isFinite(stamp) || now - stamp > 48 * 3600 * 1000;
}
function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function sourceLink(text, url) {
  const link = createElement('a', '', text);
  try {
    const target = new URL(url);
    if (target.protocol !== 'https:') return createElement('span', '', text);
    link.href = target.href;
  } catch { return createElement('span', '', text); }
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
}
function dateDescription(match) {
  if (!match.date) return (match.dateLabel || 'Fecha pendiente') + ' · Hora pendiente';
  const date = new Date(match.date + 'T12:00:00Z').toLocaleDateString('es-ES', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/Madrid'
  });
  return date + ' · ' + (match.time || 'Hora pendiente');
}
function renderMatches() {
  const container = document.querySelector('#matches');
  container.replaceChildren();
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Madrid' });
  const filtered = matches.filter(match => isUpcoming(match, today) &&
    (currentFilter === 'all' || (currentFilter === 'pending' ? isPending(match) : getViewingMode(match) === currentFilter)));
  if (!filtered.length) container.append(createElement('p', '', 'No hay partidos para este filtro.'));
  for (const match of filtered) {
    const card = createElement('article', 'match'), top = createElement('div', 'top');
    top.append(createElement('span', '', dateDescription(match)), createElement('span', '', match.competition));
    card.append(top, createElement('h3', '', match.home + ' – ' + match.away));
    if (match.scheduleStatus !== 'confirmed') card.append(createElement('p', 'notice', 'Fecha u hora pendiente de confirmación oficial.'));
    if (match.verificationStatus !== 'verified') card.append(createElement('p', 'notice', 'Encuentro conservado del histórico, sin verificar en el calendario actual.'));
    const channels = createElement('div', 'channels');
    for (const channel of effectiveChannels(match)) {
      channels.append(createElement('span', 'chip ' + (tvChannels.has(channel) ? 'tv' : 'ipad'), channelNames[channel] || channel));
    }
    if (!effectiveChannels(match).length) channels.append(createElement('span', 'chip pending', 'Operador pendiente'));
    card.append(channels);
    const mode = getViewingMode(match);
    card.append(createElement('p', 'view', mode === 'tv' ? '📺 Según tu configuración: TV' : mode === 'ipad' ? '📱 Según tu configuración: iPad' : '⏳ Sin operador verificado para este encuentro'));
    const details = createElement('details', 'evidence');
    details.append(createElement('summary', '', 'Fuentes y comprobación'));
    const schedule = createElement('p');
    schedule.append(sourceLink('Calendario oficial ↗', match.scheduleSource || match.source));
    details.append(schedule);
    for (const channel of effectiveChannels(match)) {
      for (const proof of match.channelEvidence[channel]) {
        const p = createElement('p');
        p.append(sourceLink(channelNames[channel] + ' ↗', proof.url), createElement('span', '', ' · ' + proof.text));
        details.append(p);
      }
    }
    if (match.channelCheckedAt) details.append(createElement('small', '', 'Operadores consultados: ' + formatStamp(match.channelCheckedAt)));
    card.append(details);
    container.append(card);
  }
}
function formatStamp(stamp) {
  return new Date(stamp).toLocaleString('es-ES', { timeZone: 'Europe/Madrid' });
}
function describeState(state) {
  if (Array.isArray(state)) return state.map(c => channelNames[c] || c).join(', ') || 'Operador pendiente';
  if (!state) return 'No figuraba en el calendario';
  const when = state.date ? state.date + ' ' + (state.time || 'hora pendiente') : (state.dateLabel || 'fecha pendiente') + ' · hora pendiente';
  return when + ' · ' + ((state.channels || []).map(c => channelNames[c] || c).join(', ') || 'Operador pendiente');
}
function renderHistory(history) {
  const container = document.querySelector('#changes');
  container.replaceChildren();
  for (const change of history.slice(-12).reverse()) {
    const match = matches.find(item => item.id === change.matchId);
    const item = createElement('div', 'change');
    item.append(createElement('strong', '', match ? match.home + ' – ' + match.away : change.matchId));
    const kind = change.kind === 'added' ? 'Añadido' : change.kind === 'unverified' ? 'Sin verificar' : 'Actualizado';
    item.append(createElement('small', '', kind + ' · ' + formatStamp(change.at)));
    if (change.before) item.append(createElement('p', '', 'Antes: ' + describeState(change.before)));
    item.append(createElement('p', '', 'Ahora: ' + describeState(change.after)));
    container.append(item);
  }
  if (!history.length) container.textContent = 'Todavía no se han registrado cambios automáticos.';
  if (history.length) container.append(sourceLink('Ver histórico completo (' + history.length + ' cambios) ↗', new URL('data/history.json', document.baseURI).href));
}
async function loadCalendar() {
  try {
    const [dataResponse, historyResponse] = await Promise.all([
      fetch('data/matches.json', { cache: 'no-store' }), fetch('data/history.json', { cache: 'no-store' })
    ]);
    if (!dataResponse.ok || !historyResponse.ok) throw Error('No se pudo obtener el calendario');
    const data = await dataResponse.json();
    if (data.schemaVersion !== 2) throw Error('Calendario pendiente de verificación');
    matches = data.matches.sort((a, b) => sortDate(a).localeCompare(sortDate(b)));
    document.querySelector('#updated').textContent = 'Última consulta: ' + formatStamp(data.checkedAt) + ' · Horario de Madrid';
    const warning = document.querySelector('#warning');
    warning.hidden = !isStale(data.checkedAt);
    warning.textContent = 'La última consulta tiene más de 48 horas. Revisa las fuentes antes del partido.';
    renderHistory(await historyResponse.json());
    renderMatches();
  } catch (error) {
    document.querySelector('#updated').textContent = error.message;
  }
}
if (typeof document !== 'undefined') {
  document.querySelectorAll('nav button').forEach(button => button.addEventListener('click', () => {
    currentFilter = button.dataset.filter;
    document.querySelectorAll('nav button').forEach(item => {
      item.classList.toggle('active', item === button);
      item.setAttribute('aria-pressed', String(item === button));
    });
    renderMatches();
  }));
  loadCalendar();
}
if (typeof module !== 'undefined') module.exports = {
  effectiveChannels, getViewingMode, isUpcoming, isPending, sortDate, isStale, describeState, dateDescription
};
