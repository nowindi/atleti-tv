"""Evidence-based Atlético calendar. No channel inference from broadcast rights."""
import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo('Europe/Madrid')
CLUB = 'https://www.atleticodemadrid.com/calendario-completo-primer-equipo/'
GUIDE = 'https://www.futbolenlatv.es/equipo/at-madrid'
MOVISTAR = 'https://www.movistarplus.es/deportes/futbol/horarios'
MONTHS = dict(zip(['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                   'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'], range(1, 13)))
ABBR_MONTHS = {name[:3]: number for name, number in MONTHS.items()}
CHANNELS = {'DAZN', 'M_PLUS', 'M_LALIGA', 'M_CHAMPIONS'}


class SourceError(ValueError):
    """A source cannot safely be interpreted; do not overwrite stored data."""


def normalize(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()


ALIASES = {
    'at madrid': 'Atlético de Madrid', 'atletico de madrid': 'Atlético de Madrid',
    'atletico madrid': 'Atlético de Madrid', 'fc bayern': 'Bayern Múnich',
    'bayern munich': 'Bayern Múnich', 'bayern munchen': 'Bayern Múnich',
    'fc barcelona': 'Barcelona', 'real betis': 'Betis', 'real betis balompie': 'Betis',
    'psv eindhoven': 'PSV', 'rc deportivo': 'Deportivo', 'deportivo la coruna': 'Deportivo',
    'valencia cf': 'Valencia', 'celta de vigo': 'Celta', 'rc celta': 'Celta',
    'racing santander': 'Racing Santander', 'real racing club': 'Racing Santander',
    'racing': 'Racing Santander', 'elche cf': 'Elche', 'ca osasuna': 'Osasuna',
    'athletic club': 'Athletic Club', 'villarreal cf': 'Villarreal',
    'bodo glimt': 'Bodø/Glimt', 'fk bodo glimt': 'Bodø/Glimt',
    'fenerbahce sk': 'Fenerbahçe', 'viking': 'Viking FK',
}


def team(value):
    return ALIASES.get(normalize(value), re.sub(r'\s+', ' ', value).strip())


def competition(value):
    key = normalize(value)
    if key in ('laliga', 'la liga ea sports', 'laliga ea sports'):
        return 'LaLiga'
    if key in ('uefa champions league', 'champions league'):
        return 'Champions League'
    return value.strip()


def season_for(day):
    return day.year if day.month >= 7 else day.year - 1


def clean_text(node):
    return node.get_text(' ', strip=True).rstrip(' -').strip()


def parse_club(html, today):
    """Use displayed date/time, never stale date segments in ticket/report URLs."""
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.select('.header-calendar')
    if not cards:
        raise SourceError('Club: no se reconoce el calendario')
    seasons = {int(m.group()) for img in soup.select('.competition img')
               if (m := re.search(r'20\d{2}', img.get('alt', '')))}
    if len(seasons) != 1:
        raise SourceError('Club: temporada ausente o ambigua')
    season = seasons.pop()
    if season not in (season_for(today), season_for(today) - 1):
        raise SourceError('Club: temporada inesperada')
    matches = []
    for card in cards:
        home = card.select_one('.local dt')
        away = card.select_one('.visitante dt')
        comp_img = card.select_one('.competition img')
        spans = card.select('.info-calendario > span')
        if home is None or away is None or comp_img is None or len(spans) < 3:
            raise SourceError('Club: ficha incompleta')
        home, away = team(clean_text(home)), team(clean_text(away))
        if 'Atlético de Madrid' not in (home, away):
            raise SourceError('Club: equipo inesperado')
        round_text, date_text, time_text = [clean_text(n) for n in spans[:3]]
        month_match = re.search(r'\b(' + '|'.join(MONTHS) + r')\b', normalize(date_text))
        if not month_match:
            if normalize(date_text) not in ('sin confirmar', 'por confirmar', 'fecha por confirmar'):
                raise SourceError('Club: fecha no reconocida: ' + date_text)
            dates = []
        else:
            month = MONTHS[month_match.group()]
            day_numbers = [int(n) for n in re.findall(r'\b\d{1,2}\b', normalize(date_text)[:month_match.start()])]
            if not day_numbers:
                raise SourceError('Club: fecha sin día')
            year = season if month >= 7 else season + 1
            dates = sorted({date(year, month, n).isoformat() for n in day_numbers})
        if re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', time_text):
            time = time_text
        elif normalize(time_text) in ('sin confirmar', 'por confirmar', 'hora por confirmar'):
            time = None
        else:
            raise SourceError('Club: hora no reconocida: ' + time_text)
        if len(dates) != 1:
            time = None
        comp = competition(comp_img.get('title') or comp_img.get('alt', ''))
        round_match = re.search(r'Jornada\s+(\d+)', round_text, re.I)
        round_id = round_match.group(1) if round_match else normalize(round_text)
        identity = f'{season}|{comp}|{round_id}|{normalize(home)}|{normalize(away)}'
        matches.append({
            'id': hashlib.sha256(identity.encode()).hexdigest()[:20],
            'season': season, 'round': round_id, 'home': home, 'away': away,
            'competition': comp, 'date': dates[0] if len(dates) == 1 else None,
            'dateCandidates': dates, 'dateLabel': date_text, 'time': time,
            'scheduleStatus': 'confirmed' if len(dates) == 1 and time else 'pending',
            'scheduleSource': CLUB, 'channels': [], 'channelEvidence': {},
            'channelStatus': 'pending', 'verificationStatus': 'verified',
        })
    if len({m['id'] for m in matches}) != len(matches):
        raise SourceError('Club: identidades duplicadas')
    if not any(not m['dateCandidates'] or max(m['dateCandidates']) >= today.isoformat() for m in matches):
        raise SourceError('Club: calendario desactualizado, sin próximos partidos')
    return matches


def find_channels(labels):
    channels = set()
    for label in labels:
        text = normalize(label)
        if re.match(r'^dazn(?: |$)', text):
            channels.add('DAZN')
        if re.match(r'^(?:m |movistar )?laliga(?: |$)', text) and not text.startswith('laliga tv bar'):
            channels.add('M_LALIGA')
        if re.match(r'^(?:m |movistar )liga de campeones(?: |$)', text):
            channels.add('M_CHAMPIONS')
        if re.match(r'^movistar plus(?: m7| ver partido|$)', text):
            channels.add('M_PLUS')
    return sorted(channels)


def parse_guide(html):
    """Parse only event rows; menus, ads and nearby matches carry no evidence."""
    soup = BeautifulSoup(html, 'html.parser')
    fixtures = []
    for table in soup.select('table.tablaPrincipal'):
        header = table.select_one('.cabeceraTabla')
        current_date = None
        if header and (m := re.search(r'(\d{2})/(\d{2})/(\d{4})', clean_text(header))):
            current_date = date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        for row in table.select('tr'):
            if row.select_one('td.local') is None:
                continue
            home, away = row.select_one('td.local'), row.select_one('td.visitante')
            hour, comp, channel_node = row.select_one('td.hora'), row.select_one('td.detalles img'), row.select_one('td.canales')
            if not all(n is not None for n in (away, hour, comp, channel_node)) or not current_date:
                raise SourceError('Guía: fila de partido incompleta')
            home, away = team(clean_text(home)), team(clean_text(away))
            if 'Atlético de Madrid' not in (home, away):
                continue
            labels = [clean_text(li) for li in channel_node.select('ul.listaCanales > li')]
            if not labels:
                raise SourceError('Guía: lista de operadores ausente')
            time_text = clean_text(hour)
            if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', time_text) and normalize(time_text) not in ('sin confirmar', 'por confirmar', ''):
                raise SourceError('Guía: hora no reconocida')
            fixtures.append({'home': home, 'away': away, 'competition': competition(comp.get('alt', '')),
                             'date': current_date, 'time': time_text, 'labels': labels,
                             'channels': find_channels(labels)})
    if not fixtures:
        raise SourceError('Guía: sin filas de partidos reconocibles')
    return fixtures


def card_dates(text, today):
    """Resolve Spanish event dates, but ignore programme start time (e.g. 20:53)."""
    value = normalize(text)
    if value.startswith('hoy '):
        return [today.isoformat()]
    if value.startswith('manana '):
        return [(today + timedelta(days=1)).isoformat()]
    month_re = re.search(r'\b(' + '|'.join(ABBR_MONTHS) + r')\b', value)
    if month_re:
        days = re.findall(r'\b\d{1,2}\b', value[:month_re.start()])
        month = ABBR_MONTHS[month_re.group()]
        years = range(today.year - 1, today.year + 2)
        possibilities = [date(y, month, int(d)) for d in days for y in years]
        return sorted({min((p for p in possibilities if p.day == int(d)), key=lambda p: abs((p-today).days)).isoformat() for d in days})
    # Cards use “sáb 7” for the next occurrence in the current/next month.
    match = re.match(r'^(?:lun|mar|mie|jue|vie|sab|dom)\s+(\d{1,2})\s+', value)
    if match:
        candidates = [today + timedelta(days=i) for i in range(-1, 32)
                      if (today + timedelta(days=i)).day == int(match[1])]
        return [min(candidates, key=lambda d: abs((d-today).days)).isoformat()] if candidates else []
    return []


def parse_movistar(html, today):
    soup = BeautifulSoup(html, 'html.parser')
    if 'plan libre' not in normalize(soup.get_text(' ', strip=True)):
        raise SourceError('Movistar: falta el contexto de Plan Libre')
    sections = soup.select('section.mplus-collection')
    if not sections:
        raise SourceError('Movistar: calendario no reconocido')
    cards = []
    total = 0
    for section in sections:
        heading = section.select_one('h2')
        if heading is None:
            continue
        comp = competition(clean_text(heading).replace('Fútbol · ', ''))
        if comp not in ('LaLiga', 'Champions League', 'Copa del Rey MAPFRE', 'Supercopa de España'):
            continue
        for title in section.select('.mplus-collection__title'):
            total += 1
            label = clean_text(title)
            if ':' not in label:
                continue
            event = label.rsplit(':', 1)[-1].strip()
            sides = re.split(r'\s+[–—-]\s+', event)
            if len(sides) != 2:
                continue
            home, away = team(sides[0]), team(sides[1].split(',')[0])
            if 'Atlético de Madrid' not in (home, away):
                continue
            li = title.find_parent('li')
            date_node = li.select_one('.mplus-collection__date') if li else None
            date_text = clean_text(date_node) if date_node else label.split(',')[-1]
            round_match = re.search(r'Jornada\s+(\d+)', label, re.I)
            cards.append({'home': home, 'away': away, 'competition': comp,
                          'round': round_match[1] if round_match else None,
                          'dates': card_dates(date_text, today), 'label': label,
                          'dateLabel': date_text})
    if total == 0:
        raise SourceError('Movistar: sin fichas de competiciones reconocidas')
    return cards


def pair_key(match):
    return (normalize(team(match['home'])), normalize(team(match['away'])), competition(match['competition']))


def evidence(url, text, at):
    return {'url': url, 'text': text, 'checkedAt': at}


def same_season(old, new):
    if old.get('season') is not None:
        return old['season'] == new['season']
    return bool(old.get('date')) and season_for(date.fromisoformat(old['date'])) == new['season']


def verify_channels(match, guide, movistar, at):
    match = deepcopy(match)
    candidates = [g for g in guide if pair_key(g) == pair_key(match) and g['date'] in match['dateCandidates']]
    # Ambiguous rows, conflicting kickoff times, or unknown dates must not confirm a channel.
    row = candidates[0] if len(candidates) == 1 else None
    if row and match['time'] and row['time'] != match['time']:
        row = None
    if row:
        for channel in row['channels']:
            if channel == 'M_PLUS':
                continue
            match['channelEvidence'][channel] = [evidence(GUIDE, f"{row['date']} {row['time']} · {row['home']} – {row['away']} · " + ', '.join(row['labels']), at)]
        plan_cards = [c for c in movistar if pair_key(c) == pair_key(match)
                      and row['date'] in c['dates'] and (c['round'] is None or c['round'] == match['round'])]
        if 'M_PLUS' in row['channels'] and len(plan_cards) == 1:
            match['channelEvidence']['M_PLUS'] = [
                evidence(GUIDE, f"{row['date']} · {row['home']} – {row['away']} · " + ', '.join(row['labels']), at),
                evidence(MOVISTAR, plan_cards[0]['label'] + ' · ' + plan_cards[0]['dateLabel'], at),
            ]
    match['channels'] = sorted(match['channelEvidence'])
    match['channelStatus'] = 'listed' if match['channels'] else 'pending'
    match['channelCheckedAt'] = at
    match['scheduleEvidence'] = evidence(CLUB, f"{match['competition']} · Jornada {match['round']} · {match['home']} – {match['away']} · {match['dateLabel']} · {match['time'] or 'Sin confirmar'}", at)
    match['source'] = CLUB
    return match


def snapshot(match):
    """Ignore check timestamps so unchanged polls do not fabricate history."""
    keys = ('home', 'away', 'competition', 'season', 'round', 'date', 'dateCandidates',
            'dateLabel', 'time', 'scheduleStatus', 'channels', 'channelStatus', 'verificationStatus')
    return {k: deepcopy(match.get(k)) for k in keys}


def reconcile(data, history, official, guide, movistar, at):
    old_matches = deepcopy(data.get('matches', []))
    result, events, used = [], [], set()
    for fixture in official:
        matches = [m for m in old_matches if pair_key(m) == pair_key(fixture) and same_season(m, fixture)
                   and (not m.get('round') or m['round'] == fixture['round'])]
        if len(matches) > 1:
            raise SourceError('Más de un partido guardado coincide con la identidad oficial')
        previous = matches[0] if matches else None
        # Keep existing legacy IDs so all previous history remains resolvable.
        if previous:
            fixture = {**fixture, 'id': previous['id']}
            used.add(previous['id'])
        fresh = verify_channels(fixture, guide, movistar, at)
        result.append(fresh)
        before, after = snapshot(previous) if previous else None, snapshot(fresh)
        if before != after:
            events.append({'at': at, 'matchId': fresh['id'], 'kind': 'updated' if previous else 'added',
                           'before': before, 'after': after,
                           'evidence': {'schedule': fresh['scheduleEvidence'], 'channels': fresh['channelEvidence']}})
    for previous in old_matches:
        if previous['id'] in used:
            continue
        # Absence is not cancellation: retain data, but withdraw unsupported claims.
        fresh = deepcopy(previous)
        fresh.update({'channels': [], 'channelEvidence': {}, 'channelStatus': 'pending',
                      'verificationStatus': 'unverified', 'channelCheckedAt': at})
        result.append(fresh)
        if snapshot(previous) != snapshot(fresh):
            events.append({'at': at, 'matchId': fresh['id'], 'kind': 'unverified',
                           'before': snapshot(previous), 'after': snapshot(fresh),
                           'reason': 'No localizado en el calendario oficial; no se infiere cancelación.'})
    result.sort(key=lambda m: (m.get('date') or min(m.get('dateCandidates') or ['9999']), m['id']))
    updated = {**deepcopy(data), 'schemaVersion': 2, 'timezone': 'Europe/Madrid',
               'checkedAt': at, 'updatedAt': at if events else data.get('updatedAt', at),
               'sources': [{'url': url, 'checkedAt': at, 'status': 'ok'} for url in (CLUB, GUIDE, MOVISTAR)],
               'matches': result}
    validate_data(updated)
    return updated, deepcopy(history) + events, events


def validate_data(data):
    ids = set()
    for match in data['matches']:
        if match['id'] in ids:
            raise SourceError('ID duplicado')
        ids.add(match['id'])
        if set(match['channels']) - CHANNELS or set(match['channels']) != set(match.get('channelEvidence', {})):
            raise SourceError('Operador sin evidencia')
        for channel in match['channels']:
            proof = match['channelEvidence'][channel]
            urls = {p['url'] for p in proof if p.get('text') and p.get('checkedAt')}
            required = {GUIDE, MOVISTAR} if channel == 'M_PLUS' else {GUIDE}
            if not required.issubset(urls):
                raise SourceError('Evidencia incompleta para ' + channel)


def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def fetch_html(url):
    response = requests.get(url, timeout=30, headers={'User-Agent': 'AtletiTV/2.0 (+https://github.com/nowindi/atleti-tv)'})
    response.raise_for_status()
    return response.text


def refresh(data_dir, at, fetch=fetch_html, dry_run=False):
    today = datetime.fromisoformat(at).astimezone(TZ).date()
    # Fetch and parse all sources before touching either file. A failure preserves both.
    official = parse_club(fetch(CLUB), today)
    guide = parse_guide(fetch(GUIDE))
    movistar = parse_movistar(fetch(MOVISTAR), today)
    data = load_json(data_dir / 'matches.json', {'matches': []})
    history = load_json(data_dir / 'history.json', [])
    updated, full_history, events = reconcile(data, history, official, guide, movistar, at)
    if not dry_run:
        data_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in [('history.json', full_history), ('matches.json', updated)]:
            path = data_dir / name
            temporary = path.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            temporary.replace(path)
    return updated, events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--validate', action='store_true', help='Validar el JSON guardado, sin red')
    args = parser.parse_args()
    if args.validate:
        validate_data(load_json(args.data_dir / 'matches.json', {'matches': []}))
        print('Datos y evidencias válidos')
        return
    try:
        updated, events = refresh(args.data_dir, datetime.now(TZ).isoformat(timespec='seconds'), dry_run=args.dry_run)
    except (SourceError, requests.RequestException, ValueError) as exc:
        print(f'Actualización abortada; datos conservados: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"{len(updated['matches'])} partidos; {len(events)} cambios; " + ('simulación sin escritura' if args.dry_run else 'histórico preservado'))


if __name__ == '__main__':
    main()
