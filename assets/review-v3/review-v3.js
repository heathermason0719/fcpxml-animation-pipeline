let explicitDemoId=null;
function renderProject(){const root=$('projectTree');root.innerHTML=(project.episodes||[]).map(ep=>{const versions=ep.versions||[],selected=versions.find(v=>v.id===versionId)||versions.at(-1),older=versions.filter(v=>v!==selected);const button=v=>`<button class="version ${v.id===versionId?'active':''} ${v.legacy?'legacy':''}" data-version="${esc(v.id)}">${esc(v.title||v.id)}</button>`;return `<section><div class="episode">${esc(ep.title||ep.id)}</div>${selected?button(selected):''}${older.length?`<details><summary>其他制作版（${older.length}）</summary>${older.map(button).join('')}</details>`:''}</section>`}).join('');document.querySelectorAll('[data-version]').forEach(el=>el.onclick=()=>selectVersion(el.dataset.version))}
function renderState(){if(!state)return;$('versionTitle').textContent=`${state.identity?.episodeTitle||''} · ${state.identity?.versionTitle||''}`;$('title').textContent=state.brief?.summary||state.identity?.versionTitle||'审阅工作台';$('summary').textContent=state.legacy?'这是旧版记录，可查看历史产物。':'集中查看预览、反馈和交付状态。';$('revision').textContent=`编辑版本 ${state.editRevision}`;$('exportScript').href=`/script?version=${encodeURIComponent(versionId)}`;renderBrief();renderWorkingIntent();renderCueNavigation();renderStoryboards();renderExplorations();renderCues();renderArtifacts();renderFeedback();renderActions();renderTasks();renderComparison();restoreDraft();layoutFeedbackPanel();renderDemoFeedback();updateDemoTimeAnchor();renderFeedbackSaveStatus()}
const conceptSelections=new Map(),conceptWrites=new Set(),conceptMessages=new Map();
let conceptGallery=null;
function clearConceptGallery(){conceptGallery=null;candidateChange=null;$('previousConcept').hidden=true;$('nextConcept').hidden=true;$('conceptGalleryPosition').textContent='';for(const id of ['galleryAdopt','galleryFeedback','galleryThumbnails','galleryIdea','galleryStatus'])$(id).hidden=true}
function openConceptPreview(id){
  const cue=conceptCues().find(c=>c.conceptIds.includes(id));if(!cue)return;
  const records=cue.conceptIds.map(key=>state.concepts.find(c=>c.id===key)).filter(Boolean),current=records.find(c=>c.id===cue.recommendedId);
  const ordered=[...(current?[current]:[]),...records.filter(c=>c!==current).reverse()],index=ordered.findIndex(c=>c.id===id);if(index<0)return;
  conceptGallery={versionId,title:cue.title,records:ordered,index};renderConceptGallery();if(!$('frameLightbox').open)$('frameLightbox').showModal();
}
function moveConceptPreview(step){if(!conceptGallery||conceptGallery.versionId!==versionId)return;const index=conceptGallery.index+step;if(index<0||index>=conceptGallery.records.length)return;conceptGallery.index=index;candidateChange=null;renderConceptGallery()}
function openFramePreview(title,url){clearConceptGallery();$('lightboxTitle').textContent=title;$('lightboxImage').src=url;$('lightboxImage').alt=title;$('frameLightbox').showModal()}
function conceptMode(){return !!state?.conceptDesign}
function conceptCues(){return state?.conceptDesign?.cues||[]}
function selectedConcepts(){if(!conceptSelections.has(versionId))conceptSelections.set(versionId,new Set());return conceptSelections.get(versionId)}
function conceptImageHtml(concept,title){const url=artifactUrl(concept);return `<button class="concept-image" type="button" data-concept-preview="${esc(concept.id)}" aria-label="放大概念图 ${esc(title)}"><img src="${esc(url)}" alt="${esc(title)}的概念图" loading="lazy"></button>`}
function renderConceptActions(){
  if(!conceptMode()||!$('confirmSelectedConcepts'))return;
  const pending=conceptCues().filter(c=>!c.firstConfirmed),selected=conceptCues().filter(c=>c.canConfirm&&selectedConcepts().has(c.recommendedId)),busy=conceptWrites.has(versionId);
  $('confirmSelectedConcepts').disabled=busy||!selected.length;$('confirmSelectedConcepts').textContent=`确认所选概念图（${selected.length}）`;
  $('confirmAllConcepts').disabled=busy||!pending.length||pending.some(c=>!c.canConfirm);$('confirmAllConcepts').textContent=pending.length?`确认全部待定概念图（${pending.length}）`:'全部概念图已确认';
  $('conceptPendingList').innerHTML=pending.length?`<p>尚未确认 ${pending.length} 组</p><ul>${pending.map(c=>`<li><a href="#concept-${esc(c.cueId)}">${esc(c.title)}</a><span>${esc(c.canConfirm?'可勾选确认':(c.confirmationProblems||[]).map(p=>p.message).join('；')||'尚未就绪')}</span></li>`).join('')}</ul>`:'<p>全部概念图已确认。</p>';
  $('conceptActionStatus').textContent=busy?'正在保存确认…':conceptMessages.get(versionId)||conceptHandoffSummary();
}
async function confirmConcepts(ids){
  if(conceptWrites.has(versionId)||!ids.length)return false;
  if(conceptReceipts.get(versionId)?.needsRefresh)return refreshSavedMutation(conceptReceipts.get(versionId));
  if($('feedbackBody').value.trim()||hasSceneDrafts('concept')){conceptMessages.set(versionId,'还有未保存的留言，请先保存或清空后再确认。');renderConceptActions();return false}
  const actionVersion=versionId;conceptWrites.add(actionVersion);conceptMessages.delete(actionVersion);renderConceptActions();
  try{
    const request={...requestBase(),operation:'decision',kind:'confirm-concept',conceptIds:ids,source:source(`确认采用所选 ${ids.length} 张概念图，可以按此方向制作动画。`)};
    const result=await postVersionAction(actionVersion,request);
    const receipt={versionId:actionVersion,requestId:request.requestId,result,needsRefresh:true,message:`✓ 已保存：已确认 ${ids.length} 张概念图。`};conceptReceipts.set(actionVersion,receipt);
    ids.forEach(id=>conceptSelections.get(actionVersion)?.delete(id));conceptMessages.set(actionVersion,receipt.message);
    if(versionId===actionVersion)await refreshSavedMutation(receipt);return true;
  }catch(error){conceptMessages.set(actionVersion,`确认未完成：${error.message}。所选方案已保留。`);return false}
  finally{conceptWrites.delete(actionVersion);renderConceptActions()}
}
let storyboardProduction=null,productionChecking=false;
function pendingStoryboardProduction(){return state?.storyboard?.productionRequest?.status==='pending'}
function productionAnchor(){return JSON.stringify([state.editRevision,storyboardCues().map(c=>[c.id,c.objectId,c.storyboardId,c.reviewInputKey,c.productionProblems,c.productionDeferred]),state.storyboard?.productionRequest])}
function cancelStoryboardProduction(){storyboardProduction=null;$('productionDialog').close()}
function renderProductionSelection(){
  const selected=storyboardCues().filter(c=>storyboardProduction?.selected.has(c.id)),excluded=storyboardCues().filter(c=>!storyboardProduction?.selected.has(c.id));
  const problem=designDraftProblem()||(!selected.length?'请至少选择一条动画。':selected.some(c=>!c.storyboardId||c.productionProblems?.length)?'所选动画仍有待处理事项，请返回 Storyboard 查看。':'');
  $('productionScope').textContent=`本轮制作 ${selected.length} 条：${selected.map(c=>c.title||c.id).join('、')||'无'}；暂不制作 ${excluded.length} 条：${excluded.map(c=>c.title||c.id).join('、')||'无'}。`;
  $('productionMessage').textContent=problem;$('submitProduction').disabled=!!problem||productionChecking;
}
function toggleProductionCue(id,checked){if(!storyboardProduction||productionChecking)return;checked?storyboardProduction.selected.add(id):storyboardProduction.selected.delete(id);renderProductionSelection()}
function openStoryboardProduction(){
  if(storyboardActionBusy()||productionChecking||pendingStoryboardProduction())return;
  captureStoryboardDrafts();
  storyboardProduction={versionId,anchor:productionAnchor(),selected:new Set(storyboardCues().filter(c=>!c.productionDeferred).map(c=>c.id))};
  $('productionContent').innerHTML=storyboardCues().map(c=>`<p><label><input type="checkbox" data-production-cue="${esc(c.id)}" ${storyboardProduction.selected.has(c.id)?'checked':''}> ${esc(c.title||c.id)}</label>${c.productionDeferred?' <span class="muted">有暂缓意见，默认暂不制作</span>':''}${c.productionProblems?.length?`<span class="stale-frame"> ${esc(c.productionProblems.map(confirmationProblemText).join('；'))}</span>`:''}</p>`).join('');
  document.querySelectorAll('[data-production-cue]').forEach(box=>box.onchange=()=>toggleProductionCue(box.dataset.productionCue,box.checked));
  renderProductionSelection();$('productionDialog').showModal();
}
async function submitStoryboardProduction(){
  const plan=storyboardProduction;
  if(!plan||plan.versionId!==versionId||productionChecking||storyboardActionBusy())return false;
  captureStoryboardDrafts();renderProductionSelection();if($('submitProduction').disabled)return false;
  productionChecking=true;$('submitProduction').disabled=true;
  let changed=false;
  try{
    await selectVersion(plan.versionId,{preserveTarget:true});
    if(storyboardProduction!==plan||versionId!==plan.versionId)return false;
    if(productionAnchor()!==plan.anchor){changed=true;$('productionMessage').textContent='Storyboard 或反馈已更新，请返回检查后重新打开制作范围。';return false}
    captureStoryboardDrafts();const problem=designDraftProblem();if(problem){$('productionMessage').textContent=problem;return false}
    const selected=storyboardCues().filter(c=>plan.selected.has(c.id)),excluded=storyboardCues().filter(c=>!plan.selected.has(c.id)),taskId=crypto.randomUUID();
    const saved=await runStoryboardAction('produce',{...requestBase(),operation:'decision',kind:'authorize-demo',taskId,cueIds:selected.map(c=>c.id),presentationCueIds:selected.map(c=>c.id),excludedCueIds:excluded.map(c=>c.id),storyboardIds:selected.map(c=>c.storyboardId),source:source(`通过当前 Storyboard 并开始制作动画：${selected.map(c=>c.title||c.id).join('、')}；本轮暂不制作：${excluded.map(c=>c.title||c.id).join('、')||'无'}。`)},()=> '✓ 动画制作已交棒。回到对话让 Agent 继续制作，完成后在 Demo 审阅。',()=>{if(storyboardProduction===plan)cancelStoryboardProduction()});
    if(!saved&&storyboardProduction===plan)$('productionMessage').textContent=storyboardActionStates.get(versionId)?.message||'交棒未成功，请重试。';
    return saved;
  }catch(error){if(storyboardProduction===plan)$('productionMessage').textContent=`交棒未完成：${error.message}`;return false}
  finally{productionChecking=false;if(storyboardProduction===plan)$('submitProduction').disabled=changed}
}

