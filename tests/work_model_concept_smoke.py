#!/usr/bin/env python3
"""Opt-in real concept → Review confirmation → code/PNG/MOV acceptance fixture.

Prepare uses supplied real images, never fabricates generation or approval.
Confirm the isolated version in Review, restart/reopen it, then run render.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import work_model as model
from scripts.work_model_store import load, sha
from tests.work_model_real_smoke import stage, request


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def prepare(args):
    base = args.root.resolve()
    if base.exists():
        raise ValueError('refusing to overwrite an existing acceptance fixture')
    supplied = {key: getattr(args, key) for key in ('generated_concept', 'external_concept', 'annotation_concept',
                'source_frame', 'poster_frame', 'font_source', 'gsap_source')}
    for key, value in supplied.items():
        if value is None or value.is_symlink() or not value.is_file():
            raise ValueError(f'{key} requires an existing regular local file')
    source_hashes = {str(p.resolve()): sha(p) for p in supplied.values()}
    inbox = base / 'user-inbox' / 'isolated-concepts'
    inbox.mkdir(parents=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-loop', '1', '-i', str(args.source_frame),
        '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000', '-t', '12', '-r', '24',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(inbox / 'reference.mp4')], check=True)
    (inbox / 'source.fcpxml').write_text('<?xml version="1.0" encoding="UTF-8"?><fcpxml version="1.10">'
        '<resources><format id="r1" frameDuration="1/24s" width="1920" height="1080"/></resources>'
        '<library><event name="Concept acceptance"><project name="Concept acceptance">'
        '<sequence format="r1" duration="12s"><spine><gap name="base" offset="0s" start="0s" duration="12s"/>'
        '</spine></sequence></project></event></library></fcpxml>')
    opened = model.open_project(base / 'AfterForge', {'requestId': 'open', 'expectedRevision': 0,
        'title': '概念图优先 · 隔离验收', 'episodeTitle': '两种来源、三类表达', 'inputDirectory': str(inbox)})
    root = Path(opened['root'])
    specs = [
        ('poster', '整体海报', '控制室让一段日常变成面向全球的节目。', '24小时直播\n审查 · 广告 · 蒙太奇',
         '保留外部图的控制室主画面、右侧信息栏和橙红层级。画面中的“无审查／无广告／无蒙太奇”仅为参考图原文；本次按脚本用“审查／广告／蒙太奇”，不把参考图宣传语当作影片事实。',
         '照片先建立场景，再依次出现标题与三项词语。', args.external_concept, 'user-imported'),
        ('map', '关系解释图', '摄影机记录楚门，演员参与被安排的日常，观众接收节目画面。', '摄影机\n楚门\n演员\n观众',
         '中心人物与左侧摄影机、右上演员、右下观众构成清楚关系；橙色线条说明画面的传递。不是摄影机具体位置的地图。',
         '先人物，再摄影机和演员，最后沿橙色连线抵达观众。', args.generated_concept, 'codex-generated'),
        ('annotation', '简单原片标注', '右侧这张画面让我们站到人物的观看位置。', '主观视角',
         '保留原片两幅画面，只在上方黑区增加小字和短引线；生成图用于位置参考，制作时仍使用原片原始像素。',
         '轻轻显现标注并停留，不遮挡人脸、狗或已有画面。', args.annotation_concept, 'codex-generated'),
    ]
    cues = [{'id': cid, 'title': title, 'productionMode': 'animation', 'status': 'ready',
             'resolvedTimeline': {'start': f'{index * 4}s', 'duration': '4s'}, 'narrationAnchor': narration,
             'screenText': words.split('\n'), 'finalAnimationDescription': idea, 'segmentIds': [cid],
             'renderAdapters': {'hyperframes': {'compositionId': cid, 'compositionSrc': f'compositions/cues/{cid}.html'}}}
            for index, (cid, title, narration, words, idea, motion, image, kind) in enumerate(specs)]
    brief = {'summary': '隔离验收：真实生成图与外部导入图经同一审核确认后进入制作',
             'segments': [{'id': cid, 'title': title, 'narration': narration} for cid, title, narration, *_ in specs]}
    model.update(root, request(root, 'plan', operation='edit', patch={'brief': brief, 'cues': cues}))
    vendor = stage(root, {}, {'runtime/gsap.min.js': args.gsap_source})[0]['source']
    model.update(root, request(root, 'runtime', operation='runtime', version=args.runtime, vendorSource=vendor))
    concepts = []
    for cid, title, narration, words, idea, motion, image, kind in specs:
        staged = root / '.staging' / ('concept-' + cid + image.suffix)
        shutil.copy2(image, staged)
        concepts.append(model.update(root, request(root, 'concept-' + cid, operation='concept', action='register',
            cueId=cid, imageSource=str(staged), origin={'kind': kind, 'reference': str(image.resolve())},
            idea=idea, motion=motion))['record'])
    assets = base / 'inputs'
    assets.mkdir()
    for key in ('source_frame', 'poster_frame', 'font_source'):
        shutil.copy2(supplied[key], assets / {'source_frame':'source.png', 'poster_frame':'poster.png', 'font_source':'title.woff2'}[key])
    evidence = {'root': str(root), 'afterforge': str(base / 'AfterForge'), 'runtime': args.runtime,
                'sourceHashes': source_hashes, 'concepts': concepts, 'versionId': load(root)['identity']['versionId']}
    assert not load(root)['decisions'] and not load(root)['artifacts']
    dump(base / 'prepare-evidence.json', evidence)
    dump(base / 'unconfirmed-manifest.json', load(root))
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def document(cid, contents, styles=''):
    return f'''<!doctype html><html><head><style>
html,body{{margin:0;width:1920px;height:1080px;overflow:hidden;background:transparent}}
@font-face{{font-family:ConceptChinese;src:url("assets/fonts/title.woff2") format("woff2")}}
[data-composition-id="{cid}"]{{position:relative;width:100%;height:100%;font-family:ConceptChinese,sans-serif;color:#f8f0e1}}
{styles}</style></head><body><div data-composition-id="{cid}" data-width="1920" data-height="1080" data-duration="4" data-fps="24">{contents}</div>
<script src="compositions/motion/{cid}.js"></script></body></html>'''


def poster():
    return document('poster', '''<div class="poster-bg"></div><img id="poster-photo" src="assets/images/poster.png">
<div id="poster-copy"><div class="poster-kicker">向 全 世 界 直 播</div><h1><em>24</em>小时直播</h1>
<div class="poster-feature"><span>01</span>审查</div><div class="poster-feature"><span>02</span>广告</div><div class="poster-feature"><span>03</span>蒙太奇</div>
<div class="poster-footer">楚门的世界 · 被组织的日常</div></div>''', '''
.poster-bg{position:absolute;inset:0;background:#090b0d}#poster-photo{position:absolute;left:0;top:0;width:1240px;height:1080px;object-fit:cover;object-position:45% 50%}
#poster-copy{position:absolute;left:1280px;top:140px;width:570px}.poster-kicker{font-size:27px;letter-spacing:4px;color:#e8b996}h1{font-size:62px;line-height:1.3;margin:44px 0 65px;white-space:nowrap;font-weight:700}h1 em{font-size:120px;font-style:normal;color:#ef512c;margin-right:12px}.poster-feature{font-size:64px;border-top:1px solid #763021;padding:24px 0}.poster-feature span{font-size:27px;color:#ef512c;margin-right:36px}.poster-footer{font-size:22px;letter-spacing:3px;color:#b7aaa0;margin-top:50px}''')


def map_diagram():
    person = '<circle cx="0" cy="-125" r="35"/><path d="M-34,-84 Q0,-103 34,-84 L52,50 L26,50 L23,165 L2,165 L-3,52 L-12,52 L-20,165 L-43,165 L-33,40 L-55,43Z"/>'
    return document('map', f'''<div class="map-bg"></div><svg viewBox="0 0 1920 1080" width="1920" height="1080" xmlns="http://www.w3.org/2000/svg">
<g stroke="#d8cebc" fill="none" stroke-width="3"><path d="M450 560 V330 C450 110 1320 110 1320 330 V560"/><path d="M580 540V470L655 420L730 470V540M660 540V510H690V540M970 540V470L1045 420L1120 470V540"/></g>
<g id="map-person" fill="#252827" transform="translate(885 492)">{person}</g>
<g id="map-camera" fill="#252827"><rect x="165" y="380" width="190" height="118" rx="8"/><path d="M355 402L415 378V501L355 477ZM237 498H280V535H237ZM245 535L195 670H175L230 530ZM270 530L330 670H310L255 535Z"/><circle cx="205" cy="352" r="37"/><circle cx="292" cy="352" r="37"/></g>
<g id="map-actors" fill="#252827"><g transform="translate(1230 300) scale(.65)">{person}</g><g transform="translate(1360 300) scale(.65)">{person}</g></g>
<g id="map-audience" fill="#252827"><rect x="1460" y="510" width="325" height="205" rx="12"/><rect x="1478" y="528" width="289" height="168" fill="#e4dbca"/><g transform="translate(1630 612) scale(.36)">{person}</g><circle cx="1500" cy="785" r="35"/><circle cx="1620" cy="770" r="38"/><circle cx="1740" cy="785" r="35"/><path d="M1445 888V835Q1500 775 1555 835V888M1550 888V823Q1620 757 1690 823V888M1685 888V835Q1740 775 1795 835V888Z"/><rect x="1410" y="867" width="420" height="66" rx="20"/></g>
<g fill="none" stroke="#e5532b" stroke-width="6" stroke-linecap="round"><path id="map-gaze" d="M420 440L800 492"/><path id="map-performance" d="M1170 360L945 438" stroke-dasharray="15 12"/><path id="map-transmission" d="M240 705V750Q240 790 280 790H1320Q1360 790 1360 750V650Q1360 620 1390 620H1430"/></g>
<g fill="#252827" style="font-family:ConceptChinese;font-size:56px;text-anchor:middle"><text x="280" y="730">摄影机</text><text x="880" y="730">楚门</text><text x="1300" y="150">演员</text><text x="1620" y="1010">观众</text></g></svg>''', '.map-bg{position:absolute;inset:0;background:#f4ecdf}svg{position:absolute;inset:0}')


def annotation():
    return document('annotation', '''<div id="annotation-label">主观视角</div><svg id="annotation-line" width="1920" height="1080" viewBox="0 0 1920 1080"><path d="M1160 265L1230 180" stroke="#f8f0e1" stroke-width="3" fill="none"/></svg>''', '#annotation-label{position:absolute;left:1250px;top:142px;font-size:48px;line-height:1.3}#annotation-line{position:absolute;inset:0}')


def motion(cid):
    prefix = 'window.__timelines=window.__timelines||{};const tl=gsap.timeline({paused:true});'
    if cid == 'poster':
        body = 'tl.fromTo("#poster-copy",{opacity:0,y:28},{opacity:1,y:0,duration:.8,ease:"power2.out"},.2);tl.fromTo(".poster-feature",{opacity:0,x:24},{opacity:1,x:0,duration:.6,stagger:.25,ease:"power2.out"},.7);'
    elif cid == 'map':
        body = 'tl.fromTo("#map-person",{opacity:0},{opacity:1,duration:.5},0);tl.fromTo("#map-camera,#map-actors",{opacity:0},{opacity:1,duration:.6},.4);tl.fromTo("#map-gaze,#map-performance",{opacity:0},{opacity:1,duration:.4},.9);tl.fromTo("#map-transmission",{strokeDasharray:1850,strokeDashoffset:1850},{strokeDashoffset:0,duration:1.2,ease:"power1.inOut"},1);tl.fromTo("#map-audience",{opacity:0},{opacity:1,duration:.6},1.6);'
    else:
        body = 'tl.fromTo("#annotation-label,#annotation-line",{opacity:0},{opacity:1,duration:.7,ease:"power1.out"},.35);'
    return prefix + body + f'window.__timelines["{cid}"]=tl;'


def render(args):
    base = args.root.resolve()
    prepared = json.loads((base / 'prepare-evidence.json').read_text())
    root = Path(prepared['root'])
    state = model.status(root)
    if not all(c['firstConfirmed'] for c in state['conceptDesign']['cues']):
        raise ValueError('confirm the isolated concept images in Review before code production')
    # Read the persisted image basis after reopening; generation URLs are not inputs.
    basis = []
    for cue in state['conceptDesign']['cues']:
        concept = next(c for c in state['concepts'] if c['id'] == cue['confirmedId'])
        data = (root / concept['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == concept['sha256']
        basis.append({'cueId': cue['cueId'], 'conceptId': concept['id'], 'sha256': concept['sha256'],
                      'origin': concept['origin'], 'idea': concept['idea'], 'motion': concept['motion']})
    cues = load(root)['cues']
    files = {}
    for cue in cues:
        cid = cue['id']
        cue['renderAdapters']['hyperframes'].update(motionSrc=f'compositions/motion/{cid}.js',
            layoutDependencies=['assets/fonts/title.woff2'] + (['assets/images/poster.png'] if cid == 'poster' else []))
        cue['alphaExpectation'] = {'mode': 'transparent' if cid == 'annotation' else 'opaque'}
        background = 'timeline' if cid == 'annotation' else 'none'
        cue['storyboard'] = {'frames': [{'id': 'hero', 'role': 'hero', 'label': '完整构图', 'mode': 'layout',
            'time': '0s', 'background': background, 'narration': cue['narrationAnchor']},
            {'id': 'motion', 'role': 'auxiliary', 'label': '运动过程', 'mode': 'motion', 'time': '1s',
             'background': background, 'narration': cue['narrationAnchor']}]}
        files[f'compositions/cues/{cid}.html'] = {'poster': poster, 'map': map_diagram, 'annotation': annotation}[cid]()
        files[f'compositions/motion/{cid}.js'] = motion(cid)
    staged = stage(root, files, {'assets/fonts/title.woff2': base / 'inputs/title.woff2',
                                'assets/images/poster.png': base / 'inputs/poster.png'})
    model.update(root, request(root, 'publish-confirmed-code', operation='edit', patch={'cues': cues}, files=staged))
    boards = model.preview(root, request(root, 'actual-storyboards', scope='storyboard', cueIds=[c['id'] for c in cues]))
    previews = []
    for cue in cues:
        previews.append(model.preview(root, request(root, 'local-' + cue['id'], scope='local', cueIds=[cue['id']],
                        range=cue['resolvedTimeline'])))
    state = model.status(root)
    if any(not c['firstConfirmed'] for c in state['conceptDesign']['cues']):
        raise ValueError('production lost its confirmed concept basis')
    unchanged = all(sha(Path(p)) == value for p, value in prepared['sourceHashes'].items())
    if not unchanged:
        raise ValueError('original fixture source changed')
    probes = []
    for path in (root / 'cache/cues/preview').glob('*/media.mov'):
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,pix_fmt,avg_frame_rate,duration,nb_frames', '-of', 'json', str(path)]))
        stream = probe['streams'][0]
        assert (stream['width'], stream['height'], stream['avg_frame_rate'], stream['nb_frames']) == (854, 480, '24/1', '96')
        probes.append({'path': str(path), **probe})
    evidence = {'root': str(root), 'conceptBasisReadAfterReopen': basis, 'storyboards': boards,
                'previews': previews, 'mediaProbes': probes, 'originalImagesUnchanged': unchanged,
                'artifacts': state['artifacts']}
    dump(base / 'production-evidence.json', evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'render'])
    parser.add_argument('--run', action='store_true', required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--runtime', default='0.8.146')
    for name in ('generated-concept', 'external-concept', 'annotation-concept', 'source-frame', 'poster-frame', 'font-source', 'gsap-source'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else render)(args)


if __name__ == '__main__':
    main()
