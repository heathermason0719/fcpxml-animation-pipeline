// Exercise Review v3 behavior at the DOM/network boundary without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.children=[]; this.dataset={}; this.value=''; this.checked=false; this.hidden=false; this.disabled=false; this._textContent=''; this.className=''; this.listeners={}; }
  set textContent(value) { this._textContent=String(value??''); } get textContent() { return this._textContent; }
  set innerHTML(value) { this.html=value; this.video=String(value).includes('<video') ? new Element() : null; } get innerHTML() { return this.html ?? this.textContent.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }
  querySelector(selector) { return selector==='video' ? this.video : null; }
  replaceChildren(...items) { this.children=items; }
  append(...items) { this.children.push(...items); }
  add(item) { this.children.push(item); }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  setAttribute(name,value) { (this.attributes ||= {})[name]=String(value); }
  showModal() { this.open=true; }
  close() { this.open=false; }
  pause() {this.paused=true;}
  play() {this.paused=false;this.playCalls=(this.playCalls||0)+1;return Promise.resolve();}
  focus() {}
  scrollIntoView() {}
  classList = {toggle() {}};
}
const elements = new Map();
const byId = id => { if (!elements.has(id)) elements.set(id,new Element()); return elements.get(id); };
const storage = new Map();
const requests=[];let uuidSequence=0;
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
  crypto:{randomUUID:()=>`id-${++uuidSequence}`},
  setInterval:()=>1,clearInterval:()=>{},setTimeout:fn=>{fn();return 1},
  fetch:async(url,options)=>{requests.push({url,options}); if(url==='/api/project') return {ok:true,json:async()=>projectData()}; if(url.startsWith('/api/state')) {const data=realStatus||version();if(!realStatus)data.identity.versionId=new URL(url,'http://review.test').searchParams.get('version');return {ok:true,json:async()=>data};} const request=options?.body&&JSON.parse(options.body).request; return {ok:true,json:async()=>request?.operation==='feedback'?{status:'saved',record:{id:'feedback-saved'}}:{status:'started',requestId:'x'}};},
});

