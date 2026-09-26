"""Required physical-media validation for the complete formal media closure."""
import json
import subprocess
from fractions import Fraction
from scripts.hyperframes_adapter import parse_time
from scripts.validate_delivery import DeliveryExpectation, validate_probe


def probe_formal_movie(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
        'stream=codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,duration',
        '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    streams = json.loads(result.stdout)['streams']
    if len(streams) != 1 or streams[0].get('codec_type') != 'video':
        raise ValueError('formal animation must contain exactly one video and no audio')
    return streams[0]


def validate_media_set(package, manifest, source_root):
    delivery = manifest['delivery']
    specs = {}
    for cue in manifest['cues']:
        if cue.get('productionMode') == 'animation':
            asset = cue['deliveryAsset']
            specs.setdefault(asset['sha256'], []).append(DeliveryExpectation(asset['width'], asset['height'],
                Fraction(asset['frameRate']), parse_time(asset['duration'])))
    resources = {n.get('id'): n for n in source_root.find('resources')}
    for binding in delivery['sourceMedia']:
        if not binding['afterforge']: continue
        resource = resources[binding['resourceId']]
        fmt = resources[resource.get('format')]
        specs.setdefault(binding['sha256'], []).append(DeliveryExpectation(int(fmt.get('width')), int(fmt.get('height')),
            1/parse_time(fmt.get('frameDuration')), parse_time(resource.get('duration'))))
    for media in delivery['media']:
        path = package/media['fileName']
        if path.stat().st_size != media['size']: raise ValueError('formal MOV size differs')
        probe = probe_formal_movie(path)
        for expected in specs[media['sha256']]:
            problems = validate_probe(probe, expected)
            if problems: raise ValueError(f"invalid formal media {media['fileName']}: {', '.join(problems)}")
