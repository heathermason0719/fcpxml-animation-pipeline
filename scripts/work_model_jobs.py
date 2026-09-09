"""Resumable deterministic jobs. Journals track execution; manifests own decisions."""
from __future__ import annotations
import copy
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from fractions import Fraction
from pathlib import Path

from scripts.manifest_transaction import manifest_transaction
from scripts.hyperframes_adapter import parse_time
from scripts.fcpxml_timing import format_time
from scripts.validate_delivery import DeliveryExpectation, probe_delivery, validate_probe
from scripts.work_model_store import atomic_json, digest, layout, load, now, project_lock, request_check, remember, safe, save, sha, verified_operation, fresh_hashes
from scripts.work_model_inputs import animation_cues, cue_inputs, cue_key, dependencies, preview_range, source_paths, timeline_inputs, timeline_key
from scripts.work_model_media import render_cue, composite_preview, validate_alpha


def _validate_media(path, manifest, cue, quality, log):
    dims = manifest['project']['preview' if quality == 'preview' else 'delivery']
    fps = 1 / parse_time(manifest['project']['source']['frameDuration'])
    duration = parse_time(cue['resolvedTimeline']['duration'])
    probe = probe_delivery(path)
    issues = validate_probe(probe, DeliveryExpectation(dims['width'], dims['height'], fps, duration))
    # ffprobe decimal duration is rounded; reject a missing or extra frame.
    if abs(Fraction(str(probe['duration'])) - duration) >= 1 / (fps * 2):
        issues.append('exact_duration_mismatch')
    if issues:
        raise ValueError('invalid cue media: ' + ', '.join(issues))
    alpha_cue = copy.deepcopy(cue)
    if quality == 'preview':
        # Declared points use the canonical native coordinate space.
        native = manifest['project']['delivery']
        for sample in alpha_cue.get('alphaExpectation', {}).get('samples', []):
            for field in ('transparentPoints','opaquePoints'):
                sample[field] = [[int(x*dims['width']/native['width']), int(y*dims['height']/native['height'])] for x,y in sample.get(field,[])]
    return {'probe':probe,'alpha':validate_alpha(path, alpha_cue, log_path=log)}


def supplemental_key(root, manifest, cue):
    return digest({'cue':cue_key(root,manifest,cue), 'source':manifest.get('sourceHashes'),
                   'placement':{name:format_time(parse_time(cue['resolvedTimeline'][name])) for name in ('start','duration')},
                   'dimensions':manifest['project']['preview']})


def _spec(root, manifest, action, request):
    source_paths(root,manifest)
    if action == 'preview':
        start,duration = preview_range(manifest,request)
        data = timeline_inputs(root,manifest,start=start,duration=duration,allow_draft=request.get('allowDraft',False))
        if request.get('scope') == 'still' and len(request.get('cueIds',[])) != 1:
            raise ValueError('still preview requires exactly one cueId')
        return {'timeline':data,'scope':request.get('scope','local'), 'stillTime':request.get('time'),
                'cueIds':request.get('cueIds',[])}
    data = timeline_inputs(root,manifest)
    return {'timeline':data,'native':{c['id']:cue_key(root,manifest,c,'delivery') for c in animation_cues(manifest)},
            'identity':manifest['identity'],'protocol':'2'}


def _approved(root, manifest):
    from scripts.work_model import current_review_set
    review = current_review_set(root,manifest)
    if not review:
        raise ValueError('current complete review set is required for delivery')
    kinds={d['kind'] for d in manifest['decisions'] if d.get('reviewSetId') == review['id']}
    if not ({'approve','authorize'} <= kinds or 'approve-and-deliver' in kinds):
        raise ValueError('explicit user approval and authorization are required')
    if any(f['status'] in {'pending','needs-clarification'} for f in manifest['feedback']):
        raise ValueError('pending feedback must be resolved before delivery')
    return review


def _job_path(root, job_id):
    if not isinstance(job_id,str) or not job_id.startswith('job-') or any(c not in '0123456789abcdef' for c in job_id[4:]):
        raise ValueError('invalid jobId')
    return safe(root,'jobs/'+job_id+'.json',exists=False)


