// Exercise Review v3 behavior at the DOM/network boundary without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.children=[]; this.dataset={}; this.value=''; this.checked=false; this.hidden=false; this.disabled=false; this.textContent=''; this.className=''; this.listeners={}; }
  set innerHTML(value) { this.html=value; this.video=String(value).includes('<video') ? new Element() : null; } get innerHTML() { return this.html || this.textContent || ''; }
  querySelector(selector) { return selector==='video' ? this.video : null; }
  replaceChildren(...items) { this.children=items; }
  append(...items) { this.children.push(...items); }
  add(item) { this.children.push(item); }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  classList = {toggle() {}};
}
const elements = new Map();
const byId = id => { if (!elements.has(id)) elements.set(id,new Element()); return elements.get(id); };
const storage = new Map();
const requests=[];
let revision=7;
let incomplete=false;
let localPreview=false;
const version = () => ({
  identity:{projectId:'p',episodeId:'e',versionId:'v1',episodeTitle:'第一集',versionTitle:'V1'}, editRevision:revision,
  brief:{summary:'本集概览',segments:[]}, cues:[], artifacts:[{id:'demo',kind:'full-preview',path:'previews/demo.mp4',current:true,complete:!incomplete,missingCueIds:incomplete?['cue-a','cue-b']:[],range:{start:localPreview?'5/2s':'12s'}}],
  reviewSet:{id:'review-7'}, feedback:[], deliveries:[], tasks:[], legacy:false,
  availableActions:['update','preview','approve','authorize','approve-and-deliver','deliver'],
});
const context = vm.createContext({
  document:{getElementById:byId,querySelectorAll:()=>[],createElement:()=>new Element()},
  Option:function(text,value){const x=new Element();x.textContent=text;x.value=value;return x;},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  crypto:{randomUUID:()=>`id-${requests.length}`},
  setInterval:()=>1,clearInterval:()=>{},setTimeout:fn=>{fn();return 1},
  fetch:async(url,options)=>{requests.push({url,options}); if(url==='/api/project') return {ok:true,json:async()=>({projectId:'p',title:'项目',episodes:[{id:'e',title:'第一集',versions:[{id:'v1',title:'V1',root:'x',legacy:false}]}]})}; if(url.startsWith('/api/state')) return {ok:true,json:async()=>version()}; return {ok:true,json:async()=>({status:'started',requestId:'x'})};},
});

async function main() {
  vm.runInContext(fs.readFileSync('assets/review-v3/review-v3.js','utf8'),context);
  await new Promise(setImmediate);
  const scenario=process.argv[2];
  if(scenario==='actions') {
    assert.match(byId('actions').innerHTML,/生成完整预览/);
    assert.match(byId('actions').innerHTML,/批准当前审阅/);
    assert.doesNotMatch(byId('actions').innerHTML,/undefined/);
    assert.doesNotMatch(byId('actions').innerHTML,/更新/);
  } else if(scenario==='combined') {
    await context.decision('approve-and-deliver','批准并开始交付');
    const request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body);
    assert.equal(request.action,'deliver');
    assert.equal(request.request.decision.kind,'approve-and-deliver');
    assert.equal(request.request.decision.reviewSetId,'review-7');
    assert.equal(request.request.operation,undefined);
  } else if(scenario==='incomplete-preview') {
    incomplete=true; await context.selectVersion('v1');
    assert.match(byId('artifacts').innerHTML,/缺少 cue-a、cue-b/);
    assert.doesNotMatch(byId('artifacts').innerHTML,/处理中/);
    assert.match(byId('media').innerHTML,/media\?version=v1/);
  } else if(scenario==='time-normalization') {
    localPreview=true; await context.selectVersion('v1');
    byId('media').querySelector('video').currentTime=1.25;
    byId('locateTime').onclick();
    assert.equal(byId('timeStart').value,'15/4s');
    assert.equal(byId('media').querySelector('video').currentTime,1.25);
    byId('feedbackBody').value='第一个标题太快';
    await context.submitFeedback({preventDefault(){}});
    const request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body).request;
    assert.equal(request.target.timeStart,'15/4s');
    assert.equal(request.source.text,'第一个标题太快');
    assert.equal(context.normalizeTime('12.5s'),'25/2s');
    assert.equal(context.normalizeTime('5/2s'),'5/2s');
  } else if(scenario==='invalid-time-draft') {
    byId('feedbackBody').value='保留的反馈'; byId('timeStart').value='12.5.1s'; context.saveDraft();
    const before=requests.length; await context.submitFeedback({preventDefault(){}});
    assert.equal(requests.length,before);
    assert.match(byId('message').textContent,/时间必须/);
    assert.ok([...storage.values()].some(value=>JSON.parse(value).body==='保留的反馈'));
  } else if(scenario==='stale-draft') {
    context.choose({artifactId:'demo',cueIds:['cue-a']});
    byId('feedbackBody').value='保留这条定位意见'; context.saveDraft();
    revision=8;
    await context.selectVersion('v1',{preserveTarget:true});
    assert.equal(byId('feedbackForm').disabled,false);
    assert.equal(byId('submitFeedback').disabled,true);
    assert.equal(byId('retargetDraft').hidden,false);
    assert.match(byId('draftNotice').textContent,/7.*8/);
    const before=requests.length;
    await context.submitFeedback({preventDefault(){}});
    assert.equal(requests.length,before,'stale draft must not post against a new revision');
    byId('retargetDraft').onclick();
    assert.equal(byId('submitFeedback').disabled,false);
    await context.submitFeedback({preventDefault(){}});
    const request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body).request;
    assert.equal(request.expectedRevision,8);
    assert.deepEqual(request.target.cueIds,['cue-a']);
    assert.equal(request.target.artifactId,'demo');
  } else throw new Error(`unknown scenario ${scenario}`);
}
main().catch(error=>{console.error(error);process.exitCode=1});
