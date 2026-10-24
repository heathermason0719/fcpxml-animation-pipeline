// Real page boot/refresh with shared browser storage and distinct history entries.
module.exports=async function({scenario,assert,fs,vm,context,elements,byId,storage,requests,version,setData}){
  const ids=['a','b','c'],data=version();
  data.explorations=[];data.conceptDesign={cues:[]};data.concepts=[];
  data.cues=ids.map(id=>({id,title:id,productionMode:'animation',range:{start:'0s',duration:'2s'}}));
  const board=(id,generation)=>({id,title:id,objectId:'object-'+id,storyboardId:`board-${generation}-${id}`,finalAnimationDescription:generation,frames:[{frameId:'hero',artifactId:`frame-${generation}-${id}`,path:`${generation}-${id}.png`,sha256:'a'.repeat(64)}]});
  const video=(id,generation)=>({id:`video-${generation}-${id}`,kind:'cue-preview',path:`${generation}-${id}.mp4`,current:generation==='new',complete:true,cueIds:[id],range:{start:'0s',duration:'2s'},reviewCues:[{id,range:{start:'0s',duration:'2s'}}]});
  data.storyboard={cues:ids.map(id=>board(id,'old')),snapshots:ids.map(id=>board(id,'old')),rounds:[]};
  data.artifacts=ids.map(id=>video(id,'old'));
  for(const id of ids){
    data.concepts.push(...['old','new','alternative'].map(g=>({id:`concept-${g}-${id}`,cueId:id,objectId:'object-'+id,path:`concept-${g}-${id}.png`,idea:g,motion:'Reveal'})));
    data.conceptDesign.cues.push({cueId:id,title:id,objectId:'object-'+id,recommendedId:`concept-new-${id}`,conceptIds:['old','new','alternative'].map(g=>`concept-${g}-${id}`),confirmationProblems:[]});
  }
  setData(data);
  const kind=scenario.includes('animation')?'animation':scenario.includes('concept')?'concept':'storyboard';
  const target=(id,generation,k=kind)=>({versionId:'v1',tab:k==='concept'?'overview':'storyboard',cueId:id,...(k==='concept'?{conceptId:`concept-${generation}-${id}`}:k==='animation'?{artifactId:`video-${generation}-${id}`}:{storyboardId:`board-${generation}-${id}`})});
  const url=(targets,focus=targets[0])=>'?'+new URLSearchParams({...focus,targets:JSON.stringify(targets)});
  const boot=async(search,historyState=null,navigation=historyState?'reload':'navigate')=>{
    elements.clear();
    const ctx=vm.createContext({...context,URLSearchParams,location:{search,hash:''},performance:{getEntriesByType:()=>[{type:navigation}]}});
    ctx.history={state:structuredClone(historyState),replaceState:(value,unused,next)=>{ctx.history.state=structuredClone(value);ctx.location.search=next.slice(next.indexOf('?'))}};
    for(const name of ['review-state.js','review-common.js','review-scenes.js','review-entry.js','review-v3.js'])vm.runInContext(fs.readFileSync('assets/review-v3/'+name,'utf8'),ctx);
    await new Promise(setImmediate);return ctx;
  };
  const reload=ctx=>boot(ctx.location.search,ctx.history.state);
  const shown=(ctx,id,k=kind)=>k==='concept'?ctx.displayedConcept(data.conceptDesign.cues.find(c=>c.cueId===id))?.id:k==='animation'?ctx.cueVideo(ctx.sceneCue(id))?.id:ctx.sceneCue(id)?.storyboardId;
  const expected=(id,g,k=kind)=>(k==='animation'?'video':k==='concept'?'concept':'board')+'-'+g+'-'+id;
  let ctx=await boot(url([target('a','old')]));
  for(const id of ids){if(scenario==='batch-animation-missing-board')await ctx.openReviewTarget(target(id,'old','storyboard'));await ctx.openReviewTarget(target(id,'old'));ctx.setSceneDraft(id,'Original '+id,kind==='concept'?'concept':'production')}
  const drafts=JSON.parse(JSON.stringify(ids.map(id=>ctx.getSceneDraft(id,kind==='concept'?'concept':'production'))));
  if(scenario.includes('legacy')){const key='afterforge-review-v3:reading:v1',saved=JSON.parse(storage.get(key));delete saved.targets;storage.set(key,JSON.stringify(saved))}
  data.editRevision=8;data.storyboard.cues=ids.map(id=>board(id,'new'));data.storyboard.snapshots.push(...ids.map(id=>board(id,'new')));data.artifacts.push(...ids.map(id=>video(id,'new')));
  if(scenario==='batch-animation-missing-board')data.storyboard.snapshots=data.storyboard.snapshots.filter(b=>b.storyboardId!=='board-old-b');
  const targets=ids.map(id=>target(id,'new')),entryUrl=url(targets);

  if(scenario.startsWith('batch-missing')){
    targets[1][kind==='animation'?'artifactId':kind==='concept'?'conceptId':'storyboardId']='missing-'+kind;ctx=await boot(url(targets));
    const check=()=>{assert.match(byId('reviewEntryStatus').textContent,/不可用/);assert.doesNotMatch(byId(kind==='concept'?'brief':'storyboards').innerHTML,kind==='animation'?/old-b\.mp4|new-b\.mp4/:/old-b\.png|new-b\.png/,'missing non-first target cannot display another result');assert.equal(shown(ctx,'a'),expected('a','new'))};
    check();ctx=await reload(ctx);check();await ctx.selectVersion('v1',{preserveTarget:true});check();
    if(kind==='storyboard'){assert.equal(ctx.sceneCue('b').storyboardId,'missing-storyboard');assert.equal(ctx.sceneCue('b').frames.length,0);assert.equal(ctx.sceneCue('b').canConfirm,false,'unavailable target must not borrow current snapshot eligibility')}
    await ctx.openReviewTarget(target('b','new'));assert.doesNotMatch(byId('reviewEntryStatus').textContent,/不可用/);
    assert.deepEqual(JSON.parse(JSON.stringify(ctx.getSceneDraft('b',kind==='concept'?'concept':'production'))),drafts[1]);
    if(kind==='animation')data.artifacts=data.artifacts.filter(a=>a.id!=='video-new-c');
    else if(kind==='concept')data.concepts=data.concepts.filter(c=>c.id!=='concept-new-c');
    else{data.storyboard.snapshots=data.storyboard.snapshots.filter(b=>b.storyboardId!=='board-new-c');data.storyboard.cues[2]=board('c','later')}
    data.editRevision++;
    await ctx.selectVersion('v1',{preserveTarget:true});assert.match(byId('reviewEntryStatus').textContent,/不可用/);assert.doesNotMatch(byId(kind==='concept'?'brief':'storyboards').innerHTML,kind==='animation'?/old-c\.mp4/:/later-c\.png|old-c\.png/);
  }else if(scenario==='batch-alternatives'){
    const mixed=[target('a','new'),target('a','new','animation'),target('b','new','concept'),target('b','alternative','concept'),{versionId:'v1',tab:'preview',artifactId:'video-new-a'},{versionId:'v1',tab:'preview',artifactId:'video-new-b'}];
    ctx=await boot(url(mixed));
    assert.equal(ctx.sceneView('a').mode,'storyboard','first display mode wins within a scene');assert.equal(shown(ctx,'a','animation'),'video-new-a','other mode still receives its explicit result');
    assert.equal(shown(ctx,'b','concept'),'concept-new-b','candidate order is not last-write-wins');assert.equal(byId('media').dataset.artifactId,'video-new-a','one player initially selects the first video');
    ctx.selectSceneMode('a','animation');assert.equal(shown(ctx,'a','animation'),'video-new-a');
    ctx=await boot(url(mixed,mixed[3]));assert.equal(shown(ctx,'b','concept'),'concept-alternative-b','explicit focused candidate wins');
    assert.equal(ctx.sceneView('a').mode,'storyboard');assert.equal(byId('reviewEntryTargets').children.length,mixed.length);
    await ctx.openReviewTarget({versionId:'v1',tab:'preview',artifactId:'video-old-a'});await ctx.openReviewTarget(target('a','new'));
    ctx=await reload(ctx);assert.equal(byId('media').dataset.artifactId,'video-old-a','moving focus to another tab must not lose the historical player selection on reload');
  }else{
    ctx=await boot(entryUrl);
    const checkNew=()=>{for(const id of ids){assert.equal(shown(ctx,id),expected(id,'new'),`${id}: new batch must override earlier reading`);if(kind==='animation')assert.equal(ctx.sceneView(id).mode,'animation')}};
    checkNew();assert.equal(byId('revision').textContent,'编辑版本 8');ctx=await reload(ctx);checkNew();
    // An explicit historical choice remains even after focus moves elsewhere.
    await ctx.openReviewTarget(target('b','old'));await ctx.openReviewTarget(target('a','new'));
    await ctx.selectVersion('v1',{preserveTarget:true});assert.equal(shown(ctx,'b'),expected('b','old'));
    ctx=await reload(ctx);assert.equal(shown(ctx,'b'),expected('b','old'));
    const historicalEntry={search:ctx.location.search,state:structuredClone(ctx.history.state)};
    ctx=await boot(entryUrl);checkNew(); // Same original URL, new navigation, old localStorage.
    ctx=await boot(entryUrl,historicalEntry.state,'navigate');checkNew(); // Chrome can retain state on same-URL navigation.
    ctx=await boot(historicalEntry.search,historicalEntry.state,'back_forward');assert.equal(shown(ctx,'b'),expected('b','old'),'back/reload uses this history entry despite another page changing localStorage');
    for(let i=0;i<ids.length;i++)assert.deepEqual(JSON.parse(JSON.stringify(ctx.getSceneDraft(ids[i],kind==='concept'?'concept':'production'))),drafts[i],'draft target and body are immutable across entry changes');
    storage.delete('afterforge-review-v3:reading:v1');ctx=await boot(entryUrl);checkNew(); // Clean browser control.
  }
  assert.equal(requests.filter(r=>r.options?.method==='POST').length,0,'reading navigation never writes production records');
};
