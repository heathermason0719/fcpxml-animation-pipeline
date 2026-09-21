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
let withStoryboard=false;
let boardId='board-a';
const realStatusPath=process.argv[3];
const realStatus=realStatusPath?JSON.parse(fs.readFileSync(realStatusPath,'utf8')):null;
function projectData(){if(realStatus)return {projectId:realStatus.identity.projectId,title:'项目',episodes:[{id:realStatus.identity.episodeId,title:realStatus.identity.episodeTitle,versions:[{id:realStatus.identity.versionId,title:realStatus.identity.versionTitle,root:'x',legacy:false}]}]};return {projectId:'p',title:'项目',episodes:[{id:'e',title:'第一集',versions:[{id:'v1',title:'V1',root:'x',legacy:false}]}]}}
const version = () => ({
  identity:{projectId:'p',episodeId:'e',versionId:'v1',episodeTitle:'第一集',versionTitle:'V1'}, editRevision:revision,
  brief:{summary:'本集概览',segments:[]}, cues:withStoryboard?[{id:'cue-a',title:'开场',range:{start:'0s'}}]:[], artifacts:[{id:'demo',kind:'full-preview',path:'previews/demo.mp4',current:true,complete:!incomplete,missingCueIds:incomplete?['cue-a','cue-b']:[],range:{start:localPreview?'5/2s':'12s'}}],
  storyboard:withStoryboard?{cues:[{id:'cue-a',title:'开场',narration:'旁白锚点',finalAnimationDescription:'标题进入后停留。',storyboardId:boardId,canConfirm:true,firstConfirmed:false,frames:[{frameId:'hero',role:'hero',label:'主审帧',artifactId:'frame-a',path:'frames/a.png',sha256:'a'.repeat(64),current:true}]}],rounds:[]}:undefined, workScopeCueIds:withStoryboard?['cue-a']:undefined,
  explorations:withStoryboard?[{id:'explore-a',question:'开场形式？',description:'可选视觉探索',variants:[{id:'variant-a',label:'文字优先',description:'先出现标题',references:[],artifactIds:[]}]}]:[],
  reviewSet:{id:'review-7'}, feedback:[], deliveries:[], tasks:[], legacy:false,
  availableActions:['update','preview','approve','authorize','approve-and-deliver','deliver'],
});
const context = vm.createContext({
  document:{getElementById:byId,querySelectorAll:()=>[],createElement:()=>new Element()},
  Option:function(text,value){const x=new Element();x.textContent=text;x.value=value;return x;},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  crypto:{randomUUID:()=>`id-${requests.length}`},
  setInterval:()=>1,clearInterval:()=>{},setTimeout:fn=>{fn();return 1},
  fetch:async(url,options)=>{requests.push({url,options}); if(url==='/api/project') return {ok:true,json:async()=>projectData()}; if(url.startsWith('/api/state')) return {ok:true,json:async()=>realStatus||version()}; const request=options?.body&&JSON.parse(options.body).request; return {ok:true,json:async()=>request?.operation==='feedback'?{status:'saved',record:{id:'feedback-saved'}}:{status:'started',requestId:'x'}};},
});

