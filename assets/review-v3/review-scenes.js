/* Scene presentation and review interactions. Persistent facts come from the API;
   these maps contain only reading preferences, drafts and request receipts. */
const sceneViews=new Map(),sceneDrafts=new Map(),sceneWrites=new Set(),sceneMessages=new Map();
const conceptReceipts=new Map(),sceneReviewReceipts=new Map();
let candidateChange=null,conceptProduction=null,deliveryConfirmation=null;
function settleMutationReceipts(version,revision){
  for(const [id,r] of conceptReceipts)if(r.needsRefresh&&id===version&&(!Number.isInteger(r.result.editRevision)||r.result.editRevision<=revision)){r.needsRefresh=false;conceptMessages.set(id,r.message)}
  for(const [key,r] of sceneReviewReceipts)if(r.needsRefresh&&r.versionId===version&&(!Number.isInteger(r.result.editRevision)||r.result.editRevision<=revision)){r.needsRefresh=false;sceneMessages.set(key,r.message)}
}
async function refreshSavedMutation(receipt){
  try{await selectVersion(receipt.versionId,{preserveTarget:true})}
  catch(error){const message=`${receipt.message} 刷新失败：${error.message}。请刷新状态；此次写入无需重复提交。`;if(receipt.sceneKey)sceneMessages.set(receipt.sceneKey,message);else conceptMessages.set(receipt.versionId,message)}
  if(versionId===receipt.versionId){if(receipt.sceneKey)renderStoryboards();else renderConceptActions()}
  return true;
}
const sceneKey=(id,scope='production',version=versionId)=>JSON.stringify([version,scope,id]);
const sceneDraftStorage=version=>`afterforge-review-v3:scene-drafts:${version}`;
function sceneView(id){const key=sceneKey(id);if(!sceneViews.has(key))sceneViews.set(key,{mode:'storyboard',frameId:null});return sceneViews.get(key)}
function sceneCue(id){return storyboardCues().find(c=>c.id===id)}
function sceneFrame(cue){return cue&&(sceneView(cue.id).frameId?cue.frames?.find(f=>f.frameId===sceneView(cue.id).frameId):cue.frames?.[0])}
function displayedConcept(cue){if(!cue)return null;const view=sceneView(cue.cueId);if(!view.conceptId)view.conceptId=cue.recommendedId;return state.concepts?.find(c=>c.id===view.conceptId)}
function cueVideo(cue,{latest=false}={}){
  const view=sceneView(cue.id);if(!latest&&view.artifactId)return state.artifacts?.find(a=>a.id===view.artifactId&&isVideoArtifact(a));
  const source=state.cues?.find(c=>c.id===cue.id),start=demoCueStart(source||{}),end=start+parseTime(source?.resolvedTimeline?.duration||source?.range?.duration||'0s');
  const videos=(state.artifacts||[]).filter(a=>a.current&&isVideoArtifact(a)&&a.cueIds?.includes(cue.id)&&!(a.missingCueIds||[]).includes(cue.id)&&parseTime(a.range?.start||'0s')<=start&&parseTime(a.range?.start||'0s')+parseTime(a.range?.duration||'0s')>=end);
  const chosen=latestArtifact(videos.filter(a=>a.kind==='cue-preview'))||latestArtifact(videos.filter(a=>a.kind==='local-preview'))||latestArtifact(videos.filter(a=>a.kind==='full-preview'));if(chosen&&!latest)view.artifactId=chosen.id;return chosen;
}
function persistSceneDrafts(version=versionId){try{localStorage.setItem(sceneDraftStorage(version),JSON.stringify([...sceneDrafts.values()].filter(d=>d.target.versionId===version)))}catch{}}
function restoreSceneDrafts(){try{for(const d of JSON.parse(localStorage.getItem(sceneDraftStorage(versionId))||'[]'))if(d?.target?.versionId===versionId&&d.body)sceneDrafts.set(sceneKey(d.cueId,d.scope),d)}catch{}}
function getSceneDraft(id,scope='production'){restoreSceneDrafts();return sceneDrafts.get(sceneKey(id,scope))}
function sceneAnchor(id,scope){
  if(scope==='concept'){
    const card=conceptCues().find(c=>c.cueId===id),c=displayedConcept(card);
    if(!c)return null;return {target:{versionId,cueIds:[id],conceptId:c.id},label:`概念图 · ${c.idea}`,identity:c.sha256};
  }
  const cue=sceneCue(id);if(!cue)return null;
  if(sceneView(id).mode==='animation'){
    const a=cueVideo(cue);if(!a)return null;
    const player=document.querySelector?.(`[data-scene-video="${id}"]`);player?.pause();
    const original=a.reviewCues?.find(c=>c.id===id)||(a.current?state.cues.find(c=>c.id===id):null);if(!original)return null;const start=demoCueStart(original),end=start+parseTime(original.resolvedTimeline?.duration||original.range?.duration||'0s');
    const at=parseTime(a.range.start)+(player?.currentTime??Math.max(0,start-parseTime(a.range.start)));
    if(at<start||at>=end){sceneMessages.set(sceneKey(id,scope),'请先回到本场区间再留言；其他场景的意见请到整片 Demo 保存。');return null}
    const time=secondsToTime(at);
    return {target:{versionId,cueIds:[id],artifactId:a.id,timeStart:time},label:`本场动画 · ${formatTime(parseTime(time))}`,identity:a.inputKey};
  }
  const f=sceneFrame(cue);if(!f)return null;
  return {target:{versionId,cueIds:[id],storyboardId:cue.storyboardId,artifactId:f.artifactId,frameId:f.frameId},label:`静帧 · ${f.label||f.frameId}`,identity:cue.reviewInputKey||f.sha256};
}
function setSceneDraft(id,body,scope='production'){
  if(!versionReady())return;
  const key=sceneKey(id,scope),old=getSceneDraft(id,scope);
  if(!String(body).trim())sceneDrafts.delete(key);
  else {const anchor=old||sceneAnchor(id,scope);if(!anchor)return;sceneDrafts.set(key,{...anchor,cueId:id,scope,body:String(body)})}
  persistSceneDrafts();
  const label=document.querySelector?.(`[data-scene-draft-status="${scope}:${id}"]`);
  if(label)label.textContent=body.trim()?`草稿未保存 · 固定在 ${sceneDrafts.get(key).label}`:'';
}
function hasSceneDrafts(scope){restoreSceneDrafts();return [...sceneDrafts.values()].some(d=>d.target.versionId===versionId&&(!scope||d.scope===scope)&&d.body.trim())}
function sceneFeedbackRecords(id,scope){const object=sceneCue(id)?.objectId||conceptCues().find(c=>c.cueId===id)?.objectId;return (state.feedback||[]).filter(f=>(f.target?.objectIds?.includes(object)||f.target?.cueIds?.includes(id)||(scope==='concept'&&state.concepts?.find(c=>c.id===f.target?.conceptId)?.objectId===object))&&(scope==='concept'?!!f.target.conceptId:!f.target.conceptId))}
function conceptLineage(id){const ids=new Set();let c=state.concepts?.find(c=>c.id===id);while(c&&!ids.has(c.id)){ids.add(c.id);const parent=state.concepts.find(p=>p.id===c.copiedFromConceptId);c=parent&&parent.objectId===c.objectId&&parent.sha256===c.sha256&&parent.round<c.round?parent:null}return ids}

