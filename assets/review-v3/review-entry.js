/* Exact result navigation. Reading choices never change a feedback draft or a production fact. */
let reviewEntryTargets=[],reviewEntrySelection=null,reviewEntryError=null;
let reviewEntryOpening=null;
const reviewDisplayTargets=new Map();
const readingKey=id=>`afterforge-review-v3:reading:${id}`;
function reviewReadingSnapshot(){
  return {readingVersion:2,target:reviewEntrySelection?.versionId===versionId?reviewEntrySelection:null,scenes:[...sceneViews].filter(([key])=>JSON.parse(key)[0]===versionId),targets:[...reviewDisplayTargets.values()].filter(t=>t.versionId===versionId)};
}
function initializeReviewReading(id,entry){
  const saved=typeof history==='undefined'?null:history.state?.afterforgeReviewReading;
  const navigation=typeof performance==='undefined'?null:performance.getEntriesByType?.('navigation')?.[0]?.type;
  // Reload/back restores this entry; fresh navigation applies the URL targets.
  // Chrome may retain history.state on a fresh navigation to the same URL.
  const reading=navigation!=='navigate'&&saved?.versionId===id&&saved.query===location.search&&Array.isArray(saved.reading?.scenes)?saved.reading:null;
  reviewEntryOpening={versionId:id,reading,targets:reading?[]:reviewEntryTargets.length?reviewEntryTargets:entry?[entry]:[]};
}
function saveReviewReading(){
  if(!versionId)return;
  try{localStorage.setItem(readingKey(versionId),JSON.stringify(reviewReadingSnapshot()))}catch{}
}
function restoreReviewReading(){
  const opening=reviewEntryOpening?.versionId===versionId?reviewEntryOpening:null;
  let saved=opening?.reading;try{if(!saved)saved=JSON.parse(localStorage.getItem(readingKey(versionId))||'null')}catch{}
  for(const [key,value] of saved?.scenes||[]){
    const [version,scope,id]=JSON.parse(key);if(version!==versionId||sceneViews.has(key))continue;
    const view={...value};
    // Before v2, rendering the default recommendation also stored conceptId.
    // Only exact saved navigation proves an intentional historical selection.
    if(saved.readingVersion!==2&&view.conceptId&&![saved.target,...(saved.targets||[])].some(t=>t?.versionId===versionId&&t.tab==='overview'&&t.conceptId===view.conceptId&&reviewTargetCue(t)===id))delete view.conceptId;
    sceneViews.set(key,view);
  }
  for(const t of saved?.targets||[])if(t.versionId===versionId&&!reviewDisplayTargets.has(reviewTargetSlot(t)))reviewDisplayTargets.set(reviewTargetSlot(t),t);
  if(!explicitDemoId)explicitDemoId=[...reviewDisplayTargets.values()].find(t=>t.versionId===versionId&&t.tab==='preview')?.artifactId||null;
  if(reviewEntrySelection?.versionId!==versionId)reviewEntrySelection=saved?.target||null;
  if(opening){
    const seen=new Set(),displays=new Set();
    for(const t of opening.targets.flatMap(t=>[t,...legacyVideoSceneTargets(t)])){
      const slot=reviewTargetSlot(t),display=reviewTargetDisplay(t);if(seen.has(slot))continue;seen.add(slot);
      const cue=reviewTargetCue(t),mode=cue?sceneView(cue).mode:null;
      applyReviewTarget(t);
      // A scene may have both a board and a video. Initialize both identities,
      // while keeping its first presentation; the explicit focus wins below.
      if(displays.has(display)&&cue)sceneView(cue).mode=mode;
      displays.add(display);
    }
    reviewEntryOpening=null;
  }
  applyReviewSelection();
}
function legacyVideoSceneTargets(t){
  // Existing CLI links used the shared player for every local result. Recover
  // each scene from that exact video's frozen mapping, never from latest media.
  if(t.tab!=='preview'||!t.artifactId)return [];
  const a=state?.artifacts?.find(a=>a.id===t.artifactId);
  return ['local-preview','cue-preview'].includes(a?.kind)?(a.reviewCues||[]).map(c=>({...t,tab:'storyboard',cueId:c.id})):[];
}
function reviewTargetCue(t){return t.cueId||(t.conceptId?state?.concepts?.find(c=>c.id===t.conceptId)?.cueId:t.storyboardId?sceneCueByStoryboard(t.storyboardId)?.id:null)}
function reviewTargetDisplay(t){return JSON.stringify([t.versionId,t.tab,t.tab==='preview'?'player':reviewTargetCue(t)||t.conceptId||t.storyboardId||t.artifactId])}
function reviewTargetSlot(t){return JSON.stringify([reviewTargetDisplay(t),t.tab==='preview'?'preview':t.conceptId?'concept':t.storyboardId?'storyboard':t.artifactId?'animation':'cue'])}
function reviewTargetError(t){
  if(!t||t.versionId!==versionId)return null;
  if(t.conceptId){
    const card=conceptCues().find(c=>c.conceptIds.includes(t.conceptId)),concept=state.concepts?.find(c=>c.id===t.conceptId);
    if(!card||!concept||(t.cueId&&card.cueId!==t.cueId))return '指定概念图不可用，未打开其他候选。';
  }else if(t.storyboardId){
    const board=sceneCueByStoryboard(t.storyboardId);
    if(!board||(t.cueId&&board.id!==t.cueId)||(t.frameId&&!board.frames?.some(f=>f.frameId===t.frameId)))return '指定分镜或静帧不可用，未打开其他快照。';
  }else if(t.artifactId){
    const artifact=state.artifacts?.find(a=>a.id===t.artifactId&&isVideoArtifact(a));
    if(!artifact||(t.tab==='storyboard'&&(!t.cueId||!artifact.reviewCues?.some(c=>c.id===t.cueId))))return '指定视频不可用，未打开其他视频。';
  }else if(t.cueId&&!state.cues?.some(c=>c.id===t.cueId))return '指定场景不可用，未打开其他场景。';
  return null;
}
function applyReviewTarget(t){
  if(!t||t.versionId!==versionId)return null;
  reviewDisplayTargets.set(reviewTargetSlot(t),t);
  const id=reviewTargetCue(t),view=id?sceneView(id):null;
  if(t.conceptId&&view)view.conceptId=t.conceptId;
  else if(t.storyboardId&&view)Object.assign(view,{storyboardId:t.storyboardId,frameId:t.frameId||(view.storyboardId===t.storyboardId?view.frameId:null),mode:'storyboard'});
  else if(t.artifactId){if(t.tab==='preview')explicitDemoId=t.artifactId;else if(view)Object.assign(view,{artifactId:t.artifactId,mode:'animation'})}
  return reviewTargetError(t);
}
function applyReviewSelection(){
  if(reviewEntrySelection)for(const t of legacyVideoSceneTargets(reviewEntrySelection))applyReviewTarget(t);
  reviewEntryError=applyReviewTarget(reviewEntrySelection);
}
function reviewSceneError(id,tab){
  const kind=tab==='overview'?'concept':sceneView(id).mode==='animation'?'animation':'storyboard';
  const t=[...reviewDisplayTargets.values()].find(t=>t.versionId===versionId&&t.tab===tab&&reviewTargetCue(t)===id&&(kind==='concept'?t.conceptId:kind==='animation'?t.artifactId:t.storyboardId));
  return reviewTargetError(t);
}
function reviewUnavailableScene(id,title,tab,error){
  return `<article class="${tab==='overview'?'concept':'storyboard'}-card scene-card" id="${tab==='overview'?'concept':'frames'}-${esc(id)}"><h3>${esc(title||id)}</h3><p class="empty" role="status">${esc(error)}</p><p class="muted">已保留原有意见草稿及定位。</p></article>`;
}
function renderReviewEntry(){
  const nav=$('reviewEntryTargets');nav.replaceChildren();nav.hidden=reviewEntryTargets.length<2;
  reviewEntryTargets.forEach((t,i)=>{const button=document.createElement('button');button.type='button';button.textContent=`${i+1}. ${t.conceptId?'概念图':t.storyboardId?'分镜':'视频'} · ${t.cueId||t.conceptId||t.artifactId||t.storyboardId}`;button.onclick=()=>openReviewTarget(t);nav.append(button)});
  reviewEntryError=reviewTargetError(reviewEntrySelection);
  const errors=[...reviewDisplayTargets.values()].filter(t=>t.versionId===versionId).map(t=>({t,error:reviewTargetError(t)})).filter(x=>x.error);
  $('reviewEntryStatus').textContent=errors.map(({t,error})=>`${reviewTargetCue(t)||t.artifactId||t.storyboardId||t.conceptId||''}：${error}`).join(' ');$('reviewEntryStatus').hidden=!errors.length;
  if(reviewEntryError){const panel={overview:'brief',storyboard:'storyboards',preview:'media'}[reviewEntrySelection?.tab];if(panel)$(panel).innerHTML=`<div class="empty">${esc(reviewEntryError)}</div>`;if(panel==='media')delete $('media').dataset.artifactId;}
}
function syncReviewUrl(){
  if(typeof history==='undefined'||!history.replaceState||typeof URLSearchParams==='undefined')return;
  const selection=reviewEntrySelection||{versionId,tab:activeTab},params=new URLSearchParams();for(const [key,value] of Object.entries(selection))if(value)params.set(key,value);
  if(reviewEntryTargets.length>1&&reviewEntryTargets.every(t=>t.versionId===selection.versionId))params.set('targets',JSON.stringify(reviewEntryTargets));
  const query='?'+params;
  history.replaceState({...history.state,afterforgeReviewReading:{versionId,query,reading:reviewReadingSnapshot()}},'','/'+query);
}
function rememberReviewTarget(t){reviewEntrySelection={versionId,...t};reviewDisplayTargets.set(reviewTargetSlot(reviewEntrySelection),reviewEntrySelection);reviewEntryError=null;saveReviewReading();syncReviewUrl();renderReviewEntry()}
async function openReviewTarget(t){
  if(!t.conceptId&&$('frameLightbox').open){$('frameLightbox').close();clearConceptGallery()}
  reviewEntrySelection={...t};
  if(t.versionId!==versionId)await selectVersion(t.versionId);
  else {applyReviewSelection();renderState()}
  activateTab(t.tab||'overview');renderReviewEntry();saveReviewReading();syncReviewUrl();
  if(reviewEntryError)return false;
  if(t.conceptId)openConceptPreview(t.conceptId);
  else if(t.storyboardId||t.cueId)jumpToStoryboardCue(t.cueId||sceneCueByStoryboard(t.storyboardId)?.id);
  else if(t.artifactId)jumpToTime(playingArtifact()?.range?.start||'0s',t.artifactId);
  return true;
}
function sceneCueByStoryboard(id){return [...(state.storyboard?.snapshots||[]),...(state.storyboard?.cues||[])].find(c=>c.storyboardId===id)}
function displayedStoryboardCues(){
  const cards=[...(state?.storyboard?.cues||[])];
  for(const [key,view] of sceneViews){const [version,scope,id]=JSON.parse(key);if(version!==versionId||scope!=='production'||!view.storyboardId)continue;
    const exact=sceneCueByStoryboard(view.storyboardId),index=cards.findIndex(c=>c.id===id);
    if(index>=0){
      if(exact)cards[index]=exact;
      else if(view.mode==='animation')continue; // A missing old board cannot hide an explicitly selected video.
      else if(reviewSceneError(id,'storyboard'))cards[index]={...cards[index],storyboardId:view.storyboardId,frames:[],current:false,canConfirm:false,productionProblems:[{code:'missing-storyboard'}]};
      else cards.splice(index,1);
    }else if(exact)cards.push(exact);
  }
  return cards;
}
