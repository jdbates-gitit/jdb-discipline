const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '..', 'practice.js'), 'utf8');
const prefix = 'daily-discipline.evening.v1.';

function element() {
  const handlers = {};
  return { hidden: true, value: '', textContent: '', addEventListener(type, callback) { handlers[type] = callback; }, fire(type) { handlers[type]?.(); } };
}
function run({ dates = ['2026-10-03'], stored = {}, blocked = false } = {}) {
  const data = new Map(Object.entries(stored));
  const panels = dates.map(date => {
    const controls = element(), input = element(), status = element(), save = element(), clear = element();
    const selectors = { '.private-note': controls, textarea: input, '.note-status': status, '[data-note-save]': save, '[data-note-clear]': clear };
    return { controls, input, status, save, clear, dataset: { noteDate: date }, querySelector: selector => selectors[selector] };
  });
  const storage = {
    getItem(key) { if (blocked) throw Error('unavailable'); return data.get(key) ?? null; },
    setItem(key, value) { if (blocked) throw Error('quota'); data.set(key, value); },
    removeItem(key) { if (blocked) throw Error('unavailable'); data.delete(key); }
  };
  vm.runInNewContext(script, { document: { querySelectorAll: () => panels }, localStorage: storage, fetch() { throw Error('Notes must never be transmitted'); } });
  return { panels, data };
}

test('save and restore the dated note as plain text', () => {
  const { panels: [panel], data } = run();
  panel.input.value = '<script>private words</script>';
  panel.input.fire('input');
  assert.match(panel.status.textContent, /Unsaved/);
  panel.save.fire('click');
  assert.equal(JSON.parse(data.get(prefix + '2026-10-03')).note, panel.input.value);
  const restored = run({ stored: Object.fromEntries(data) });
  assert.equal(restored.panels[0].input.value, '<script>private words</script>');
  assert.match(restored.panels[0].status.textContent, /Saved/);
});
test('clear affects only this date and leaves other site storage alone', () => {
  const { panels: [panel], data } = run({ stored: { [prefix + '2026-10-02']: 'older', unrelated: 'keep' } });
  panel.input.value = 'Today'; panel.save.fire('click'); panel.clear.fire('click');
  assert.equal(data.has(prefix + '2026-10-03'), false);
  assert.equal(data.get(prefix + '2026-10-02'), 'older');
  assert.equal(data.get('unrelated'), 'keep');
  assert.equal(panel.input.value, '');
});
test('today and its trail entry share saved notes without overwriting another draft', () => {
  const { panels: [today, trail], data } = run({ dates: ['2026-10-03', '2026-10-03'] });
  today.input.value = 'First thought'; today.save.fire('click');
  assert.equal(trail.input.value, 'First thought');
  trail.input.value = 'Unfinished draft'; trail.input.fire('input');
  today.input.value = 'Second thought'; today.save.fire('click');
  assert.equal(trail.input.value, 'Unfinished draft');
  assert.equal(JSON.parse(data.get(prefix + '2026-10-03')).note, 'Second thought');
  assert.match(trail.status.textContent, /draft remains/);
});
test('storage failure keeps draft visible and reports that it was not saved', () => {
  const { panels: [panel] } = run({ blocked: true });
  assert.equal(panel.controls.hidden, false);
  panel.input.value = 'Keep these words'; panel.save.fire('click');
  assert.equal(panel.input.value, 'Keep these words');
  assert.match(panel.status.textContent, /Could not save/);
});
test('corrupt saved data is left untouched until an explicit save or clear', () => {
  const key = prefix + '2026-10-03';
  const { panels: [panel], data } = run({ stored: { [key]: '{broken' } });
  assert.equal(data.get(key), '{broken');
  assert.equal(panel.input.value, '');
  assert.match(panel.status.textContent, /could not be read/);
});
test('invalid dates cannot create arbitrary storage keys and notes are bounded', () => {
  const { panels, data } = run({ dates: ['wrong', '2026-10-03'] });
  assert.equal(panels[0].controls.hidden, true);
  panels[1].input.value = 'a'.repeat(5000); panels[1].save.fire('click');
  assert.equal(JSON.parse(data.get(prefix + '2026-10-03')).note.length, 4000);
});