function storyboardCues(){return state?.storyboard?.cues||[]}
function storyboardKey(cue,frame){return JSON.stringify([versionId,cue.id,cue.storyboardId,frame.frameId])}
function storyboardAnchor(frame){return JSON.stringify([frame.artifactId,frame.path,frame.sha256])}
function storyboardFrame(cue,frame){return (cue.frames||[]).find(item=>item.frameId===frame.frameId)}
function storyboardDraftIsStale(draft){const cue=storyboardCues().find(item=>item.id===draft.cueId&&item.storyboardId===draft.storyboardId),frame=cue&&storyboardFrame(cue,draft);return !frame||draft.anchor!==storyboardAnchor(frame)}
function persistStoryboardDrafts(id=versionId){localStorage.setItem(storyboardStorageKey(id),JSON.stringify([...storyboardDrafts.values()].filter(draft=>draft.target?.versionId===id)))}
function clearSubmittedDraft(draft){const key=JSON.stringify([draft.target.versionId,draft.cueId,draft.storyboardId,draft.frameId]),current=storyboardDrafts.get(key);if(current?.body===draft.body&&current?.anchor===draft.anchor)storyboardDrafts.delete(key)}
function restoreStoryboardDrafts(){const raw=localStorage.getItem(storyboardStorageKey());if(!raw)return;try{for(const draft of JSON.parse(raw)){if(draft?.target?.versionId===versionId&&draft.cueId&&draft.storyboardId&&draft.frameId&&draft.body)storyboardDrafts.set(JSON.stringify([versionId,draft.cueId,draft.storyboardId,draft.frameId]),draft)}}catch{}}
function setStoryboardDraft(cueId,storyboardId,frameId,body){const cue=storyboardCues().find(item=>item.id===cueId&&item.storyboardId===storyboardId),frame=cue&&storyboardFrame(cue,{frameId});if(!cue||!frame)return;const key=storyboardKey(cue,frame);if((storyboardDrafts.get(key)?.body||'')!==String(body||'')&&storyboardSaveStates.has(key)&&storyboardSaveStates.get(key).kind!=='pending')updateFrameSaveState(key,'draft',String(body||'').trim()?'草稿未保存。':'');if(!String(body||'').trim())storyboardDrafts.delete(key);else storyboardDrafts.set(key,{cueId,storyboardId,frameId,body:String(body),anchor:storyboardAnchor(frame),target:{versionId,cueIds:[cueId],artifactId:frame.artifactId,storyboardId,frameId}});persistStoryboardDrafts()}
function captureStoryboardDrafts(){document.querySelectorAll('[data-storyboard-draft]').forEach(area=>setStoryboardDraft(area.dataset.cueId,area.dataset.storyboardId,area.dataset.frameId,area.value))}
function source(text){return {channel:'review',text,reference:`review:${versionId}:${crypto.randomUUID()}`}}
function toggleConfirmDesignCue(cueId){confirmedDesignCueIds.has(cueId)?confirmedDesignCueIds.delete(cueId):confirmedDesignCueIds.add(cueId);renderStoryboards()}
function storyboardActionBusy(id=versionId){const item=storyboardActionStates.get(id);return !!(item&&(item.inFlight||['pending','running'].includes(item.kind)))}
function renderStoryboardActionStatus(){
  let item=storyboardActionStates.get(versionId);
  if(item?.action==='preview'&&item.kind==='running'){
    const task=(state.tasks||[]).find(t=>t.requestId===item.requestId||t.id===item.requestId);
    if(task?.status==='failed')item={...item,kind:'error',message:`静帧生成失败：${task.error||'请查看任务详情。'}`};
    else if(['complete','completed'].includes(task?.status))item={...item,kind:'success',message:'✓ 静帧已生成，图片与说明已更新。'};
    else if(task?.completedCueIds?.length)item={...item,message:`静帧生成中，已完成 ${task.completedCueIds.length} 个镜头…`};
    storyboardActionStates.set(versionId,item);
  }
  const lastRound=state?.storyboard?.rounds?.filter(r=>r.storyboardIds?.length).at(-1),fallback=lastRound?`最近一轮反馈已提交：${lastRound.feedbackIds?.length||0} 条 · ${{submitted:'待处理',processing:'处理中',processed:'已处理'}[lastRound.status]||lastRound.status}。`:'';
  const message=$('storyboardActionStatus');if(message){message.textContent=item?.message||(pendingStoryboardProduction()?'✓ 动画制作已交棒。回到对话让 Agent 继续制作，完成后在 Demo 审阅。':fallback);message.className=`storyboard-action-status ${item?.kind||(fallback?'success':'')}`}
  document.querySelectorAll('[data-storyboard-produce]').forEach(button=>{button.disabled=storyboardActionBusy()||productionChecking||pendingStoryboardProduction();button.textContent=pendingStoryboardProduction()?'动画制作已交棒':'确认本轮，生成整片 Demo'});
  renderStoryboardQualification();
  const busy=storyboardActionBusy(),labels={preview:'生成静帧',submit:'提交本轮反馈',confirm:`确认所选设计（${confirmedDesignCueIds.size}）`},pending={preview:'生成中…',submit:'提交中…',confirm:'确认中…'};
  for(const [action,selector] of Object.entries({preview:'[data-storyboard-preview]',submit:'[data-storyboard-submit]',confirm:'[data-confirm-design]'}))document.querySelectorAll(selector).forEach(button=>{button.disabled=busy||(action==='confirm'&&!confirmedDesignCueIds.size);button.textContent=busy&&item?.action===action?pending[action]:labels[action]})
}
function setStoryboardActionState(id,item){storyboardActionStates.set(id,item);if(versionId===id)renderStoryboardActionStatus()}
async function runStoryboardAction(action,request,success,onSaved=()=>{}){
  const actionVersion=versionId;
  if(storyboardActionBusy())return false;
  if(frameFeedbackWrites.has(actionVersion)){setStoryboardActionState(actionVersion,{kind:'error',message:'逐帧反馈正在保存，请等保存完成后再操作。'});return false}
  const pending={preview:'静帧生成请求发送中…',submit:'本轮反馈提交中…',confirm:'所选设计确认中…',produce:'正在保存动画制作交棒…'};
  setStoryboardActionState(actionVersion,{action,kind:'pending',inFlight:true,message:pending[action]});
  let saved=false;
  try{
    const result=await postVersionAction(actionVersion,request,action==='preview'?'preview':'update');
    saved=true;onSaved(result);
    const started=action==='preview'&&result.status==='started';
    setStoryboardActionState(actionVersion,{action,kind:started?'running':'success',inFlight:true,requestId:result.requestId||request.requestId,message:started?'静帧生成中，完成后会自动更新图片。':success(result)});
    if(versionId===actionVersion)await selectVersion(actionVersion,{preserveTarget:true});
    return true;
  }catch(error){
    const item=storyboardActionStates.get(actionVersion);
    setStoryboardActionState(actionVersion,saved?{...item,message:`${item.message} 状态刷新失败：${error.message}；可点击「刷新状态」。`}:{action,kind:'error',message:`未能确认${action==='submit'?'提交':action==='confirm'?'确认':action==='produce'?'制作交棒':'生成请求'}：${error.message}。草稿与选择已保留。`});
    return saved;
  }finally{
    const item=storyboardActionStates.get(actionVersion);if(item)setStoryboardActionState(actionVersion,{...item,inFlight:false});
    if(versionId===actionVersion&&storyboardActionStates.get(actionVersion)?.kind==='running'){clearInterval(pollTimer);pollTimer=setInterval(()=>selectVersion(actionVersion,{preserveTarget:true}).catch(error=>{if(versionId===actionVersion)setStoryboardActionState(actionVersion,{...storyboardActionStates.get(actionVersion),message:`生成任务已启动，状态刷新失败：${error.message}。正在重试…`})}),4000)}
  }
}
async function previewStoryboards(){captureStoryboardDrafts();return runStoryboardAction('preview',{...requestBase(),scope:'storyboard',cueIds:storyboardCues().map(c=>c.id)},()=> '✓ 静帧已生成。')}
async function confirmSelectedDesigns(){
  if(storyboardActionBusy())return false;
  const actionVersion=versionId,cues=storyboardCues().filter(cue=>confirmedDesignCueIds.has(cue.id)&&cue.canConfirm&&cue.storyboardId),storyboardIds=cues.map(cue=>cue.storyboardId);
  if(!storyboardIds.length){setStoryboardActionState(actionVersion,{kind:'error',message:'请先勾选镜头旁的「确认完整 Cue」，再确认所选设计。'});return false}
  return runStoryboardAction('confirm',{...requestBase(),operation:'decision',kind:'confirm-design',storyboardIds,source:source('确认所选 storyboard 设计')},()=>`✓ 已确认 ${storyboardIds.length} 组设计。`,()=>{if(versionId===actionVersion){for(const cue of cues)confirmedDesignCueIds.delete(cue.id);renderStoryboards()}})
}

let designConfirmation=null,roundConfirmationChecking=false;
function roundDesignPlan(){
  const cues=storyboardCues(),pending=cues.filter(c=>!c.firstConfirmed);
  return {cues,pending,existing:cues.filter(c=>c.firstConfirmed),blocked:pending.filter(c=>!c.canConfirm||!c.storyboardId)};
}
function roundDesignAnchor(){
  return JSON.stringify(storyboardCues().map(c=>[c.id,c.objectId,c.reviewInputKey,selectionAnchor(c),!!c.firstConfirmed,!!c.canConfirm,c.confirmationProblems]));
}
function designDraftProblem(){
  if(frameFeedbackWrites.has(versionId))return '逐帧反馈正在保存，请等保存完成后再确认。';
  if(currentStoryboardDrafts().length||hasSceneDrafts()||$('feedbackBody').value.trim())return '还有未保存的留言草稿，请先保存／提交意见，或清空不再需要的草稿后再确认。';
  return '';
}
function cancelRoundDesignConfirmation(){designConfirmation=null;$('designConfirmDialog').close()}
function openRoundDesignConfirmation(){
  if(storyboardActionBusy()||roundConfirmationChecking)return;
  captureStoryboardDrafts();
  const plan=roundDesignPlan();
  designConfirmation={versionId,anchor:roundDesignAnchor(),storyboardIds:plan.pending.map(c=>c.storyboardId)};
  const list=(cues)=>`<ul>${cues.map(c=>`<li>${esc(c.title||c.id)}${!c.firstConfirmed&&(!c.canConfirm||!c.storyboardId)?`<p class="stale-frame">${esc((c.confirmationProblems||[]).map(confirmationProblemText).join('；')||'请先生成当前 Storyboard。')}</p>`:''}</li>`).join('')}</ul>`;
  const original=(state.cues||[]).filter(c=>c.productionMode==='source-only');
  $('designConfirmContent').innerHTML=`<p><strong>本次确认 ${plan.pending.length} 组</strong> · 已有首次确认 ${plan.existing.length} 组</p>${list(plan.pending)}${plan.existing.length?`<details><summary>已有确认 · 保留现有记录</summary>${list(plan.existing)}</details>`:''}${original.length?`<details><summary>保留原片 · 不在本次确认范围（${original.length} 组）</summary>${list(original)}</details>`:''}<p class="muted">范围仅限以上待确认的完整 Cue；尚未建立为动画 Cue 的段落不包含在内。此操作只记录设计确认，动画完成后仍需审阅。</p>`;
  const problem=designDraftProblem()||(plan.blocked.length?'上述设计仍有待处理事项，请处理后再整体确认。':'');
  $('designConfirmMessage').textContent=problem||(!plan.pending.length?'当前设计均已有首次确认，无需重复确认。':'');
  $('submitDesignConfirm').disabled=!!problem||!plan.pending.length;
  $('submitDesignConfirm').textContent='确认这些设计';
  if(!$('designConfirmDialog').open)$('designConfirmDialog').showModal();
}
async function submitRoundDesignConfirmation(){
  const confirmation=designConfirmation;
  if(!confirmation||confirmation.versionId!==versionId||roundConfirmationChecking||storyboardActionBusy())return false;
  captureStoryboardDrafts();
  const initial=roundDesignPlan(),problem=designDraftProblem();
  if(problem||initial.blocked.length||!initial.pending.length){$('designConfirmMessage').textContent=problem||'请先处理待确认设计中的问题。';return false}
  roundConfirmationChecking=true;$('submitDesignConfirm').disabled=true;$('submitDesignConfirm').textContent='核对中…';
  let changed=false;
  try{
    // Re-read before committing: the summary belongs to the exact boards the user saw.
    await selectVersion(confirmation.versionId,{preserveTarget:true});
    if(designConfirmation!==confirmation||versionId!==confirmation.versionId)return false;
    if(roundDesignAnchor()!==confirmation.anchor){changed=true;$('designConfirmMessage').textContent='设计、确认状态或范围已更新，请返回检查后重新打开本轮确认。';return false}
    captureStoryboardDrafts();
    const draftProblem=designDraftProblem();
    if(draftProblem){$('designConfirmMessage').textContent=draftProblem;return false}
    $('submitDesignConfirm').textContent='确认中…';
    const saved=await runStoryboardAction('confirm',{...requestBase(),operation:'decision',kind:'confirm-design',storyboardIds:confirmation.storyboardIds,source:source(`确认本轮设计：${initial.pending.map(c=>c.title||c.id).join('、')}。可以开始动画制作，后续继续打磨。`)},()=>`✓ 已确认本轮 ${confirmation.storyboardIds.length} 组设计，可以开始动画制作。`,()=>{
      if(versionId===confirmation.versionId){for(const cue of initial.pending)confirmedDesignCueIds.delete(cue.id);cancelRoundDesignConfirmation()}
    });
    if(!saved&&designConfirmation===confirmation)$('designConfirmMessage').textContent=storyboardActionStates.get(versionId)?.message||'确认未成功，请重试。';
    return saved;
  }catch(error){if(designConfirmation===confirmation)$('designConfirmMessage').textContent=`未能核对当前设计：${error.message}。尚未提交确认。`;return false}
  finally{
    roundConfirmationChecking=false;
    if(designConfirmation===confirmation){$('submitDesignConfirm').disabled=changed;$('submitDesignConfirm').textContent='确认这些设计'}
  }
}
function renderStoryboardQualification(){
  const {cues,pending,existing}=roundDesignPlan(),root=$('storyboardQualificationStatus');
  if(root)root.textContent=conceptMode()?'视觉方向在「画面方案」中确认；此处查看实际制作静帧。':!cues.length?'':!pending.length?`✓ 当前 ${cues.length} 组均已完成首次设计确认，可继续制作与修改。`:`${cues.length} 组设计 · ${existing.length} 组已有确认 · ${pending.length} 组待首次确认`;
  for(const button of document.querySelectorAll('[data-confirm-round]')){button.disabled=storyboardActionBusy()||!pending.length;button.textContent=pending.length?'确认本轮设计':'本轮首次设计已确认'}
}