def _number(root, manifest, afterforge, index):
    numbers=[]
    episode=next(ep for ep in index['episodes'] if ep['id']==manifest['identity']['episodeId'])
    for version in episode['versions']:
        version_root=safe(afterforge,version['root'])
        m=load(version_root)
        numbers += [int(d['id'][1:]) for d in m.get('deliveries',[])]
        for file in (version_root/'jobs').glob('*.json'):
            record=json.loads(file.read_text())
            if record.get('releaseId'):
                numbers.append(int(record['releaseId'][1:]))
    return 'd'+str(max(numbers,default=0)+1).zfill(4)


def _snapshot(root, manifest, spec, destination, review=None):
    names=set()
    for overlay in spec['timeline']['overlays']:
        cue=next(c for c in manifest['cues'] if c['id']==overlay['cueId'])
        names.update(cue_inputs(root,manifest,cue)['files'])
    names.update(path.relative_to(root).as_posix() for path in source_paths(root,manifest))
    names.update(p.relative_to(root).as_posix() for p in (root/'assets/source').glob('narration-*') if p.is_file())
    if review:
        names.update(a['path'] for a in manifest['artifacts'] if a['id'] in review['artifactIds'])
    for name in names:
        target=safe(destination,name,exists=False)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(safe(root,name),target)
    return sorted(names)


def _cache(root, snapshot, manifest, cue, quality, job):
    key=cue_key(snapshot,manifest,cue,quality)
    relative=f'cache/cues/{quality}/{key}/media.mov'
    movie=safe(root,relative,exists=False)
    record_path=movie.with_suffix('.json')
    log=snapshot/'render.log'
    valid=None
    if movie.is_file() and record_path.is_file():
        try:
            record=json.loads(record_path.read_text())
            if record.get('inputKey')==key and record.get('sha256')==sha(movie):
                valid=_validate_media(movie,manifest,cue,quality,log)
        except (ValueError,OSError,subprocess.CalledProcessError):
            valid=None
    if valid is None:
        target=safe(snapshot,relative,exists=False)
        render_cue(snapshot,manifest,cue,quality=quality,target=target,log_path=log)
        valid=_validate_media(target,manifest,cue,quality,log)
        record={'inputKey':key,'sha256':sha(target),'path':relative,**valid}
        with manifest_transaction(root):
            movie.parent.mkdir(parents=True,exist_ok=True)
            temporary=movie.with_name('.media-'+job['id']+'.mov')
            shutil.copy2(target,temporary)
            os.replace(temporary,movie)
            atomic_json(record_path,record)
    destination=safe(snapshot,relative,exists=False)
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(movie,destination)
    job['completedCueIds']=list(dict.fromkeys(job.get('completedCueIds',[])+[cue['id']]))
    atomic_json(_job_path(root,job['id']),job)
    return {'path':relative,'sha256':sha(destination),'inputKey':key,**valid}


def _artifact(root, manifest, kind, path, key, time_range, cue_ids, complete=True, **extra):
    return {'id':'artifact-'+digest([kind,key,time_range,extra])[:20], 'kind':kind,
            'path':path.relative_to(root).as_posix(),'sha256':sha(path),'inputKey':key,
            'range':time_range,'cueIds':cue_ids,'complete':complete,'createdAt':now(),**extra}


def _overlap_ids(overlays):
    result=set()
    for i,a in enumerate(overlays):
        for b in overlays[i+1:]:
            if max(parse_time(a['start']),parse_time(b['start'])) < min(parse_time(a['start'])+parse_time(a['duration']),parse_time(b['start'])+parse_time(b['duration'])):
                result.update([a['cueId'],b['cueId']])
    return result


