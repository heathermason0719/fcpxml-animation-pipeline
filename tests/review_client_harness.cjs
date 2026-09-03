// Execute the shipped inline client. Only the browser DOM/network boundary is doubled.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

class Element {
  constructor() {
    this.dataset = {}; this.children = []; this.hidden = false; this.disabled = false; this.checked = false;
    this.textContent = ''; this.value = ''; this.currentTime = 0; this.paused = true;
    this.classes = new Set();
    this.classList = {toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name)};
  }
  set src(value) { this.source = value; this.currentTime = 0; this.paused = true; }
  get src() { return this.source; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener() {}
}

const elements = new Map();
const get = id => {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
};
const initial = {
  sourceVersion: 'test_V1', manifestSha256: 'manifest-one', cues: [{
    id: 'cue-02', shotNumber: 2, frames: [], approvalBlockers: [],
    resolvedTimeline: {start: '8.5s', duration: '6.125s'},
  }],
  stageStatus: {activeContext: 'A13', blockingStage: 'A13', nextEligibleStage: 'A13'},
  demo: {src: 'previews/demo.mp4', sha256: 'hash-one', comments: []},
};
let respond = async () => ({ok: true, json: async () => structuredClone(initial)});
const requests = [];
const context = vm.createContext({
  document: {getElementById: get, createElement: () => new Element(), createTextNode: text => ({textContent: text})},
  fetch: async (url, options) => { requests.push({url, options}); return respond(); },
  setTimeout: () => 1, clearTimeout: () => {},
});

async function run() {
  const html = fs.readFileSync(0, 'utf8');
  vm.runInContext(html.match(/<script>([\s\S]*)<\/script>/)[1], context);
  await new Promise(setImmediate); // initial async load
  const player = get('demo');
  player.currentTime = 21.5; player.paused = false;
  get('demoBody').value = '尚未提交的创作意见';
  const scenario = process.argv[2];
  const textOf = element => [element.textContent, ...element.children.map(textOf)].join(' ');
  const submit = () => get('demoComment').onsubmit({preventDefault() {}});
  get('impactMotion').checked = true; get('impactMotion').value = 'motion';
  get('impactStatic').value = 'static';
  const captureRange = () => {
    player.currentTime = 11; get('captureStart').onclick();
    player.currentTime = 14.42; get('captureEnd').onclick();
  };
  const actionResponse = () => {
    const comment = {...JSON.parse(requests.at(-1).options.body), id: 'A13-C0001', status: 'open'};
    return {ok: true, json: async () => ({message: '评论已保存', state: {
      ...initial, demo: {...initial.demo, comments: [comment]},
    }})};
  };

  if (scenario === 'refresh-success') {
    let finish;
    respond = () => new Promise(resolve => { finish = resolve; });
    const pending = get('refresh').onclick();
    assert.equal(get('refresh').disabled, true, 'refresh must expose its pending state');
    finish({ok: true, json: async () => ({...initial, sourceVersion: 'fresh_V1'})});
    await pending;
    assert.match(get('title').textContent, /fresh_V1/);
    assert.equal(get('notice').hidden, false);
    assert.match(get('notice').textContent, /已刷新/);
    assert.equal(requests.at(-1).options?.cache, 'no-store');
    assert.equal(player.currentTime, 21.5);
    assert.equal(player.paused, false);
    assert.equal(get('demoBody').value, '尚未提交的创作意见');
    assert.equal(get('demoView').hidden, false);
    assert.equal(get('refresh').disabled, false);
  } else if (scenario === 'refresh-errors') {
    for (const failure of [
      async () => { throw new Error('offline'); },
      async () => ({ok: false, status: 503, json: async () => ({error: 'temporarily unavailable'})}),
    ]) {
      respond = failure;
      await assert.doesNotReject(() => get('refresh').onclick());
      assert.match(get('notice').textContent, /刷新失败/);
      assert.equal(get('notice').classes.has('error'), true);
      assert.equal(get('refresh').disabled, false);
      assert.match(get('title').textContent, /test_V1/);
      assert.equal(player.currentTime, 21.5);
      assert.equal(get('demoBody').value, '尚未提交的创作意见');
    }
  } else if (scenario === 'refresh-media') {
    const oldSource = player.src;
    respond = async () => ({ok: true, json: async () => ({...initial, demo: {...initial.demo, sha256: 'hash-two'}})});
    await get('refresh').onclick();
    assert.notEqual(player.src, oldSource, 'a new registered hash must replace same-path cached media');
    assert.match(player.src, /hash-two/);
    assert.equal(player.currentTime, 0, 'new demo must not silently inherit old time context');
  } else if (scenario === 'range-submit') {
    captureRange();
    assert.equal(get('useRange').checked, true, 'capturing endpoints must never silently submit a point');
    assert.equal(get('rangePanel').hidden, false);
    assert.equal(get('submitDemoComment').textContent, '提交区间评论');
    player.currentTime = 30; // later playback must not replace captured anchors
    respond = async () => actionResponse();
    await submit();
    const payload = JSON.parse(requests.at(-1).options.body);
    assert.equal(payload.timeStart, '11.000s');
    assert.equal(payload.timeEnd, '14.420s');
    assert.equal(payload.cueId, 'cue-02');
    assert.equal(payload.body, '尚未提交的创作意见');
    assert.equal(payload.manifestSha256, 'manifest-one');
    assert.match(textOf(get('demoComments')), /区间 00:11\.000–00:14\.420/);
    assert.equal(get('demoBody').value, '');
  } else if (scenario === 'range-refresh') {
    respond = async () => ({ok: true, json: async () => ({...initial, demo: {...initial.demo, comments: [{
      id: 'A13-C0001', status: 'open', impactScopes: ['motion'], body: '跨一段时间的意见',
      timeStart: '11.000s', timeEnd: '14.420s',
    }]}})});
    await get('refresh').onclick();
    assert.match(textOf(get('demoComments')), /区间 00:11\.000–00:14\.420/);
  } else if (scenario === 'range-disable') {
    captureRange();
    get('useRange').checked = false;
    get('useRange').onchange({target: get('useRange')});
    assert.equal(get('rangePanel').hidden, true);
    assert.equal(get('rangeStart').textContent, '未设置');
    assert.equal(get('rangeEnd').textContent, '未设置');
    assert.equal(get('submitDemoComment').textContent, '提交当前时间评论');
    player.currentTime = 12;
    respond = async () => actionResponse();
    await submit();
    const payload = JSON.parse(requests.at(-1).options.body);
    assert.equal(payload.timeStart, '12.000s');
    assert.equal(payload.timeEnd, null);
    assert.match(textOf(get('demoComments')), /时间点 00:12\.000/);
  } else if (scenario === 'range-incomplete') {
    player.currentTime = 11; get('captureStart').onclick();
    respond = async () => actionResponse();
    const before = requests.length;
    await submit();
    assert.equal(requests.length, before, 'one endpoint must not fall through to a point comment');
    assert.match(get('log').textContent, /有效的起点和终点/);
    assert.equal(get('demoBody').value, '尚未提交的创作意见');
    player.currentTime = 10; get('captureEnd').onclick();
    await submit();
    assert.equal(requests.length, before, 'reversed endpoints must not be submitted');
  } else {
    throw new Error(`Unknown scenario: ${scenario}`);
  }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
