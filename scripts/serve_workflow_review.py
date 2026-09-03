#!/usr/bin/env python3
"""Serve a local Review UI bound to exactly one AfterForge Vn."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

try:
    from scripts.hyperframes_adapter import cue_adapter, load_manifest, safe_project_path
    from scripts.layout_lock import verify_layouts
    from scripts.workflow_review import (
        add_review_comment,
        approve_demo,
        approve_storyboard,
        authorize_native_render,
        record_fcp_acceptance,
    )
    from scripts.workflow_status import resolve_stage_status
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hyperframes_adapter import cue_adapter, load_manifest, safe_project_path  # type: ignore
    from layout_lock import verify_layouts  # type: ignore
    from workflow_review import (  # type: ignore
        add_review_comment,
        approve_demo,
        approve_storyboard,
        authorize_native_render,
        record_fcp_acceptance,
    )
    from workflow_status import resolve_stage_status  # type: ignore


def _manifest_hash(root: Path) -> str:
    return hashlib.sha256((root / "animation-manifest.json").read_bytes()).hexdigest()


def review_state(version_root: Path) -> dict[str, Any]:
    root = Path(version_root).expanduser().resolve()
    manifest = load_manifest(root)
    stage_evidence = manifest.get("workflow", {}).get("stageEvidence", {})
    a11 = stage_evidence.get("A11", {}) if isinstance(stage_evidence, dict) else {}
    a13 = stage_evidence.get("A13", {}) if isinstance(stage_evidence, dict) else {}
    a11_comments = a11.get("comments", []) if isinstance(a11, dict) else []
    a13_comments = a13.get("comments", []) if isinstance(a13, dict) else []
    cue_approvals = a11.get("cueApprovals", {}) if isinstance(a11, dict) else {}
    layout_verification = verify_layouts(root)
    valid_lock_ids = set(layout_verification.get("checkedCueIds", [])) - set(
        layout_verification.get("invalidCueIds", [])
    )
    cues: list[dict[str, Any]] = []
    for cue in manifest["cues"]:
        if cue.get("productionMode") != "animation":
            continue
        adapter = cue_adapter(cue)
        lock = adapter.get("layoutLock")
        cue_comments = [comment for comment in a11_comments if comment.get("cueId") == cue["id"]]
        approval = cue_approvals.get(cue["id"], {}) if isinstance(cue_approvals, dict) else {}
        frame_src = lock.get("approvedPoster") if isinstance(lock, dict) else adapter.get("stillSrc")
        locked_frames = lock.get("reviewFrames") if isinstance(lock, dict) else None
        if not isinstance(locked_frames, list) or not locked_frames:
            locked_frames = [
                {
                    "id": "hero",
                    "role": "hero",
                    "label": "主审帧",
                    "path": frame_src,
                }
            ]
        description = cue.get("finalAnimationDescription")
        has_description = isinstance(description, str) and bool(description.strip())
        has_open_comments = any(comment.get("status") == "open" for comment in cue_comments)
        approval_blockers = []
        if cue["id"] not in valid_lock_ids:
            approval_blockers.append("布局锁无效")
        if not has_description:
            approval_blockers.append("缺少最终动画说明")
        if has_open_comments:
            approval_blockers.append("存在未处理 comment")
        cues.append(
            {
                "id": cue["id"],
                "shotNumber": cue.get("originalShotNumber"),
                "narrationAnchor": cue.get("narrationAnchor"),
                "reviewSrc": adapter.get("reviewSrc"),
                "stillSrc": adapter.get("stillSrc"),
                "heroTime": adapter.get("heroTime"),
                "resolvedTimeline": cue.get("resolvedTimeline"),
                "finalAnimationDescription": description.strip() if has_description else None,
                "approvedPoster": lock.get("approvedPoster") if isinstance(lock, dict) else None,
                "layoutRevision": lock.get("revision") if isinstance(lock, dict) else None,
                "frames": [
                    {
                        "id": frame["id"],
                        "role": frame["role"],
                        "label": frame.get("label") or ("主审帧" if frame["role"] == "hero" else "辅助帧"),
                        "src": frame.get("path") or frame.get("src"),
                        "comments": [
                            comment
                            for comment in cue_comments
                            if comment.get("frameId") == frame["id"]
                            or (comment.get("frameId") is None and frame["role"] == "hero")
                        ],
                    }
                    for frame in locked_frames
                ],
                "comments": cue_comments,
                "approvalStatus": approval.get("status", "pending") if isinstance(approval, dict) else "pending",
                "canApprove": not approval_blockers,
                "approvalBlockers": approval_blockers,
            }
        )
    comments = [*a11_comments, *a13_comments]
    demo_evidence = stage_evidence.get("A12")
    demo = None
    if isinstance(demo_evidence, dict) and isinstance(demo_evidence.get("preview"), str):
        demo = {
            "src": demo_evidence["preview"],
            "sha256": demo_evidence.get("sha256"),
            "comments": a13_comments,
        }
    return {
        "sourceVersion": manifest["sourceVersion"],
        "manifestSha256": _manifest_hash(root),
        "stageStatus": resolve_stage_status(root),
        "cues": cues,
        "demo": demo,
        "comments": comments,
    }


def apply_review_action(version_root: Path, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    root = Path(version_root).expanduser().resolve()
    if payload.get("manifestSha256") != _manifest_hash(root):
        raise ValueError("stale Review state; refresh before submitting")
    if action == "approve-storyboard":
        result = approve_storyboard(root, actor="user", cue_ids=payload.get("cueIds"))
    elif action == "add-storyboard-comment":
        result = add_review_comment(
            root,
            stage_id="A11",
            impact_scopes=["static"],
            body=payload.get("body"),
            actor="user",
            cue_id=payload.get("cueId"),
            frame_id=payload.get("frameId"),
        )
    elif action == "add-demo-comment":
        result = add_review_comment(
            root,
            stage_id="A13",
            impact_scopes=payload.get("impactScopes"),
            body=payload.get("body"),
            actor="user",
            cue_id=payload.get("cueId"),
            time_start=payload.get("timeStart"),
            time_end=payload.get("timeEnd"),
        )
    elif action == "add-comment":
        result = add_review_comment(
            root,
            stage_id=payload.get("stageId"),
            impact_scopes=payload.get("impactScopes"),
            issue_type=payload.get("issueType"),
            body=payload.get("body"),
            actor="user",
            cue_id=payload.get("cueId"),
            frame_id=payload.get("frameId"),
            time_start=payload.get("timeStart"),
            time_end=payload.get("timeEnd"),
        )
    elif action == "approve-demo":
        result = approve_demo(root, actor="user")
    elif action == "authorize-native-render":
        result = authorize_native_render(root, actor="user")
    elif action == "accept-fcp-import":
        result = record_fcp_acceptance(root, actor="user")
    else:
        raise ValueError(f"unsupported Review action: {action}")
    message = "评论已保存" if action.startswith("add-") else "已保存"
    return {"result": result, "message": message, "state": review_state(root)}


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AfterForge Review</title><style>
:root{color-scheme:dark;--bg:#0b0f14;--panel:#121923;--line:#2b3949;--text:#edf3f8;--muted:#94a3b3;--accent:#51b7d9;--warn:#f1b65d;--ok:#69c291}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
header{position:sticky;top:0;z-index:4;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 24px;background:#0b0f14ee;border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}
h1{font-size:20px;margin:0}h2{font-size:18px;margin:0}.status,.muted{color:var(--muted)}button,input,textarea{font:inherit}button{border:1px solid #466074;background:#182633;color:var(--text);padding:9px 14px;cursor:pointer}button.primary{background:var(--accent);border-color:var(--accent);color:#071017;font-weight:700}button:disabled{opacity:.35;cursor:not-allowed}
.header-actions,.review-nav,.actions,.scope-row,.range-actions{display:flex;align-items:center;flex-wrap:wrap;gap:10px}.review-nav button.active{border-color:var(--accent);color:var(--accent)}
main{max-width:1440px;margin:auto;padding:24px}.view[hidden]{display:none}.section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:18px}.section-head p{margin:5px 0 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(410px,1fr));gap:18px}.card{background:var(--panel);border:1px solid var(--line);padding:14px}.cue-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px}.cue-head h3{font-size:15px;margin:0}.badge{display:inline-block;border:1px solid var(--line);padding:2px 7px;color:var(--muted);font-size:12px}.badge.open{border-color:#745c37;color:var(--warn)}.badge.addressed{border-color:#39654e;color:var(--ok)}.badge.accepted,.badge.approved{border-color:#39654e;color:var(--ok)}
.frame{aspect-ratio:16/9;width:100%;background:#06090d;border:0;object-fit:contain}.narration{margin:0 0 12px;color:var(--muted);font-size:13px}.eyebrow{display:block;margin-bottom:4px;color:var(--accent);font-size:11px;font-weight:700;letter-spacing:.08em}.frame-gallery{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.frame-block{margin:0}.frame-block.hero{grid-column:1/-1}.frame-block figcaption{display:flex;gap:8px;align-items:center;margin-top:5px;color:var(--muted);font-size:12px}.final-description{margin:12px 0;padding:12px;border-left:2px solid var(--accent);background:#0d131b}.final-description h4{font-size:12px;margin:0 0 5px;color:var(--accent)}.final-description p{margin:0}.frame-review{margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}.frame-review h4{font-size:12px;margin:0;color:var(--muted)}.comment-list{display:grid;gap:8px;margin:10px 0}.comment-item{border-left:2px solid var(--line);padding:7px 9px;background:#0d131b}.comment-meta{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:12px}.comment-item p{margin:5px 0 0;white-space:pre-wrap}.inline-comment,.demo-comment{display:grid;gap:9px;margin-top:10px}.inline-comment textarea,.demo-comment textarea{min-height:76px;resize:vertical;background:#0d131b;color:var(--text);border:1px solid var(--line);padding:10px}.cue-actions{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:12px}
.demo{width:100%;max-height:72vh;background:#000}.player-context{display:flex;justify-content:space-between;gap:16px;padding:10px 12px;background:#0d131b;border:1px solid var(--line);border-top:0}.scope-row label,.range-actions label{display:flex;align-items:center;gap:6px}.range-panel{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px;border:1px solid var(--line);background:#0d131b}.range-value{color:var(--muted)}.context-warning{margin:12px 0;padding:10px 12px;border:1px solid #745c37;color:var(--warn)}.demo-comments{margin-top:18px}.log{white-space:pre-wrap;color:var(--muted);font-size:13px;min-height:20px}.notice{position:fixed;right:22px;bottom:22px;z-index:10;padding:11px 15px;border:1px solid #39654e;background:#11251c;color:var(--ok);box-shadow:0 10px 30px #0008}.notice.error{border-color:#745c37;background:#2a1e10;color:var(--warn)}
.range-panel[hidden]{display:none}
@media(max-width:720px){header,.section-head{align-items:stretch;flex-direction:column}.grid{grid-template-columns:1fr}.range-panel{grid-template-columns:1fr}main{padding:16px}}
</style></head><body>
<header><div><h1 id="title">AfterForge Review</h1><div class="status" id="stage"></div></div><div class="header-actions"><nav class="review-nav" aria-label="Review views"><button id="showStoryboard">Storyboard</button><button id="showDemo">480p Demo</button></nav><button id="refresh">刷新</button></div></header>
<main>
<section class="view" id="storyboardView"><div class="section-head"><div><h2>Storyboard · 静态设计</h2><p class="muted">在当前镜头和静帧旁直接评论；不需要选择 Stage、cue 或时间码。</p></div><button class="primary" id="approveCleanStoryboard">批准全部可批准镜头</button></div><div class="grid" id="cues"></div></section>
<section class="view" id="demoView" hidden><div class="section-head"><div><h2>480p Demo · 运动路径</h2><p class="muted">评论自动绑定当前播放时间和对应镜头。</p></div></div><video class="demo" id="demo" controls></video><div class="player-context"><span id="currentTime">00:00.000</span><span id="currentCue">当前镜头：—</span></div><div id="demoReopened" class="context-warning" hidden>这条静态意见已重新打开 A11，但你可以留在 Demo 页面继续审阅。</div><form class="demo-comment" id="demoComment"><textarea id="demoBody" placeholder="完整写下这条创作意见"></textarea><div><strong>影响范围</strong><span class="muted">（可多选，由你判断）</span></div><div class="scope-row"><label><input type="checkbox" id="impactStatic" value="static">静态设计</label><label><input type="checkbox" id="impactMotion" value="motion" checked>动画运动</label><label><input type="checkbox" id="useRange">标记持续范围</label></div><div class="range-panel" id="rangePanel" hidden><div><button type="button" id="captureStart">以当前时间为起点</button> <span class="range-value" id="rangeStart">未设置</span></div><div><button type="button" id="captureEnd">以当前时间为终点</button> <span class="range-value" id="rangeEnd">未设置</span></div></div><div><button class="primary" type="submit" id="submitDemoComment">提交当前时间评论</button></div></form><div class="comment-list demo-comments" id="demoComments"></div><div class="actions"><button class="primary" id="approveDemo">批准完整 Demo</button><button id="authorize">独立授权原生渲染</button><button id="acceptFcp">确认 FCP 导入验收</button></div></section>
<pre class="log" id="log" aria-live="polite"></pre>
<div class="notice" id="notice" role="status" aria-live="polite" hidden></div>
</main><script>
let state=null,activeView=null,rangeStartValue=null,rangeEndValue=null,noticeTimer=null;
const byId=id=>document.getElementById(id);const vn=p=>'/vn/'+p.split('/').map(encodeURIComponent).join('/');const sec=s=>{const x=s.slice(0,-1).split('/').map(Number);return x.length===1?x[0]:x[0]/x[1]};
function node(tag,className,text){const element=document.createElement(tag);if(className)element.className=className;if(text!==undefined)element.textContent=text;return element}
function formatTime(seconds){const mins=Math.floor(seconds/60),secs=(seconds-mins*60).toFixed(3).padStart(6,'0');return `${String(mins).padStart(2,'0')}:${secs}`}
function scopes(comment){return comment.impactScopes||[comment.issueType].filter(Boolean)}
function scopeText(comment){return scopes(comment).map(scope=>scope==='static'?'静态':'运动').join(' + ')}
function showNotice(message,isError=false){const notice=byId('notice');notice.textContent=message;notice.classList.toggle('error',isError);notice.hidden=false;if(noticeTimer)clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{notice.hidden=true},4000)}
function renderCommentList(target,comments,{showTime=false}={}){target.replaceChildren();if(!comments.length){target.append(node('div','muted','暂无 comment'));return}for(const comment of comments){const item=node('article','comment-item');const meta=node('div','comment-meta');const anchor=showTime&&comment.timeStart?`${comment.timeEnd?'区间':'时间点'} ${formatTime(sec(comment.timeStart))}${comment.timeEnd?`–${formatTime(sec(comment.timeEnd))}`:''} · `:'';meta.append(node('span','',`${anchor}${scopeText(comment)}`),node('span',`badge ${comment.status}`,comment.status));item.append(meta,node('p','',comment.body));target.append(item)}}
function switchView(name){activeView=name;const storyboard=name==='storyboard';byId('storyboardView').hidden=!storyboard;byId('demoView').hidden=storyboard;byId('showStoryboard').classList.toggle('active',storyboard);byId('showDemo').classList.toggle('active',!storyboard)}
function cueAt(seconds){return state.cues.find(cue=>{const start=sec(cue.resolvedTimeline.start),end=start+sec(cue.resolvedTimeline.duration);return start<=seconds&&seconds<end})||null}
function updatePlayerContext(seconds=byId('demo').currentTime||0){const cue=cueAt(seconds);byId('currentTime').textContent=formatTime(seconds);byId('currentCue').textContent=`当前镜头：${cue?(cue.shotNumber?`第 ${cue.shotNumber} 镜 · `:'')+cue.id:'—'}`;return cue}
function makeCueCard(cue){const card=node('article','card');const head=node('div','cue-head');const title=node('h3','',`${cue.shotNumber?`第 ${cue.shotNumber} 镜 · `:''}${cue.id} · layout r${cue.layoutRevision??'—'}`);head.append(title,node('span',`badge ${cue.approvalStatus}`,cue.approvalStatus));const narration=node('p','narration');narration.append(node('span','eyebrow','对应旁白'),document.createTextNode(cue.narrationAnchor||''));card.append(head,narration);const gallery=node('div','frame-gallery');for(const frame of cue.frames){const figure=node('figure',`frame-block ${frame.role}`);const image=node('img','frame');image.src=vn(frame.src);image.alt=`${cue.id} ${frame.label}`;const caption=node('figcaption','',`${frame.role==='hero'?'主审帧':'辅助帧'} · ${frame.label}`);figure.append(image,caption);gallery.append(figure)}card.append(gallery);const description=node('section','final-description');description.append(node('h4','','最终动画说明'),node('p','',cue.finalAnimationDescription||'尚未填写'));card.append(description);for(const frame of cue.frames){const review=node('section','frame-review');review.append(node('h4','',`${frame.role==='hero'?'主审帧':'辅助帧'} · ${frame.label} · comment`));const comments=node('div','comment-list');renderCommentList(comments,frame.comments);review.append(comments);const form=node('form','inline-comment');const body=node('textarea','');body.placeholder=`针对“${frame.label}”写 comment`;const submit=node('button','primary','提交当前静帧评论');submit.type='submit';form.append(body,submit);form.addEventListener('submit',async event=>{event.preventDefault();if(!body.value.trim()){byId('log').textContent='comment 不能为空';return}await act('add-storyboard-comment',{cueId:cue.id,frameId:frame.id,body:body.value});body.value=''});review.append(form);card.append(review)}const cueActions=node('div','cue-actions');const hint=node('span','muted',cue.canApprove?'当前镜头可批准':cue.approvalBlockers.join('；'));const approve=node('button','','批准当前镜头');approve.type='button';approve.disabled=!cue.canApprove||cue.approvalStatus==='approved';approve.addEventListener('click',()=>act('approve-storyboard',{cueIds:[cue.id]}));cueActions.append(hint,approve);card.append(cueActions);return card}
function render(){byId('cues').replaceChildren(...state.cues.map(makeCueCard));const clean=state.cues.filter(cue=>cue.canApprove&&cue.approvalStatus!=='approved').map(cue=>cue.id);byId('approveCleanStoryboard').disabled=!clean.length;byId('approveCleanStoryboard').onclick=()=>act('approve-storyboard',{cueIds:clean});if(state.demo){byId('showDemo').disabled=false;const source=vn(state.demo.src)+'?v='+encodeURIComponent(state.demo.sha256||'');if(byId('demo').dataset.src!==source){byId('demo').src=source;byId('demo').dataset.src=source}renderCommentList(byId('demoComments'),state.demo.comments,{showTime:true})}else{byId('showDemo').disabled=true;if(activeView==='demo')switchView('storyboard')}byId('demoReopened').hidden=!(state.stageStatus.activeContext==='A13'&&state.stageStatus.blockingStage==='A11');byId('approveDemo').disabled=state.stageStatus.blockingStage!=='A13';byId('authorize').disabled=state.stageStatus.blockingStage!=='A14';byId('acceptFcp').disabled=state.stageStatus.blockingStage!=='D5';updatePlayerContext()}
async function load({notify=false}={}){
  const refresh=byId('refresh');
  if(refresh.disabled)return false;
  refresh.disabled=true;refresh.textContent='刷新中…';
  try{
    const response=await fetch('/api/state',{cache:'no-store'});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||`HTTP ${response.status}`);
    state=result;
    byId('title').textContent='AfterForge Review · '+state.sourceVersion;
    byId('stage').textContent=`阻塞阶段 ${state.stageStatus.blockingStage??'无'} · 下一阶段 ${state.stageStatus.nextEligibleStage??'已完成'}`;
    if(!activeView)activeView=state.stageStatus.activeContext==='A13'&&state.demo?'demo':'storyboard';
    switchView(activeView);render();
    if(notify){const message='审核状态已刷新 · '+new Date().toLocaleTimeString();byId('log').textContent=message;showNotice(message)}
    return true;
  }catch(error){
    const message='刷新失败：'+error.message;byId('log').textContent=message;showNotice(message,true);return false;
  }finally{refresh.disabled=false;refresh.textContent='刷新'}
}
async function act(name,data={}){byId('log').textContent='提交中…';const response=await fetch('/api/action/'+name,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({manifestSha256:state.manifestSha256,...data})});const result=await response.json();if(!response.ok){byId('log').textContent=result.error;showNotice(result.error,true);await load();return false}state=result.state;byId('stage').textContent=`阻塞阶段 ${state.stageStatus.blockingStage??'无'} · 下一阶段 ${state.stageStatus.nextEligibleStage??'已完成'}`;byId('log').textContent=result.message;render();showNotice(result.message);return true}
function setRangeMode(enabled){
  byId('useRange').checked=enabled;byId('rangePanel').hidden=!enabled;
  byId('submitDemoComment').textContent=enabled?'提交区间评论':'提交当前时间评论';
  if(!enabled){rangeStartValue=null;rangeEndValue=null;byId('rangeStart').textContent='未设置';byId('rangeEnd').textContent='未设置'}
}
byId('showStoryboard').onclick=()=>switchView('storyboard');byId('showDemo').onclick=()=>switchView('demo');byId('refresh').onclick=()=>load({notify:true});byId('demo').ontimeupdate=()=>updatePlayerContext();
byId('useRange').onchange=event=>setRangeMode(event.target.checked);
byId('captureStart').onclick=()=>{setRangeMode(true);rangeStartValue=byId('demo').currentTime;byId('rangeStart').textContent=formatTime(rangeStartValue)};
byId('captureEnd').onclick=()=>{setRangeMode(true);rangeEndValue=byId('demo').currentTime;byId('rangeEnd').textContent=formatTime(rangeEndValue)};
byId('demoComment').onsubmit=async event=>{event.preventDefault();const impacts=[byId('impactStatic'),byId('impactMotion')].filter(input=>input.checked).map(input=>input.value);if(!impacts.length){byId('log').textContent='请选择至少一个影响范围';return}const ranged=byId('useRange').checked;if(ranged&&(rangeStartValue===null||rangeEndValue===null||rangeEndValue<rangeStartValue)){byId('log').textContent='持续范围需要有效的起点和终点';return}const anchor=ranged?rangeStartValue:byId('demo').currentTime;const cue=cueAt(anchor);if(impacts.includes('static')&&!cue){byId('log').textContent='静态影响需要落在一个具体镜头内';return}const saved=await act('add-demo-comment',{impactScopes:impacts,cueId:cue?cue.id:null,timeStart:`${anchor.toFixed(3)}s`,timeEnd:ranged?`${rangeEndValue.toFixed(3)}s`:null,body:byId('demoBody').value});if(saved){byId('demoBody').value=''}};
byId('approveDemo').onclick=()=>act('approve-demo');byId('authorize').onclick=()=>act('authorize-native-render');byId('acceptFcp').onclick=()=>act('accept-fcp-import');load();
</script></body></html>"""


