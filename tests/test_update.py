from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from scripts import update as u

FIXTURES = Path(__file__).parent / 'fixtures'
TODAY = date(2026, 11, 3)
AT = '2026-11-03T19:30:00+01:00'


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.club_html = (FIXTURES / 'club.html').read_text()
        self.guide_html = (FIXTURES / 'guide.html').read_text()
        self.movistar_html = (FIXTURES / 'movistar.html').read_text()
        self.club = u.parse_club(self.club_html, TODAY)
        self.guide = u.parse_guide(self.guide_html)
        self.movistar = u.parse_movistar(self.movistar_html, TODAY)

    def match(self, opponent, home=True):
        return deepcopy(next(m for m in self.club if m['away' if home else 'home'] == opponent))

    def verify(self, match, guide=None, movistar=None):
        return u.verify_channels(match, self.guide if guide is None else guide,
                                 self.movistar if movistar is None else movistar, AT)

    def test_captured_sources_and_four_operator_families(self):
        self.assertGreater(len(self.club), 40)
        self.assertGreater(len(self.guide), 20)
        self.assertEqual(len(self.movistar), 2)  # no women / academy / other teams
        self.assertEqual(self.verify(self.match('Bayern Múnich'))['channels'], ['M_CHAMPIONS', 'M_PLUS'])
        self.assertEqual(self.verify(self.match('Barcelona'))['channels'], ['M_LALIGA'])
        self.assertEqual(u.find_channels(['DAZN LaLiga (M55)', 'DAZN 2', 'M+ LALIGA 2', 'M+ Liga de Campeones 4', 'Movistar Plus+ (M7)']),
                         ['DAZN', 'M_CHAMPIONS', 'M_LALIGA', 'M_PLUS'])
        self.assertEqual(u.find_channels(['LaLiga TV Bar', 'M+ Vamos', 'Orange Fútbol 1']), [])

    def test_channels_are_scoped_to_event_row(self):
        # Bayern precedes Barcelona, but its M_PLUS and Champions cannot leak.
        result = self.verify(self.match('Barcelona'))
        self.assertEqual(result['channels'], ['M_LALIGA'])
        self.assertTrue(all('Barcelona' in e['text'] for e in result['channelEvidence']['M_LALIGA']))
        self.assertEqual(self.verify(self.match('Viking FK'))['channels'], [])

    def test_club_date_ranges_override_guide_placeholder_time(self):
        elche = self.verify(self.match('Elche', home=False))
        self.assertIsNone(elche['date'])
        self.assertIsNone(elche['time'])
        self.assertEqual(elche['dateCandidates'], ['2026-11-28', '2026-11-29'])
        self.assertEqual(elche['scheduleStatus'], 'pending')
        self.assertEqual(elche['channels'], ['M_LALIGA', 'M_PLUS'])
        self.assertEqual(self.match('Rayo Vallecano', home=False)['dateCandidates'], ['2027-01-02', '2027-01-03'])

    def test_visible_date_wins_over_stale_url_date(self):
        match = self.match('Deportivo')
        self.assertEqual(match['date'], '2026-10-24')  # URL says 25 October
        self.assertEqual(match['time'], '21:00')

    def test_no_plan_libre_from_same_opponent_different_match(self):
        wrong = deepcopy(self.movistar)
        for card in wrong:
            card['home'] = 'Real Madrid'
        self.assertEqual(self.verify(self.match('Bayern Múnich'), movistar=wrong)['channels'], ['M_CHAMPIONS'])

    def test_plan_libre_requires_date_round_and_both_sources(self):
        for field, value in [('dates', ['2026-11-04']), ('round', '5'), ('competition', 'LaLiga'), ('home', 'Bayern Múnich')]:
            cards = deepcopy(self.movistar)
            cards[0][field] = value
            with self.subTest(field=field):
                self.assertNotIn('M_PLUS', self.verify(self.match('Bayern Múnich'), movistar=cards)['channels'])
        guide = deepcopy(self.guide)
        for row in guide:
            row['channels'] = [c for c in row['channels'] if c != 'M_PLUS']
        self.assertNotIn('M_PLUS', self.verify(self.match('Bayern Múnich'), guide=guide)['channels'])

    def test_programme_time_does_not_change_kickoff(self):
        self.assertEqual(self.movistar[0]['dateLabel'], 'Hoy - 20:53h')
        self.assertEqual(self.verify(self.match('Bayern Múnich'))['time'], '21:00')

    def test_stale_or_duplicate_guide_row_cannot_confirm(self):
        for field, value in [('date', '2026-11-04'), ('time', '20:00')]:
            guide = deepcopy(self.guide)
            guide[0][field] = value
            self.assertEqual(self.verify(self.match('Bayern Múnich'), guide=guide)['channels'], [])
        self.assertEqual(self.verify(self.match('Bayern Múnich'), guide=self.guide + [self.guide[0]])['channels'], [])

    def test_new_match_and_reschedule_preserve_identity_and_history(self):
        initial = [self.match('Bayern Múnich')]
        old = {'matches': [{**deepcopy(initial[0]), 'id': 'legacy-bayern', 'channels': ['DAZN']}]}
        history = [{'at': 'old', 'matchId': 'legacy-bayern', 'before': [], 'after': ['DAZN']}]
        changed = deepcopy(initial)
        changed[0].update(date='2026-11-05', dateCandidates=['2026-11-05'], dateLabel='Jueves 5 de noviembre', time='18:45')
        changed.append(self.match('Valencia'))
        data, full, events = u.reconcile(old, history, changed, self.guide, self.movistar, AT)
        self.assertEqual(full[:1], history)
        self.assertEqual(len(events), 2)
        match = next(m for m in data['matches'] if m['away'] == 'Bayern Múnich')
        self.assertEqual(match['id'], 'legacy-bayern')
        self.assertEqual(match['date'], '2026-11-05')
        self.assertEqual(match['channels'], [])
        change = next(e for e in events if e['matchId'] == 'legacy-bayern')
        self.assertEqual(change['before']['date'], '2026-11-03')
        self.assertEqual(change['after']['time'], '18:45')
        # Inputs are not mutated.
        self.assertEqual(old['matches'][0]['channels'], ['DAZN'])
        self.assertEqual(history, full[:1])

    def test_channel_replacement_and_withdrawal_are_recorded(self):
        official = [self.match('Barcelona')]
        data, history, _ = u.reconcile({'matches': []}, [], official, self.guide, self.movistar, AT)
        guide = deepcopy(self.guide)
        row = next(g for g in guide if g['away'] == 'Barcelona')
        row.update(channels=['DAZN'], labels=['DAZN LaLiga'])
        data2, history2, events = u.reconcile(data, history, official, guide, self.movistar, AT)
        self.assertEqual(data2['matches'][0]['channels'], ['DAZN'])
        self.assertEqual(events[0]['before']['channels'], ['M_LALIGA'])
        self.assertEqual(events[0]['after']['channels'], ['DAZN'])
        row.update(channels=[], labels=['Canal por confirmar'])
        data3, history3, events = u.reconcile(data2, history2, official, guide, self.movistar, AT)
        self.assertEqual(data3['matches'][0]['channels'], [])
        self.assertEqual(history3[:len(history2)], history2)

    def test_missing_match_is_retained_and_unverified_not_cancelled(self):
        old = {'matches': [{**self.match('Barcelona'), 'channels': ['DAZN']}]}
        data, history, events = u.reconcile(old, [], [self.match('Bayern Múnich')], self.guide, self.movistar, AT)
        retained = next(m for m in data['matches'] if m['away'] == 'Barcelona')
        self.assertEqual(retained['verificationStatus'], 'unverified')
        self.assertEqual(retained['channels'], [])
        self.assertEqual(events[-1]['kind'], 'unverified')

    def test_second_run_does_not_duplicate_history(self):
        data, history, _ = u.reconcile({'matches': []}, [], self.club, self.guide, self.movistar, AT)
        again, history2, changes = u.reconcile(data, history, self.club, self.guide, self.movistar, '2026-11-03T20:00:00+01:00')
        self.assertEqual(changes, [])
        self.assertEqual(history2, history)
        self.assertEqual(again['updatedAt'], data['updatedAt'])
        self.assertNotEqual(again['checkedAt'], data['checkedAt'])

    def test_broken_source_preserves_both_files(self):
        sources = {u.CLUB: self.club_html, u.GUIDE: self.guide_html, u.MOVISTAR: self.movistar_html}
        for url in sources:
            with self.subTest(url=url), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                for file in ('matches.json', 'history.json'):
                    (path/file).write_text('{"unchanged":true}')
                broken = {**sources, url: '<html>Captcha / Access denied</html>'}
                with self.assertRaises(u.SourceError):
                    u.refresh(path, AT, fetch=broken.__getitem__)
                self.assertEqual((path/'matches.json').read_text(), '{"unchanged":true}')
                self.assertEqual((path/'history.json').read_text(), '{"unchanged":true}')

    def test_unknown_club_format_fails_closed(self):
        with self.assertRaises(u.SourceError):
            u.parse_club(self.club_html.replace('21:00', 'horario desconocido'), TODAY)
        with self.assertRaises(u.SourceError):
            u.parse_club(self.club_html.replace('2026', '2022'), TODAY)

    def test_dates_at_year_boundary_and_ambiguous_promo(self):
        self.assertEqual(u.card_dates('Mañana - 20:53h', date(2026,12,31)), ['2027-01-01'])
        self.assertEqual(u.card_dates('2 ene - 20:53h', date(2026,12,30)), ['2027-01-02'])
        self.assertEqual(u.card_dates('28 o 29 NOV.', TODAY), ['2026-11-28', '2026-11-29'])

    def test_dry_run_does_not_write_and_validation_requires_evidence(self):
        sources = {u.CLUB: self.club_html, u.GUIDE: self.guide_html, u.MOVISTAR: self.movistar_html}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            data, events = u.refresh(path, AT, fetch=sources.__getitem__, dry_run=True)
            self.assertTrue(events)
            self.assertEqual(list(path.iterdir()), [])
        data['matches'][0]['channels'] = ['M_PLUS']
        with self.assertRaises(u.SourceError):
            u.validate_data(data)


if __name__ == '__main__':
    unittest.main()
