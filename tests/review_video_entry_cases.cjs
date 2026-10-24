// Exercise the actual Python handoff query/status at the page boundary.
module.exports=async function({assert,fs,vm,context,elements,byId,storage,requests,data}){
  const {cueIds:ids,oldIds,newIds,query}=data.testCase,versionId=data.identity.versionId;
  const target=(i,artifactId)=>({versionId,tab:'storyboard',cueId:ids[i],artifactId});
  const url=(targets,focus=targets[0])=>'?'+new URLSearchParams({...focus,targets:JSON.stringify(targets)});
  const boot=async(search,historyState=null,navigation=historyState?'reload':'navigate')=>{
    elements.clear();
    const ctx=vm.createContext({...context,URLSearchParams,location:{search,hash:''},performance:{getEntriesByType:()=>[{type:navigation}]}});
    ctx.history={state:structuredClone(historyState),replaceState:(value,unused,next)=>{ctx.history.state=structuredClone(value);ctx.location.search=next.slice(next.indexOf('?'))}};
    for(const name of ['review-state.js','review-common.js','review-scenes.js','review-entry.js','review-v3.js'])vm.runInContext(fs.readFileSync('assets/review-v3/'+name,'utf8'),ctx);
    await new Promise(setImmediate);return ctx;
  };
  const reload=ctx=>boot(ctx.location.search,ctx.history.state);
  const shown=(ctx,i)=>ctx.cueVideo(ctx.sceneCue(ids[i]))?.id;
  const checkNew=ctx=>ids.forEach((id,i)=>{
    assert.equal(shown(ctx,i),newIds[i],`${id}: actual CLI entry must replace the saved old movie`);
    assert.equal(ctx.sceneView(id).mode,'animation');
    assert.match(ctx.productionSceneHtml(ctx.sceneCue(id)),new RegExp('New film '+id),'video must show its own description, not the old storyboard or later prose');
    assert.match(ctx.productionSceneHtml(ctx.sceneCue(id)),new RegExp('New narration '+id));
  });
  const entries=['?'+new URLSearchParams(query),url(newIds.map(artifactId=>({versionId,tab:'preview',artifactId})))];
  for(const entry of entries){
    storage.clear();let ctx=await boot(url(oldIds.map((id,i)=>target(i,id))));
    ids.forEach(id=>ctx.setSceneDraft(id,'Keep old feedback '+id));
    const drafts=JSON.stringify(ids.map(id=>ctx.getSceneDraft(id)));
    ctx=await boot(entry);checkNew(ctx);ctx=await reload(ctx);checkNew(ctx);
    await ctx.selectVersion(versionId,{preserveTarget:true});checkNew(ctx);
    await ctx.openReviewTarget(target(1,oldIds[1]));await ctx.openReviewTarget(target(0,newIds[0]));
    ctx=await reload(ctx);assert.equal(shown(ctx,1),oldIds[1]);
    assert.match(ctx.productionSceneHtml(ctx.sceneCue(ids[1])),new RegExp('Old film '+ids[1]));
    assert.equal(JSON.stringify(ids.map(id=>ctx.getSceneDraft(id))),drafts,'old feedback keeps its exact video/time/body');
    ctx=await boot(entry,ctx.history.state,'navigate');checkNew(ctx);
  }
  // Previously rendered media has no text snapshot. Never borrow an old board's prose.
  for(const a of data.artifacts)for(const c of a.reviewCues||[]){delete c.finalAnimationDescription;delete c.narration}
  let ctx=await boot(entries[0]);
  assert.match(ctx.productionSceneHtml(ctx.sceneCue(ids[0])),new RegExp('Later text '+ids[0]));
  assert.match(ctx.productionSceneHtml(ctx.sceneCue(ids[0])),/当前制作说明/);
  await ctx.openReviewTarget(target(1,oldIds[1]));
  assert.doesNotMatch(ctx.productionSceneHtml(ctx.sceneCue(ids[1])),/Later text|标题进入后/);
  assert.match(ctx.productionSceneHtml(ctx.sceneCue(ids[1])),/未保存.*说明/);
  assert.equal(requests.filter(r=>r.options?.method==='POST').length,0);
};
