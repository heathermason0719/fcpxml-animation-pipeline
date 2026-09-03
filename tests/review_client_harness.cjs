// Execute the shipped inline client. Only the browser DOM/network boundary is doubled.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

class Element {
  constructor(tagName = '') {
    this.tagName = tagName;
    this.dataset = {}; this.children = []; this.hidden = false; this.disabled = false; this.checked = false;
    this.textContent = ''; this.value = ''; this.currentTime = 0; this.paused = true;
    this.classes = new Set();
    this.classList = {toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name)};
    this.listeners = new Map();
  }
  set src(value) { this.source = value; this.currentTime = 0; this.paused = true; }
  get src() { return this.source; }
  set id(value) { this.elementId = value; elements.set(value, this); }
  get id() { return this.elementId; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(type, callback) { this.listeners.set(type, callback); }
  dispatch(type) { return this.listeners.get(type)?.({preventDefault() {}, target: this}); }
}

const elements = new Map();
const get = id => {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
};
const initial = {
  sourceVersion: 'test_V1', manifestSha256: 'manifest-one', cues: [{
    id: 'cue-02', shotNumber: 2, layoutRevision: 1, approvalStatus: 'current', canApprove: true, approvalBlockers: [],
    frames: [
      {id: 'hero', role: 'hero', label: '主审帧', src: 'hero.png', sha256: 'hero-one', comments: []},
      {id: 'aux', role: 'auxiliary', label: '辅助帧', src: 'aux.png', sha256: 'aux-one', comments: []},
    ],
    resolvedTimeline: {start: '8.5s', duration: '6.125s'},
  }],
  stageStatus: {activeContext: 'A13', blockingStage: 'A13', nextEligibleStage: 'A13'},
  demo: {src: 'previews/demo.mp4', sha256: 'hash-one', comments: []},
};
let respond = async () => ({ok: true, json: async () => structuredClone(initial)});
const requests = [];
const context = vm.createContext({
  document: {getElementById: get, createElement: tag => new Element(tag), createTextNode: text => ({textContent: text, children: []})},
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
  const descendants = element => [element, ...element.children.flatMap(descendants)];
  const storyboardForms = () => descendants(get('cues')).filter(element => element.tagName === 'form');
  const bodyOf = form => form.children.find(element => element.tagName === 'textarea');
  const buttonsOf = element => descendants(element).filter(child => child.tagName === 'button');
  const actionRequests = () => requests.filter(request => request.url.startsWith('/api/action/'));
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
    finish({ok: true, json: async () => ({...initial, stageStatus: {...initial.stageStatus, nextEligibleStage: 'A14'}})});
    await pending;
    assert.match(get('stage').textContent, /A14/);
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
  } else if (scenario === 'approval-current-stale') {
    const stale = structuredClone(initial.cues[0]);
    stale.approvalStatus = 'stale';
    const current = {...structuredClone(initial.cues[0]), id: 'cue-03'};
    respond = async () => ({ok: true, json: async () => ({...initial, cues: [stale, current]})});
    await get('refresh').onclick();
    const cards = get('cues').children;
    assert.match(textOf(cards[0]), /stale/);
    assert.equal(buttonsOf(cards[0]).find(button => button.textContent === '批准当前镜头').disabled, false);
    assert.equal(buttonsOf(cards[1]).find(button => button.textContent === '批准当前镜头').disabled, true);
    respond = async () => ({ok: true, json: async () => ({message: '已保存', state: initial})});
    await get('approveCleanStoryboard').onclick();
    assert.deepEqual(JSON.parse(actionRequests().at(-1).options.body).cueIds, ['cue-02']);
  } else if (scenario === 'storyboard-conflict-drafts') {
    const forms = storyboardForms();
    bodyOf(forms[0]).value = '当前主审帧未提交意见';
    bodyOf(forms[1]).value = '另一张辅助帧草稿';
    respond = async () => requests.at(-1).url.startsWith('/api/action/')
      ? {ok: false, status: 409, json: async () => ({error: 'stale Review state'})}
      : {ok: true, json: async () => ({...initial, manifestSha256: 'manifest-two'})};
    await forms[0].dispatch('submit');
    assert.equal(bodyOf(storyboardForms()[0]).value, '当前主审帧未提交意见');
    assert.equal(bodyOf(storyboardForms()[1]).value, '另一张辅助帧草稿');
    assert.match(get('notice').textContent, /stale/);
    assert.equal(actionRequests().length, 1, 'conflict must not automatically retry a write');
    respond = async () => ({ok: true, json: async () => ({message: '评论已保存', state: {...initial, manifestSha256: 'manifest-three'}})});
    await storyboardForms()[0].dispatch('submit');
    const saved = JSON.parse(actionRequests().at(-1).options.body);
    assert.equal(saved.manifestSha256, 'manifest-two');
    assert.equal(saved.cueId, 'cue-02');
    assert.equal(saved.frameId, 'hero');
    assert.equal(bodyOf(storyboardForms()[0]).value, '');
    assert.equal(bodyOf(storyboardForms()[1]).value, '另一张辅助帧草稿');
  } else if (scenario === 'storyboard-refresh-anchor') {
    bodyOf(storyboardForms()[0]).value = '属于旧静帧的意见';
    const changed = structuredClone(initial);
    changed.cues[0].frames[0].sha256 = 'hero-two';
    respond = async () => ({ok: true, json: async () => changed});
    await get('refresh').onclick();
    const form = storyboardForms()[0];
    assert.equal(bodyOf(form).value, '属于旧静帧的意见');
    assert.equal(buttonsOf(form).find(button => button.type === 'submit').disabled, true);
    const before = actionRequests().length;
    await form.dispatch('submit');
    assert.equal(actionRequests().length, before, 'changed frame must not silently receive an old draft');
    assert.match(textOf(get('cues')), /草稿.*旧.*帧/);
    const rebind = buttonsOf(form).find(button => button.type === 'button');
    await rebind.dispatch('click');
    assert.equal(buttonsOf(form).find(button => button.type === 'submit').disabled, false);
    respond = async () => ({ok: true, json: async () => ({message: '评论已保存', state: changed})});
    await form.dispatch('submit');
    assert.equal(JSON.parse(actionRequests().at(-1).options.body).body, '属于旧静帧的意见');
    assert.equal(bodyOf(storyboardForms()[0]).value, '');
  } else if (scenario === 'storyboard-removed-anchor') {
    bodyOf(storyboardForms()[1]).value = '已移除帧仍可复制的草稿';
    const changed = structuredClone(initial);
    changed.cues[0].frames.pop();
    respond = async () => ({ok: true, json: async () => changed});
    await get('refresh').onclick();
    const retained = descendants(get('cues')).find(element => element.value === '已移除帧仍可复制的草稿');
    assert.ok(retained, 'a removed frame draft must remain visibly recoverable');
    assert.match(textOf(get('cues')), /已移除/);
    assert.equal(bodyOf(storyboardForms()[0]).value, '', 'removed auxiliary text must never be rebound to hero');
  } else if (scenario === 'action-network-error-drafts') {
    bodyOf(storyboardForms()[0]).value = '网络错误不能丢意见';
    respond = async () => { throw new Error('offline'); };
    await assert.doesNotReject(() => storyboardForms()[0].dispatch('submit'));
    assert.equal(bodyOf(storyboardForms()[0]).value, '网络错误不能丢意见');
    assert.match(get('notice').textContent, /offline/);
  } else if (scenario === 'demo-conflict-point-draft') {
    player.currentTime = 11;
    get('impactStatic').checked = true;
    respond = async () => {
      if (requests.at(-1).url.startsWith('/api/action/')) {
        player.currentTime = 14;
        return {ok: false, status: 409, json: async () => ({error: 'stale Review state'})};
      }
      return {ok: true, json: async () => ({...initial, manifestSha256: 'manifest-two'})};
    };
    await submit();
    assert.equal(get('demoBody').value, '尚未提交的创作意见');
    assert.equal(get('impactStatic').checked, true);
    assert.equal(get('impactMotion').checked, true);
    respond = async () => actionResponse();
    await submit();
    const payload = JSON.parse(actionRequests().at(-1).options.body);
    assert.equal(payload.timeStart, '11.000s', 'retry must retain the rejected point, not later playback');
    assert.equal(payload.cueId, 'cue-02');
    assert.equal(payload.manifestSha256, 'manifest-two');
    assert.deepEqual(payload.impactScopes, ['static', 'motion']);
  } else if (scenario === 'demo-conflict-range-draft') {
    captureRange();
    get('impactStatic').checked = true;
    respond = async () => requests.at(-1).url.startsWith('/api/action/')
      ? {ok: false, status: 409, json: async () => ({error: 'stale Review state'})}
      : {ok: true, json: async () => ({...initial, manifestSha256: 'manifest-two'})};
    await submit();
    await get('refresh').onclick();
    assert.equal(get('demoBody').value, '尚未提交的创作意见');
    assert.equal(get('useRange').checked, true);
    assert.equal(get('rangeStart').textContent, '00:11.000');
    assert.equal(get('rangeEnd').textContent, '00:14.420');
    assert.equal(get('impactStatic').checked, true);
    assert.equal(get('impactMotion').checked, true);
  } else if (scenario === 'draft-vn-isolation') {
    bodyOf(storyboardForms()[0]).value = 'V1 主审帧草稿';
    respond = async () => ({ok: true, json: async () => ({...initial, sourceVersion: 'test_V2'})});
    await get('refresh').onclick();
    assert.equal(bodyOf(storyboardForms()[0]).value, '', 'draft must not cross the Vn boundary');
    assert.equal(get('demoBody').value, '', 'Demo draft must not cross the Vn boundary');
    respond = async () => ({ok: true, json: async () => initial});
    await get('refresh').onclick();
    assert.equal(bodyOf(storyboardForms()[0]).value, 'V1 主审帧草稿');
    assert.equal(get('demoBody').value, '尚未提交的创作意见');
  } else {
    throw new Error(`Unknown scenario: ${scenario}`);
  }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
