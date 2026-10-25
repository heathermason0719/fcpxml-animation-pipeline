// Use the real page boot and reading persistence, not a replacement selector.
module.exports=async function({scenario,assert,fs,vm,context,elements,byId,storage,requests,version,setData}){
  const data=version(),ids=['a','b','c'];
  data.concepts=[];data.conceptDesign={cues:[]};data.explorations=[];
  data.cues=ids.map(id=>({id,title:id,productionMode:'animation'}));
  for(const id of ids){
    data.concepts.push(...['old','new'].map(g=>({id:`${g}-${id}`,cueId:id,objectId:'object-'+id,path:`${g}-${id}.png`,sha256:g+id,idea:g+' idea',motion:g+' motion'})));
    data.conceptDesign.cues.push({cueId:id,title:id,objectId:'object-'+id,recommendedId:`old-${id}`,conceptIds:[`old-${id}`,`new-${id}`],confirmationProblems:[]});
  }
  setData(data);
  const target=id=>({versionId:'v1',tab:'overview',cueId:id,conceptId:'old-'+id});
  const rootUrl='?versionId=v1&tab=overview';
  const boot=async(search=rootUrl,historyState=null,navigation=historyState?'reload':'navigate')=>{
    elements.clear();
    const ctx=vm.createContext({...context,URLSearchParams,location:{search,hash:''},performance:{getEntriesByType:()=>[{type:navigation}]}});
    ctx.history={state:structuredClone(historyState),replaceState:(value,unused,next)=>{ctx.history.state=structuredClone(value);ctx.location.search=next.slice(next.indexOf('?'))}};
    for(const name of ['review-state.js','review-common.js','review-scenes.js','review-entry.js','review-v3.js'])vm.runInContext(fs.readFileSync('assets/review-v3/'+name,'utf8'),ctx);
    await new Promise(setImmediate);return ctx;
  };
  const reload=ctx=>boot(ctx.location.search,ctx.history.state);
  const card=id=>data.conceptDesign.cues.find(c=>c.cueId===id);
  const shown=(ctx,id)=>ctx.displayedConcept(card(id))?.id;
  const newRecommendation=()=>{for(const id of ids)card(id).recommendedId='new-'+id;data.editRevision++};
  let ctx;
  if(scenario==='concept-reading-default'){
    ctx=await boot();assert.equal(shown(ctx,'a'),'old-a');
    ctx.setSceneDraft('a','Keep this note on the old image','concept');
    const draft=JSON.parse(JSON.stringify(ctx.getSceneDraft('a','concept')));
    ctx.saveReviewReading();newRecommendation();
    await ctx.selectVersion('v1',{preserveTarget:true});
    const check=()=>{for(const id of ids)assert.equal(shown(ctx,id),'new-'+id);assert.match(ctx.conceptCardHtml(card('a')),/new-a\.png/);assert.match(ctx.conceptCardHtml(card('a')),/new motion/);assert.deepEqual(JSON.parse(JSON.stringify(ctx.getSceneDraft('a','concept'))),draft)};
    check();ctx=await reload(ctx);check();ctx=await boot();check();
    const entry=structuredClone(ctx.history.state);ctx=await boot(ctx.location.search,entry,'back_forward');check();
  }else if(scenario==='concept-reading-explicit'){
    ctx=await boot();ctx.openConceptPreview('old-b');
    ctx.setSceneDraft('b','Historical image note','concept');ctx.saveReviewReading();
    const draft=JSON.parse(JSON.stringify(ctx.getSceneDraft('b','concept')));
    newRecommendation();await ctx.selectVersion('v1',{preserveTarget:true});
    assert.equal(shown(ctx,'a'),'new-a');assert.equal(shown(ctx,'b'),'old-b');
    ctx=await reload(ctx);assert.equal(shown(ctx,'b'),'old-b');
    await ctx.selectVersion('v2');assert.equal(shown(ctx,'b'),'new-b');assert.equal(ctx.getSceneDraft('b','concept'),undefined);
    await ctx.selectVersion('v1');assert.equal(shown(ctx,'b'),'old-b');assert.deepEqual(JSON.parse(JSON.stringify(ctx.getSceneDraft('b','concept'))),draft);
    ctx=await boot('?'+new URLSearchParams({...target('b'),conceptId:'new-b'}));assert.equal(shown(ctx,'b'),'new-b');
    assert.deepEqual(JSON.parse(JSON.stringify(ctx.getSceneDraft('b','concept'))),draft);
  }else if(scenario==='concept-reading-legacy'){
    // Only a and b have evidence of an intentional selection. c's stale id
    // could have been written by the old default renderer; do not infer intent.
    const scenes=ids.map(id=>[JSON.stringify(['v1','production',id]),{mode:'animation',frameId:'hero',videoTime:1.25,conceptId:'old-'+id}]);
    storage.set('afterforge-review-v3:reading:v1',JSON.stringify({scenes,target:target('a'),targets:[target('b')]}));
    const draft={cueId:'c',scope:'concept',body:'Old unsubmitted note',target:{versionId:'v1',cueIds:['c'],conceptId:'old-c'},label:'Old image',identity:'oldc'};
    storage.set('afterforge-review-v3:scene-drafts:v1',JSON.stringify([draft]));
    newRecommendation();ctx=await boot();
    const check=()=>{assert.equal(shown(ctx,'a'),'old-a');assert.equal(shown(ctx,'b'),'old-b');assert.equal(shown(ctx,'c'),'new-c');assert.equal(ctx.sceneView('c').mode,'animation');assert.equal(ctx.sceneView('c').frameId,'hero');assert.equal(ctx.sceneView('c').videoTime,1.25);assert.deepEqual(JSON.parse(JSON.stringify(ctx.getSceneDraft('c','concept'))),draft)};
    check();ctx.saveReviewReading();ctx=await reload(ctx);check();
  }else if(scenario==='concept-reading-no-recommendation'){
    delete card('a').recommendedId;
    card('a').confirmationProblems=[{code:'missing-concept',message:'已有候选，尚未指定推荐。'}];
    ctx=await boot();
    assert.equal(shown(ctx,'a'),undefined);
    const html=ctx.conceptCardHtml(card('a'));assert.match(html,/尚未指定推荐/);assert.doesNotMatch(html,/请先生成或导入/);assert.match(html,/data-concept-preview="old-a"/);
    ctx.openConceptPreview('old-a');assert.equal(shown(ctx,'a'),'old-a');
  }else if(scenario==='concept-reading-missing'){
    ctx=await boot('?'+new URLSearchParams(target('a')));newRecommendation();data.concepts=data.concepts.filter(c=>c.id!=='old-a');
    await ctx.selectVersion('v1',{preserveTarget:true});
    assert.match(byId('reviewEntryStatus').textContent,/指定概念图不可用/);assert.doesNotMatch(ctx.conceptCardHtml(card('a')),/new-a\.png/);
    ctx=await reload(ctx);assert.match(byId('reviewEntryStatus').textContent,/指定概念图不可用/);
  }else throw new Error('unknown concept reading case: '+scenario);
  assert.equal(requests.filter(r=>r.options?.method==='POST').length,0,'reading and migration must not write production facts');
};
