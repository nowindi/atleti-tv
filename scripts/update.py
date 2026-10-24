"""Refresh existing Atlético fixtures from public television listings."""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'matches.json'
HISTORY = ROOT / 'data' / 'history.json'
SOURCE = 'https://www.futbolenlatv.es/equipo/at-madrid'
MOVISTAR = 'https://www.movistarplus.es/deportes/futbol/horarios'
CHANNEL_PATTERNS = {'M_PLUS': r'Movistar Plus\+\s*\(M7\)', 'M_LALIGA': r'M\+ LALIGA\s*\(M54', 'M_CHAMPIONS': r'M\+ Liga de Campeones\s*\(M60', 'DAZN': r'DAZN(?: LaLiga| LALIGA| 1| 2)?'}

def loadJson(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def fetchText(url):
    response = requests.get(url, timeout=25, headers={'User-Agent':'Mozilla/5.0 (compatible; AtletiTV/1.0)'})
    response.raise_for_status()
    return BeautifulSoup(response.text, 'html.parser').get_text(' ', strip=True)

def normalize(value):
    return re.sub(r'\s+', ' ', value).strip().casefold()

def findChannels(segment):
    return sorted(name for name, pattern in CHANNEL_PATTERNS.items() if re.search(pattern, segment, re.I))

def updateMatches(matches, listing, movistar):
    changes = []
    for match in matches:
        opponents = [match['home'], match['away']]
        opponent = next((name for name in opponents if 'atlético' not in normalize(name)), '')
        aliases = {'Deportivo':['Deportivo'], 'Bayern Múnich':['Bayern'], 'Viking FK':['Viking']}
        names = aliases.get(opponent, [opponent])
        candidates = []
        for name in names:
            for found in re.finditer(re.escape(name), listing, re.I):
                fragment = listing[max(0, found.start()-140):found.end()+340]
                if re.search(r'At\.? Madrid|Atlético', fragment, re.I):
                    candidates.append(fragment)
        if not candidates:
            continue
        detected = max((findChannels(part) for part in candidates), key=len, default=[])
        if 'M_PLUS' in detected and not any(re.search(re.escape(name), movistar, re.I) for name in names):
            detected.remove('M_PLUS')
        if not detected:
            continue
        oldChannels = set(match['channels'])
        newChannels = sorted(oldChannels | set(detected))
        if newChannels != sorted(oldChannels):
            changes.append({'at':datetime.now(ZoneInfo('Europe/Madrid')).isoformat(),'matchId':match['id'],'before':sorted(oldChannels),'after':newChannels})
            match['channels'] = newChannels
            match['source'] = SOURCE
    return changes

def main():
    data = loadJson(DATA, {'matches':[]})
    history = loadJson(HISTORY, [])
    listing = fetchText(SOURCE)
    movistar = fetchText(MOVISTAR)
    if len(listing)<500 or len(movistar)<300:
        raise RuntimeError('Source appears incomplete; leaving data unchanged')
    changes = updateMatches(data['matches'], listing, movistar)
    if changes:
        data['updatedAt'] = datetime.now(ZoneInfo('Europe/Madrid')).isoformat()
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
        HISTORY.write_text(json.dumps(history+changes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(changes)} changes detected')

if __name__=='__main__':
    main()