function currentStoryboardDrafts(){return [...storyboardDrafts.values()].filter(draft=>draft.target?.versionId===versionId&&draft.body.trim())}
function validStoryboardDrafts(){return currentStoryboardDrafts().filter(draft=>!storyboardDraftIsStale(draft))}
function updateFrameSaveState(key,kind,message){
  storyboardSaveStates.set(key,{kind,message});
  document.querySelectorAll('[data-frame-save-status]').forEach(el=>{if(el.dataset.frameSaveStatus===key){el.textContent=message;el.className=`frame-save-status ${kind}`}});
  document.querySelectorAll('[data-save-frame]').forEach(button=>{if(JSON.stringify([versionId,button.dataset.cueId,button.dataset.storyboardId,button.dataset.saveFrame])===key){button.disabled=kind==='pending';button.textContent=kind==='pending'?'保存中…':'保存此帧反馈'}})
}
async function saveStoryboardFeedback(cueId,storyboardId,frameId){
  const actionVersion=versionId,key=JSON.stringify([actionVersion,cueId,storyboardId,frameId]);
  if(storyboardSaveStates.get(key)?.kind==='pending')return;
  if(storyboardActionStates.get(actionVersion)?.inFlight){updateFrameSaveState(key,'error','顶部操作正在处理，请完成后再保存此帧反馈。');return}
  captureStoryboardDrafts();
  const draft=storyboardDrafts.get(key);
  if(!draft){updateFrameSaveState(key,'error','请先填写此帧反馈。');return}
  if(storyboardDraftIsStale(draft)){updateFrameSaveState(key,'error','静帧已更新；请核对并重新绑定草稿后保存。');return}
  updateFrameSaveState(key,'pending','正在保存此帧反馈…');
  let saved=false;
  try{
    const response=await postVersionAction(actionVersion,{...requestBase(),operation:'feedback',body:draft.body,source:source(draft.body),target:draft.target});
    saved=true;
    const feedbackId=response?.record?.id||response?.feedback?.id||response?.result?.feedback?.id;
    clearSubmittedDraft(draft);persistStoryboardDrafts(actionVersion);
    const newerDraft=storyboardDrafts.has(key);
    updateFrameSaveState(key,'success',newerDraft?'上一条反馈已保存；新修改尚未保存。':'✓ 此帧反馈已保存。审阅完可「提交本轮反馈」。');
    if(versionId!==actionVersion)return;
    document.querySelectorAll('[data-storyboard-draft]').forEach(area=>{if(area.dataset.cueId===cueId&&area.dataset.storyboardId===storyboardId&&area.dataset.frameId===frameId&&area.value===draft.body)area.value=''});
    if(feedbackId)savedStoryboardFeedbackIds.add(feedbackId);
    await selectVersion(actionVersion,{preserveTarget:true});
  }catch(error){
    updateFrameSaveState(key,saved?'success':'error',saved?`✓ 此帧反馈已保存，但列表刷新失败：${error.message}。请刷新状态。`:`未能确认保存：${error.message}；草稿已保留。`)
  }
}
function recoverStoryboardFeedbackIds(){const submitted=new Set((state?.storyboard?.rounds||[]).flatMap(round=>round.feedbackIds||[]));for(const id of submitted)savedStoryboardFeedbackIds.delete(id);for(const feedback of state?.feedback||[]){if(feedback.target?.versionId===versionId&&feedback.target?.storyboardId&&!submitted.has(feedback.id))savedStoryboardFeedbackIds.add(feedback.id)}}
async function submitStoryboardRound(){
  if(conceptMode())return submitSceneRound('production');
  if(storyboardActionBusy())return false;
  const actionVersion=versionId;captureStoryboardDrafts();
  const all=currentStoryboardDrafts(),stale=all.filter(storyboardDraftIsStale);
  if(stale.length){setStoryboardActionState(actionVersion,{kind:'error',message:'有草稿属于旧静帧；请核对并重新绑定后再提交，草稿已保留。'});return false}
  recoverStoryboardFeedbackIds();
  const viewed=storyboardCues().map(cue=>cue.storyboardId).filter(Boolean),feedbackIds=[...savedStoryboardFeedbackIds],drafts=all.map(draft=>({body:draft.body,target:draft.target,source:source(draft.body)}));
  return runStoryboardAction('submit',{...requestBase(),operation:'review-submit',storyboardIds:viewed,feedbackIds,drafts,source:source('提交本轮静帧反馈')},result=>`✓ 本轮反馈已提交：${result.record?.feedbackIds?.length??(feedbackIds.length+drafts.length)} 条，待处理。`,result=>{
    for(const draft of all)clearSubmittedDraft(draft);persistStoryboardDrafts(actionVersion);
    if(versionId!==actionVersion)return;
    for(const id of feedbackIds)savedStoryboardFeedbackIds.delete(id);
    if(Array.isArray(result.record?.feedbackIds)&&result.record.id){state.storyboard.rounds.push(result.record)}
    renderStoryboards();
  })
}