def _preview_output(root, snap, manifest, spec, job):
    data=spec['timeline']; overlays=copy.deepcopy(data['overlays'])
    for overlay in overlays:
        cue=next(c for c in manifest['cues'] if c['id']==overlay['cueId'])
        overlay['path']=_cache(root,snap,manifest,cue,'preview',job)['path']
    start=parse_time(data['range']['start']);duration=parse_time(data['range']['duration'])
    key=digest(data)
    output=snap/f'previews/{job["inputKey"]}.mp4'
    composite_preview(snap,manifest,overlays,start=start,duration=duration,target=output,log_path=snap/'render.log')
    kind='full-preview' if spec['scope']=='full' else 'local-preview'
    artifacts=[]
    if spec['scope']=='still':
        moment=parse_time(spec['stillTime']) if spec['stillTime'] else start+duration/2
        if moment<start or moment>=start+duration:
            raise ValueError('still time must lie inside preview range')
        png=output.with_suffix('.png')
        with (snap/'render.log').open('ab') as log:
            subprocess.run(['ffmpeg','-v','error','-ss',str(float(moment-start)),'-i',str(output),'-frames:v','1',str(png)],check=True,stdout=log,stderr=log)
        artifacts.append(_artifact(snap,manifest,'still',png,key,data['range'],spec['cueIds'],not data['missingCueIds'],time=format_time(moment),timelineBased=True))
    else:
        artifacts.append(_artifact(snap,manifest,kind,output,key,data['range'],[o['cueId'] for o in overlays],not data['missingCueIds'],missingCueIds=data['missingCueIds']))
    # Conservatively supply every overlapping animation in isolation, covering its entire local duration.
    if kind=='full-preview' and not data['missingCueIds']:
        for overlay in overlays:
            if overlay['cueId'] not in _overlap_ids(overlays):
                continue
            cue=next(c for c in manifest['cues'] if c['id']==overlay['cueId'])
            supplemental=supplemental_key(snap,manifest,cue)
            target=snap/f'previews/cue-{supplemental}.mp4'
            composite_preview(snap,manifest,[overlay],start=parse_time(overlay['start']),duration=parse_time(overlay['duration']),target=target,log_path=snap/'render.log')
            artifacts.append(_artifact(snap,manifest,'cue-preview',target,supplemental,{'start':overlay['start'],'duration':overlay['duration']},[cue['id']]))
    return artifacts


def _finish_preview(root,snap,manifest,spec,job):
    artifacts=_preview_output(root,snap,manifest,spec,job)
    with manifest_transaction(root):
        fresh_hashes()
        current=load(root,writable=True)
        if digest(_spec(root,current,'preview',job['request']))!=job['inputKey']:
            raise ValueError('inputs changed during preview; valid cue caches retained')
        for artifact in artifacts:
            target=safe(root,artifact['path'],exists=False)
            target.parent.mkdir(parents=True,exist_ok=True)
            # Fingerprinted outputs are replaced only if already damaged; hash binds this result.
            os.replace(safe(snap,artifact['path']),target)
            current['artifacts']=[a for a in current['artifacts'] if a['id']!=artifact['id']]+[artifact]
        review=None
        if spec['scope']=='full' and all(a['complete'] for a in artifacts):
            review={'id':'review-'+digest([a['sha256'] for a in artifacts]+[job['inputKey']])[:20],
                    'inputKey':digest(spec['timeline']),'artifactIds':[a['id'] for a in artifacts],'createdAt':now()}
            current['reviewSets']=[r for r in current['reviewSets'] if r['id']!=review['id']]+[review]
        current['editRevision']+=1
        result={'status':'complete','jobId':job['id'],'artifactIds':[a['id'] for a in artifacts],
                'reviewSet':review,'editRevision':current['editRevision']}
        remember(current,job['request'],result)
        save(root,current)
    return result


