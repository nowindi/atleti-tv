const {test} = require('node:test');
const assert = require('node:assert/strict');
const app = require('../app.js');
const match = {date:null, dateCandidates:['2026-11-28','2026-11-29'], scheduleStatus:'pending', verificationStatus:'verified', channels:['M_PLUS'], channelEvidence:{M_PLUS:[{url:'https://example.com'}]}};
test('pending date does not break sort/filter and remains upcoming on final day', () => {
  assert.equal(app.sortDate(match),'2026-11-28');
  assert.equal(app.isUpcoming(match,'2026-11-29'),true);
  assert.equal(app.isUpcoming(match,'2026-11-30'),false);
  assert.equal(app.isPending(match),true);
  assert.equal(app.getViewingMode(match),'tv');
});
test('unsupported legacy channels do not imply viewing availability', () => {
  assert.equal(app.getViewingMode({...match,channelEvidence:{}}),'pending');
  assert.equal(app.getViewingMode({...match,verificationStatus:'unverified'}),'pending');
  assert.equal(app.getViewingMode({...match,channels:['M_CHAMPIONS'],channelEvidence:{M_CHAMPIONS:[{}]}}),'ipad');
});
test('history supports old channel arrays, schedule changes and withdrawals', () => {
  assert.match(app.describeState(['DAZN']),/DAZN/);
  assert.match(app.describeState({date:'2026-11-03',time:'21:00',channels:[]}),/21:00.*Operador pendiente/);
  assert.match(app.describeState(null),/No figuraba/);
});
test('stale and missing check timestamps are visible', () => {
  const now=Date.parse('2026-11-03T19:00:00+01:00');
  assert.equal(app.isStale('2026-10-24T00:00:00+02:00',now),true);
  assert.equal(app.isStale('2026-11-03T18:00:00+01:00',now),false);
  assert.equal(app.isStale(undefined,now),true);
});