function rebindStoryboardDraft(cueId,storyboardId,frameId,fromKey){const cue=storyboardCues().find(item=>item.id===cueId&&item.storyboardId===storyboardId),frame=cue&&storyboardFrame(cue,{frameId}),key=cue&&frame&&storyboardKey(cue,frame),draft=(fromKey&&storyboardDrafts.get(fromKey))||(key&&storyboardDrafts.get(key));if(draft&&frame){storyboardDrafts.delete(fromKey||key);storyboardDrafts.set(key,{...draft,storyboardId,frameId,anchor:storyboardAnchor(frame),target:{versionId,cueIds:[cueId],artifactId:frame.artifactId,storyboardId,frameId}});persistStoryboardDrafts();renderStoryboards()}}
const noteExpansion=new Map();
function commentKey(cue,frame){return JSON.stringify([versionId,cue.objectId||cue.id,frame.frameId])}
function commentStorageKey(key){return `afterforge-review-v3:comment-open:${key}`}
function commentIsOpen(key){try{return localStorage.getItem(commentStorageKey(key))!=='false'}catch{return true}}
function rememberCommentOpen(key,open){try{localStorage.setItem(commentStorageKey(key),JSON.stringify(!!open))}catch{}}
function noteKey(cue,note){return JSON.stringify([versionId,cue.objectId||cue.id,cue.storyboardId,note.id])}
function relatedFrames(cue,note){return (cue.frames||[]).filter(frame=>(note.frameIds||[]).includes(frame.frameId))}
function localNotesHtml(cue,frame){return (cue.animationNotes||[]).filter(note=>relatedFrames(cue,note).at(-1)?.frameId===frame.frameId).map(note=>{
  const key=noteKey(cue,note),open=noteExpansion.get(key)||false,numbers=relatedFrames(cue,note).map(f=>String(cue.frames.indexOf(f)+1).padStart(2,'0'));
  return `<section class="animation-note" data-note-key="${esc(key)}"><div class="note-heading"><button class="note-toggle" type="button" data-note-toggle="${esc(key)}" aria-expanded="${open}">动画说明</button><button class="note-relation" type="button" data-note-relation="${esc(key)}" aria-pressed="false">对应帧 ${esc(numbers.join('、'))}</button></div><p ${open?'':'hidden'}>${esc(note.text)}</p></section>`
}).join('')}
function storyboardFrameHtml(cue,frame,index){
  const key=storyboardKey(cue,frame),draft=storyboardDrafts.get(key),stale=draft&&storyboardDraftIsStale(draft),url=artifactUrl({id:frame.artifactId,path:frame.path,sha256:frame.sha256}),alt=String(cue.title||cue.id)+' '+String(frame.label||frame.frameId),commentId=commentKey(cue,frame);
  const comments=(state.feedback||[]).filter(item=>item.target?.storyboardId===cue.storyboardId&&item.target?.frameId===frame.frameId).map(item=>`<p class="muted saved-frame-feedback">${esc(item.body)} · ${esc(feedbackStatus[item.status]||item.status)}</p>`).join('');
  const saveState=storyboardSaveStates.get(key),pending=saveState?.kind==='pending';
  const action=stale?`<button data-rebind-frame="${esc(frame.frameId)}" data-cue-id="${esc(cue.id)}" data-storyboard-id="${esc(cue.storyboardId)}" type="button">重新绑定草稿</button>`:`<button data-save-frame="${esc(frame.frameId)}" data-cue-id="${esc(cue.id)}" data-storyboard-id="${esc(cue.storyboardId)}" type="button" ${pending?'disabled':''}>${pending?'保存中…':'保存此帧反馈'}</button>`;
  const narration=typeof frame.frameNarration==='string'?frame.frameNarration:'尚未标注对应旁白';
  return `<figure class="review-frame storyboard-frame" data-frame="${esc(frame.frameId)}" data-frame-cue="${esc(cue.id)}"><button class="frame-preview" type="button" data-frame-preview data-image-url="${esc(url)}" data-image-title="${esc(alt)}" aria-label="放大 ${esc(alt)}"><img src="${esc(url)}" alt="${esc(alt)}" loading="lazy"></button><figcaption class="frame-meta"><span class="frame-number">${String(index+1).padStart(2,'0')}</span><span class="frame-name">${esc(frame.label||frame.frameId)}</span>${frame.current?'':'<span class="stale-frame">历史图片</span>'}</figcaption><p class="frame-narration"><span class="eyebrow">对应旁白</span> ${esc(narration)}</p>${localNotesHtml(cue,frame)}${comments}<details class="frame-comment" data-comment-key="${esc(commentId)}" ${commentIsOpen(commentId)?'open':''}><summary>此帧留言</summary><textarea data-storyboard-draft data-cue-id="${esc(cue.id)}" data-storyboard-id="${esc(cue.storyboardId)}" data-frame-id="${esc(frame.frameId)}" ${stale?'disabled':''} placeholder="对这张静帧留下意见">${esc(draft?.body||'')}</textarea>${stale?'<p class="stale-frame">静帧已更新；草稿保留在原帧，核对后才可重新绑定。</p>':''}<div>${action}</div><p class="frame-save-status ${esc(saveState?.kind||'')}" data-frame-save-status="${esc(key)}" role="status" aria-live="polite" aria-atomic="true">${esc(saveState?.message||'')}</p></details></figure>`
}
function confirmationProblemText(problem){return ({'missing-storyboard':'请先生成当前 Storyboard。','storyboard-not-current':'图片或说明已更新，请生成当前 Storyboard 后再确认。','missing-final-animation-description':'请先补充总体动画说明。','unresolved-feedback':'此 Cue 还有待处理或待澄清的反馈。'}[problem.code]||'旁白或屏幕文字的内容依据仍待补全。')}
function legacyStoryboardCueHtml(cue){
  const selected=confirmedDesignCueIds.has(cue.id),frames=(cue.frames||[]).map((frame,index)=>storyboardFrameHtml(cue,frame,index)).join(''),hasNotes=!!cue.animationNotes?.length;
  return `<article class="storyboard-card" id="frames-${esc(cue.id)}"><div class="storyboard-head"><div><h3>${esc(cue.title||cue.id)}</h3><p class="narration-anchor"><span class="eyebrow">对应旁白</span> ${esc(cue.narration||'—')}</p><p class="muted">${conceptMode()?(cue.firstConfirmed?'概念图已确认 · 实际制作静帧':'请先在脚本与思路中确认概念图'):(cue.firstConfirmed?'首次设计已确认 · 可继续修改':'尚未首次确认')}</p></div>${conceptMode()?'':`<label><input type="checkbox" data-confirm-cue="${esc(cue.id)}" ${selected?'checked':''} ${cue.canConfirm?'':'disabled'}> 确认完整 Cue</label>`}</div><section class="cue-intent"><span class="intent-label">总体意图 · 最终动画说明</span><p>${esc(cue.finalAnimationDescription||'尚未填写')}</p></section>${!conceptMode()&&!cue.canConfirm&&cue.storyboardId?`<p class="stale-frame">${esc((cue.confirmationProblems||[]).map(confirmationProblemText).join('；')||'审阅依据已更新，请生成当前 Storyboard。')}</p>`:''}<div class="frame-toolbar"><span>${(cue.frames||[]).length} 张静帧 · 编号为 Cue 内帧序号</span>${hasNotes?`<button class="all-notes" data-all-notes="${esc(cue.id)}" type="button">展开全部说明</button>`:''}</div><div class="review-frame-grid frame-grid">${frames}</div></article>`
}
function storyboardCueHtml(cue){return conceptMode()?productionSceneHtml(cue):legacyStoryboardCueHtml(cue)}
let activeTab='overview',activeStoryboardCue=null;
function intentPreferenceKey(){return `afterforge-review-v3:intent-open:${versionId}:${activeTab}`}
function workingIntentIsOpen(){try{const value=localStorage.getItem(intentPreferenceKey());return value===null?false:value==='true'}catch{return !['storyboard','preview'].includes(activeTab)}}
function toggleWorkingIntent(){
  const open=!workingIntentIsOpen();
  try{localStorage.setItem(intentPreferenceKey(),String(open))}catch{}
  applyWorkingIntentOpen(open);
}
function applyWorkingIntentOpen(open){
  const button=$('toggleWorkingIntent'),body=$('workingIntentBody');
  if(button){button.setAttribute('aria-expanded',String(open));button.textContent=open?'收起 ▴':'展开 ▾'}
  if(body)body.hidden=!open;
}
function renderWorkingIntent(){
  const items=state?.workingIntent?.items||[],root=$('workingIntent');root.hidden=!items.length;
  root.innerHTML=items.length?`<div class="working-intent-head"><p class="working-intent-label">工作意图 <span>本版备忘 · ${items.length} 条</span></p><button id="toggleWorkingIntent" type="button" aria-controls="workingIntentBody">展开</button></div><div id="workingIntentBody">`+['focus','preserve'].map(kind=>items.filter(item=>item.kind===kind).map(item=>`<section><div class="intent-row ${kind}"><strong>${kind==='focus'?'本轮重点':'暂时保持'}</strong><p>${esc(item.text)}${item.locator?.description?`<small class="intent-location">${esc(item.locator.description)}</small>`:''}</p></div><details class="intent-source"><summary>用户来源</summary><p>${esc(item.source?.text)}<br>${esc(item.source?.reference)}</p></details></section>`).join('')).join('')+'</div>':'';
  if(items.length){$('toggleWorkingIntent').onclick=toggleWorkingIntent;applyWorkingIntentOpen(workingIntentIsOpen())}
}
function setActiveStoryboardCue(id){
  activeStoryboardCue=id;
  document.querySelectorAll('[data-storyboard-jump]').forEach(link=>{const active=link.dataset.storyboardJump===id;link.classList.toggle('is-current',active);link.setAttribute('aria-current',active?'location':'false')});
}
function jumpToStoryboardCue(id){
  if(!storyboardCues().some(c=>c.id===id))return;
  activateTab('storyboard');setActiveStoryboardCue(id);
  $('frames-'+id)?.scrollIntoView?.({block:'start'});
}
function renderCueNavigation(){
  const cues=storyboardCues();
  const status=cue=>{if(activeTab==='overview'&&conceptMode()){const c=conceptCues().find(c=>c.cueId===cue.id);return c?.confirmationProblems?.length?'待处理':c?.firstConfirmed?'已确认':'待确认'}const p=cue.sceneReview?.[sceneView(cue.id).mode];return p?.problems?.length?'待处理':p?.current?'已审阅':conceptMode()?'待审阅':cue.firstConfirmed?'已确认':cue.canConfirm?'待确认':'待处理'};
  const marker=cue=>`<span class="nav-dot ${['已确认','已审阅'].includes(status(cue))?'confirmed':''}" aria-label="${status(cue)}"></span>`;
  $('cueNavigation').hidden=activeTab==='storyboard'||activeTab==='preview';
  $('cueNavigation').innerHTML=cues.map(c=>`<a href="#${esc(encodeURIComponent((conceptMode()?'concept-':'frames-')+c.id))}" data-cue-jump="${esc(c.id)}"><span>${esc(c.title||c.id)}<small>${status(c)}</small></span>${marker(c)}</a>`).join('');
  document.querySelectorAll('[data-cue-jump]').forEach(link=>link.onclick=event=>{event.preventDefault();if(conceptMode())$('concept-'+link.dataset.cueJump)?.scrollIntoView?.({block:'start'});else jumpToStoryboardCue(link.dataset.cueJump)});
  $('storyboardNavigator').hidden=activeTab!=='storyboard'||!cues.length;
  $('storyboardNavProgress').textContent=`${cues.length} 场 · ${cues.filter(c=>!['已确认','已审阅'].includes(status(c))).length} 场待处理`;
  $('storyboardCueNavigation').innerHTML=cues.map((c,i)=>`<a href="#${esc(encodeURIComponent('frames-'+c.id))}" data-storyboard-jump="${esc(c.id)}" class="storyboard-nav-link"><span class="storyboard-nav-number">${String(i+1).padStart(2,'0')}</span><span class="storyboard-nav-label">${esc(c.title||c.id)}<small>${status(c)}</small></span>${marker(c)}</a>`).join('');
  document.querySelectorAll('[data-storyboard-jump]').forEach(link=>link.onclick=event=>{event.preventDefault();jumpToStoryboardCue(link.dataset.storyboardJump)});
  setActiveStoryboardCue(cues.some(c=>c.id===activeStoryboardCue)?activeStoryboardCue:cues[0]?.id);renderDemoNavigation();
}
function updateStoryboardPosition(){
  if(activeTab!=='storyboard')return;
  const cards=[...document.querySelectorAll('#storyboard .storyboard-card[id]')];
  let current=cards[0];for(const card of cards){if(card.getBoundingClientRect().top<=150)current=card;else break}
  if(typeof window!=='undefined'&&window.scrollY+window.innerHeight>=document.documentElement.scrollHeight-2)current=cards.at(-1);
  if(current)setActiveStoryboardCue(current.id.slice('frames-'.length));
}
function updateAllNotesLabels(){document.querySelectorAll('[data-all-notes]').forEach(button=>{const cue=storyboardCues().find(c=>c.id===button.dataset.allNotes);button.textContent=cue?.animationNotes?.every(n=>noteExpansion.get(noteKey(cue,n)))?'收起全部说明':'展开全部说明'})}
function setNoteOpen(key,open){noteExpansion.set(key,open);document.querySelectorAll('[data-note-key]').forEach(note=>{if(note.dataset.noteKey!==key)return;note.querySelector('p').hidden=!open;note.querySelector('[data-note-toggle]').setAttribute('aria-expanded',String(open))});updateAllNotesLabels()}
function showRelatedNote(key){
  const cue=storyboardCues().find(c=>(c.animationNotes||[]).some(n=>noteKey(c,n)===key)),note=cue?.animationNotes.find(n=>noteKey(cue,n)===key);if(!note)return;
  setNoteOpen(key,true);
  document.querySelectorAll('[data-frame-cue]').forEach(frame=>frame.classList.toggle('is-related',frame.dataset.frameCue===cue.id&&note.frameIds.includes(frame.dataset.frame)));
  document.querySelectorAll('[data-note-relation]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.noteRelation===key)));
}
function bindStoryboardPresentation(){
  updateAllNotesLabels();
  document.querySelectorAll('[data-comment-key]').forEach(details=>details.ontoggle=()=>{if(details.isConnected)rememberCommentOpen(details.dataset.commentKey,details.open)});
  document.querySelectorAll('[data-note-toggle]').forEach(button=>button.onclick=()=>setNoteOpen(button.dataset.noteToggle,button.getAttribute('aria-expanded')!=='true'));
  document.querySelectorAll('[data-note-relation]').forEach(button=>button.onclick=()=>showRelatedNote(button.dataset.noteRelation));
  document.querySelectorAll('[data-all-notes]').forEach(button=>button.onclick=()=>{const cue=storyboardCues().find(c=>c.id===button.dataset.allNotes),open=!cue.animationNotes.every(n=>noteExpansion.get(noteKey(cue,n)));for(const n of cue.animationNotes)setNoteOpen(noteKey(cue,n),open);button.textContent=open?'收起全部说明':'展开全部说明'});
  document.querySelectorAll('[data-frame-preview]').forEach(button=>button.onclick=()=>openFramePreview(button.dataset.imageTitle,button.dataset.imageUrl));
}
function orphanStoryboardHtml(){return currentStoryboardDrafts().filter(storyboardDraftIsStale).map(draft=>{const cue=storyboardCues().find(item=>item.id===draft.cueId),frame=cue&&storyboardFrame(cue,draft);return `<article class="storyboard-card"><h3>${esc(draft.cueId)} · 旧静帧草稿</h3><p class="stale-frame">${esc(draft.body)}。此草稿绑定 ${esc(draft.storyboardId)}，不会自动绑定新静帧。</p>${frame?`<button data-orphan-rebind="${esc(JSON.stringify([versionId,draft.cueId,draft.storyboardId,draft.frameId]))}" data-cue-id="${esc(cue.id)}" data-storyboard-id="${esc(cue.storyboardId)}" data-frame-id="${esc(frame.frameId)}">核对后绑定当前同名帧</button>`:'<p class="muted">当前没有同名帧；草稿保留供复制。</p>'}</article>`}).join('')}
function captureCommentPreferences(){document.querySelectorAll('[data-comment-key]').forEach(details=>rememberCommentOpen(details.dataset.commentKey,details.open))}
function renderStoryboards(){captureCommentPreferences();const root=$('storyboards'),cues=storyboardCues();if(!cues.length){root.innerHTML=orphanStoryboardHtml();renderCueNavigation();return}recoverStoryboardFeedbackIds();const selected=cues.filter(cue=>confirmedDesignCueIds.has(cue.id)).length,rounds=(state.storyboard.rounds||[]).filter(round=>round.storyboardIds?.length).map(round=>({submitted:'已交棒，待 Agent 处理',processing:'Agent 处理中',processed:'本轮意见已处理，设计确认单独记录'}[round.status]||round.status)).join('；')||'尚未提交',header=`<section class="storyboard-round-actions"><div><h2>分镜与动画 · 逐场审阅</h2><p class="muted">${conceptMode()?'检查实际构图、文字和素材关系，留下制作反馈。':'旁白、静帧和最终动画说明在同一处审阅；确认始终针对完整 Cue 的 Storyboard。'}审阅轮次：${esc(rounds)}</p></div><div><button data-storyboard-preview type="button">生成静帧</button> <button data-storyboard-submit type="button">提交本轮反馈</button>${conceptMode()?' <button class="primary" data-storyboard-produce type="button">确认本轮，生成整片 Demo</button>':` <button data-confirm-design type="button" ${selected?'':'disabled'}>确认所选设计（${selected}）</button> <button class="primary" data-confirm-round type="button">确认本轮设计</button>`}</div><p id="storyboardQualificationStatus" class="storyboard-qualification" role="status"></p><p id="storyboardActionStatus" class="storyboard-action-status" role="status" aria-live="polite" aria-atomic="true"></p>${conceptMode()?'':'<p class="storyboard-action-help">整轮通过请直接「确认本轮设计」；只通过部分设计时，再勾选「确认完整 Cue」。</p>'}</section>`;root.innerHTML=header+cues.map(storyboardCueHtml).join('')+orphanStoryboardHtml();document.querySelectorAll('[data-storyboard-draft]').forEach(area=>area.oninput=()=>setStoryboardDraft(area.dataset.cueId,area.dataset.storyboardId,area.dataset.frameId,area.value));document.querySelectorAll('[data-confirm-cue]').forEach(box=>box.onchange=()=>toggleConfirmDesignCue(box.dataset.confirmCue));document.querySelectorAll('[data-save-frame]').forEach(button=>button.onclick=()=>saveStoryboardFeedback(button.dataset.cueId,button.dataset.storyboardId,button.dataset.saveFrame));document.querySelectorAll('[data-rebind-frame]').forEach(button=>button.onclick=()=>rebindStoryboardDraft(button.dataset.cueId,button.dataset.storyboardId,button.dataset.rebindFrame));document.querySelectorAll('[data-orphan-rebind]').forEach(button=>button.onclick=()=>rebindStoryboardDraft(button.dataset.cueId,button.dataset.storyboardId,button.dataset.frameId,button.dataset.orphanRebind));const preview=document.querySelectorAll('[data-storyboard-preview]')[0],submit=document.querySelectorAll('[data-storyboard-submit]')[0],confirm=document.querySelectorAll('[data-confirm-design]')[0];if(preview)preview.onclick=previewStoryboards;if(submit)submit.onclick=submitStoryboardRound;if(confirm)confirm.onclick=confirmSelectedDesigns;const round=document.querySelectorAll('[data-confirm-round]')[0];if(round)round.onclick=openRoundDesignConfirmation;const produce=document.querySelectorAll('[data-storyboard-produce]')[0];if(produce)produce.onclick=openStoryboardProduction;bindStoryboardPresentation();if(conceptMode())bindSceneCards();renderStoryboardActionStatus();renderCueNavigation()}
const explorationSelection=new Map();
function explorationReferences(variant){return (variant?.references||[]).map(ref=>{const label=ref.title||ref.label||ref.description||ref.url||ref.path||'参考资料';return /^https?:\/\//i.test(ref.url||'')?`<p class="muted"><a href="${esc(ref.url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a></p>`:`<p class="muted">参考：${esc(label)}</p>`}).join('')}
function renderExplorations(){const root=$('explorations'),items=state?.explorations||[],artifacts=new Map((state?.artifacts||[]).map(item=>[item.id,item]));$('explorationTab').hidden=!items.length;if(!items.length){root.innerHTML='';return}root.innerHTML=`<section class="exploration"><h2>可选视觉探索</h2><p class="muted">切换候选只改变当前浏览；采用意向会作为普通反馈提交，实际采用由 Agent 按确认范围落实到制作源。</p>${items.map(item=>{const chosen=explorationSelection.get(item.id)||item.variants?.[0]?.id,variant=item.variants?.find(value=>value.id===chosen)||item.variants?.[0],images=(variant?.artifactIds||[]).map(id=>artifacts.get(id)).filter(Boolean).map(artifact=>`<img class="exploration-image" src="${esc(artifactUrl(artifact))}" alt="${esc(variant.label||variant.id)}">`).join('')||'<p class="muted">候选尚无 PNG。</p>';return `<details open><summary>${esc(item.question||item.id)} · ${esc(item.description||'')}</summary><div class="exploration-switch">${(item.variants||[]).map(value=>`<button data-exploration-id="${esc(item.id)}" data-variant-id="${esc(value.id)}" class="${value.id===chosen?'active':''}">${esc(value.label||value.id)}</button>`).join('')}</div><article class="exploration-variant"><strong>${esc(variant?.label||variant?.id)}</strong><p>${esc(variant?.description||'')}</p><div class="exploration-gallery">${images}</div>${explorationReferences(variant)}<button data-adopt-exploration="${esc(item.id)}" data-variant-id="${esc(variant?.id)}" type="button">作为反馈目标</button></article></details>`}).join('')}</section>`;document.querySelectorAll('[data-exploration-id]').forEach(button=>button.onclick=()=>{explorationSelection.set(button.dataset.explorationId,button.dataset.variantId);renderExplorations()});document.querySelectorAll('[data-adopt-exploration]').forEach(button=>button.onclick=()=>{choose({explorationId:button.dataset.adoptExploration,variantId:button.dataset.variantId,cueIds:target.cueIds||[]});$('feedbackBody').focus?.()})}
function allVersions(){return (project?.episodes||[]).flatMap(ep=>(ep.versions||[]).map(v=>({...v,episodeTitle:ep.title})))}function latestArtifact(items){return [...(items||[])].sort((a,b)=>String(b.createdAt||'').localeCompare(String(a.createdAt||'')))[0]}function currentArtifact(s){return latestArtifact((s?.artifacts||[]).filter(a=>a.current))||latestArtifact(s?.artifacts)}function latestFullPreview(s){return latestArtifact((s?.artifacts||[]).filter(a=>a.current&&a.kind==='full-preview'))}function compareCard(label,s,forVersion){const art=currentArtifact(s),playable=art&&/\.(mp4|mov|webm)$/i.test(art.path||'');return `<article class="compare-card"><strong>${esc(label)} · ${esc(s?.identity?.versionTitle||'')}</strong>${playable?`<video controls src="${esc(artifactUrl(art,forVersion))}"></video>`:''}<p>${esc(s?.brief?.summary||'未填写说明')}</p><p>当前素材：${esc(art?.kind||art?.id||'暂无')}</p></article>`}function renderComparison(){const select=$('compareVersion'),choice=select.value;select.replaceChildren(new Option('不对照',''));for(const v of allVersions().filter(v=>v.id!==versionId)){select.add(new Option(`${v.episodeTitle||''} · ${v.title||v.id}`,v.id))}if(choice&&choice!==versionId)select.value=choice;$('compareContent').innerHTML=comparisonState?`${compareCard('当前版本',state,versionId)}${compareCard('对照版本',comparisonState,choice)}`:''}
function choose(next,{persist=true}={}){if(target.conceptId&&!('conceptId' in next))target={versionId};target={...target,...next,versionId};$('feedbackTarget').textContent=(target.conceptId||target.artifactId||(target.cueIds||[]).length||target.timeStart)?'已定位反馈':'整个版本';renderCues();if(persist)saveDraft()}
function renderCues(){$('cues').innerHTML=(state.cues||[]).filter(c=>!conceptMode()||c.productionMode==='source-only').map(c=>`<article class="cue ${(target.cueIds||[]).includes(c.id)?'selected':''}" data-cue="${esc(c.id)}"><div class="cue-meta"><strong>${esc(c.title||c.id)}</strong><span>${esc(c.range?.start||'')}</span></div><p>${esc(c.purpose||c.finalAnimationDescription||c.visualPlan||'等待设计说明')}</p></article>`).join('')||(conceptMode()?'':'<div class="empty">此版本还没有可审阅的镜头。</div>');document.querySelectorAll('[data-cue]').forEach(el=>el.onclick=()=>{const selected=new Set(target.cueIds||[]);selected.has(el.dataset.cue)?selected.delete(el.dataset.cue):selected.add(el.dataset.cue);choose({cueIds:[...selected]})})}
function artifactUrl(a,forVersion=versionId){return a.url||`/media?version=${encodeURIComponent(forVersion)}&path=${encodeURIComponent(a.path)}&v=${encodeURIComponent(a.sha256||a.id||'current')}`}
function incompleteText(a){const missing=(a.missingCueIds||[]).join('、');return missing?`不完整：缺少 ${missing}`:'不完整，不能用于批准或交付'}
function updateMediaTime(a,localTime=0){$('mediaTime').textContent=`全局时间：${formatTime(parseTime(a?.range?.start)+localTime)}`}
function isVideoArtifact(a){return /\.(mp4|mov|webm)$/i.test(a?.path||'')}
function playingArtifact(){return (state?.artifacts||[]).find(a=>a.id===$('media').dataset.artifactId)}
function renderMedia(a){
  if(!a)return;
  const video=isVideoArtifact(a);$('media').innerHTML=video?`<video controls preload="metadata" src="${esc(artifactUrl(a))}"></video>`:`<img alt="${esc(a.kind||'审阅素材')}" src="${esc(artifactUrl(a))}">`;
  $('media').dataset.artifactId=a.id;updateMediaTime(a);
  const player=$('media').querySelector?.('video');if(player)player.ontimeupdate=()=>{updateMediaTime(a,player.currentTime);updateDemoCuePosition()};
}
const artifactLabels={'full-preview':'完整预览','local-preview':'局部预览','cue-preview':'镜头预览',still:'静帧'};
function renderArtifacts(){
  const artifacts=(state.artifacts||[]).filter(isVideoArtifact),full=latestFullPreview(state),current=artifacts.filter(a=>a.current);
  const selected=explicitDemoId?artifacts.find(a=>a.id===explicitDemoId):artifacts.find(a=>a.id===$('media').dataset.artifactId)||full||latestArtifact(current)||latestArtifact(artifacts);
  const card=a=>`<article class="artifact ${a.current?'current':''}"><div><strong>${esc(artifactLabels[a.kind]||a.kind)}</strong><div class="artifact-meta">${esc(a.createdAt?.slice(0,16).replace('T',' ')||'')} · ${a.current?'当前素材':'历史素材'} · ${a.complete?'可审阅':esc(incompleteText(a))}</div></div><button data-artifact="${esc(a.id)}">查看</button></article>`;
  $('artifacts').innerHTML=artifacts.filter(a=>a.id!==selected?.id).map(card).join('')||'<div class="empty">暂无其他视频。</div>';
  // An incomplete main preview must still explain what is missing.
  if(full&&!full.complete)$('artifacts').innerHTML=card(full)+$('artifacts').innerHTML;
  document.querySelectorAll('[data-artifact]').forEach(el=>el.onclick=()=>showArtifact(artifacts.find(a=>a.id===el.dataset.artifact)));
  if(explicitDemoId&&!selected){$('media').innerHTML='<div class="empty">指定视频不可用。</div>';delete $('media').dataset.artifactId;}
  if(selected&&($('media').dataset.artifactId!==selected.id||!$('media').querySelector?.('video')))renderMedia(selected);
  renderDemoStatus();
}
function showArtifact(a){if(!a)return;explicitDemoId=null;if(!demoRoundStates.get(versionId)?.busy)demoRoundStates.delete(versionId);if(!feedbackSaveStates.get(versionId)?.busy)feedbackSaveStates.delete(versionId);$('message').textContent='';renderMedia(a);activateTab('preview');renderDemoNavigation();renderDemoFeedback();renderDemoStatus()}
function jumpToTime(value,artifactId){
  const seconds=parseTime(value);if(!Number.isFinite(seconds)||seconds<0)return false;
  const art=(state.artifacts||[]).find(a=>a.id===artifactId&&isVideoArtifact(a))||(artifactId?null:playingArtifact()||latestFullPreview(state));if(!art){$('demoStatus').textContent='指定视频不可用，未切换到其他视频。';return false;}
  explicitDemoId=null;
  if(playingArtifact()?.id!==art.id||!$('media').querySelector?.('video'))renderMedia(art);
  renderDemoNavigation();renderDemoFeedback();
  const player=$('media').querySelector?.('video');if(player){player.pause();player.currentTime=Math.max(0,seconds-parseTime(art.range?.start||'0s'))}
  activateTab('preview');updateMediaTime(art,player?.currentTime||0);updateDemoCuePosition();$('media').scrollIntoView?.({block:'start',behavior:'smooth'});return true;
}
function capturePlaybackTime(){
  const art=playingArtifact(),player=$('media').querySelector?.('video');if(!art||!player)return;
  player.pause();
  if(draftStale||($('feedbackBody').value.trim()&&(target.storyboardId||target.explorationId||target.artifactId&&target.artifactId!==art.id))){setDraftNotice('这份草稿属于原素材。请先保存，或明确重新定位草稿。',true);draftStale=true;return}
  const time=secondsToTime(parseTime(art.range?.start||'0s')+(player.currentTime||0));
  target={versionId,artifactId:art.id,cueIds:demoCueIdsAt(parseTime(time)),timeStart:time};$('timeStart').value=time;$('timeEnd').value='';draftBasisRevision=state.editRevision;
  $('demoWholeFeedback').checked=false;$('feedbackTarget').textContent='当前播放时间';updateDemoTimeAnchor();saveDraft();$('feedbackBody').focus?.();
}
const feedbackStatus={pending:'待处理',"needs-clarification":'待澄清',addressed:'已处理',accepted:'已接受'};
function renderFeedback(){$('feedbackList').innerHTML=(state.feedback||[]).map(f=>`<article class="feedback-item"><div class="feedback-meta">${esc(f.target?.artifactId||f.target?.cueIds?.join('、')||'整个版本')} · <span class="status ${esc(f.status)}">${esc(feedbackStatus[f.status]||f.status)}</span></div><p>${esc(f.body)}</p>${f.target?.timeStart?`<button type="button" data-feedback-time="${esc(f.target.timeStart)}" data-feedback-artifact="${esc(f.target?.artifactId||'')}">定位 ${esc(f.target.timeStart)}</button>`:''}</article>`).join('')||'<div class="empty">还没有保存的反馈。</div>';document.querySelectorAll('[data-feedback-time]').forEach(el=>el.onclick=()=>jumpToTime(el.dataset.feedbackTime,el.dataset.feedbackArtifact||undefined))}
const actionLabels={preview:'生成完整预览',approve:'本版效果通过',authorize:'授权正式交付','approve-and-deliver':'批准并开始交付',deliver:'开始已授权交付'};
function renderActions(){
  const available=state.availableActions||[],approved=demoIsApproved(),allowed=available.filter(a=>actionLabels[a]);
  const button=a=>`<button data-action="${esc(a)}">${esc(actionLabels[a])}</button>`;
  const scopes=demoScopes(),scopeNote=state.storyboard?`<p class="demo-scope muted">本轮创作：${esc(scopes.workScopeCueIds.join('、')||'无新增修改')}<br>Demo 呈现：${esc(scopes.presentationCueIds.join('、')||'无')}<br>明确排除：${esc(scopes.excludedCueIds.join('、')||'无')}</p>`:'';
  $('actions').innerHTML=scopeNote+allowed.filter(a=>a==='preview'||a==='approve'||approved).map(button).join('');
  $('demoProductionActions').innerHTML=scopeNote+allowed.filter(a=>a==='preview').map(button).join('');
  $('demoDeliveryButtons').innerHTML=approved?allowed.filter(a=>['authorize','deliver'].includes(a)).map(button).join(''):'';
  $('demoDeliveryActions').hidden=!approved;
  document.querySelectorAll('[data-action]').forEach(el=>el.onclick=()=>runAction(el.dataset.action,el.textContent));
  renderDemoStatus();
}
function renderTasks(){
  const tasks=state.tasks||[];$('demoTasks').innerHTML=tasks.map(task=>`<details><summary>${esc({failed:'历史失败',complete:'已完成',completed:'已完成'}[task.status]||'执行中')} · ${esc(task.createdAt||task.id)}</summary><p class="muted">${esc(task.error||task.id)}</p>${task.status==='failed'?`<button data-resume="${esc(task.id)}">恢复此任务</button>`:''}</details>`).join('')||'<p class="muted">暂无任务记录。</p>';
  document.querySelectorAll('[data-resume]').forEach(el=>el.onclick=()=>sendAction('resume',{...requestBase(),jobId:el.dataset.resume}));
}
function draft(){return {wholeDemo:$('demoWholeFeedback').checked,body:$('feedbackBody').value,timeStart:$('timeStart').value,timeEnd:$('timeEnd').value,target,basisRevision:draftBasisRevision??state?.editRevision}}function setDraftNotice(message,stale=false){$('draftNotice').hidden=false;$('draftNotice').textContent=message;$('retargetDraft').hidden=!stale;$('submitFeedback').disabled=stale}function saveDraft(){const key=storageKey();localStorage.setItem(key,JSON.stringify(draft()));localStorage.setItem(draftPointerKey(),key)}function clearDraft(){const key=storageKey();localStorage.removeItem(key);if(localStorage.getItem(draftPointerKey())===key)localStorage.removeItem(draftPointerKey())}function markDraftStale(previous){draftStale=true;draftBasisRevision=previous;setDraftNotice(`草稿基于编辑版本 ${previous}，当前已更新为 ${state.editRevision}；请核对后重新定位。`,true)}function restoreDraft(){const raw=localStorage.getItem(localStorage.getItem(draftPointerKey())||storageKey());if(!raw)return;try{const d=JSON.parse(raw);$('demoWholeFeedback').checked=d.wholeDemo??!!(d.body&&!d.timeStart);if(d.target?.versionId===versionId)target=d.target;$('feedbackBody').value=d.body||'';$('timeStart').value=d.timeStart||'';$('timeEnd').value=d.timeEnd||'';draftBasisRevision=d.basisRevision??state.editRevision;if(d.body){$('feedbackTarget').textContent=(target.conceptId||target.artifactId||(target.cueIds||[]).length||target.timeStart)?'已定位反馈':'整个版本';renderCues();if(draftBasisRevision!==state.editRevision&&!immutableVideoDraft())markDraftStale(draftBasisRevision);else setDraftNotice('已恢复本版本、素材和编辑版本对应的本地草稿。')}}catch{}}
function selectionAnchor(cue){return JSON.stringify([cue.storyboardId,(cue.frames||[]).map(storyboardAnchor)])}
async function submitFeedback(e){
  e.preventDefault();if(feedbackSaveStates.get(versionId)?.busy||demoRoundStates.get(versionId)?.busy)return;if(draftStale){markDraftStale(draftBasisRevision);return}
  const body=$('feedbackBody').value.trim();if(!body){setFeedbackSaveStatus(versionId,'error','请先填写意见。');return}
  const start=normalizeTime($('timeStart').value),end=normalizeTime($('timeEnd').value);
  if(start===null||end===null||(start&&parseTime(start)<0)||(end&&(!start||parseTime(end)<parseTime(start)))){setFeedbackSaveStatus(versionId,'error','时间必须是有效秒数，且终点不早于起点。');saveDraft();return}
  if(activeTab==='preview'&&!target.artifactId){const a=playingArtifact();if(!a){setFeedbackSaveStatus(versionId,'error','请先选择 Demo 视频。');return}target={versionId,artifactId:a.id}}
  $('timeStart').value=start;$('timeEnd').value=end;
  const actionVersion=versionId,storedKey=storageKey(),pointerKey=draftPointerKey(),originalTarget=JSON.stringify(target),storedSnapshot=localStorage.getItem(storedKey);
  const request={...requestBase(),operation:'feedback',body,source:{channel:'review',text:body,reference:`review:${actionVersion}:${crypto.randomUUID()}`},target:{...target,timeStart:start||undefined,timeEnd:end||undefined}};
  let saved=false;const token={};setFeedbackSaveStatus(actionVersion,'pending','保存中…',true);feedbackSaveStates.get(actionVersion).token=token;
  const notify=(kind,message,busy=false)=>{if(feedbackSaveStates.get(actionVersion)?.token===token){setFeedbackSaveStatus(actionVersion,kind,message,busy);feedbackSaveStates.get(actionVersion).token=token}};
  try{
    const result=await postVersionAction(actionVersion,request);saved=true;demoRoundStates.delete(actionVersion);
    const stored=localStorage.getItem(storedKey);
    if(stored&&stored===storedSnapshot){localStorage.removeItem(storedKey);if(localStorage.getItem(pointerKey)===storedKey)localStorage.removeItem(pointerKey)}
    notify('success','✓ 已保存。审阅完可提交本轮反馈。');
    if(versionId!==actionVersion)return;
    if(result.record?.id&&!state.feedback.some(f=>f.id===result.record.id))state.feedback.push(result.record);
    if($('feedbackBody').value.trim()===body&&originalTarget===JSON.stringify(target)&&normalizeTime($('timeStart').value)===start&&normalizeTime($('timeEnd').value)===end){draftBasisRevision=null;$('feedbackBody').value='';if(activeTab==='preview'){$('timeStart').value='';$('timeEnd').value='';$('demoWholeFeedback').checked=false;target={versionId,artifactId:playingArtifact()?.id};updateDemoTimeAnchor()}}
    renderDemoFeedback();await selectVersion(actionVersion,{preserveTarget:true});
  }catch(error){notify(saved?'success':'error',saved?`✓ 已保存，但列表刷新失败：${error.message}。请刷新状态。`:error.status===409?'版本已更新：草稿与原定位已保留，请核对后重试。':`保存失败：${error.message}。草稿已保留。`,true);if(!saved&&versionId===actionVersion)saveDraft()}
  finally{const item=feedbackSaveStates.get(actionVersion);if(item?.token===token){item.busy=false;if(versionId===actionVersion){renderFeedbackSaveStatus();renderDemoFeedback();renderDemoStatus()}}}
}
async function sendAction(action,request){
  const actionVersion=versionId;
  try{
    const result=await postVersionAction(actionVersion,request,action);
    if(versionId===actionVersion){$('message').textContent=result.status==='started'?'任务已开始，状态会自动更新。':'操作已保存。';setTimeout(()=>{if(versionId===actionVersion)selectVersion(actionVersion,{preserveTarget:true})},350)}
    return true;
  }catch(error){if(versionId===actionVersion){$('message').className='message error';$('message').textContent=error.message}return false}
}
async function decision(kind,label){const source={channel:'review',text:label,reference:`review:${versionId}:${crypto.randomUUID()}`};if(kind==='approve-and-deliver')return sendAction('deliver',{...requestBase(),decision:{kind,reviewSetId:state.reviewSet?.id,source}});return sendAction('update',{...requestBase(),operation:'decision',kind,reviewSetId:state.reviewSet?.id,source})}
function demoScopes(){const workScopeCueIds=state.workScopeCueIds||[],presentationCueIds=state.presentationCueIds||state.cues?.map(cue=>cue.id)||[],excludedCueIds=state.excludedCueIds||[];return {workScopeCueIds,presentationCueIds,excludedCueIds}}
async function runAction(action,label){if(action==='preview'){if(!state.storyboard)return sendAction('preview',{...requestBase(),scope:'full'});const taskId=crypto.randomUUID(),scopes=demoScopes(),detail=`完整 Demo：工作 cue ${scopes.workScopeCueIds.join('、')||'无'}；展示 cue ${scopes.presentationCueIds.join('、')||'无'}；排除 ${scopes.excludedCueIds.join('、')||'无'}`,decisionSource=source(detail);return sendAction('preview',{requestId:taskId,taskId,expectedRevision:state.editRevision,scope:'full',cueIds:scopes.workScopeCueIds,workCueIds:scopes.workScopeCueIds,excludedCueIds:scopes.excludedCueIds,decision:{kind:'authorize-demo',taskId,cueIds:scopes.workScopeCueIds,presentationCueIds:scopes.presentationCueIds,excludedCueIds:scopes.excludedCueIds,source:decisionSource}})}if(action==='deliver')return sendAction('deliver',requestBase());return decision(action,label)}
function activateTab(name){activeTab=name;$('reviewShell').dataset.activeTab=name;renderWorkingIntent();renderCueNavigation();document.querySelectorAll('.tab').forEach(el=>el.hidden=el.id!==name);document.querySelectorAll('[data-tab]').forEach(el=>el.classList.toggle('active',el.dataset.tab===name));layoutFeedbackPanel();scheduleReviewPoll();if(state){renderDemoNavigation();renderDemoFeedback();renderActions();renderDemoStatus()}}document.querySelectorAll('[data-tab]').forEach(el=>el.onclick=()=>{activateTab(el.dataset.tab);if(el.dataset.tab==='preview')refreshReview()});$('feedbackForm').onsubmit=submitFeedback;$('locateTime').onclick=capturePlaybackTime;['feedbackBody','timeStart','timeEnd'].forEach(id=>$(id).oninput=()=>{if(activeTab==='preview'&&!draftStale&&!target.artifactId){const a=playingArtifact();if(a)target={versionId,artifactId:a.id}}if(activeTab==='preview'&&id==='feedbackBody'&&$('feedbackBody').value.trim()&&!$('timeStart').value&&!$('demoWholeFeedback').checked&&!draftStale)capturePlaybackTime();if(id==='timeStart'&&$('timeStart').value){$('demoWholeFeedback').checked=false;if(target.artifactId)target.cueIds=demoCueIdsAt(parseTime($('timeStart').value),(state.artifacts||[]).find(a=>a.id===target.artifactId))};saveDraft();updateDemoTimeAnchor()});$('refresh').onclick=()=>versionId&&selectVersion(versionId,{preserveTarget:true});$('retargetDraft').onclick=()=>{if(activeTab==='preview'){const a=playingArtifact();target={versionId,artifactId:a?.id,timeStart:$('timeStart').value||undefined,timeEnd:$('timeEnd').value||undefined}}draftStale=false;draftBasisRevision=state.editRevision;$('submitFeedback').disabled=false;$('retargetDraft').hidden=true;setDraftNotice('草稿已按当前版本重新定位。');saveDraft()};$('compareVersion').onchange=async event=>{comparisonState=event.target.value?await api(`/api/state?version=${encodeURIComponent(event.target.value)}`):null;renderComparison()};
$('cancelProduction').onclick=cancelStoryboardProduction;
$('submitProduction').onclick=submitStoryboardProduction;
$('productionDialog').addEventListener('cancel',cancelStoryboardProduction);
$('cancelDesignConfirm').onclick=cancelRoundDesignConfirmation;
$('submitDesignConfirm').onclick=submitRoundDesignConfirmation;
$('designConfirmDialog').addEventListener('cancel',cancelRoundDesignConfirmation);
$('storyboardNavTop').onclick=event=>{event.preventDefault();$('storyboard').scrollIntoView?.({block:'start'})};
if(typeof window!=='undefined'){let scrollQueued=false;window.addEventListener('scroll',()=>{if(activeTab!=='storyboard'||scrollQueued)return;scrollQueued=true;window.requestAnimationFrame(()=>{scrollQueued=false;updateStoryboardPosition()})},{passive:true})}
$('closeLightbox').onclick=()=>{$('frameLightbox').close();clearConceptGallery()};
$('previousConcept').onclick=()=>moveConceptPreview(-1);$('nextConcept').onclick=()=>moveConceptPreview(1);
$('frameLightbox').addEventListener('close',clearConceptGallery);
$('frameLightbox').addEventListener('keydown',event=>{if(conceptGallery&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();moveConceptPreview(event.key==='ArrowLeft'?-1:1)}});
function restoreCueHash(){if(typeof location==='undefined')return;let id;try{id=decodeURIComponent(location.hash.slice(1))}catch{return}if(storyboardCues().some(c=>'frames-'+c.id===id)){activateTab('storyboard');$(id)?.scrollIntoView?.({block:'start'})}}
const feedbackSaveStates=new Map(),demoRoundStates=new Map();
function setFeedbackSaveStatus(id,kind,message,busy=false){feedbackSaveStates.set(id,{kind,message,busy});if(id===versionId)renderFeedbackSaveStatus()}
function renderFeedbackSaveStatus(){const item=feedbackSaveStates.get(versionId);if(item){$('message').className=`message ${item.kind==='error'?'error':''}`;$('message').textContent=item.message}$('submitFeedback').disabled=draftStale||!!item?.busy||!!demoRoundStates.get(versionId)?.busy;$('submitFeedback').textContent=item?.busy?'保存中…':activeTab==='preview'?'保存这条意见':'提交反馈'}
function demoCues(){return playingArtifact()?.reviewCues||[]}
function demoCueStart(c){return parseTime(c.resolvedTimeline?.start||c.range?.start||'0s')}
function demoCueIdsAt(t,artifact=playingArtifact()){return (artifact?.reviewCues||[]).filter(c=>t>=demoCueStart(c)-.001&&t<demoCueStart(c)+parseTime(c.resolvedTimeline?.duration||c.range?.duration||'0s')).map(c=>c.id)}
function renderDemoNavigation(){
  $('demoNavigator').hidden=activeTab!=='preview';
  $('demoCueNavigation').innerHTML=demoCues().map(c=>`<button class="storyboard-nav-link" data-demo-cue="${esc(c.id)}"><span class="storyboard-nav-number demo-cue-time">${formatTime(demoCueStart(c)).slice(0,5)}</span><span class="storyboard-nav-label">${esc(c.title||c.id)}</span></button>`).join('');
  document.querySelectorAll('[data-demo-cue]').forEach(b=>b.onclick=()=>jumpToTime(secondsToTime(demoCueStart(demoCues().find(c=>c.id===b.dataset.demoCue)))));updateDemoCuePosition();
}
function updateDemoCuePosition(){const a=playingArtifact(),p=$('media').querySelector?.('video');if(!a||!p)return;const ids=demoCueIdsAt(parseTime(a.range?.start||'0s')+(p.currentTime||0));document.querySelectorAll('[data-demo-cue]').forEach(b=>{const current=ids.includes(b.dataset.demoCue);b.classList.toggle('is-current',current);b.setAttribute('aria-current',current?'location':'false')})}
function layoutFeedbackPanel(){
  const demo=activeTab==='preview';$('demoFeedbackToolbar').hidden=!demo;
  if(demo&&!$('feedbackBody').value.trim()&&!$('timeStart').value&&playingArtifact())target={versionId,artifactId:playingArtifact().id};
  (demo?$('demoFeedbackSlot'):$('reviewShell')).append($('feedbackPanel'));
  $('previewActions').append($('mediaTime'),$('locateTime'));
  if(demo)$('demoFeedbackToolbar').append($('submitFeedback'),$('demoTimeAnchor'),$('demoWholeFeedbackLabel'),$('editDemoTime'));
  else $('feedbackForm').append($('submitFeedback'));
  $('submitFeedback').setAttribute('form','feedbackForm');$('feedbackTimeRange').hidden=demo&&$('editDemoTime').getAttribute?.('aria-expanded')!=='true';
  $('feedbackBody').placeholder=demo?'开始输入会暂停视频并记录时间，写下希望调整的地方…':'描述希望如何修改；可在预览中选择素材或镜头定位。';
  $('feedbackBody').setAttribute('aria-label',demo?'Demo 修改意见':'反馈内容');renderFeedbackSaveStatus();
}
function updateDemoTimeAnchor(){const t=parseTime($('timeStart').value);$('demoTimeAnchor').textContent=Number.isFinite(t)?`意见时间：${formatTime(t)}`:$('demoWholeFeedback').checked?'整版意见 · 不绑定时间':'开始输入时自动记录时间'}
function demoIsApproved(){return !!state?.reviewSet&&(state.decisions||[]).some(d=>d.reviewSetId===state.reviewSet.id&&['approve','approve-and-deliver'].includes(d.kind))}
function renderDemoStatus(){
  if(!state)return;const full=latestFullPreview(state),shown=playingArtifact(),approved=demoIsApproved();
  const newest=latestArtifact((state.artifacts||[]).filter(a=>a.kind==='full-preview')),newer=newest&&shown&&newest.id!==shown.id&&String(newest.createdAt||'')>=String(shown.createdAt||'');$('newDemoNotice').hidden=!newer;$('viewNewDemo').onclick=()=>showArtifact(newest);
  $('demoStatus').textContent=!shown?(explicitDemoId?'指定视频不可用，未切换到其他视频。':'暂无视频预览'):shown.id!==full?.id?`正在查看：${shown.id} · 历史视频${shown.reviewCues?'':' · 场景未定位'}；效果通过仅针对最新完整 Demo`:!full.complete?incompleteText(full):`最新完整 Demo · ${formatTime(parseTime(full.range?.duration))} · ${approved?'本版效果已通过':'待审阅'}`;
  if(shown&&!shown.reviewCues&&!$('demoStatus').textContent.includes('场景未定位'))$('demoStatus').textContent+=' · 场景未定位';
  const eligible=full?.complete&&state.reviewSet?.artifactIds?.includes(full.id);
  $('approveDemo').textContent='确认整片，生成交付文件';
  $('approveDemo').disabled=!eligible||shown?.id!==full.id||!!feedbackSaveStates.get(versionId)?.busy||!!demoRoundStates.get(versionId)?.busy;
}
function demoFeedbackSelection(){
  const full=playingArtifact(),ids=new Set((state?.artifacts||[]).filter(a=>a.id===full?.id).map(a=>a.id));
  const feedback=(state?.feedback||[]).filter(f=>ids.has(f.target?.artifactId)&&!f.target?.storyboardId&&!f.target?.explorationId&&(!f.applicability||f.applicability.kind==='current'));
  const rounds=state?.storyboard?.rounds||[],submitted=new Set(rounds.flatMap(r=>r.feedbackIds||[]));
  const pending=feedback.filter(f=>!submitted.has(f.id));
  const latest=[...rounds].reverse().find(r=>feedback.some(f=>(r.feedbackIds||[]).includes(f.id)));
  const current=pending.length?pending:feedback.filter(f=>(latest?.feedbackIds||[]).includes(f.id));
  return {pending,current,latest};
}
function demoFeedbackWithdrawn(f){return f.applicability?.kind==='not-applicable'&&f.applicability?.source?.reference?.startsWith('review-feedback-withdraw:')}
function demoFeedbackCanWithdraw(f){return !f.target?.storyboardId&&!f.target?.explorationId&&(state.artifacts||[]).some(a=>a.id===f.target?.artifactId&&['full-preview','cue-preview'].includes(a.kind))&&(!f.applicability||f.applicability.kind==='current'||demoFeedbackWithdrawn(f))}
function feedbackCard(f,submitted=false){
  const playbackId=f.target?.artifactId;
  const withdrawn=demoFeedbackWithdrawn(f),busy=demoRoundStates.get(versionId)?.busy||feedbackSaveStates.get(versionId)?.busy;
  return `<article class="feedback-item"><div class="feedback-meta">${esc(f.target?.cueIds?.map(id=>(state.artifacts||[]).find(a=>a.id===f.target?.artifactId)?.reviewCues?.find(c=>c.id===id)?.title||id).join('、')||(f.target?.timeStart?'场景未定位':'Demo 意见'))} · ${withdrawn?'已撤回':`${submitted?'已提交 · ':''}${esc(feedbackStatus[f.status]||f.status||'已保存')}`}</div><p>${esc(f.body)}</p>${f.target?.timeStart?`<button data-demo-feedback-time="${esc(f.target.timeStart)}" data-demo-feedback-artifact="${esc(playbackId||'')}">${formatTime(parseTime(f.target.timeStart))} · 回看</button>`:''} ${demoFeedbackCanWithdraw(f)?`<button type="button" data-demo-feedback-withdraw="${esc(f.id)}" ${busy?'disabled':''}>${withdrawn?'恢复意见':'撤回意见'}</button>`:''}</article>`;
}
async function setDemoFeedbackWithdrawn(feedbackId,withdrawn){
  const id=versionId,f=(state.feedback||[]).find(f=>f.id===feedbackId);
  if(!f||!demoFeedbackCanWithdraw(f)||demoRoundStates.get(id)?.busy||feedbackSaveStates.get(id)?.busy)return;
  const verb=withdrawn?'撤回':'恢复',set=(message,busy=false)=>{demoRoundStates.set(id,{message,busy});if(versionId===id){renderDemoFeedback();renderDemoStatus();renderFeedbackSaveStatus()}};
  const evidence=source(`${verb}这条 Demo 意见：${f.body}`);
  if(withdrawn)evidence.reference=`review-feedback-withdraw:${id}:${crypto.randomUUID()}`;
  set(`${verb}中…`,true);let saved=false;
  try{const result=await postVersionAction(id,{...requestBase(),operation:'feedback-applicability',feedbackId,kind:withdrawn?'not-applicable':'current',source:evidence});saved=true;
    if(versionId===id&&result.record){const index=state.feedback.findIndex(item=>item.id===feedbackId);if(index>=0)state.feedback[index]=result.record}
    set(withdrawn?'✓ 意见已撤回，不再作为修改要求；可在历史意见中恢复。':'✓ 意见已恢复。',true);
    if(versionId===id)await selectVersion(id,{preserveTarget:true});
  }catch(error){set(saved?`已${verb}，但状态刷新失败：${error.message}。请刷新状态。`:`${verb}失败：${error.message}。原意见保持不变。`,true)}
  finally{const item=demoRoundStates.get(id);if(item)set(item.message,false)}
}
function renderDemoFeedback(){
  if(!state)return;const {pending,current,latest}=demoFeedbackSelection(),ids=new Set(current.map(f=>f.id)),rawItem=demoRoundStates.get(versionId),item=rawItem?.artifactId&&rawItem.artifactId!==playingArtifact()?.id?null:rawItem;
  $('demoFeedbackCount').textContent=`${current.length} 条`;$('demoFeedbackList').innerHTML=current.map(f=>feedbackCard(f,!pending.length)).join('')||'<div class="empty">本轮还没有意见。保存后会出现在这里。</div>';
  $('demoFeedbackHistory').innerHTML=(state.feedback||[]).filter(f=>!ids.has(f.id)).map(f=>feedbackCard(f)).join('')||'<p class="muted">暂无以往意见。</p>';
  $('demoRoundStatus').textContent=item?.message||(!pending.length&&latest?`最近一轮已提交 ${current.length} 条 · ${{submitted:'待处理',processing:'处理中',processed:'已处理'}[latest.status]||latest.status}`:'看完这一轮，再交给我处理。');
  $('submitDemoRound').disabled=!pending.length||!!item?.busy||!!feedbackSaveStates.get(versionId)?.busy;
  const requested=(state.decisions||[]).some(d=>d.reviewRoundId===latest?.id);$('requestDemoRework').disabled=(!pending.length&&(!current.length||requested))||!!item?.busy||!!feedbackSaveStates.get(versionId)?.busy;
  document.querySelectorAll('[data-demo-feedback-withdraw]').forEach(b=>b.onclick=()=>{const f=state.feedback.find(f=>f.id===b.dataset.demoFeedbackWithdraw);if(f)setDemoFeedbackWithdrawn(f.id,!demoFeedbackWithdrawn(f))});
  document.querySelectorAll('[data-demo-feedback-time]').forEach(b=>b.onclick=()=>jumpToTime(b.dataset.demoFeedbackTime,b.dataset.demoFeedbackArtifact));
}
async function submitDemoRound(rework=false){
  const id=versionId;if(demoRoundStates.get(id)?.busy||feedbackSaveStates.get(id)?.busy)return;
  let outgoing,signature;const reviewedId=playingArtifact()?.id;
  const set=(message,busy=false)=>{demoRoundStates.set(id,{message,busy,artifactId:reviewedId,request:outgoing,signature});if(versionId===id){renderDemoFeedback();renderDemoStatus();renderFeedbackSaveStatus()}};
  if($('feedbackBody').value.trim()){set('还有未保存的意见，请先保存。');return}
  const selection=demoFeedbackSelection(),pending=rework&&!selection.pending.length?selection.current:selection.pending;if(!pending.length)return;
  let saved=false;
  try{signature=JSON.stringify([reviewedId,rework,pending.map(f=>f.id),selection.pending.length?null:selection.latest?.id]);const prior=demoRoundStates.get(id);outgoing=prior?.signature===signature?prior.request:{...requestBase(),operation:'review-submit',storyboardIds:[],feedbackIds:pending.map(f=>f.id),...(rework?{...demoReworkRequest(pending),...(!selection.pending.length?{roundId:selection.latest.id}:{})}:{}),source:source(rework?'按这些意见修改并更新 Demo':'提交本轮 Demo 修改意见；不批准 Demo，也不授权交付')};set('提交中…',true);const result=await postVersionAction(id,outgoing);saved=true;
    if(versionId===id&&result.record?.id){if(!state.storyboard.rounds.some(r=>r.id===result.record.id))state.storyboard.rounds.push(result.record);renderDemoFeedback()}
    set(rework?`✓ 已登记返修，${pending.length} 条意见已提交。回到对话继续修改并生成新版。`:`✓ 已提交 ${pending.length} 条意见，等待处理。`,true);if(versionId===id)await selectVersion(id,{preserveTarget:true});
  }catch(error){set(saved?`已提交，但状态刷新失败：${error.message}。请刷新状态。`:`提交失败：${error.message}。意见仍已保存。`,true)}
  finally{const item=demoRoundStates.get(id);if(item)set(item.message,false)}
}
let demoSpaceHeld=false;
function isTextEntry(event){return (event.composedPath?.()||[event.target]).some(el=>el?.isContentEditable||el?.tagName==='TEXTAREA'||el?.getAttribute?.('role')==='textbox'||(el?.tagName==='INPUT'&&!['button','submit','reset','checkbox','radio','range','color','file','image'].includes(el.type)))}
function handleDemoSpace(event){
  if(event.type==='keyup'&&['Space',' '].includes(event.code||event.key)&&demoSpaceHeld){demoSpaceHeld=false;event.preventDefault();event.stopImmediatePropagation();return}
  if(activeTab!=='preview'||!['Space',' '].includes(event.code||event.key)||event.isComposing||isTextEntry(event))return;
  const p=$('media').querySelector?.('video');if(!p)return;event.preventDefault();event.stopImmediatePropagation();
  if(event.type==='keyup'){demoSpaceHeld=false;return}if(event.repeat||demoSpaceHeld)return;demoSpaceHeld=true;
  if(p.paused)p.play()?.catch(()=>{setFeedbackSaveStatus(versionId,'error','播放未能开始，请点击播放器重试。')});else p.pause();
}
if(typeof window!=='undefined'){window.addEventListener('keydown',handleDemoSpace,true);window.addEventListener('keyup',handleDemoSpace,true);window.addEventListener('blur',()=>{demoSpaceHeld=false})}
$('demoWholeFeedback').onchange=()=>{if(draftStale){$('demoWholeFeedback').checked=false;return}if($('demoWholeFeedback').checked){$('timeStart').value='';$('timeEnd').value='';delete target.timeStart;delete target.timeEnd}else if($('feedbackBody').value.trim())capturePlaybackTime();saveDraft();updateDemoTimeAnchor()};
$('editDemoTime').onclick=()=>{const open=$('feedbackTimeRange').hidden;$('feedbackTimeRange').hidden=!open;$('editDemoTime').setAttribute('aria-expanded',String(open))};
$('submitDemoRound').onclick=()=>submitDemoRound();
$('requestDemoRework').onclick=()=>submitDemoRound(true);
function demoReworkRequest(feedback){const art=playingArtifact(),scope=art?.coverage?.presentedCueIds||[],ids=[...new Set(feedback.flatMap(f=>f.target?.cueIds?.length?f.target.cueIds:f.target?.timeStart?[]:scope))];if(!art||!ids.length||ids.some(id=>!scope.includes(id)))throw new Error('场景尚未定位。意见已保存，请回到对话明确返修场景。');return {artifactId:art.id,decision:{kind:'authorize-demo',taskId:crypto.randomUUID(),cueIds:ids,source:source('按这些意见修改并更新 Demo')}}}
$('approveDemo').onclick=()=>{if(!$('approveDemo').disabled)openDeliveryConfirmation()};
$('confirmConceptProduction').onclick=submitConceptProduction;
$('cancelConceptProduction').onclick=()=>{conceptProduction=null;$('conceptProductionDialog').close()};
$('cancelDeliveryConfirm').onclick=()=>{deliveryConfirmation=null;$('deliveryConfirmDialog').close()};
$('submitDeliveryConfirm').onclick=submitDeliveryConfirmation;
$('backToTop').onclick=()=>{if(typeof window!=='undefined')window.scrollTo({top:0,behavior:'smooth'})};

(async()=>{project=await api('/api/project');renderProject();const initial=project.episodes?.flatMap(e=>e.versions||[]).find(v=>!v.legacy)||project.episodes?.flatMap(e=>e.versions||[])[0];const params=typeof location==='undefined'?null:new URLSearchParams(location.search);const requested=params?.get('versionId');if(requested&&!allVersions().some(v=>v.id===requested)){throw new Error('指定制作版不可用，未打开其他版本。')}if(initial){explicitDemoId=params?.get('artifactId')||null;await selectVersion(requested||initial.id);if(params?.get('tab')==='preview'||explicitDemoId){activateTab('preview');if(explicitDemoId&&!jumpToTime(playingArtifact()?.range?.start||'0s',explicitDemoId)){$('media').innerHTML='<div class="empty">指定视频不可用。</div>';delete $('media').dataset.artifactId}}else restoreCueHash()}})().catch(error=>{$('summary').textContent=error.message});
