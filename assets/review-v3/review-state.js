/* Authoritative API access, revisions and serialized writes. */
const $=id=>document.getElementById(id);let project=null,state=null,versionId=null,target={},pollTimer=null,comparisonState=null,draftBasisRevision=null,draftStale=false;
const frameFeedbackWrites=new Map(),reviewRevisions=new Map(),storyboardActionStates=new Map();
const attemptedReviewRequests=new WeakSet();
let stateReadCount=0,stateReadSequence=0;
const storyboardSaveStates=new Map(),storyboardDrafts=new Map(),confirmedDesignCueIds=new Set(),savedStoryboardFeedbackIds=new Set();
const storyboardStorageKey=(id=versionId)=>`afterforge-review-v3:storyboard:${id||'none'}`;
const storageKey=()=>`afterforge-review-v3:${versionId||'none'}:${target.artifactId||'all'}:${state?.editRevision??'none'}`;const draftPointerKey=()=>`afterforge-review-v3:pointer:${versionId||'none'}:${state?.editRevision??'none'}`;
const api=async(path,options)=>{const r=await fetch(path,options);const body=await r.json();if(!r.ok){const e=new Error(body.error||'请求失败');e.status=r.status;throw e}return body};
function versionReady(id=versionId){return id===versionId&&state?.identity?.versionId===id}
function updateVersionReadiness(){const loading=!versionReady();$('reviewShell').setAttribute('aria-busy',String(loading));for(const node of document.querySelectorAll('.workspace, #feedbackPanel'))node.inert=loading}
async function postVersionAction(actionVersion,request,action='update'){
  if(!versionReady(actionVersion))throw new Error('制作版正在读取，请等待当前内容显示后再操作。');
  // Serialize writes for this version, but do not wait for its expensive display refresh.
  const send=async()=>{
    if(!attemptedReviewRequests.has(request)){request.expectedRevision=Math.max(request.expectedRevision,reviewRevisions.get(actionVersion)||0);attemptedReviewRequests.add(request)}
    const response=await api('/api/action',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({version:actionVersion,action,request})});
    if(Number.isInteger(response.editRevision)){
      const revision=Math.max(response.editRevision,reviewRevisions.get(actionVersion)||0);
      reviewRevisions.set(actionVersion,revision);
      if(versionId===actionVersion&&state?.identity?.versionId===actionVersion){
        state.editRevision=revision;$('revision').textContent=`编辑版本 ${revision}`;
      }
    }
    return response;
  };
  const previous=frameFeedbackWrites.get(actionVersion),pending=previous?previous.catch(()=>{}).then(send):send();
  frameFeedbackWrites.set(actionVersion,pending);
  try{return await pending}finally{if(frameFeedbackWrites.get(actionVersion)===pending)frameFeedbackWrites.delete(actionVersion)}
}
async function selectVersion(id,{preserveTarget=false}={}){
  captureCommentPreferences();
  if(versionId!==id&&$('frameLightbox').open){$('frameLightbox').close();clearConceptGallery()}
  const previous=target,hadDraft=!!$('feedbackBody').value.trim(),basis=draftBasisRevision??state?.editRevision;
  if(versionId!==id){if(versionId)explicitDemoId=null;candidateChange=null;conceptProduction=null;deliveryConfirmation=null;$('conceptProductionDialog').close();$('deliveryConfirmDialog').close();cancelRoundDesignConfirmation();cancelStoryboardProduction();activeStoryboardCue=null;$('message').textContent='';$('feedbackTarget').textContent='整个版本';$('media').innerHTML='<div class="empty">此版本尚无预览素材。</div>';delete $('media').dataset.artifactId;$('mediaTime').textContent='全局时间：—';if(versionId&&hadDraft)saveDraft();for(const field of ['feedbackBody','timeStart','timeEnd'])$(field).value='';draftBasisRevision=null;draftStale=false;$('demoWholeFeedback').checked=false;confirmedDesignCueIds.clear();savedStoryboardFeedbackIds.clear()}
  const selectedBasis=new Map(storyboardCues().filter(cue=>confirmedDesignCueIds.has(cue.id)).map(cue=>[cue.id,selectionAnchor(cue)]));
  versionId=id;target=preserveTarget&&previous.versionId===id?previous:{versionId};comparisonState=null;
  updateVersionReadiness();
  $('draftNotice').hidden=true;$('retargetDraft').hidden=true;$('submitFeedback').disabled=false;
  const sequence=++stateReadSequence;stateReadCount++;
  let nextState;try{nextState=await api(`/api/state?version=${encodeURIComponent(id)}`)}finally{stateReadCount--}
  if(versionId!==id||sequence!==stateReadSequence||nextState.editRevision<(reviewRevisions.get(id)||0))return;
  reviewRevisions.set(id,nextState.editRevision);
  state=nextState;
  settleMutationReceipts(id,nextState.editRevision);
  updateVersionReadiness();
  for(const cueId of confirmedDesignCueIds){const cue=storyboardCues().find(item=>item.id===cueId);if(!cue?.canConfirm||selectedBasis.get(cueId)!==selectionAnchor(cue))confirmedDesignCueIds.delete(cueId)}
  restoreStoryboardDrafts();renderProject();renderState();
  if(preserveTarget&&hadDraft&&basis!==state.editRevision&&!immutableVideoDraft())markDraftStale(basis);
  scheduleReviewPoll();
}
function immutableVideoDraft(){return !!target.artifactId&&!target.storyboardId&&!target.explorationId&&(state?.artifacts||[]).some(a=>a.id===target.artifactId&&isVideoArtifact(a))}
function refreshReview(){if(stateReadCount||!versionId)return;return selectVersion(versionId,{preserveTarget:true}).catch(error=>{if(storyboardActionStates.get(versionId)?.kind==='running')setStoryboardActionState(versionId,{...storyboardActionStates.get(versionId),message:`状态刷新失败：${error.message}。正在重试…`})})}
function scheduleReviewPoll(){clearInterval(pollTimer);pollTimer=null;if(typeof document!=='undefined'&&document.hidden)return;const running=(state?.tasks||[]).some(t=>!['complete','completed','failed'].includes(t.status))||storyboardActionStates.get(versionId)?.kind==='running';if(running||activeTab==='preview')pollTimer=setInterval(refreshReview,running?4000:15000)}
if(typeof document.addEventListener==='function')document.addEventListener('visibilitychange',()=>{scheduleReviewPoll();if(!document.hidden)refreshReview()});
function requestBase(){return {requestId:crypto.randomUUID(),expectedRevision:state.editRevision}}