def make_handler(version_root: Path):
    root = Path(version_root).expanduser().resolve()

    class ReviewHandler(BaseHTTPRequestHandler):
        def end_headers(self) -> None:
            # State and same-path review assets may change while this page stays open.
            self.send_header("cache-control", "no-store")
            super().end_headers()

        def _json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _file(self, target: Path) -> None:
            with target.open("rb") as source:
                size = os.fstat(source.fileno()).st_size
                start, end, partial = 0, size - 1, False
                requested = self.headers.get("Range", "") if self.command == "GET" else ""
                # Unsupported/malformed/multiple ranges fall back to a full response.
                # Without validators, If-Range cannot establish representation identity.
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
                if match and any(match.groups()) and not self.headers.get("If-Range"):
                    first, last = match.groups()
                    partial = True
                    if first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                    else:
                        start = max(0, size - int(last))
                    if start >= size or start > end:
                        self.send_response(416)
                        self.send_header("content-range", f"bytes */{size}")
                        self.send_header("accept-ranges", "bytes")
                        self.send_header("content-length", "0")
                        self.end_headers()
                        return
                self.send_response(206 if partial else 200)
                self.send_header("content-type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                self.send_header("accept-ranges", "bytes")
                self.send_header("content-length", str(end - start + 1))
                if partial:
                    self.send_header("content-range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if self.command == "HEAD":
                    return
                source.seek(start)
                remaining = end - start + 1
                try:
                    while remaining:
                        chunk = source.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Seeking may cancel an in-flight media request.

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = INDEX_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                return
            if parsed.path == "/api/state":
                try:
                    state = review_state(root)
                except (OSError, ValueError, KeyError) as error:
                    self._json(500, {"error": str(error)})
                    return
                self._json(200, state)
                return
            if parsed.path.startswith("/vn/"):
                try:
                    target = safe_project_path(root, unquote(parsed.path[4:]))
                    self._file(target)
                except (OSError, ValueError) as error:
                    self._json(404, {"error": str(error)})
                    return
                return
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/action/"):
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("content-length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("invalid request body length")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be an object")
                result = apply_review_action(root, parsed.path.rsplit("/", 1)[-1], payload)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                self._json(409, {"error": str(error)})
                return
            self._json(200, result)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ReviewHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="启动绑定单个 Vn 的本地 AfterForge Review。")
    parser.add_argument("version_root", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = args.version_root.expanduser().resolve()
    load_manifest(root)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(root))
    print(json.dumps({"status": "serving", "url": f"http://{args.host}:{args.port}", "versionRoot": str(root)}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