async function main() {
  vm.runInContext(fs.readFileSync('assets/review-v3/review-v3.js','utf8'),context);
  await new Promise(setImmediate);
  const scenario=process.argv[2];
  if(scenario==='empty-version') {
    assert.match(byId('media').innerHTML,/video/);
    const normalFetch=context.fetch;
    context.fetch=async(url,options)=>url==='/api/state?version=v2'?{ok:true,json:async()=>({...version(),artifacts:[],cues:[]})}:normalFetch(url,options);
    await context.selectVersion('v2');
    assert.doesNotMatch(byId('media').innerHTML,/video|previews\/demo/);
    assert.equal(byId('feedbackTarget').textContent,'整个版本');
  } else if(scenario==='notes-and-intent') {
    withStoryboard=true; await context.selectVersion('v1');
    const cue={id:'cue-a',objectId:'object-a',storyboardId:'b',title:'S01 开场',narration:'旁白',finalAnimationDescription:'总体描述',frames:[
      {frameId:'b',label:'先出现'}, {frameId:'a',label:'再停留'}, {frameId:'c',label:'无说明'}],animationNotes:[
      {id:'n1',frameIds:['a','b'],text:'一条跨帧说明'}, {id:'n2',frameIds:['b'],text:'共享前帧'}]};
    const html=context.storyboardCueHtml(cue);
    assert.equal(html.split('一条跨帧说明').length,2);
    assert.ok(html.indexOf('一条跨帧说明')>html.indexOf('再停留'));
    assert.ok(html.indexOf('一条跨帧说明')<html.indexOf('无说明'));
    assert.ok(html.indexOf('总体描述')<html.indexOf('先出现'));
    assert.match(html,/对应帧 01、02/);
    assert.equal((html.match(/data-comment-key=/g)||[]).length,3);
    assert.match(context.esc('" onclick="evil'),/&quot; onclick=&quot;evil/);
    const key=context.commentKey(cue,cue.frames[0]);
    assert.equal(context.commentIsOpen(key),true);
    context.rememberCommentOpen(key,false);
    assert.equal(context.commentIsOpen(key),false);
    assert.equal(context.commentKey({...cue,storyboardId:'new'},cue.frames[0]),key);
    assert.equal(context.commentIsOpen(context.commentKey({...cue,objectId:'new'},cue.frames[0])),true);
    await context.selectVersion('v2');
    assert.equal(context.commentIsOpen(context.commentKey(cue,cue.frames[0])),true);
  } else if(scenario==='actions') {
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
  } else if(scenario==='storyboard-round') {
    withStoryboard=true; await context.selectVersion('v1');
    assert.match(byId('storyboards').innerHTML,/旁白锚点/);
    assert.match(byId('storyboards').innerHTML,/最终动画说明/);
    assert.match(byId('explorations').innerHTML,/文字优先/);
    context.toggleConfirmDesignCue('cue-a');
    await context.confirmSelectedDesigns();
    let request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body);
    assert.equal(request.action,'update');
    assert.equal(request.request.operation,'decision');
    assert.equal(request.request.kind,'confirm-design');
    assert.deepEqual(request.request.storyboardIds,['board-a']);
    assert.match(byId('storyboards').innerHTML,/确认所选设计（0）/);
    context.setStoryboardDraft('cue-a','board-a','hero','固定主标题的位置');
    await context.saveStoryboardFeedback('cue-a','board-a','hero');
    context.setStoryboardDraft('cue-a','board-a','hero','本轮剩余意见');
    await context.submitStoryboardRound();
    request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body);
    assert.equal(request.request.operation,'review-submit');
    assert.equal(request.request.storyboardIds[0],'board-a');
    assert.deepEqual(request.request.feedbackIds,['feedback-saved']);
    assert.deepEqual(request.request.drafts[0].target,{versionId:'v1',cueIds:['cue-a'],artifactId:'frame-a',storyboardId:'board-a',frameId:'hero'});
    assert.doesNotMatch(byId('storyboards').innerHTML, /<textarea[^>]*>本轮剩余意见<\/textarea>/);
    await context.runAction('preview','生成完整预览');
    request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body);
    assert.equal(request.action,'preview');
    assert.equal(request.request.scope,'full');
    assert.equal(request.request.requestId,request.request.decision.taskId);
    assert.equal(request.request.taskId,request.request.decision.taskId);
    assert.deepEqual(request.request.workCueIds,['cue-a']);
    assert.deepEqual(request.request.excludedCueIds,[]);
    assert.equal(request.request.decision.kind,'authorize-demo');
    assert.deepEqual(request.request.decision.cueIds,['cue-a']);
    assert.deepEqual(request.request.decision.presentationCueIds,['cue-a']);
  } else if(scenario==='selection-identity') {
    withStoryboard=true; await context.selectVersion('v1');
    context.toggleConfirmDesignCue('cue-a');
    context.setStoryboardDraft('cue-a','board-a','hero','仅第一版的意见');
    await context.saveStoryboardFeedback('cue-a','board-a','hero');
    boardId='board-v2'; await context.selectVersion('v2');
    assert.match(byId('storyboards').innerHTML,/确认所选设计（0）/);
    const before=requests.filter(item=>item.url==='/api/action').length;
    await context.confirmSelectedDesigns();
    assert.equal(requests.filter(item=>item.url==='/api/action').length,before,'version switch must require a new selection');
    await context.submitStoryboardRound();
    let request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body).request;
    assert.deepEqual(request.feedbackIds,[],'previous-version feedback cannot join this round');
    await new Promise(setImmediate);
    context.toggleConfirmDesignCue('cue-a');
    await context.selectVersion('v2');
    assert.match(byId('storyboards').innerHTML,/确认所选设计（1）/,'unchanged design keeps the selection');
    boardId='board-v2-new-design'; await context.selectVersion('v2');
    assert.match(byId('storyboards').innerHTML,/确认所选设计（0）/,'updated design requires a new selection');
  } else if(scenario==='version-draft') {
    byId('feedbackBody').value='第一版的定位意见';context.saveDraft();
    await context.selectVersion('v2');
    assert.equal(byId('feedbackBody').value,'','new version must not inherit the old draft');
    byId('feedbackBody').value='第二版的定位意见';context.saveDraft();
    await context.selectVersion('v1');
    assert.equal(byId('feedbackBody').value,'第一版的定位意见');
    await context.selectVersion('v2');
    assert.equal(byId('feedbackBody').value,'第二版的定位意见');
    await context.selectVersion('v1');
    const normalFetch=context.fetch;let release;
    context.fetch=async(url,options)=>url==='/api/action'?new Promise(resolve=>{requests.push({url,options});release=()=>resolve({ok:true,json:async()=>({status:'saved'})})}):normalFetch(url,options);
    const save=context.submitFeedback({preventDefault(){}});
    await new Promise(setImmediate);await context.selectVersion('v2');
    release();await save;context.fetch=normalFetch;
    assert.equal(byId('feedbackBody').value,'第二版的定位意见','late general feedback response must preserve v2');
  } else if(scenario==='late-response') {
    withStoryboard=true;
    const normalFetch=context.fetch;
    for(const action of ['save','confirm','handoff']){
      await context.selectVersion('v1');
      context.setStoryboardDraft('cue-a','board-a','hero','第一版的草稿');
      let release;
      context.fetch=async(url,options)=>url==='/api/action'?new Promise(resolve=>{requests.push({url,options});release=()=>resolve({ok:true,json:async()=>({status:'saved',record:{id:'saved-v1'}})})}):normalFetch(url,options);
      let pending;
      if(action==='save')pending=context.saveStoryboardFeedback('cue-a','board-a','hero');
      else if(action==='confirm'){context.toggleConfirmDesignCue('cue-a');pending=context.confirmSelectedDesigns()}
      else pending=context.submitStoryboardRound();
      await new Promise(setImmediate);
      await context.selectVersion('v2');
      context.setStoryboardDraft('cue-a','board-a','hero','第二版的新草稿');
      context.toggleConfirmDesignCue('cue-a');
      release();await pending;await new Promise(setImmediate);
      context.fetch=normalFetch;
      assert.equal(context.currentStoryboardDrafts()[0]?.body,'第二版的新草稿',`${action} response must not remove v2 draft`);
      assert.match(byId('storyboards').innerHTML,/确认所选设计（1）/,`${action} response must not clear v2 selection`);
      await context.submitStoryboardRound();
      const sent=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body);
      assert.equal(sent.version,'v2');
      assert.deepEqual(sent.request.feedbackIds,[],'late v1 feedback must not leak into v2');
      assert.equal(sent.request.drafts[0].body,'第二版的新草稿');
      await new Promise(setImmediate);
    }
  } else if(scenario==='real-status') {
    assert.ok(realStatus,'real-status needs a model.status fixture');
    const cue=realStatus.storyboard.cues[0],frame=cue.frames[0];
    assert.equal(cue.canConfirm,true,'active fixture must expose a confirmable storyboard');
    assert.match(byId('storyboards').innerHTML,new RegExp(cue.narration));
    assert.match(byId('storyboards').innerHTML,new RegExp(frame.label));
    assert.match(byId('storyboards').innerHTML,/最终动画说明/);
    context.toggleConfirmDesignCue(cue.id);
    await context.confirmSelectedDesigns();
    let request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body).request;
    assert.deepEqual(request.storyboardIds,[cue.storyboardId]);
    context.setStoryboardDraft(cue.id,cue.storyboardId,frame.frameId,'真实状态帧级意见');
    await context.saveStoryboardFeedback(cue.id,cue.storyboardId,frame.frameId);
    context.setStoryboardDraft(cue.id,cue.storyboardId,frame.frameId,'留给本轮提交的意见');
    await context.submitStoryboardRound();
    request=JSON.parse(requests.filter(item=>item.url==='/api/action').at(-1).options.body).request;
    assert.deepEqual(request.feedbackIds,['feedback-saved']);
    assert.deepEqual(request.drafts[0].target,{versionId:realStatus.identity.versionId,cueIds:[cue.id],artifactId:frame.artifactId,storyboardId:cue.storyboardId,frameId:frame.frameId});
  } else throw new Error(`unknown scenario ${scenario}`);
}
main().catch(error=>{console.error(error);process.exitCode=1});