function submittedFeedbackIds(){return new Set((state.storyboard?.rounds||[]).flatMap(r=>r.feedbackIds||[]))}
function sceneFeedbackHtml(id,scope){
  const draft=getSceneDraft(id,scope),key=sceneKey(id,scope),submitted=submittedFeedbackIds(),records=sceneFeedbackRecords(id,scope),anchor=sceneAnchorForDisplay(id,scope);
  const current=records.filter(f=>scope==='concept'?conceptLineage(anchor?.conceptId).has(f.target.conceptId):(anchor?.storyboardId&&f.target.storyboardId===anchor.storyboardId)||(anchor?.artifactId&&f.target.artifactId===anchor.artifactId));
  const historical=records.filter(f=>!current.includes(f));
  const note=f=>`<article class="saved-note"><small>${submitted.has(f.id)?'已提交':f.status==='accepted'?'已保存':'已保存 · 待提交'} · ${esc(feedbackStatus[f.status]||f.status)}${f.applicability?.kind&&f.applicability.kind!=='current'?' · '+esc(f.applicability.kind==='deferred'?'已暂缓':'不适用'):''}</small><p>${esc(f.body)}</p><details><summary>原定位与制作回复</summary><p>${esc(f.target.conceptId||f.target.frameId||f.target.artifactId||'整个场景')}${f.target.timeStart?' · '+esc(f.target.timeStart):''}</p><p>${esc(f.resolution||'尚无制作回复')}</p></details>${f.status==='addressed'?`<button data-accept-feedback="${esc(f.id)}">这条已解决</button>`:''}</article>`;
  return `<section class="scene-feedback"><h3>留下修改意见</h3><p class="muted">${esc(draft?`固定位置：${draft.label}`:'开始输入时固定所看图片或视频位置')}</p><textarea data-scene-draft="${esc(id)}" data-scene-scope="${scope}" placeholder="描述希望怎样调整…" ${state.legacy?'disabled':''}>${esc(draft?.body||'')}</textarea><div class="scene-actions"><button data-save-scene="${esc(id)}" data-scene-scope="${scope}" ${sceneWrites.has(key)||state.legacy?'disabled':''}>${sceneWrites.has(key)?'保存中…':'保存意见'}</button></div><p data-scene-draft-status="${scope}:${esc(id)}" role="status">${esc(sceneMessages.get(key)||(draft?'草稿未保存':''))}</p>${current.map(note).join('')}${historical.length?`<details class="feedback-history"><summary>历史意见 · ${historical.length}</summary>${historical.map(note).join('')}</details>`:''}</section>`;
}
function sceneAnchorForDisplay(id,scope){
  if(scope==='concept')return {conceptId:displayedConcept(conceptCues().find(c=>c.cueId===id))?.id};
  const cue=sceneCue(id);return sceneView(id).mode==='animation'?{artifactId:cue&&cueVideo(cue)?.id}:{storyboardId:cue?.storyboardId};
}
async function saveSceneFeedback(id,scope='production'){
  const version=versionId,key=sceneKey(id,scope),d=getSceneDraft(id,scope);if(sceneWrites.has(key))return false;
  if(!d?.body.trim()){sceneMessages.set(key,'请先填写意见。');renderSceneCards(scope);return false}
  const snapshot=JSON.stringify(d);sceneWrites.add(key);sceneMessages.set(key,'保存中…');renderSceneCards(scope);let saved=false;
  try{
    const r=await postVersionAction(version,{...requestBase(),operation:'feedback',body:d.body,source:source(d.body),target:d.target});saved=true;
    if(JSON.stringify(sceneDrafts.get(key))===snapshot)sceneDrafts.delete(key);persistSceneDrafts(version);
    sceneMessages.set(key,'✓ 已保存 · 审阅完可提交本轮反馈。');
    if(versionId===version){if(r.record?.id&&!state.feedback.some(f=>f.id===r.record.id))state.feedback.push(r.record);await selectVersion(version,{preserveTarget:true})}
    return true;
  }catch(error){sceneMessages.set(key,saved?`✓ 已保存，状态刷新失败：${error.message}`:`保存失败：${error.message}。草稿及原定位保留。`);return saved}
  finally{sceneWrites.delete(key);if(versionId===version)renderSceneCards(scope)}
}
function renderSceneCards(scope){if(scope==='concept')renderBrief();else renderStoryboards()}
function bindSceneFeedback(){
  document.querySelectorAll('[data-scene-draft]').forEach(a=>a.oninput=()=>setSceneDraft(a.dataset.sceneDraft,a.value,a.dataset.sceneScope));
  document.querySelectorAll('[data-save-scene]').forEach(b=>b.onclick=()=>saveSceneFeedback(b.dataset.saveScene,b.dataset.sceneScope));
  document.querySelectorAll('[data-accept-feedback]').forEach(b=>b.onclick=()=>acceptSceneFeedback(b.dataset.acceptFeedback));
}
async function acceptSceneFeedback(id){
  const f=state.feedback.find(f=>f.id===id);if(!f)return;
  try{await postVersionAction(versionId,{...requestBase(),operation:'feedback-status',feedbackId:id,status:'accepted',actor:'user',resolution:f.resolution||'',source:source(`确认这条意见已解决：${f.body}`)});await selectVersion(versionId,{preserveTarget:true})}catch(error){$('message').textContent=error.message}
}
async function submitSceneRound(scope){
  if(hasSceneDrafts(scope)){$('conceptActionStatus').textContent='还有草稿未保存，请先保存；提交不会自动保存草稿。';setStoryboardActionState(versionId,{kind:'error',message:'还有草稿未保存，请先保存意见。'});return false}
  const submitted=submittedFeedbackIds(),feedbackIds=(state.feedback||[]).filter(f=>!submitted.has(f.id)&&f.status!=='accepted'&&(!f.applicability||f.applicability.kind==='current')&&(scope==='concept'?!!f.target?.conceptId:!f.target?.conceptId&&f.target?.cueIds?.length&&!f.target?.explorationId)).map(f=>f.id);
  if(!feedbackIds.length){$('conceptActionStatus').textContent='没有尚待提交的已保存意见。';return false}
  return runStoryboardAction('submit',{...requestBase(),operation:'review-submit',storyboardIds:scope==='concept'?[]:storyboardCues().map(c=>c.storyboardId).filter(Boolean),feedbackIds,source:source(`提交本轮${scope==='concept'?'画面方案':'分镜与动画'}修改意见；不批准、不授权下一轮整版制作。`)},()=>`✓ 已提交 ${feedbackIds.length} 条意见，等待处理。`)
}
function conceptCardHtml(cue){
  const records=(state.concepts||[]).filter(c=>cue.conceptIds.includes(c.id)),current=displayedConcept(cue),problems=cue.confirmationProblems||[];
  const missing=problems.some(p=>p.code==='concept-image-unavailable'),pending=problems.some(p=>p.code==='unresolved-feedback')||sceneFeedbackRecords(cue.cueId,'concept').some(f=>f.target.conceptId===cue.confirmedId&&['pending','needs-clarification'].includes(f.status)&&(!f.applicability||f.applicability.kind==='current'));
  const label=current&&current.id!==cue.recommendedId?'候选稿 · 正在浏览':cue.firstConfirmed?(missing?'已确认 · 概念图不可用':pending?'已确认 · 有待处理意见':'已确认 · 可进入制作'):cue.revisionPending?'概念改稿 · 待重新确认':current?'推荐稿 · 待确认':'待概念图';
  const content=cue.contentContext||{};
  return `<article class="concept-card scene-card" id="concept-${esc(cue.cueId)}"><header class="scene-heading"><h3>${esc(cue.title)}</h3><span class="badge ${pending?'note':cue.firstConfirmed?'ok':''}">${esc(label)}</span></header><div class="columns"><div class="picture">${current?conceptImageHtml(current,cue.title):'<div class="empty">请先生成或导入概念图。</div>'}<div class="image-meta"><span>${records.length} 张候选 · 点击图片放大、翻阅与采用</span></div><div class="candidate-strip">${records.map((c,i)=>`<button data-concept-preview="${esc(c.id)}" class="${c.id===cue.recommendedId?'selected':''}">${i+1}${c.id===cue.recommendedId?' · 当前选择':''}${c.id===cue.confirmedId?' · 已确认':''}</button>`).join('')}</div></div><div class="copy"><h3>动画描述</h3><p class="motion">${esc(current?.motion||'等待运动思路')}</p>${sceneFeedbackHtml(cue.cueId,'concept')}<div class="scene-actions">${cue.canConfirm&&current?.id===cue.recommendedId?`<button class="primary" data-confirm-concept="${esc(current.id)}">确认此场</button><label><input type="checkbox" data-select-concept="${esc(current.id)}" ${selectedConcepts().has(current.id)?'checked':''}> 纳入批量确认</label>`:''}</div>${(cue.firstConfirmed?problems.filter(p=>p.code==='concept-image-unavailable'):problems).map(p=>`<p class="stale-frame">${esc(p.message)}</p>`).join('')}<details><summary>旁白、文字与创意</summary><p>${esc(content.narration?.text||'尚未填写对应旁白')}</p><p>${esc(content.screenText?.text||'无屏幕文字记录')}</p><p>${esc(current?.idea||'')}</p></details></div></div></article>`
}
function renderBrief(){
  const b=state.brief||{};
  if(!conceptMode()){$('brief').innerHTML=`<h3>本版说明</h3><p>${esc(b.summary||'尚未填写概述。')}</p><div class="segments">${(b.segments||[]).map(s=>`<article class="segment"><strong>${esc(s.title||s.id)}</strong><p>${esc(s.purpose||s.narration||s.visualPlan||'')}</p></article>`).join('')}</div>`;return}
  $('brief').innerHTML=`<section class="concept-actions"><div><h2>先把画面方向聊明白</h2><p class="muted">逐场看图，采用候选后单独确认。实际静帧与运动在「分镜与动画」查看。</p></div><div class="scene-actions"><button id="submitConceptRound">提交修改意见</button><button id="conceptStageButton" class="primary">确认方案，继续制作分镜</button></div><details><summary>批量确认与待处理范围</summary><button id="confirmSelectedConcepts">确认所选概念图</button><button id="confirmAllConcepts">确认全部待定概念图</button><div id="conceptPendingList"></div></details><p id="conceptActionStatus" role="status"></p></section><div class="concept-scenes concept-grid">${conceptCues().map(conceptCardHtml).join('')}</div><details><summary>本版说明与段落</summary><p>${esc(b.summary||'')}</p><p>${esc(b.changeSummary||'')}</p>${(b.segments||[]).map(s=>`<p><strong>${esc(s.title||s.id)}</strong> ${esc(s.purpose||s.narration||'')}</p>`).join('')}</details>`;
  document.querySelectorAll('[data-select-concept]').forEach(box=>box.onchange=()=>{box.checked?selectedConcepts().add(box.dataset.selectConcept):selectedConcepts().delete(box.dataset.selectConcept);renderConceptActions()});
  document.querySelectorAll('[data-concept-preview]').forEach(b=>b.onclick=()=>openConceptPreview(b.dataset.conceptPreview));
  document.querySelectorAll('[data-confirm-concept]').forEach(b=>b.onclick=()=>confirmConcepts([b.dataset.confirmConcept]));
  $('confirmSelectedConcepts').onclick=()=>confirmConcepts(conceptCues().filter(c=>c.canConfirm&&selectedConcepts().has(c.recommendedId)).map(c=>c.recommendedId));
  $('confirmAllConcepts').onclick=()=>confirmConcepts(conceptCues().filter(c=>!c.firstConfirmed).map(c=>c.recommendedId));
  $('submitConceptRound').onclick=()=>submitSceneRound('concept');$('conceptStageButton').onclick=openConceptProduction;
  bindSceneFeedback();renderConceptActions();
}
function renderConceptGallery(){
  if(!conceptGallery||conceptGallery.versionId!==versionId)return;
  const {records,index,title}=conceptGallery,c=records[index],multiple=records.length>1,card=conceptCues().find(q=>q.objectId===c.objectId);
  if(card){sceneView(card.cueId).conceptId=c.id;rememberReviewTarget({tab:'overview',conceptId:c.id,cueId:card.cueId});renderBrief()}
  $('lightboxTitle').textContent=c.idea;$('lightboxImage').src=artifactUrl(c);$('lightboxImage').alt=c.idea;
  $('conceptGalleryPosition').textContent=`${title} · ${index+1} / ${records.length}`;
  $('previousConcept').hidden=!multiple;$('nextConcept').hidden=!multiple;$('previousConcept').disabled=index===0;$('nextConcept').disabled=index===records.length-1;
  $('galleryIdea').textContent=`${c.idea||''} ${c.motion||''}`;
  for(const id of ['galleryIdea','galleryStatus','galleryThumbnails'])$(id).hidden=false;
  $('galleryAdopt').hidden=false;$('galleryAdopt').disabled=conceptWrites.has(versionId)||card?.recommendedId===c.id;
  $('galleryAdopt').textContent=candidateChange?.conceptId===c.id?'更换概念并等待重新确认':card?.recommendedId===c.id?'当前选择':'采用这版候选';
  $('galleryStatus').textContent=candidateChange?.conceptId===c.id?'这会更换本场已确认概念、保留旧图和反馈，并等待重新确认。再次点击确认改选。':conceptMessages.get(versionId)||'浏览与采用均不等于确认。';
  $('galleryAdopt').onclick=()=>adoptConcept(c.id,{acceptRevision:candidateChange?.conceptId===c.id});
  $('galleryFeedback').hidden=false;$('galleryFeedback').onclick=()=>{
    const old=getSceneDraft(card.cueId,'concept');
    if(old?.body.trim()&&old.target.conceptId!==c.id){$('galleryStatus').textContent='本场已有绑定其他图片的草稿，请先保存；原定位保持。';return}
    sceneDrafts.set(sceneKey(card.cueId,'concept'),{cueId:card.cueId,scope:'concept',body:'',target:{versionId,conceptId:c.id,cueIds:[card.cueId]},label:`概念图 · ${c.idea}`,identity:c.sha256});
    $('frameLightbox').close();renderBrief();$('concept-'+card.cueId)?.scrollIntoView?.({block:'start'});
    document.querySelectorAll('[data-scene-draft]').forEach(a=>{if(a.dataset.sceneDraft===card.cueId&&a.dataset.sceneScope==='concept')a.focus()});
  };
  $('galleryThumbnails').innerHTML=records.map((r,i)=>`<button data-gallery-index="${i}" class="${i===index?'selected':''}" aria-label="候选 ${i+1}"><img src="${esc(artifactUrl(r))}" alt="候选 ${i+1}"></button>`).join('');
  document.querySelectorAll('[data-gallery-index]').forEach(b=>b.onclick=()=>{conceptGallery.index=Number(b.dataset.galleryIndex);candidateChange=null;renderConceptGallery()});
}
async function adoptConcept(id,{acceptRevision=false}={}){
  const c=state.concepts?.find(c=>c.id===id),card=conceptCues().find(q=>q.conceptIds.includes(id));if(!c||!card||conceptWrites.has(versionId)||state.legacy)return false;
  if(conceptReceipts.get(versionId)?.needsRefresh)return refreshSavedMutation(conceptReceipts.get(versionId));
  if(hasSceneDrafts('concept')){conceptMessages.set(versionId,'还有未保存的草稿；原定位保留，请先保存。');renderConceptGallery();return false}
  const current=state.concepts.find(c=>c.id===card.recommendedId),changes=card.firstConfirmed&&card.confirmedId!==id;
  if(changes&&!acceptRevision){candidateChange={versionId,conceptId:id};renderConceptGallery();return false}
  const version=versionId;conceptWrites.add(version);
  try{const request={...requestBase(),operation:'concept',action:!card.firstConfirmed&&current?.round===c.round?'propose':'select',conceptId:id,source:source(changes?'更换本场概念，采用这版候选并等待重新确认。':'采用这版候选；此操作不确认概念。')};const result=await postVersionAction(version,request);candidateChange=null;const receipt={versionId:version,requestId:request.requestId,result,needsRefresh:true,message:'✓ 当前候选已保存，概念确认单独记录。'};conceptReceipts.set(version,receipt);conceptMessages.set(version,receipt.message);if(versionId===version){$('frameLightbox').close();clearConceptGallery();await refreshSavedMutation(receipt)}return true}
  catch(error){conceptMessages.set(version,`采用未完成：${error.message}。原选择保持。`);if(versionId===version)renderConceptGallery();return false}
  finally{conceptWrites.delete(version);if(versionId===version)renderConceptActions()}
}
function conceptHandoffSummary(){
  const handoff=state?.conceptDesign?.storyboardHandoff;if(!handoff)return '';
  const title=item=>conceptCues().find(c=>c.objectId===item.objectId)?.title||item.cueId;
  return `✓ 方案和本次制作范围已保存。回到对话后可继续制作分镜。本次制作：${handoff.selected.map(title).join('、')}；暂不制作：${handoff.excluded.map(title).join('、')||'无'}。${handoff.current?'':'当前方案已变化，请重新核对本次制作范围。'}`;
}
function openConceptProduction(){
  const previous=state.conceptDesign.storyboardHandoff,eligible=conceptCues().filter(c=>!c.confirmationProblems?.length&&(c.firstConfirmed||c.canConfirm));
  const selected=previous?.current?eligible.filter(c=>previous.selected.some(item=>item.objectId===c.objectId)):eligible;
  conceptProduction={versionId,anchor:JSON.stringify(conceptCues()),selected:new Set(selected.map(c=>c.cueId)),request:null,busy:false};
  $('conceptProductionContent').innerHTML=conceptCues().map(c=>`<p><label><input type="checkbox" data-concept-scope="${esc(c.cueId)}" ${conceptProduction.selected.has(c.cueId)?'checked':''} ${!c.confirmationProblems?.length&&(c.firstConfirmed||c.canConfirm)?'':'disabled'}> ${esc(c.title)}</label> · ${c.confirmationProblems?.length?esc(c.confirmationProblems.map(p=>p.message).join('；')):c.firstConfirmed?'已有概念确认':c.canConfirm?'本次确认':'尚未就绪'}</p>`).join('');
  document.querySelectorAll('[data-concept-scope]').forEach(b=>b.onchange=()=>{if(conceptProduction.busy)return;b.checked?conceptProduction.selected.add(b.dataset.conceptScope):conceptProduction.selected.delete(b.dataset.conceptScope);conceptProduction.request=null;renderConceptProductionScope()});
  renderConceptProductionScope();$('conceptProductionDialog').showModal();
}
function renderConceptProductionScope(){
  if(!conceptProduction)return;const selected=conceptCues().filter(c=>conceptProduction.selected.has(c.cueId)),excluded=conceptCues().filter(c=>!conceptProduction.selected.has(c.cueId));
  $('conceptProductionMessage').textContent=`本次制作：${selected.map(c=>c.title).join('、')||'无'}；暂不制作：${excluded.map(c=>c.title).join('、')||'无'}。方案和本次制作范围将一起保存。回到对话后可继续制作分镜。`;
  $('confirmConceptProduction').disabled=conceptProduction.busy||!selected.length||hasSceneDrafts('concept');
}
async function submitConceptProduction(){
  const plan=conceptProduction;if(!plan||plan.versionId!==versionId||plan.busy)return false;
  plan.busy=true;$('confirmConceptProduction').disabled=true;let saved=false;
  try{
    await selectVersion(plan.versionId,{preserveTarget:true});
    if(conceptProduction!==plan||versionId!==plan.versionId)return false;
    if(plan.request&&state.conceptDesign.storyboardHandoff?.requestId===plan.request.requestId){saved=true;conceptMessages.set(plan.versionId,conceptHandoffSummary());$('conceptProductionDialog').close();conceptProduction=null;renderConceptActions();return true}
    if(JSON.stringify(conceptCues())!==plan.anchor){$('conceptProductionMessage').textContent='方案或反馈已更新，请重新核对范围。';return false}
    if(hasSceneDrafts('concept')||$('feedbackBody').value.trim()){$('conceptProductionMessage').textContent='还有未保存的意见，请先保存。';return false}
    const selected=conceptCues().filter(c=>plan.selected.has(c.cueId)),excluded=conceptCues().filter(c=>!plan.selected.has(c.cueId));if(!selected.length)return false;
    if(!plan.request)plan.request={...requestBase(),operation:'concept-handoff',cueIds:selected.map(c=>c.cueId),conceptIds:selected.map(c=>c.recommendedId),excludedCueIds:excluded.map(c=>c.cueId),source:source(`确认所选概念并交棒分镜制作：${selected.map(c=>c.title).join('、')}；本轮排除：${excluded.map(c=>c.title).join('、')||'无'}。不授权 Motion、Demo 或正式交付。`)};
    const result=await postVersionAction(plan.versionId,plan.request);saved=true;
    const receipt={versionId:plan.versionId,requestId:plan.request.requestId,result,needsRefresh:true,message:`✓ 方案和本次制作范围已保存。回到对话后可继续制作分镜。本次制作：${selected.map(c=>c.title).join('、')}；暂不制作：${excluded.map(c=>c.title).join('、')||'无'}。`};conceptReceipts.set(plan.versionId,receipt);conceptMessages.set(plan.versionId,receipt.message);
    if(conceptProduction===plan&&versionId===plan.versionId){if(result.record)state.conceptDesign.storyboardHandoff={...result.record,current:true,problems:[]};$('conceptProductionDialog').close();conceptProduction=null;await refreshSavedMutation(receipt)}
    return true;
  }catch(error){if(conceptProduction===plan&&versionId===plan.versionId)$('conceptProductionMessage').textContent=saved?`✓ 方案和本次制作范围已保存。刷新失败：${error.message}。无需重复提交。`:`暂未确认保存结果：${error.message}。本次制作范围已保留，可重试。`;return saved}
  finally{plan.busy=false;if(conceptProduction===plan&&versionId===plan.versionId)$('confirmConceptProduction').disabled=!plan.selected.size||hasSceneDrafts('concept')}
}
function selectSceneFrame(id,frameId){Object.assign(sceneView(id),{frameId,storyboardId:sceneCue(id)?.storyboardId});rememberReviewTarget({tab:'storyboard',storyboardId:sceneView(id).storyboardId,cueId:id,frameId});renderStoryboards()}
function selectSceneMode(id,mode){const view=sceneView(id);view.mode=mode;if(mode==='animation'){const video=cueVideo(sceneCue(id));if(video)rememberReviewTarget({tab:'storyboard',cueId:id,artifactId:video.id})}else{view.storyboardId=sceneCue(id)?.storyboardId;rememberReviewTarget({tab:'storyboard',cueId:id,storyboardId:view.storyboardId,frameId:view.frameId})}saveReviewReading();renderStoryboards()}
function showCurrentScene(id){
  const view=sceneView(id),current=state.storyboard?.cues?.find(c=>c.id===id);if(!current)return;
  if(view.mode==='animation'){const video=cueVideo(current,{latest:true});if(!video)return;view.artifactId=video.id;rememberReviewTarget({tab:'storyboard',cueId:id,artifactId:video.id})}
  else {view.storyboardId=current.storyboardId;view.frameId=null;rememberReviewTarget({tab:'storyboard',cueId:id,storyboardId:current.storyboardId})}
  renderStoryboards();
}
function productionSceneHtml(cue){
  const view=sceneView(cue.id),frame=sceneFrame(cue),video=cueVideo(cue),animation=view.mode==='animation',progress=cue.sceneReview?.[view.mode],problems=cue.productionProblems||[],pending=sceneFeedbackRecords(cue.id,'production').some(f=>['pending','needs-clarification'].includes(f.status)&&(!f.applicability||f.applicability.kind==='current'));
  const conceptCard=conceptCues().find(c=>c.cueId===cue.id),concept=state.concepts?.find(c=>c.id===(conceptCard?.confirmedId||conceptCard?.recommendedId));
  const currentScene=state.storyboard?.cues?.find(c=>c.id===cue.id),newer=animation?cueVideo(cue,{latest:true})?.id!==video?.id:currentScene?.storyboardId!==cue.storyboardId;
  const staleBoard=!animation&&problems.some(p=>['storyboard-not-current','missing-storyboard'].includes(p.code));
  const status=staleBoard?'历史静帧 · 当前分镜待更新':pending||progress?.problems?.some(p=>p.code==='unresolved-feedback')?'有待处理意见':progress?.current?'本场当前内容已确认':progress?'内容已变化 · 请重新查看':'待审阅';
  return `<article class="storyboard-card scene-card" id="frames-${esc(cue.id)}"><header class="scene-heading"><h3>${esc(cue.title||cue.id)}</h3><span class="badge ${pending?'note':progress?.current?'ok':''}">${status}</span></header><div class="review-layout"><section class="view-column"><div class="viewer-toolbar">${newer&&currentScene?`<button data-scene-current="${esc(cue.id)}">查看当前${animation?'动画':'分镜'}</button>`:''}<div class="segmented"><button data-scene-mode="storyboard" data-scene-id="${esc(cue.id)}" class="${!animation?'selected':''}">过程静帧</button><button data-scene-mode="animation" data-scene-id="${esc(cue.id)}" class="${animation?'selected':''}">本场动画</button></div>${concept?`<button data-compare-concept="${esc(cue.id)}">${view.compare?'收起对照':'对照概念图'}</button>`:''}</div><div class="screens ${view.compare?'compare':''}"><div class="scene-media media">${animation?(video?`<video data-scene-video="${esc(cue.id)}" data-artifact-id="${esc(video.id)}" src="${esc(artifactUrl(video))}" controls preload="none" playsinline></video>`:'<p class="empty">本场尚无可验证的当前动画预览。</p>'):(frame?`<button data-frame-preview data-image-url="${esc(artifactUrl(frame))}" data-image-title="${esc(cue.title)}" class="frame-preview"><img src="${esc(artifactUrl(frame))}" alt="${esc(frame.label||frame.frameId)}" loading="lazy"></button>`:'<p class="empty">尚无 Storyboard 静帧。</p>')}</div>${view.compare&&concept?`<figure class="comparison"><img src="${esc(artifactUrl(concept))}" alt="已选概念图"><figcaption>概念图对照</figcaption></figure>`:''}</div>${animation?`<p class="muted">${video?`${video.kind==='full-preview'?'完整 Demo 的本场区间':'本场实际视频预览'} · ${esc(video.id)}`:''}</p>`:`<div class="steps">${(cue.frames||[]).map((f,i)=>`<button data-scene-frame="${esc(f.frameId)}" data-scene-id="${esc(cue.id)}" class="${f===frame?'selected':''}"><small>${String(i+1).padStart(2,'0')}</small>${esc(f.label||f.frameId)}</button>`).join('')}</div><p class="frame-narration">${esc(frame?.frameNarration||'尚未标注对应旁白')}</p>${frame?localNotesHtml(cue,frame):''}`}</section><aside class="description"><h3>动画描述</h3><p class="motion">${esc(cue.finalAnimationDescription||'尚未填写')}</p>${sceneFeedbackHtml(cue.id,'production')}<div class="scene-actions"><button data-confirm-scene="${esc(cue.id)}" ${(!animation&&(!frame||staleBoard))||(animation&&(!video||video.current===false))||state.legacy?'disabled':''}>确认此场</button></div><p class="muted">仅记录看过并认可当前${animation?'动画':'静帧'}；不启动制作或增加生产门槛。</p><p role="status">${esc(sceneMessages.get(sceneKey(cue.id,'review'))||'')}</p>${problems.map(p=>`<p class="stale-frame">${esc(p.code==='concept-unavailable'?'本场概念依据待恢复或重新确认。':confirmationProblemText(p))}</p>`).join('')}<details><summary>旁白与制作依据</summary><p>${esc(cue.narration||'—')}</p><p>${cue.firstConfirmed?'概念图已确认':'尚未确认概念图'}</p></details></aside></div></article>`
}
function bindSceneCards(){
  bindSceneFeedback();document.querySelectorAll('[data-scene-frame]').forEach(b=>b.onclick=()=>selectSceneFrame(b.dataset.sceneId,b.dataset.sceneFrame));
  document.querySelectorAll('[data-scene-mode]').forEach(b=>b.onclick=()=>selectSceneMode(b.dataset.sceneId,b.dataset.sceneMode));
  document.querySelectorAll('[data-compare-concept]').forEach(b=>b.onclick=()=>{const v=sceneView(b.dataset.compareConcept);v.compare=!v.compare;renderStoryboards()});
  document.querySelectorAll('[data-scene-current]').forEach(b=>b.onclick=()=>showCurrentScene(b.dataset.sceneCurrent));
  document.querySelectorAll('[data-confirm-scene]').forEach(b=>b.onclick=()=>confirmSceneReview(b.dataset.confirmScene));
  document.querySelectorAll('[data-scene-video]').forEach(p=>{const a=state.artifacts.find(a=>a.id===p.dataset.artifactId),cue=a?.reviewCues?.find(c=>c.id===p.dataset.sceneVideo)||(a?.current?state.cues.find(c=>c.id===p.dataset.sceneVideo):null);if(!cue)return;const v=sceneView(cue.id),begin=Math.max(0,demoCueStart(cue)-parseTime(a.range.start)),end=begin+parseTime(cue.resolvedTimeline?.duration||cue.range?.duration||'0s');const inside=time=>time>=begin&&time<end;p.onloadedmetadata=()=>{const time=v.videoArtifact===a.id?v.videoTime??begin:begin;p.currentTime=inside(time)?time:begin};p.onseeked=()=>{if(!inside(p.currentTime)){p.pause();p.currentTime=begin}};p.onplay=()=>{if(!inside(p.currentTime))p.currentTime=begin};p.ontimeupdate=()=>{if(p.currentTime>=end){p.pause();p.currentTime=Math.max(begin,end-0.001)}v.videoTime=p.currentTime;v.videoArtifact=a.id}});
}
async function confirmSceneReview(id){
  const key=sceneKey(id,'review'),cue=sceneCue(id),kind=sceneView(id).mode,artifact=kind==='animation'?cueVideo(cue):null;if(!cue||sceneWrites.has(key))return false;
  if(sceneReviewReceipts.get(key)?.needsRefresh)return refreshSavedMutation(sceneReviewReceipts.get(key));
  if(hasSceneDrafts('production')){sceneMessages.set(key,'还有未保存的草稿，请先保存。');renderStoryboards();return false}
  const version=versionId;sceneWrites.add(key);
  try{const request={...requestBase(),operation:'scene-review',kind,cueId:id,...(kind==='storyboard'?{storyboardId:cue.storyboardId}:{artifactId:artifact?.id}),source:source(`确认看过并认可本场当前${kind==='storyboard'?'分镜静帧':'动画呈现'}；仅记录审阅进度。`)};const result=await postVersionAction(version,request);const receipt={versionId:version,sceneKey:key,requestId:request.requestId,result,needsRefresh:true,message:'✓ 当前呈现的审阅进度已保存。'};sceneReviewReceipts.set(key,receipt);sceneMessages.set(key,receipt.message);if(versionId===version)await refreshSavedMutation(receipt);return true}
  catch(error){sceneMessages.set(key,`确认未完成：${error.message}`);return false}
  finally{sceneWrites.delete(key);if(versionId===version)renderStoryboards()}
}
function openDeliveryConfirmation(){
  const review=state.reviewSet;if(!review||state.legacy)return;
  deliveryConfirmation={versionId,reviewSetId:review.id,anchor:JSON.stringify(review)};
  $('deliveryConfirmContent').textContent=`制作版：${state.identity.versionTitle}（${versionId}）\n完整审阅集合：${review.id}\n输入：${review.inputKey}\n包含产物：${review.artifactIds.join('、')}\n批准当前整片并授权生成正式交付文件。`;
  $('deliveryConfirmMessage').textContent='发布前仍由现有交付系统核验完整动画、批准与授权。';$('submitDeliveryConfirm').disabled=false;$('deliveryConfirmDialog').showModal();
}
async function submitDeliveryConfirmation(){
  const plan=deliveryConfirmation;
  if(!plan||plan.versionId!==versionId||plan.busy)return false;
  plan.busy=true;$('submitDeliveryConfirm').disabled=true;
  try{
    await selectVersion(plan.versionId,{preserveTarget:true});
    if(deliveryConfirmation!==plan||versionId!==plan.versionId)return false;
    if(JSON.stringify(state.reviewSet)!==plan.anchor){$('deliveryConfirmMessage').textContent='整片版本或审阅集合已经变化，请重新核对。';return false}
    if($('feedbackBody').value.trim()||hasSceneDrafts()){$('deliveryConfirmMessage').textContent='还有未保存的草稿，请先保存。';return false}
    const saved=await decision('approve-and-deliver','确认当前完整审阅集合的整片效果，并授权生成交付文件。');
    if(saved&&deliveryConfirmation===plan&&versionId===plan.versionId){$('deliveryConfirmDialog').close();deliveryConfirmation=null}
    return saved;
  }catch(error){if(deliveryConfirmation===plan&&versionId===plan.versionId)$('deliveryConfirmMessage').textContent=`交付未完成：${error.message}`;return false}
  finally{plan.busy=false;if(deliveryConfirmation===plan&&versionId===plan.versionId)$('submitDeliveryConfirm').disabled=false}
}
