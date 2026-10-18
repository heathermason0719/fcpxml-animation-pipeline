#!/usr/bin/env python3
"""Opt-in synthetic Review round trip; real runtime/FFmpeg, no user works."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import work_model as model
from scripts.work_model_store import load, sha
from tests.work_model_real_smoke import stage
from tests.work_model_fixtures import request, user


def run(command):
    subprocess.run(command, check=True)


def composition(cid, color):
    return f'''<!doctype html><html><head><style>html,body{{margin:0;background:transparent;width:1920px;height:1080px;overflow:hidden}}[data-composition-id]{{position:relative;width:1920px;height:1080px}}#box{{position:absolute;left:300px;top:280px;width:900px;height:420px;background:{color};border-radius:35px;color:white;font:140px sans-serif;text-align:center;line-height:420px}}</style></head><body><div data-composition-id="{cid}" data-width="1920" data-height="1080" data-duration="3" data-fps="24"><div id="box" class="clip" data-start="0" data-duration="3" data-track-index="1">Scene {cid.upper()}</div></div><script src="compositions/motion/{cid}.js"></script></body></html>'''


def motion(cid, seconds=1):
    return f'window.__timelines=window.__timelines||{{}};const tl=gsap.timeline({{paused:true}});tl.fromTo("#box",{{x:-240,opacity:0}},{{x:0,opacity:1,duration:{seconds}}},0);window.__timelines["{cid}"]=tl;'


def cli_preview(base, root, name, payload):
    file=base/(name+'-request.json');file.write_text(json.dumps(payload))
    process=subprocess.run([sys.executable,'-B','scripts/afterforge.py','preview',str(root),'--request-file',str(file)],capture_output=True,text=True)
    (base/(name+'-stdout.json')).write_text(process.stdout)
    (base/(name+'-stderr.log')).write_text(process.stderr)
    if process.returncode: raise ValueError(process.stdout+process.stderr)
    result=json.loads(process.stdout)
    if not result['reviewEntry']['available']: raise ValueError(result['reviewEntry'])
    return result


def prepare(base, vendor, runtime):
    if base.exists(): raise ValueError('output directory must not exist')
    inbox=base/'user-inbox/synthetic';inbox.mkdir(parents=True)
    run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x111c30:s=854x480:r=24:d=12','-f','lavfi','-i','sine=frequency=220:sample_rate=48000:d=12','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(inbox/'rough-preview.mp4')])
    (inbox/'source.fcpxml').write_text('<?xml version="1.0"?><!DOCTYPE fcpxml><fcpxml version="1.10"><resources><format id="r1" frameDuration="1/24s" width="1920" height="1080"/></resources><library><event name="Synthetic"><project name="Review loop"><sequence duration="12s" format="r1"><spine><gap name="base" offset="0s" start="0s" duration="12s"/></spine></sequence></project></event></library></fcpxml>')
    (inbox/'narration.srt').write_text('1\n00:00:00,000 --> 00:00:12,000\nSynthetic scenes A and B.\n')
    opened=model.open_project(base/'AfterForge',{'requestId':'open','expectedRevision':0,'episodeTitle':'Review loop synthetic','inputDirectory':str(inbox)})
    root=Path(opened['root'])
    cues=[{'id':cid,'title':'Scene '+cid.upper(),'productionMode':'animation','status':'ready','layer':2,'resolvedTimeline':{'start':start,'duration':'3s'},'narrationAnchor':'Synthetic scene '+cid,'screenText':[{'text':'Scene '+cid.upper()}],'contentContext':{'narration':{'state':'present'},'screenText':{'state':'present'}},'finalAnimationDescription':'A colored card enters slowly.','renderAdapters':{'hyperframes':{'compositionId':cid,'compositionSrc':f'compositions/cues/{cid}.html','layoutDependencies':[f'compositions/cues/{cid}.html']}},'alphaExpectation':{'mode':'transparent'}} for cid,start in [('a','1s'),('b','7s')]]
    model.update(root,request(root,'cues',operation='edit',patch={'cues':cues}))
    image=root/'.staging/creative-inputs/synthetic/concept.png';image.parent.mkdir(parents=True)
    run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x685edb:s=854x480','-frames:v','1',str(image)])
    concepts=[]
    for cid in ['a','b']:
        concepts.append(model.update(root,request(root,'concept-'+cid,operation='concept',action='register',cueId=cid,imageSource=str(image),origin={'kind':'user-imported','reference':'synthetic FFmpeg color fixture; no paid image service'},idea='Colored card',motion='Enter horizontally'))['record']['id'])
    model.update(root,request(root,'confirm',operation='decision',kind='confirm-concept',conceptIds=concepts,source=user('隔离样例确认合成概念图')))
    files={}
    for cid,color in [('a','#685edb'),('b','#127e83')]:
        next(c for c in cues if c['id']==cid)['renderAdapters']['hyperframes']['motionSrc']=f'compositions/motion/{cid}.js'
        files[f'compositions/cues/{cid}.html']=composition(cid,color);files[f'compositions/motion/{cid}.js']=motion(cid)
    model.update(root,request(root,'publish',operation='edit',patch={'cues':cues},files=stage(root,files,{})))
    vendor_file=stage(root,{}, {'runtime/gsap.min.js':vendor})[0]['source']
    model.update(root,request(root,'runtime',operation='runtime',version=runtime,vendorSource=vendor_file))
    first=cli_preview(base,root,'first',request(root,'first',scope='full',taskId='first',cueIds=['a','b'],decision={'kind':'authorize-demo','taskId':'first','cueIds':['a','b'],'presentationCueIds':['a','b'],'excludedCueIds':[],'source':user('制作合成样例第一版')}))
    evidence={'root':str(root),'first':first,'sourceHashes':{str(p):sha(p) for p in inbox.iterdir()}}
    (base/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps(evidence,ensure_ascii=False,indent=2))


def revise(base):
    evidence=json.loads((base/'evidence.json').read_text());root=Path(evidence['root']);state=model.status(root)
    commission=state['storyboard']['productionRequest']
    if not commission or not commission.get('reviewRoundId') or commission['status']!='pending': raise ValueError('browser must explicitly request rework first')
    # Follow the saved scope: modify A only; move both placements to exercise historical mapping.
    m=load(root);cues=copy.deepcopy(m['cues']);cues[0]['resolvedTimeline']['start']='7s';cues[1]['resolvedTimeline']['start']='1s'
    model.update(root,request(root,'retime',operation='edit',patch={'cues':cues}))
    model.update(root,request(root,'slow-a',operation='edit',patch={},files=stage(root,{'compositions/motion/a.js':motion('a',2)},{}),work={'mode':'motion','cueIds':commission['cueIds'],'taskId':commission['taskId']}))
    round_record=next(r for r in load(root)['reviewRounds'] if r['id']==commission['reviewRoundId'])
    for fid in round_record['feedbackIds']:
        model.update(root,request(root,'address-'+fid,operation='feedback-status',feedbackId=fid,status='addressed',resolution='A enters over two seconds; scene placements swapped in the synthetic timeline.'))
    second=cli_preview(base,root,'second',request(root,'second',scope='full',taskId=commission['taskId'],cueIds=commission['cueIds'],workCueIds=commission['cueIds'],excludedCueIds=commission['excludedCueIds']))
    cached=cli_preview(base,root,'cache',json.loads((base/'second-request.json').read_text()))
    resume_file=base/'resume-request.json';resume_file.write_text(json.dumps(request(root,'resume-second',jobId=second['jobId'])))
    result=subprocess.run([sys.executable,'-B','scripts/afterforge.py','resume',str(root),'--request-file',str(resume_file)],check=True,capture_output=True,text=True)
    resumed=json.loads(result.stdout);(base/'resume-stdout.json').write_text(result.stdout)
    assert cached['reviewEntry']['artifactId']==resumed['reviewEntry']['artifactId']==second['artifactIds'][0]
    assert all(sha(Path(p))==value for p,value in evidence['sourceHashes'].items())
    evidence.update(second=second,cache=cached,resume=resumed,commission=commission)
    (base/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2));print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','revise']);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--vendor',type=Path);parser.add_argument('--runtime',default='0.8.146');parser.add_argument('--run',action='store_true');args=parser.parse_args()
    if not args.run: parser.error('--run is required for real local rendering')
    if args.action=='prepare': prepare(args.root.resolve(),args.vendor.resolve(),args.runtime)
    else: revise(args.root.resolve())