def _recover_publication(root, job):
    """A journal is a locator, never evidence: validate every actual released byte."""
    record = job.get('preparedRelease')
    if not record:
        return None
    from scripts.work_model_delivery import verify_release, _inventory
    afterforge, _ = layout(root)
    with manifest_transaction(root):
        fresh_hashes()
        current = load(root, writable=True)
        if digest(_spec(root,current,'deliver',job['request'])) != job['inputKey']:
            raise ValueError('delivery inputs changed before publication recovery')
        if _approved(root,current)['id'] != job['reviewSetId']:
            raise ValueError('delivery review changed before publication recovery')
        package = safe(afterforge,record['packagePath'],exists=False)
        snapshot = safe(root,record['snapshotPath'],exists=False)
        if package.exists() and snapshot.exists():
            verify_release(root,afterforge,record)
            if not any(d['id']==record['id'] for d in current['deliveries']):
                current['deliveries'].append(record)
                current['editRevision'] += 1
            result={'status':'complete','delivery':record,'jobId':job['id'],
                    'recovered':True,'editRevision':current['editRevision']}
            remember(current,job['request'],result)
            save(root,current)
            return result
        # One directory rename may have completed before interruption. Only
        # remove the exact inventory this job staged, then rebuild normally.
        if package.exists() and _inventory(package) != record['inventory']['package']:
            raise ValueError('partial package differs from this job; recovery refused')
        if snapshot.exists() and (_inventory(snapshot,exclude={'inventory.json'}) != record['inventory']['snapshot']
                or json.loads((snapshot/'inventory.json').read_text()) != record['inventory']):
            raise ValueError('partial snapshot differs from this job; recovery refused')
        for path in (package,snapshot):
            if path.exists(): shutil.rmtree(path)
    return None


def _finish_delivery(root,snap,manifest,spec,job,names):
    from scripts.work_model_delivery import prepare_release,publish_release,verify_release
    recovered = _recover_publication(root,job)
    if recovered:
        return recovered
    afterforge,_=layout(root)
    for number,cue in enumerate(manifest['cues']):
        if cue['productionMode']!='animation': continue
        media=_cache(root,snap,manifest,cue,'delivery',job)
        dims=manifest['project']['delivery']
        cue['layer']=cue.get('layer',number+1)
        cue['deliveryAsset']={'fileName':'AF__'+digest(cue['id'])[:12]+'.mov',
             'relativePath':media['path'],'sha256':media['sha256'],'width':dims['width'],'height':dims['height'],
             'frameRate':str(1/parse_time(manifest['project']['source']['frameDuration'])),
             'duration':cue['resolvedTimeline']['duration'],'probe':media['probe'],'alphaEvidence':media['alpha']}
    prepared=prepare_release(root,manifest,afterforge_root=afterforge,release_id=job['releaseId'],
            input_key=job['inputKey'],dependency_paths=names,input_root=snap)
    job['preparedRelease'] = prepared['record']
    atomic_json(_job_path(root,job['id']),job)
    published=False
    try:
        with manifest_transaction(root):
            fresh_hashes()
            current=load(root,writable=True)
            if digest(_spec(root,current,'deliver',job['request']))!=job['inputKey']:
                raise ValueError('inputs changed during delivery; valid cue caches retained')
            if _approved(root,current)['id']!=job['reviewSetId']:
                raise ValueError('delivery review changed during rendering')
            for existing in current['deliveries']:
                if existing['inputKey']==job['inputKey']:
                    verify_release(root,afterforge,existing)
                    return {'status':'complete','delivery':existing,'reused':True,'jobId':job['id']}
            record=publish_release(root,prepared);published=True
            current['deliveries'].append(record);current['editRevision']+=1
            result={'status':'complete','delivery':record,'jobId':job['id'],'editRevision':current['editRevision']}
            remember(current,job['request'],result)
            try: save(root,current)
            except BaseException:
                shutil.rmtree(safe(afterforge,record['packagePath']))
                shutil.rmtree(safe(root,record['snapshotPath']))
                raise
        return result
    finally:
        for field in ('stagingPackage','stagingSnapshot'):
            path=Path(prepared[field])
            if path.exists(): shutil.rmtree(path)


