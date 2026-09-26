"""Physical codec double for tests whose renderer deliberately writes stub bytes."""
def fake_probe(path):
    return {'codec_type':'video', 'codec_name':'prores', 'profile':'4444', 'pix_fmt':'yuva444p12le',
            'width':1920, 'height':1080, 'r_frame_rate':'24',
            'duration':'1' if path.read_bytes() == b'older registered animation' else '2'}