async function main() {
  for(const name of ['review-state.js','review-common.js','review-scenes.js','review-v3.js'])vm.runInContext(fs.readFileSync('assets/review-v3/'+name,'utf8'),context);
  await new Promise(setImmediate);
  const scenario=process.argv[2];
  if(scenario==='thread-delivery') {
    // Removed delivery DOM must never be dereferenced while loading or switching versions.
    context.document.getElementById=id=>['delivery','deliveries'].includes(id)?null:byId(id);
    await context.selectVersion('v1');context.activateTab('preview');await context.selectVersion('v2');
    const data=version();data.identity.versionId='v2';data.reviewSet={id:'review-7',inputKey:'input-a',artifactIds:['demo']};
    context.fetch=async(url,options)=>url.startsWith('/api/state')?{ok:true,json:async()=>structuredClone(data)}:{ok:true,json:async()=>({status:'started'})};
    await context.selectVersion('v2');context.openDeliveryConfirmation();assert.equal(byId('deliveryConfirmDialog').open,true);assert.match(byId('deliveryConfirmContent').textContent,/review-7/);
    assert.equal(requests.filter(r=>r.url==='/api/action').length,0,'loading and inspecting Demo confirmation never starts delivery');
  } else if(scenario==='saved-mutation-refresh-failure') {
    withStoryboard=true;const data=version();data.concepts=[{id:'c1',round:1,objectId:'o',cueId:'cue-a',path:'one.png',sha256:'a',idea:'一'},{id:'c2',round:1,objectId:'o',cueId:'cue-a',path:'two.png',sha256:'b',idea:'二'}];
    data.conceptDesign={cues:[{cueId:'cue-a',title:'场景A',objectId:'o',recommendedId:'c1',firstConfirmed:false,canConfirm:true,conceptIds:['c1','c2'],confirmationProblems:[]}]};
    const posts=[];let failRefresh=false;
    context.fetch=async(url,options)=>{if(url.startsWith('/api/state')){if(failRefresh)throw new Error('refresh unavailable');return {ok:true,json:async()=>structuredClone(data)}}const payload=JSON.parse(options.body);posts.push(payload);failRefresh=true;return {ok:true,json:async()=>({editRevision:++data.editRevision,record:{id:'server-receipt-'+posts.length}})}};
    for(const operation of ['confirm','adopt','scene']){
      failRefresh=false;await context.selectVersion('v1');const before=posts.length;
      const invoke=()=>operation==='confirm'?context.confirmConcepts(['c1']):operation==='adopt'?context.adoptConcept('c2'):context.confirmSceneReview('cue-a');
      assert.equal(await invoke(),true,`${operation} reports saved despite refresh failure`);
      const message=operation==='scene'?context.productionSceneHtml(data.storyboard.cues[0]):byId('conceptActionStatus').textContent;
      assert.match(message,/已保存.*刷新失败/,`${operation} distinguishes the actual write receipt`);assert.doesNotMatch(message,/确认未完成|采用未完成|原选择保持/);
      assert.equal(posts.length,before+1);assert.equal(await invoke(),true);assert.equal(posts.length,before+1,'retry refresh never creates a new mutation');
    }
  } else if(scenario==='concept-storyboard-handoff') {
    const data=version();data.concepts=[{id:'ca',round:1,objectId:'oa',cueId:'a',path:'a.png'},{id:'cb',round:1,objectId:'ob',cueId:'b',path:'b.png'}];
    data.conceptDesign={cues:['a','b'].map(id=>({cueId:id,title:'场景'+id,objectId:'o'+id,recommendedId:'c'+id,confirmedId:'c'+id,firstConfirmed:true,canConfirm:false,conceptIds:['c'+id],confirmationProblems:[]}))};
    const posts=[];let release;context.fetch=async(url,options)=>{if(url.startsWith('/api/state')){const next=structuredClone(data);next.identity.versionId=new URL(url,'http://review.test').searchParams.get('version');return {ok:true,json:async()=>next}}const payload=JSON.parse(options.body);posts.push(payload);return new Promise(resolve=>{release=()=>{data.conceptDesign.storyboardHandoff={id:'handoff-1',requestId:payload.request.requestId,current:true,selected:[{cueId:'a',objectId:'oa',conceptId:'ca'}],excluded:[{cueId:'b',objectId:'ob',conceptId:'cb'}]};resolve({ok:true,json:async()=>({editRevision:++data.editRevision,record:data.conceptDesign.storyboardHandoff})})}})};
    await context.selectVersion('v1');assert.match(byId('brief').innerHTML,/确认方案，继续制作分镜/);assert.match(fs.readFileSync('assets/review-v3/index.html','utf8'),/id="confirmConceptProduction"[^>]*>确认方案，继续制作分镜</);context.openConceptProduction();vm.runInContext("conceptProduction.selected.delete('b')",context);context.renderConceptProductionScope();assert.match(byId('conceptProductionMessage').textContent,/本次制作：场景a；暂不制作：场景b/);
    const first=context.submitConceptProduction();await new Promise(setImmediate);
    assert.equal(posts.length,1,'all-confirmed selection still persists exactly one handoff');assert.equal(await context.submitConceptProduction(),false);assert.equal(posts[0].request.operation,'concept-handoff');assert.deepEqual(posts[0].request.cueIds,['a']);assert.deepEqual(posts[0].request.conceptIds,['ca']);assert.deepEqual(posts[0].request.excludedCueIds,['b']);
    release();assert.equal(await first,true);await context.selectVersion('v1');assert.match(byId('conceptActionStatus').textContent,/方案和本次制作范围已保存。回到对话后可继续制作分镜。/);assert.match(byId('conceptActionStatus').textContent,/本次制作：场景a；暂不制作：场景b/);assert.doesNotMatch(byId('conceptActionStatus').textContent,/Motion|权威|交棒/);assert.match(byId('conceptActionStatus').textContent,/场景a/);assert.match(byId('conceptActionStatus').textContent,/场景b/);
    context.openConceptProduction();const late=context.submitConceptProduction();await new Promise(setImmediate);await context.selectVersion('v2');context.openConceptProduction();release();await late;assert.equal(byId('conceptProductionDialog').open,true,'late handoff receipt preserves the next version dialog');
    await context.selectVersion('v1');context.openConceptProduction();let attempts=0;const retryIds=[];context.fetch=async(url,options)=>{if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data)};const request=JSON.parse(options.body).request;retryIds.push(request.requestId);if(++attempts===1)throw new Error('write disconnected');return {ok:true,json:async()=>({editRevision:data.editRevision})}};
    assert.equal(await context.submitConceptProduction(),false);assert.match(byId('conceptProductionMessage').textContent,/暂未确认保存结果.*write disconnected/,'failed request explanation remains visible');assert.equal(await context.submitConceptProduction(),true);assert.equal(retryIds[0],retryIds[1],'retry retains the request identity');
  } else if(scenario==='candidate-selection') {
    const data=version();data.concepts=[{id:'c1',round:1,objectId:'o',cueId:'a',path:'one.png',sha256:'a',idea:'第一稿',origin:{kind:'codex-generated'}},{id:'c2',round:1,objectId:'o',cueId:'a',path:'two.png',sha256:'b',idea:'第二稿',origin:{kind:'codex-generated'}}];
    data.conceptDesign={cues:[{cueId:'a',title:'场景A',objectId:'o',recommendedId:'c1',confirmedId:null,firstConfirmed:false,canConfirm:true,conceptIds:['c1','c2'],segmentIds:[],confirmationProblems:[]}]};
    const posts=[];context.fetch=async(url,options)=>{if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data)};const req=JSON.parse(options.body).request;posts.push(req);data.editRevision++;data.conceptDesign.cues[0].recommendedId=req.conceptId;return {ok:true,json:async()=>({editRevision:data.editRevision})}};
    await context.selectVersion('v1');context.openConceptPreview('c2');
    assert.equal(posts.length,0,'browsing has no effect');
    assert.equal(typeof context.adoptConcept,'function');
    await context.adoptConcept('c2');assert.equal(posts.length,1);assert.equal(posts[0].action,'propose');assert.equal(posts[0].kind,undefined);
    assert.equal(data.conceptDesign.cues[0].firstConfirmed,false,'selection must not confirm');
    data.conceptDesign.cues[0].firstConfirmed=true;data.conceptDesign.cues[0].confirmedId='c2';await context.selectVersion('v1');
    assert.equal(await context.adoptConcept('c1'),false,'confirmed change requires a visible second decision');assert.equal(posts.length,1);
    await context.adoptConcept('c1',{acceptRevision:true});assert.equal(posts.length,2);assert.equal(posts[1].action,'select');assert.ok(posts[1].source.text.includes('重新确认'));assert.equal(posts[1].adopt,undefined);
  } else if(scenario==='scene-anchor-progress') {
    withStoryboard=true;const data=version();data.conceptDesign={cues:[]};const cue=data.storyboard.cues[0];cue.reviewInputKey='review-a';cue.productionProblems=[];cue.frames.push({...cue.frames[0],frameId:'second',artifactId:'frame-b',path:'frames/b.png'});data.artifacts.push(...cue.frames.map(f=>({...f,id:f.artifactId,kind:'storyboard-frame'})));
    const posts=[];context.fetch=async(url,options)=>{if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data)};const payload=JSON.parse(options.body);posts.push(payload);data.editRevision++;return {ok:true,json:async()=>({editRevision:data.editRevision,record:{id:'saved',status:'pending',body:payload.request.body,target:payload.request.target}})}};
    await context.selectVersion('v1');context.activateTab('storyboard');assert.equal(typeof context.setSceneDraft,'function');
    context.setSceneDraft('cue-a','第一帧要慢一点');context.selectSceneFrame('cue-a','second');context.setSceneDraft('cue-a','第一帧要慢一点，停久一点');
    assert.equal(context.getSceneDraft('cue-a').target.frameId,'hero');
    await context.saveSceneFeedback('cue-a');assert.equal(posts[0].request.target.frameId,'hero');assert.equal(posts[0].request.operation,'feedback');
    await context.confirmSceneReview('cue-a');assert.equal(posts[1].request.operation,'scene-review');assert.equal(posts[1].request.kind,'storyboard');assert.equal(posts[1].request.storyboardId,'board-a');assert.equal(posts[1].action,'update');
    assert.ok(posts.every(p=>p.action==='update'),'scene confirmation never starts rendering');
  } else if(scenario==='version-loading-writer') {
    withStoryboard=true;const originalFetch=context.fetch;let release;
    await context.selectVersion('v1');
    context.fetch=async(url,options)=>url==='/api/state?version=v2'?new Promise(resolve=>{release=()=>{const next=version();next.identity.versionId='v2';resolve({ok:true,json:async()=>next})}}):originalFetch(url,options);
    const loading=context.selectVersion('v2');await new Promise(setImmediate);
    const before=requests.filter(r=>r.url==='/api/action').length;
    assert.equal(await context.runAction('preview','生成完整预览'),false,'old displayed state must never authorize the loading version');
    assert.equal(requests.filter(r=>r.url==='/api/action').length,before);
    await assert.rejects(context.postVersionAction('v2',{requestId:'old-dom',expectedRevision:7,operation:'scene-review',kind:'storyboard',cueId:'cue-a',storyboardId:'board-a'}),/读取/);
    release();await loading;await context.runAction('preview','生成完整预览');
    const sent=JSON.parse(requests.filter(r=>r.url==='/api/action').at(-1).options.body);assert.equal(sent.version,'v2');
  } else if(scenario==='dialog-late-version') {
    const data=version();data.reviewSet={id:'review-7',inputKey:'input-a',artifactIds:['demo']};
    data.concepts=[{id:'c1',objectId:'o',cueId:'cue-a',round:1,path:'one.png',sha256:'a',idea:'第一稿'}];
    data.conceptDesign={cues:[{cueId:'cue-a',title:'场景A',objectId:'o',recommendedId:'c1',firstConfirmed:false,canConfirm:true,conceptIds:['c1'],confirmationProblems:[]}]};
    let release;context.fetch=async(url,options)=>{if(url.startsWith('/api/state')){const next=structuredClone(data);next.identity.versionId=new URL(url,'http://review.test').searchParams.get('version');return {ok:true,json:async()=>next}}return new Promise(resolve=>{release=()=>resolve({ok:true,json:async()=>({editRevision:8})})})};
    for(const kind of ['delivery','concept']){
      await context.selectVersion('v1');if(kind==='delivery')context.openDeliveryConfirmation();else context.openConceptProduction();
      const pending=kind==='delivery'?context.submitDeliveryConfirmation():context.submitConceptProduction();await new Promise(setImmediate);
      await context.selectVersion('v2');if(kind==='delivery')context.openDeliveryConfirmation();else context.openConceptProduction();
      release();await pending;
      assert.equal(byId(kind==='delivery'?'deliveryConfirmDialog':'conceptProductionDialog').open,true,`late ${kind} response never closes the next version's dialog`);
      assert.doesNotMatch(byId('conceptActionStatus').textContent,/所选方案已有明确概念确认/,'late confirmation does not declare another version confirmed');
    }
  } else if(scenario==='scene-video-bounds') {
    withStoryboard=true;const data=version();data.conceptDesign={cues:[]};data.cues[0].resolvedTimeline={start:'2s',duration:'2s'};
    data.artifacts[0]={...data.artifacts[0],range:{start:'0s',duration:'10s'},cueIds:['cue-a']};
    context.fetch=async()=>({ok:true,json:async()=>structuredClone(data)});await context.selectVersion('v1');context.selectSceneMode('cue-a','animation');
    const player=new Element();player.currentTime=8;context.document.querySelector=selector=>selector==='[data-scene-video="cue-a"]'?player:null;
    context.setSceneDraft('cue-a','这句在场景之外');assert.equal(context.getSceneDraft('cue-a'),undefined,'outside video time cannot bind the card cue');
    assert.match(context.sceneFeedbackHtml('cue-a','production'),/本场区间/);
    player.currentTime=3;context.setSceneDraft('cue-a','回到本场再留言');assert.equal(context.getSceneDraft('cue-a').target.timeStart,'3s');
  } else if(scenario==='scene-save-failure') {
    withStoryboard=true;const data=version();data.conceptDesign={cues:[]};data.storyboard.cues[0].reviewInputKey='review-a';
    const posts=[];context.fetch=async(url,options)=>{if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data)};posts.push(JSON.parse(options.body));return {ok:false,status:409,json:async()=>({error:'stale edit revision'})}};
    await context.selectVersion('v1');context.setSceneDraft('cue-a','第一帧原意见');
    await context.submitSceneRound('production');assert.equal(posts.length,0,'submission does not silently save drafts');
    assert.equal(await context.saveSceneFeedback('cue-a'),false);assert.equal(posts.length,1);
    assert.equal(context.getSceneDraft('cue-a').body,'第一帧原意见');assert.equal(context.getSceneDraft('cue-a').target.frameId,'hero');
    assert.match(context.sceneFeedbackHtml('cue-a','production'),/保存失败/);
    data.identity.versionId='v2';await context.selectVersion('v2');assert.equal(context.getSceneDraft('cue-a'),undefined,'other version never inherits the draft');
    data.identity.versionId='v1';await context.selectVersion('v1');assert.equal(context.getSceneDraft('cue-a').target.frameId,'hero');
  } else if(scenario==='delivery-dialog') {
    const data=version();data.reviewSet={id:'review-7',inputKey:'input-a',artifactIds:['demo']};const posts=[];
    context.fetch=async(url,options)=>{if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data)};posts.push(JSON.parse(options.body));return {ok:true,json:async()=>({editRevision:++data.editRevision})}};
    await context.selectVersion('v1');context.openDeliveryConfirmation();assert.equal(byId('deliveryConfirmDialog').open,true);assert.match(byId('deliveryConfirmContent').textContent,/review-7/);
    data.reviewSet.id='review-8';await context.submitDeliveryConfirmation();assert.equal(posts.length,0,'changing review set invalidates the visible confirmation');assert.match(byId('deliveryConfirmMessage').textContent,/已经变化/);
    context.openDeliveryConfirmation();byId('feedbackBody').value='尚未保存';await context.submitDeliveryConfirmation();assert.equal(posts.length,0,'drafts are not silently discarded or approved');
    byId('feedbackBody').value='';const submitting=context.submitDeliveryConfirmation();assert.equal(await context.submitDeliveryConfirmation(),false,'duplicate clicks do not create another delivery request');await submitting;assert.equal(posts.length,1);assert.equal(posts[0].action,'deliver');assert.equal(posts[0].request.decision.kind,'approve-and-deliver');assert.equal(posts[0].request.decision.reviewSetId,'review-8');assert.equal(byId('deliveryConfirmDialog').open,false);
  } else if(scenario==='storyboard-production') {
    withStoryboard=true;
    const data=version();data.conceptDesign={cues:[]};
    data.storyboard.cues[0].productionProblems=[];
    data.storyboard.cues.push({...data.storyboard.cues[0],id:'music',title:'五线谱',storyboardId:'music-board',productionDeferred:true});
    data.cues.push({id:'music',title:'五线谱'});
    const posts=[];
    context.fetch=async(url,options)=>{
      if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data)};
      const payload=JSON.parse(options.body);posts.push(payload);
      data.editRevision++;
      data.storyboard.productionRequest={...payload.request,status:'pending'};
      return {ok:true,json:async()=>({editRevision:data.editRevision})};
    };
    await context.selectVersion('v1');
    assert.match(byId('storyboards').innerHTML,/data-storyboard-produce/);
    context.openStoryboardProduction();
    assert.equal(byId('productionDialog').open,true);
    assert.match(byId('productionContent').innerHTML,/五线谱/);
    byId('feedbackBody').value='还没提交';
    assert.equal(await context.submitStoryboardProduction(),false);
    assert.equal(posts.length,0);byId('feedbackBody').value='';
    data.storyboard.cues[0].storyboardId='new-board';
    assert.equal(await context.submitStoryboardProduction(),false);
    assert.equal(posts.length,0);
    context.cancelStoryboardProduction();context.openStoryboardProduction();
    const first=context.submitStoryboardProduction();
    assert.equal(await context.submitStoryboardProduction(),false,'ignore duplicate click');
    assert.equal(await first,true);
    assert.equal(posts.length,1);
    assert.equal(posts[0].action,'update');
    assert.equal(posts[0].request.kind,'authorize-demo');
    assert.deepEqual(posts[0].request.cueIds,['cue-a']);
    assert.deepEqual(posts[0].request.storyboardIds,['new-board']);
    assert.deepEqual(posts[0].request.excludedCueIds,['music']);
    assert.equal(byId('productionDialog').open,false);
    await context.selectVersion('v1');
    assert.match(byId('storyboardActionStatus').textContent,/已交棒/);
    context.openStoryboardProduction();assert.equal(byId('productionDialog').open,false,'pending commission is persistent');
  } else if(scenario==='concept-gallery') {
    const data=version();data.concepts=[
      {id:'old',objectId:'oa',cueId:'a',path:'old.png',idea:'旧稿',origin:{kind:'codex-generated'}},
      {id:'other',objectId:'ob',cueId:'b',path:'other.png',idea:'另一条',origin:{kind:'codex-generated'}},
      {id:'current',objectId:'oa',cueId:'a',path:'current.png',idea:'当前稿',origin:{kind:'codex-generated'}}];
    data.conceptDesign={cues:[
      {cueId:'a',objectId:'oa',title:'花园',recommendedId:'current',conceptIds:['old','current'],firstConfirmed:false,canConfirm:false,confirmationProblems:[{code:'unresolved-feedback',message:'仍有待处理意见'}],segmentIds:[]},
      {cueId:'b',objectId:'ob',title:'码头',recommendedId:'other',conceptIds:['other'],firstConfirmed:true,canConfirm:false,confirmationProblems:[],segmentIds:[]}]};
    context.fetch=async()=>({ok:true,json:async()=>data});await context.selectVersion('v1');
    assert.equal(typeof context.openConceptPreview,'function','concept gallery must provide cue-local navigation');
    context.openConceptPreview('current');
    assert.match(byId('lightboxImage').src,/current.png/);
    assert.equal(byId('previousConcept').disabled,true);
    byId('nextConcept').onclick();assert.match(byId('lightboxImage').src,/old.png/);
    assert.equal(byId('nextConcept').disabled,true);
    byId('nextConcept').onclick();assert.match(byId('lightboxImage').src,/old.png/,'must stop before another cue');
    byId('previousConcept').onclick();assert.match(byId('lightboxImage').src,/current.png/);
    context.openConceptPreview('other');assert.equal(byId('previousConcept').hidden,true);assert.equal(byId('nextConcept').hidden,true);
    context.openConceptPreview('old');context.openFramePreview('静帧','frame.png');
    assert.equal(byId('previousConcept').hidden,true);assert.equal(byId('nextConcept').hidden,true);
    assert.equal(byId('lightboxImage').src,'frame.png');
    const pending=byId('conceptPendingList').innerHTML;
    assert.match(pending,/花园/);assert.match(pending,/仍有待处理意见/);assert.doesNotMatch(pending,/码头/);
    assert.equal(requests.filter(r=>r.options?.method==='POST').length,0,'browsing must not record decisions');
  } else if(scenario==='concept-image-unavailable') {
    assert.equal(realStatus.conceptDesign.cues[0].firstConfirmed,true);
    assert.match(byId('brief').innerHTML,/已确认 · 概念图不可用/);
    assert.match(byId('brief').innerHTML,/图片缺失或内容已变动，请恢复原图片/);
    assert.doesNotMatch(byId('brief').innerHTML,/已确认 · 可进入制作|概念改稿 · 待重新确认/);
    assert.doesNotMatch(byId('brief').innerHTML,/data-select-concept=/,'image loss does not request another confirmation');
  } else if(scenario==='concept-image-restored') {
    assert.equal(realStatus.conceptDesign.cues[0].firstConfirmed,true);
    assert.match(byId('brief').innerHTML,/已确认 · 可进入制作/);
    assert.doesNotMatch(byId('brief').innerHTML,/概念图不可用|图片缺失或内容已变动/);
  } else if(scenario==='concept-version-race') {
    function conceptData(id, count) {
      const data=version();data.identity.versionId=id;data.concepts=[];data.conceptDesign={cues:[]};
      for(let i=0;i<count;i++) {
        const cid=id+'-concept-'+i;data.concepts.push({id:cid,objectId:id+'-object-'+i,path:cid+'.png',sha256:'b'.repeat(64),origin:{kind:i?'codex-generated':'user-imported'},idea:'关系图',motion:'依次出现'});
        data.conceptDesign.cues.push({cueId:'cue-'+i,objectId:id+'-object-'+i,title:'动画'+i,segmentIds:[],contentContext:{},recommendedId:cid,confirmedId:null,firstConfirmed:false,canConfirm:true,confirmationProblems:[],conceptIds:[cid]});
      }
      data.storyboard={cues:[],rounds:[]};return data;
    }
    const data={v1:conceptData('v1',2),v2:conceptData('v2',1)},posts=[],release={};
    context.fetch=async(url,options)=>{
      if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data[new URL(url,'http://localhost').searchParams.get('version')])};
      const payload=JSON.parse(options.body);posts.push(payload);
      return new Promise(resolve=>{release[payload.version]=()=>{data[payload.version].editRevision++;resolve({ok:true,json:async()=>({editRevision:data[payload.version].editRevision})})}});
    };
    await context.selectVersion('v1');
    const first=context.confirmConcepts(data.v1.concepts.map(c=>c.id));await new Promise(setImmediate);
    assert.equal(posts[0].request.kind,'confirm-concept');assert.deepEqual(posts[0].request.conceptIds,['v1-concept-0','v1-concept-1']);
    await context.selectVersion('v2');assert.equal(byId('confirmAllConcepts').disabled,false);
    const second=context.confirmConcepts(['v2-concept-0']);await new Promise(setImmediate);
    assert.equal(posts.length,2,'enabled v2 confirmation must submit despite the v1 write');
    release.v1();await first;
    assert.equal(byId('conceptActionStatus').textContent,'正在保存确认…','v1 receipt must not replace pending v2 receipt');
    release.v2();await second;
    assert.match(byId('conceptActionStatus').textContent,/已确认 1 张/);
    await context.selectVersion('v1');assert.match(byId('conceptActionStatus').textContent,/已确认 2 张/);
  } else if(scenario==='demo-reencoded-feedback') {
    const data=version();data.artifacts[0].inputKey='same-content';data.artifacts.push({...data.artifacts[0],id:'new-encode',createdAt:'2026-09-26'});
    data.artifacts.push({...data.artifacts[0],id:'changed',inputKey:'different',createdAt:'2020-01-01'});
    data.feedback=[{id:'old-note',body:'keep my note',target:{artifactId:'demo',timeStart:'15s'}},{id:'different-note',body:'other',target:{artifactId:'changed'}}];
    context.fetch=async()=>({ok:true,json:async()=>data});await context.selectVersion('v1');
    assert.deepEqual(Array.from(context.demoFeedbackSelection().pending,f=>f.id),['old-note']);
    assert.equal(data.feedback[0].target.artifactId,'demo','retain original evidence binding');
    assert.match(byId('demoFeedbackList').innerHTML,/data-demo-feedback-artifact="new-encode"/);
  } else if(scenario==='demo-auto-time') {
    context.activateTab('preview');const p=byId('media').querySelector('video');p.currentTime=3;p.paused=false;
    byId('feedbackBody').value='first';byId('feedbackBody').oninput();
    assert.equal(byId('timeStart').value,'15s');assert.equal(p.paused,true);
    p.currentTime=9;byId('feedbackBody').value='first more';byId('feedbackBody').oninput();assert.equal(byId('timeStart').value,'15s');
    await context.submitFeedback({preventDefault(){}});assert.equal(byId('timeStart').value,'','next feedback must get its own time');
    byId('feedbackBody').value='second';byId('feedbackBody').oninput();assert.equal(byId('timeStart').value,'21s');
    byId('demoWholeFeedback').checked=true;byId('demoWholeFeedback').onchange();assert.equal(byId('timeStart').value,'');
    byId('feedbackBody').value='whole';byId('feedbackBody').oninput();assert.equal(byId('timeStart').value,'');
    context.restoreDraft();assert.equal(byId('demoWholeFeedback').checked,true);
    await context.submitFeedback({preventDefault(){}});
    const posts=requests.filter(r=>r.url==='/api/action').map(r=>JSON.parse(r.options.body).request);
    assert.equal(posts[0].target.timeStart,'15s');assert.equal(posts[1].target.timeStart,undefined);
    assert.equal(byId('demoWholeFeedback').checked,false);
  } else if(scenario==='demo-withdraw') {
    context.activateTab('preview');const data=version();data.storyboard={rounds:[]};
    data.feedback=[{id:'f1',body:'keep',status:'pending',target:{artifactId:'demo'}},{id:'f2',body:'withdraw me',status:'pending',target:{artifactId:'demo'}}];
    let fail=false,release;const posts=[];
    context.fetch=async(url,options)=>{if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data)};
      const request=JSON.parse(options.body).request;posts.push(request);
      if(fail)return {ok:false,json:async()=>({error:'conflict'})};
      return new Promise(resolve=>{release=()=>{const record=data.feedback.find(f=>f.id===request.feedbackId);record.applicability={kind:request.kind,source:request.source};data.editRevision++;resolve({ok:true,json:async()=>({record:structuredClone(record),editRevision:data.editRevision})})}})};
    await context.selectVersion('v1');
    assert.match(byId('demoFeedbackList').innerHTML,/撤回意见/);
    const saving=context.setDemoFeedbackWithdrawn('f2',true);await new Promise(setImmediate);
    await context.setDemoFeedbackWithdrawn('f2',true);assert.equal(posts.length,1);
    assert.equal(byId('submitDemoRound').disabled,true);
    release();await saving;
    assert.equal(posts[0].operation,'feedback-applicability');assert.equal(posts[0].kind,'not-applicable');
    assert.equal(context.demoFeedbackSelection().pending.length,1);
    assert.doesNotMatch(byId('demoFeedbackList').innerHTML,/withdraw me/);
    assert.match(byId('demoFeedbackHistory').innerHTML,/已撤回/);assert.match(byId('demoFeedbackHistory').innerHTML,/恢复意见/);
    fail=true;await context.setDemoFeedbackWithdrawn('f2',false);
    assert.equal(context.demoFeedbackSelection().pending.length,1);assert.match(byId('demoRoundStatus').textContent,/失败/);
    fail=false;const restoring=context.setDemoFeedbackWithdrawn('f2',false);await new Promise(setImmediate);release();await restoring;
    assert.equal(context.demoFeedbackSelection().pending.length,2);
    data.storyboard.rounds=[{id:'r',feedbackIds:['f2'],status:'submitted'}];await context.selectVersion('v1');
    const withdrawn=context.setDemoFeedbackWithdrawn('f2',true);await new Promise(setImmediate);release();await withdrawn;
    assert.deepEqual(data.storyboard.rounds[0].feedbackIds,['f2'],'withdrawal preserves handoff history');
  } else if(scenario==='demo-capture') {
    context.activateTab('preview');
    const player=byId('media').querySelector('video');player.currentTime=2.5;player.paused=false;
    byId('locateTime').onclick();
    assert.equal(byId('media').querySelector('video'),player,'capture must not replace the player');
    assert.equal(player.paused,true,'capture must pause rather than restart playback');
    assert.equal(player.playCalls||0,0);
    assert.equal(byId('timeStart').value,'29/2s');
    context.jumpToTime('18s');
    assert.equal(byId('timeStart').value,'29/2s','navigation must not retarget the feedback');
    assert.equal(player.currentTime,6);
  } else if(scenario==='demo-save-refresh') {
    context.activateTab('preview');let data=version(),releasePost;const refreshes=[],posts=[];
    context.fetch=async(url,options)=>{if(url.startsWith('/api/state')){const snapshot=structuredClone(data);return new Promise(resolve=>refreshes.push(()=>resolve({ok:true,json:async()=>snapshot})))}
      const payload=JSON.parse(options.body);posts.push(payload);return new Promise(resolve=>{releasePost=()=>{data.editRevision++;const record={id:'f'+data.editRevision,body:payload.request.body,target:payload.request.target,status:'pending'};data.feedback.push(record);resolve({ok:true,json:async()=>({editRevision:data.editRevision,record})})}})};
    byId('feedbackBody').value='first';context.saveDraft();const first=context.submitFeedback({preventDefault(){}});await new Promise(setImmediate);
    await context.submitFeedback({preventDefault(){}});assert.equal(posts.length,1,'double-click during POST must not duplicate feedback');
    releasePost();await new Promise(setImmediate);assert.equal(byId('submitFeedback').disabled,false,'saved receipt must free the editor before slow refresh');
    byId('feedbackBody').value='second';context.saveDraft();const second=context.submitFeedback({preventDefault(){}});await new Promise(setImmediate);
    assert.equal(posts[1].request.expectedRevision,8,'next save uses acknowledged revision');releasePost();await new Promise(setImmediate);
    refreshes[1]();await second;refreshes[0]();await first;
    assert.match(byId('demoFeedbackList').innerHTML,/first/);assert.match(byId('demoFeedbackList').innerHTML,/second/);
    context.fetch=async(url,options)=>url==='/api/action'?{ok:false,status:409,json:async()=>({error:'conflict'})}:{ok:true,json:async()=>data};
    byId('feedbackBody').value='retain on failure';context.saveDraft();await context.submitFeedback({preventDefault(){}});
    assert.equal(byId('feedbackBody').value,'retain on failure');assert.match(byId('message').textContent,/草稿.*保留/);
  } else if(scenario==='demo-space') {
    context.activateTab('preview');const player=byId('media').querySelector('video');player.paused=true;
    let prevented=0;const event=(type,target={},repeat=false)=>({type,code:'Space',target,repeat,preventDefault(){prevented++},stopImmediatePropagation(){}});
    context.handleDemoSpace(event('keydown',{tagName:'BUTTON'}));assert.equal(player.paused,false);
    context.handleDemoSpace(event('keydown',{tagName:'BUTTON'},true));assert.equal(player.paused,false,'held space must not toggle repeatedly');
    context.handleDemoSpace(event('keyup',{tagName:'BUTTON'}));context.handleDemoSpace(event('keydown',{tagName:'BUTTON'}));assert.equal(player.paused,true);
    context.handleDemoSpace(event('keyup',{tagName:'BUTTON'}));
    for(const target of [{tagName:'TEXTAREA'},{tagName:'INPUT',type:'text'},{isContentEditable:true}]){
      const before=prevented;context.handleDemoSpace(event('keydown',target));assert.equal(prevented,before);assert.equal(player.paused,true);
    }
    context.activateTab('storyboard');const before=prevented;context.handleDemoSpace(event('keydown',{tagName:'BUTTON'}));assert.equal(prevented,before);
  } else if(scenario==='demo-artifacts') {
    const data=version();data.artifacts.push({id:'frame',kind:'storyboard-frame',path:'x.png',current:true,range:{start:'0s'},createdAt:'2099'});
    context.fetch=async()=>({ok:true,json:async()=>data});await context.selectVersion('v1');context.activateTab('preview');
    assert.doesNotMatch(byId('artifacts').innerHTML,/storyboard-frame|x.png/);
    assert.match(byId('media').innerHTML,/demo.mp4/);
    byId('message').textContent='saved';data.tasks=[{id:'old',status:'failed',error:'old alpha'}];await context.selectVersion('v1',{preserveTarget:true});
    assert.doesNotMatch(byId('message').textContent,/old alpha/,'historical failure must not overwrite current feedback status');
  } else if(scenario==='demo-round') {
    const data=version();data.storyboard={cues:[],rounds:[]};data.feedback=[
      {id:'movie-note',body:'slower',target:{versionId:'v1',artifactId:'demo'},status:'pending'},
      {id:'board-note',body:'still',target:{versionId:'v1',storyboardId:'board',artifactId:'frame'},status:'pending'}];
    const posts=[];context.fetch=async(url,options)=>{if(url.startsWith('/api/state'))return {ok:true,json:async()=>structuredClone(data)};
      const req=JSON.parse(options.body);posts.push(req);data.editRevision++;data.storyboard.rounds.push({id:'round-demo',feedbackIds:req.request.feedbackIds,storyboardIds:[],status:'submitted'});return {ok:true,json:async()=>({editRevision:data.editRevision,record:data.storyboard.rounds.at(-1)})}};
    await context.selectVersion('v1');context.activateTab('preview');await context.submitDemoRound();
    assert.equal(posts.length,1);assert.equal(posts[0].request.operation,'review-submit');
    assert.deepEqual(posts[0].request.feedbackIds,['movie-note']);assert.deepEqual(posts[0].request.storyboardIds,[]);
    assert.equal(posts[0].request.kind,undefined,'feedback handoff must not approve or authorize');
    await context.submitDemoRound();assert.equal(posts.length,1,'submitted notes must not be handed off twice');
    assert.match(byId('demoFeedbackList').innerHTML,/slower/);assert.doesNotMatch(byId('demoFeedbackList').innerHTML,/still/);
  } else if(scenario==='empty-version') {
    assert.match(byId('media').innerHTML,/video/);
    const normalFetch=context.fetch;
    context.fetch=async(url,options)=>url==='/api/state?version=v2'?{ok:true,json:async()=>({...version(),artifacts:[],cues:[]})}:normalFetch(url,options);
    await context.selectVersion('v2');
    assert.doesNotMatch(byId('media').innerHTML,/video|previews\/demo/);
    assert.equal(byId('feedbackTarget').textContent,'整个版本');
  } else if(scenario==='round-confirmation') {
    withStoryboard=true;
    let data=version();
    const first=data.storyboard.cues[0];
    data.storyboard.cues.push({...first,id:'cue-b',title:'第二组',storyboardId:'board-b'},
      {...first,id:'cue-active',title:'已确认组',storyboardId:'board-active',firstConfirmed:true});
    data.cues.push({id:'source',title:'保留原片',productionMode:'source-only'});
    const posts=[];
    let holdRefresh=null,holdPost=null;
    context.fetch=async(url,options)=>{
      if(url.startsWith('/api/state')){if(holdRefresh)return new Promise(resolve=>{holdRefresh=()=>resolve({ok:true,json:async()=>structuredClone(data)})});return {ok:true,json:async()=>structuredClone(data)}}
      if(url==='/api/action'){
        const body=JSON.parse(options.body);posts.push(body);
        const finish=()=>{data.editRevision++;data.storyboard.cues.forEach(c=>c.firstConfirmed=true);return {ok:true,json:async()=>({editRevision:data.editRevision,record:{id:'batch'}})}};
        if(holdPost)return new Promise(resolve=>{holdPost=()=>resolve(finish())});
        return finish();
      }
      throw new Error('Unexpected request '+url);
    };
    await context.selectVersion('v1');
    assert.match(byId('storyboards').innerHTML,/data-confirm-round/,'global confirmation must be reachable without selecting individual cues');
    context.openRoundDesignConfirmation();
    assert.equal(byId('designConfirmDialog').open,true);
    assert.equal(posts.length,0,'opening the scope summary must not create a decision');
    context.cancelRoundDesignConfirmation();
    await context.submitRoundDesignConfirmation();assert.equal(posts.length,0,'cancelled confirmation must do nothing');
    // Do not silently skip an unconfirmable Cue and report a successful whole round.
    data.storyboard.cues[1].canConfirm=false;
    data.storyboard.cues[1].confirmationProblems=[{code:'unresolved-feedback'}];
    await context.selectVersion('v1');context.openRoundDesignConfirmation();
    await context.submitRoundDesignConfirmation();assert.equal(posts.length,0);
    assert.match(byId('designConfirmContent').innerHTML,/第二组/);
    data.storyboard.cues[1].canConfirm=true;
    data.storyboard.cues[1].confirmationProblems=[];
    await context.selectVersion('v1');
    context.setStoryboardDraft('cue-a','board-a','hero','尚未保存的意见');
    context.openRoundDesignConfirmation();await context.submitRoundDesignConfirmation();
    assert.equal(posts.length,0);assert.equal(context.currentStoryboardDrafts()[0].body,'尚未保存的意见');
    context.setStoryboardDraft('cue-a','board-a','hero','');
    // New immutable board after opening must require another look at the scope.
    context.openRoundDesignConfirmation();data.storyboard.cues[1].storyboardId='board-b-new';
    await context.submitRoundDesignConfirmation();assert.equal(posts.length,0);
    assert.match(byId('designConfirmMessage').textContent,/更新|变化/);
    context.openRoundDesignConfirmation();holdRefresh=true;
    const cancelled=context.submitRoundDesignConfirmation();await new Promise(setImmediate);
    context.cancelRoundDesignConfirmation();holdRefresh();holdRefresh=null;await cancelled;
    assert.equal(posts.length,0,'cancel during refresh must not post a decision');
    // The second click sends exactly the current pending boards as one existing decision.
    context.openRoundDesignConfirmation();holdPost=true;
    const submit=context.submitRoundDesignConfirmation();await new Promise(setImmediate);
    await context.submitRoundDesignConfirmation();assert.equal(posts.length,1);
    assert.deepEqual(posts[0].request.storyboardIds,['board-a','board-b-new']);
    assert.equal(posts[0].request.operation,'decision');assert.equal(posts[0].request.kind,'confirm-design');
    assert.equal(posts[0].action,'update');assert.equal(posts[0].request.decision,undefined,'design confirmation must not authorize a Demo or delivery');
    holdPost();await submit;assert.equal(byId('designConfirmDialog').open,false);
    await context.selectVersion('v1');
    assert.match(byId('storyboardQualificationStatus').textContent,/3.*首次设计确认/,'qualification must be derived from saved state on refresh');
    context.openRoundDesignConfirmation();await context.submitRoundDesignConfirmation();assert.equal(posts.length,1);
    data.storyboard.cues[0].firstConfirmed=false;await context.selectVersion('v1');
    context.openRoundDesignConfirmation();await context.selectVersion('v2');
    await context.submitRoundDesignConfirmation();assert.equal(posts.length,1,'changing version invalidates the open scope');
  } else if(scenario==='notes-and-intent') {
    withStoryboard=true; await context.selectVersion('v1');
    const cue={id:'cue-a',objectId:'object-a',storyboardId:'b',title:'S01 开场',narration:'旁白',finalAnimationDescription:'总体描述',frames:[
      {frameId:'b',label:'先出现',frameNarration:'原声：同一句'}, {frameId:'a',label:'再停留',frameNarration:'<script>unsafe</script>'}, {frameId:'c',label:'无说明'}],animationNotes:[
      {id:'n1',frameIds:['a','b'],text:'一条跨帧说明'}, {id:'n2',frameIds:['b'],text:'共享前帧'}]};
    const html=context.storyboardCueHtml(cue);
    assert.equal(html.split('一条跨帧说明').length,2);
    assert.ok(html.indexOf('一条跨帧说明')>html.indexOf('再停留'));
    assert.ok(html.indexOf('一条跨帧说明')<html.indexOf('无说明'));
    assert.ok(html.indexOf('总体描述')<html.indexOf('先出现'));
    assert.match(html,/对应帧 01、02/);
    assert.match(html,/原声：同一句/);
    assert.match(html,/尚未标注对应旁白/);
    assert.match(html,/&lt;script&gt;unsafe&lt;\/script&gt;/);
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
  } else if(scenario==='frame-save-sequential') {
    withStoryboard=true;
    const baseFetch=context.fetch, reads=[], writes=[], committed=[];
    let serverRevision=7;
    const snapshot=()=>{const s=version();s.editRevision=serverRevision;s.storyboard.cues[0].frames.push({...s.storyboard.cues[0].frames[0],frameId:'second'});return s};
    context.fetch=async(url,options)=>url.startsWith('/api/state')?{ok:true,json:async()=>snapshot()}:baseFetch(url,options);
    await context.selectVersion('v1');
    context.fetch=async(url,options)=>{
      if(url.startsWith('/api/state')){const s=snapshot();return new Promise(resolve=>reads.push(()=>resolve({ok:true,json:async()=>s})))}
      if(url==='/api/action'){
        const request=JSON.parse(options.body).request;
        writes.push(request);
        if(request.expectedRevision!==serverRevision)return {ok:false,status:409,json:async()=>({error:'stale revision'})};
        serverRevision++;committed.push(request.body);
        return {ok:true,json:async()=>({editRevision:serverRevision,record:{id:'saved-'+serverRevision}})};
      }
      return baseFetch(url,options);
    };
    context.setStoryboardDraft('cue-a','board-a','hero','第一帧意见');
    const first=context.saveStoryboardFeedback('cue-a','board-a','hero');
    await new Promise(setImmediate); // Write acknowledged, expensive state refresh still pending.
    context.setStoryboardDraft('cue-a','board-a','second','第二帧意见');
    const second=context.saveStoryboardFeedback('cue-a','board-a','second');
    await new Promise(setImmediate);
    assert.deepEqual(writes.map(w=>w.expectedRevision),[7,8],'next frame must use the acknowledged revision before refresh finishes');
    reads[1]();await second;reads[0]();await first;
    assert.equal(context.requestBase().expectedRevision,9,'late revision-8 refresh must not roll revision 9 back');
    assert.deepEqual(committed,['第一帧意见','第二帧意见']);
    assert.equal(context.currentStoryboardDrafts().length,0);
    // Two clicks before either POST acknowledges must also serialize, without dropping either draft.
    let acknowledge;
    context.fetch=async(url,options)=>{
      if(url.startsWith('/api/state'))return {ok:true,json:async()=>snapshot()};
      if(url==='/api/action'){
        const request=JSON.parse(options.body).request;writes.push(request);
        assert.equal(request.expectedRevision,serverRevision);
        if(!acknowledge)return new Promise(resolve=>{acknowledge=()=>{serverRevision++;resolve({ok:true,json:async()=>({editRevision:serverRevision,record:{id:'fast-first'}})})}});
        serverRevision++;return {ok:true,json:async()=>({editRevision:serverRevision,record:{id:'fast-second'}})};
      }
      return baseFetch(url,options);
    };
    context.setStoryboardDraft('cue-a','board-a','hero','连点第一帧');
    context.setStoryboardDraft('cue-a','board-a','second','连点第二帧');
    const fastFirst=context.saveStoryboardFeedback('cue-a','board-a','hero');
    const fastSecond=context.saveStoryboardFeedback('cue-a','board-a','second');
    await new Promise(setImmediate);
    assert.equal(writes.length,3,'second POST must wait until the first POST acknowledges');
    acknowledge();await Promise.all([fastFirst,fastSecond]);
    assert.deepEqual(writes.map(w=>w.expectedRevision),[7,8,9,10]);
    assert.equal(context.currentStoryboardDrafts().length,0);
  } else if(scenario==='storyboard-buttons') {
    withStoryboard=true;await context.selectVersion('v1');
    const normalFetch=context.fetch;let release;let posts=0;
    context.setStoryboardDraft('cue-a','board-a','hero','本轮修改意见');
    context.fetch=async(url,options)=>url==='/api/action'?new Promise(resolve=>{posts++;release=()=>resolve({ok:true,json:async()=>({editRevision:8,record:{id:'round-one',feedbackIds:['f1'],status:'submitted'}})})}):normalFetch(url,options);
    const submit=context.submitStoryboardRound();
    assert.match(byId('storyboardActionStatus').textContent,/提交中/,'round feedback needs a nearby pending receipt');
    await context.submitStoryboardRound();assert.equal(posts,1,'double click must not submit two rounds');
    release();await submit;
    assert.match(byId('storyboardActionStatus').textContent,/已提交.*1.*待处理/);
    assert.equal(context.requestBase().expectedRevision,8);
    assert.equal(context.currentStoryboardDrafts().length,0);
    context.renderTasks();assert.match(byId('storyboardActionStatus').textContent,/已提交/);
    context.fetch=async(url,options)=>url==='/api/action'?{ok:false,status:409,json:async()=>({error:'stale revision'})}:normalFetch(url,options);
    context.setStoryboardDraft('cue-a','board-a','hero','失败后保留');
    await context.submitStoryboardRound();
    assert.match(byId('storyboardActionStatus').textContent,/未能确认.*stale revision/);
    assert.equal(context.currentStoryboardDrafts()[0].body,'失败后保留');
    context.setStoryboardDraft('cue-a','board-a','hero','');
    await context.confirmSelectedDesigns();assert.match(byId('storyboardActionStatus').textContent,/勾选/);
    context.toggleConfirmDesignCue('cue-a');
    context.fetch=async(url,options)=>url==='/api/action'?{ok:true,json:async()=>({editRevision:9,record:{id:'decision-one'}})}:normalFetch(url,options);
    await context.confirmSelectedDesigns();assert.match(byId('storyboardActionStatus').textContent,/已确认.*1/);
    let previewRequest;
    context.fetch=async(url,options)=>{if(url==='/api/action'){previewRequest=JSON.parse(options.body).request;return {ok:true,json:async()=>({status:'started',requestId:previewRequest.requestId})}}return normalFetch(url,options)};
    await context.previewStoryboards();assert.match(byId('storyboardActionStatus').textContent,/生成中/);
    const before=previewRequest.requestId;await context.previewStoryboards();assert.equal(previewRequest.requestId,before);
    // The generated job ID differs from the request ID; old unrelated failures must not override it.
    revision=10;
    context.fetch=async(url,options)=>url.startsWith('/api/state')?{ok:true,json:async()=>({...version(),tasks:[{id:'old',status:'failed',error:'old failure'},{id:'job-other-id',requestId:before,status:'complete'}]})}:normalFetch(url,options);
    await context.selectVersion('v1');assert.match(byId('storyboardActionStatus').textContent,/静帧已生成/);
    context.fetch=async(url,options)=>{if(url==='/api/action'){previewRequest=JSON.parse(options.body).request;return {ok:true,json:async()=>({status:'started',requestId:previewRequest.requestId})}}return normalFetch(url,options)};
    await context.previewStoryboards();
    context.fetch=async(url,options)=>url.startsWith('/api/state')?{ok:true,json:async()=>({...version(),tasks:[{id:previewRequest.requestId,status:'failed',error:'测试生成失败'}]})}:normalFetch(url,options);
    await context.selectVersion('v1');assert.match(byId('storyboardActionStatus').textContent,/生成失败.*测试生成失败/);
  } else if(scenario==='frame-save-status') {
    withStoryboard=true; await context.selectVersion('v1');
    const html=()=>context.storyboardFrameHtml(version().storyboard.cues[0],version().storyboard.cues[0].frames[0],0);
    await context.saveStoryboardFeedback('cue-a','board-a','hero');
    assert.match(html(),/请先填写/,'empty save must explain why nothing happened next to the frame');
    context.setStoryboardDraft('cue-a','board-a','hero','延长停留');
    const normalFetch=context.fetch; let resolveSave; let posts=0;
    context.fetch=async(url,options)=>{if(url==='/api/action'){posts++;return new Promise(resolve=>resolveSave=resolve)}return normalFetch(url,options)};
    const pending=context.saveStoryboardFeedback('cue-a','board-a','hero');
    assert.match(html(),/disabled[^>]*>保存中/);
    await context.saveStoryboardFeedback('cue-a','board-a','hero');
    assert.equal(posts,1,'double click must not create duplicate feedback');
    resolveSave({ok:true,json:async()=>({record:{id:'feedback-saved'}})});
    await pending;
    context.renderTasks();
    assert.match(html(),/已保存/,'confirmation must remain in the frame after state refresh');
    assert.equal(context.currentStoryboardDrafts().length,0);
    context.setStoryboardDraft('cue-a','board-a','hero','保存中的意见');
    const savingAgain=context.saveStoryboardFeedback('cue-a','board-a','hero');
    context.setStoryboardDraft('cue-a','board-a','hero','保存期间继续输入');
    resolveSave({ok:true,json:async()=>({record:{id:'feedback-newer'}})});
    await savingAgain;
    assert.equal(context.currentStoryboardDrafts()[0].body,'保存期间继续输入');
    assert.match(html(),/上一条反馈已保存.*新修改尚未保存/);
    context.setStoryboardDraft('cue-a','board-a','hero','第二条意见');
    assert.match(html(),/草稿未保存/);
    context.fetch=async(url,options)=>url==='/api/action'?{ok:false,status:409,json:async()=>({error:'版本已更新'})}:normalFetch(url,options);
    await context.saveStoryboardFeedback('cue-a','board-a','hero');
    assert.match(html(),/未能确认保存.*版本已更新/);
    assert.equal(context.currentStoryboardDrafts()[0].body,'第二条意见');
    assert.doesNotMatch(html(),/disabled[^>]*>保存中/);
    context.fetch=async(url,options)=>url==='/api/action'?{ok:true,json:async()=>({record:{id:'feedback-2'}})}:{ok:false,status:500,json:async()=>({error:'刷新失败'})};
    await context.saveStoryboardFeedback('cue-a','board-a','hero');
    assert.match(html(),/已保存.*刷新/,'refresh failure must not say the acknowledged write failed');
    assert.equal(context.currentStoryboardDrafts().length,0);
  } else if(scenario==='actions') {
    assert.match(byId('actions').innerHTML,/生成完整预览/);
    assert.match(byId('actions').innerHTML,/data-action="approve"/);
    assert.doesNotMatch(byId('actions').innerHTML,/data-action="(?:authorize|deliver|approve-and-deliver)"/,'delivery controls stay hidden before approval');
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
