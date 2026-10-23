/* Exact result navigation. Reading choices never change a feedback draft or a production fact. */
let reviewEntryTargets=[],reviewEntrySelection=null,reviewEntryError=null;
const readingKey=id=>`afterforge-review-v3:reading:${id}`;
function saveReviewReading(){
  if(!versionId)return;
  try{localStorage.setItem(readingKey(versionId),JSON.stringify({target:reviewEntrySelection?.versionId===versionId?reviewEntrySelection:null,scenes:[...sceneViews].filter(([key])=>JSON.parse(key)[0]===versionId)}))}catch{}
}
function restoreReviewReading(){
  let saved;try{saved=JSON.parse(localStorage.getItem(readingKey(versionId))||'null')}catch{}
  for(const [key,value] of saved?.scenes||[])if(JSON.parse(key)[0]===versionId&&!sceneViews.has(key))sceneViews.set(key,value);
  if(reviewEntrySelection?.versionId!==versionId)reviewEntrySelection=saved?.target||null;
  applyReviewSelection();
}
function applyReviewSelection(){
  reviewEntryError=null;const t=reviewEntrySelection;if(!t||t.versionId!==versionId)return;
  if(t.conceptId){
    const card=conceptCues().find(c=>c.conceptIds.includes(t.conceptId)),concept=state.concepts?.find(c=>c.id===t.conceptId);
    if(!card||!concept||(t.cueId&&card.cueId!==t.cueId))reviewEntryError='指定概念图不可用，未打开其他候选。';
    else sceneView(card.cueId).conceptId=t.conceptId;
  }else if(t.storyboardId){
    const board=[...(state.storyboard?.snapshots||[]),...(state.storyboard?.cues||[])].find(b=>b.storyboardId===t.storyboardId);
    if(!board||(t.cueId&&board.id!==t.cueId)||(t.frameId&&!board.frames?.some(f=>f.frameId===t.frameId)))reviewEntryError='指定分镜或静帧不可用，未打开其他快照。';
    else {const view=sceneView(board.id);Object.assign(view,{storyboardId:t.storyboardId,frameId:t.frameId||(view.storyboardId===t.storyboardId?view.frameId:null),mode:'storyboard'})}
  }else if(t.artifactId){
    const artifact=state.artifacts?.find(a=>a.id===t.artifactId&&isVideoArtifact(a));
    if(!artifact||(t.tab==='storyboard'&&(!t.cueId||!artifact.reviewCues?.some(c=>c.id===t.cueId))))reviewEntryError='指定视频不可用，未打开其他视频。';
    else if(t.tab==='storyboard')Object.assign(sceneView(t.cueId),{artifactId:t.artifactId,mode:'animation'});
    if(t.tab==='preview')explicitDemoId=t.artifactId;
  }else if(t.cueId&&!state.cues?.some(c=>c.id===t.cueId))reviewEntryError='指定场景不可用，未打开其他场景。';
}
function renderReviewEntry(){
  const nav=$('reviewEntryTargets');nav.replaceChildren();nav.hidden=reviewEntryTargets.length<2;
  reviewEntryTargets.forEach((t,i)=>{const button=document.createElement('button');button.type='button';button.textContent=`${i+1}. ${t.conceptId?'概念图':t.storyboardId?'分镜':'视频'} · ${t.cueId||t.conceptId||t.artifactId||t.storyboardId}`;button.onclick=()=>openReviewTarget(t);nav.append(button)});
  $('reviewEntryStatus').textContent=reviewEntryError||'';$('reviewEntryStatus').hidden=!reviewEntryError;
  if(reviewEntryError){const panel={overview:'brief',storyboard:'storyboards',preview:'media'}[reviewEntrySelection?.tab];if(panel)$(panel).innerHTML=`<div class="empty">${esc(reviewEntryError)}</div>`;if(panel==='media')delete $('media').dataset.artifactId;}
}
function syncReviewUrl(){
  if(typeof history==='undefined'||!history.replaceState||typeof URLSearchParams==='undefined')return;
  const selection=reviewEntrySelection||{versionId,tab:activeTab},params=new URLSearchParams();for(const [key,value] of Object.entries(selection))if(value)params.set(key,value);
  if(reviewEntryTargets.length>1&&reviewEntryTargets.every(t=>t.versionId===selection.versionId))params.set('targets',JSON.stringify(reviewEntryTargets));
  history.replaceState(null,'','/?'+params);
}
function rememberReviewTarget(t){reviewEntrySelection={versionId,...t};reviewEntryError=null;saveReviewReading();syncReviewUrl();renderReviewEntry()}
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
    if(index>=0){if(exact)cards[index]=exact;else cards.splice(index,1)}else if(exact)cards.push(exact);
  }
  return cards;
}