@verified_operation
def _run(root,action,request,*,resume_id=None):
    root=Path(root).expanduser().resolve()
    load(root,writable=True)  # Before any lock/directory in legacy versions.
    afterforge,_=layout(root)
    job_id=resume_id or 'job-'+digest([action,request.get('requestId')])[:24]
    job_path=_job_path(root,job_id)
    lock_dir=safe(root,'jobs/locks/'+job_id,exists=False);lock_dir.mkdir(parents=True,exist_ok=True)
    with manifest_transaction(lock_dir,timeout=0.1):
        with (project_lock(afterforge) if action=='deliver' else nullcontext()),manifest_transaction(root):
            manifest=load(root,writable=True)
            existing=json.loads(job_path.read_text()) if job_path.is_file() else None
            if resume_id:
                request_check(manifest,request)
                if not existing: raise ValueError('unknown resumable job')
                original=existing['request'];action=existing['action']
            else:
                original=request
                if existing and existing['request']!=request:
                    raise ValueError('requestId was already used with another job request')
                previous=request_check(manifest,request) if not existing else None
                if previous is not None:
                    if action=='deliver' and previous.get('delivery'):
                        from scripts.work_model_delivery import verify_release
                        verify_release(root,afterforge,previous['delivery'])
                    return previous
            if existing and existing['status']=='complete':
                if action=='deliver' and existing['result'].get('delivery'):
                    from scripts.work_model_delivery import verify_release
                    verify_release(root,afterforge,existing['result']['delivery'])
                return existing['result']
            source_paths(root,manifest)
            if action=='deliver' and not animation_cues(manifest):
                return {'status':'no-animation','message':'无需动画交付'}
            if not existing and action=='deliver' and request.get('decision'):
                from scripts.work_model import _record_decision
                _record_decision(root,manifest,request['decision'])
            review=_approved(root,manifest) if action=='deliver' else None
            spec=_spec(root,manifest,action,original);key=digest(spec)
            if existing and existing['inputKey']!=key:
                raise ValueError('job inputs changed; start a new request to reuse unaffected caches')
            if action=='deliver':
                for release in manifest['deliveries']:
                    if release['inputKey']==key:
                        from scripts.work_model_delivery import verify_release
                        verify_release(root,afterforge,release)
                        manifest['editRevision'] += 1
                        result = {'status':'complete','delivery':release,'reused':True,
                                  'editRevision':manifest['editRevision']}
                        remember(manifest,original,result)
                        save(root,manifest)
                        return result
            job=existing or {'id':job_id,'action':action,'inputKey':key,'request':original,'createdAt':now(),'completedCueIds':[]}
            if action=='deliver':
                job['reviewSetId']=review['id']
                if not job.get('releaseId'):
                    _,index=layout(root);job['releaseId']=_number(root,manifest,afterforge,index)
                if not existing and request.get('decision'):
                    manifest['editRevision']+=1;save(root,manifest)
            job.update(status='running',updatedAt=now(),error=None)
            atomic_json(job_path,job)
            scratch=safe(root,'jobs/.scratch',exists=False);scratch.mkdir(parents=True,exist_ok=True)
            snap=Path(tempfile.mkdtemp(prefix=job_id+'-',dir=scratch))
            try:
                names=_snapshot(root,manifest,spec,snap,review)
                if digest(_spec(snap,manifest,action,original))!=key:
                    raise ValueError('inputs changed while freezing task')
            except BaseException as error:
                job.update(status='failed',error=str(error),updatedAt=now())
                atomic_json(job_path,job)
                shutil.rmtree(snap);raise
        try:
            result=(_finish_preview(root,snap,manifest,spec,job) if action=='preview' else
                    _finish_delivery(root,snap,manifest,spec,job,names))
            job.update(status='complete',result=result,updatedAt=now());atomic_json(job_path,job)
            if resume_id:
                with manifest_transaction(root):
                    current=load(root,writable=True);remember(current,request,result);save(root,current)
            return result
        except BaseException as error:
            job.update(status='failed',error=str(error),updatedAt=now());atomic_json(job_path,job)
            raise
        finally:
            log=snap/'render.log'
            if log.is_file():
                with (root/'jobs'/f'{job_id}.log').open('ab') as dest,log.open('rb') as source:
                    shutil.copyfileobj(source,dest)
            shutil.rmtree(snap,ignore_errors=True)


def preview(root,request): return _run(root,'preview',request)
def deliver(root,request): return _run(root,'deliver',request)
def resume(root,request):
    job_path=_job_path(Path(root).resolve(),request.get('jobId'))
    if not job_path.is_file(): raise ValueError('unknown resumable job')
    action=json.loads(job_path.read_text())['action']
    return _run(root,action,request,resume_id=request['jobId'])
