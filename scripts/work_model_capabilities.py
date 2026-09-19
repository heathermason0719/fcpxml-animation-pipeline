"""Finite declarative render profile. Unsupported syntax is never inert by default.

This is a deliberately bounded CSS value/rule parser, not a general web sanitizer.
Each accepted resource-bearing construct contributes to the canonical closure.
"""
import base64
import re
import struct
from dataclasses import dataclass, field
from urllib.parse import unquote_to_bytes

HTML_TAGS = set('html head body title meta style link template div span p br hr section article main header footer aside nav h1 h2 h3 h4 h5 h6 b i em strong small sub sup ul ol li dl dt dd figure figcaption img picture source table thead tbody tfoot tr td th col colgroup a'.split())
SVG_TAGS = set('svg image g defs symbol use path rect circle ellipse line polyline polygon text tspan textpath lineargradient radialgradient stop clippath mask pattern filter feimage feblend fecolormatrix fecomponenttransfer fecomposite feconvolvematrix fediffuselighting fedisplacementmap fedistantlight fedropshadow feflood fefunca fefuncb fefuncg fefuncr fegaussianblur femerge femergenode femorphology feoffset fepointlight fespecularlighting fespotlight fetile feturbulence desc title'.split())
TIME_TAGS = set('script marquee iframe object embed video audio animate animatetransform animatemotion set'.split())
ATTRIBUTES = set('id class style title role lang dir hidden xmlns xmlns:xlink charset name content http-equiv src srcset sizes href xlink:href rel type media alt width height viewbox preserveaspectratio d x y x1 x2 y1 y2 dx dy cx cy r rx ry points transform pathlength fill fill-opacity fill-rule stroke stroke-width stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset stroke-opacity opacity clip-path clip-rule mask filter offset stop-color stop-opacity gradientunits gradienttransform spreadmethod fx fy fr patternunits patterncontentunits patterntransform marker-start marker-mid marker-end vector-effect text-anchor dominant-baseline alignment-baseline textlength lengthadjust startoffset method spacing in in2 result mode values operator k1 k2 k3 k4 stddeviation edgemode radius scale xchannelselector ychannelselector color-interpolation-filters flood-color flood-opacity lighting-color surfacescale diffuseconstant specularconstant specularexponent limitingconeangle azimuth elevation kernelmatrix kernelunitlength order targetx targety divisor bias preservealpha basefrequency numoctaves seed stitchtiles slope intercept amplitude exponent tablevalues pointsatx pointsaty pointsatz z loading decoding crossorigin as fetchpriority referrerpolicy data tabindex colspan rowspan scope poster autoplay loop muted controls playsinline preload crossorigin scrolling behavior direction scrollamount scrolldelay truespeed async defer integrity nomodule attributename attributetype begin dur end repeatcount repeatdur restart calcmode keytimes keysplines keypoints from to by additive accumulate'  .split())
PRESENTATION = set('fill stroke filter clip-path mask marker-start marker-mid marker-end'.split())
PROPERTIES = set('color background background-color background-image background-position background-size background-repeat background-clip background-origin background-blend-mode display position inset top right bottom left width height min-width max-width min-height max-height inline-size block-size margin margin-top margin-right margin-bottom margin-left padding padding-top padding-right padding-bottom padding-left box-sizing border border-width border-style border-color border-radius border-top border-right border-bottom border-left border-top-color border-bottom-color border-left-color border-right-color border-top-width border-bottom-width border-left-width border-right-width outline outline-color outline-width outline-offset box-shadow text-shadow opacity overflow overflow-x overflow-y z-index isolation mix-blend-mode font font-family font-size font-weight font-style font-stretch font-display font-synthesis font-variation-settings font-feature-settings font-kerning line-height letter-spacing word-spacing text-align text-transform text-decoration text-decoration-line text-decoration-color text-decoration-thickness text-underline-offset text-overflow text-wrap white-space word-break overflow-wrap vertical-align content quotes counter-reset counter-increment list-style list-style-type list-style-position list-style-image object-fit object-position aspect-ratio transform transform-origin transform-style translate rotate scale perspective perspective-origin backface-visibility filter backdrop-filter clip-path mask mask-image mask-size mask-position mask-repeat mask-mode fill fill-opacity fill-rule stroke stroke-width stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset stroke-opacity paint-order vector-effect stop-color stop-opacity flood-color flood-opacity text-anchor dominant-baseline align-items align-content align-self justify-items justify-content justify-self place-items place-content place-self flex flex-basis flex-direction flex-wrap flex-grow flex-shrink order gap row-gap column-gap grid grid-template grid-template-columns grid-template-rows grid-template-areas grid-auto-columns grid-auto-rows grid-auto-flow grid-column grid-row grid-area visibility pointer-events user-select cursor contain container-type container-name will-change src unicode-range size-adjust ascent-override descent-override line-gap-override -webkit-text-stroke -webkit-text-stroke-width -webkit-text-stroke-color -webkit-text-fill-color -webkit-background-clip -webkit-mask-image -webkit-mask-size -webkit-mask-repeat'.split())
FUNCTIONS = set('var calc min max clamp rgb rgba hsl hsla hwb lab lch oklab oklch color color-mix linear-gradient radial-gradient conic-gradient repeating-linear-gradient repeating-radial-gradient repeating-conic-gradient translate translatex translatey translatez translate3d scale scalex scaley scalez scale3d rotate rotatex rotatey rotatez rotate3d skew skewx skewy matrix matrix3d perspective blur brightness contrast drop-shadow grayscale hue-rotate invert opacity saturate sepia inset circle ellipse polygon path round format tech counter counters repeat minmax fit-content cubic-bezier steps linear'.split())
TIME_PROPERTIES = set('animation animation-name animation-duration animation-delay animation-timing-function animation-iteration-count animation-direction animation-fill-mode animation-play-state animation-timeline animation-range animation-range-start animation-range-end animation-composition transition transition-property transition-duration transition-delay transition-timing-function transition-behavior'.split())


def unescape(text):
    def replace(match):
        value=match.group(1)
        if re.fullmatch(r'[0-9a-fA-F]{1,6}\s?',value):
            number=int(value.strip(),16)
            return chr(number) if 0<number<=0x10ffff else '\ufffd'
        return '' if value in ('\n','\r','\f') else value
    return re.sub(r'\\([0-9a-fA-F]{1,6}\s?|.)',replace,text,flags=re.S)


@dataclass
class Token:
    kind: str
    value: str = ''
    children: list = field(default_factory=list)


def tokens(text):
    index=0
    def scan(end=None):
        nonlocal index
        out=[]
        while index<len(text):
            ch=text[index]
            if ch.isspace(): index+=1;continue
            if text.startswith('/*',index):
                stop=text.find('*/',index+2)
                if stop<0:raise ValueError('unsupported unterminated CSS comment')
                index=stop+2;continue
            if ch==end:index+=1;return out
            if ch in '})]':raise ValueError('unsupported unmatched CSS delimiter')
            if ch in '\"\'':
                quote=ch;index+=1;start=index
                while index<len(text) and text[index]!=quote:
                    index+=2 if text[index]=='\\' else 1
                if index>=len(text):raise ValueError('unsupported unterminated CSS string')
                out.append(Token('string',unescape(text[start:index])));index+=1;continue
            if ch in '{([':
                index+=1;out.append(Token(ch,children=scan({'{':'}','(':')','[':']'}[ch])));continue
            if ch.isalnum() or ch in '_-\\' or ord(ch)>127:
                start=index
                while index<len(text):
                    c=text[index]
                    if c=='\\':
                        m=re.match(r'\\(?:[0-9a-fA-F]{1,6}\s?|.)',text[index:],re.S)
                        if not m:raise ValueError('unsupported CSS escape')
                        index+=len(m.group());continue
                    if not(c.isalnum() or c in '_-' or ord(c)>127):break
                    index+=1
                name=unescape(text[start:index])
                if index<len(text) and text[index]=='(':
                    index+=1
                    if name.lower()=='url':
                        start=index;quote=None
                        while index<len(text):
                            c=text[index]
                            if c=='\\':index+=2;continue
                            if quote:
                                if c==quote:quote=None
                            elif c in '\"\'':quote=c
                            elif c==')':break
                            index+=1
                        if index>=len(text) or quote:raise ValueError('unsupported CSS URL')
                        raw=text[start:index].strip();index+=1
                        if raw[:1] in ('\"',"'"):
                            if raw[-1:]!=raw[:1]:raise ValueError('unsupported CSS URL')
                            raw=raw[1:-1]
                        out.append(Token('url',unescape(raw)))
                    else:out.append(Token('function',name.lower(),scan(')')))
                else:out.append(Token('ident',name))
                continue
            index+=1;out.append(Token(ch,ch))
        if end:raise ValueError('unsupported unclosed CSS block')
        return out
    return scan()


def css(text, *, declarations=False):
    references=[];dynamic=False
    def values(items):
        for item in items:
            if item.kind=='url':references.append((item.value,'resource'))
            elif item.kind=='function':
                if item.value in {'image-set','-webkit-image-set'}:
                    if any(t.kind == 'function' and t.value == 'var' for t in item.children):
                        raise ValueError('unsupported computed image-set resource; use explicit local candidates')
                    references.extend((t.value,'image') for t in item.children if t.kind=='string')
                elif item.value=='type':
                    if any(t.kind!='string' for t in item.children):raise ValueError('unsupported image type capability')
                elif item.value not in FUNCTIONS:raise ValueError('unsupported CSS function capability: '+item.value)
                values(item.children)
            elif item.children:values(item.children)
    def declarations_in(items):
        nonlocal dynamic
        group=[]
        for item in [*items,Token(';')]:
            if item.kind!=';':group.append(item);continue
            if not group:continue
            if len(group)<2 or group[0].kind!='ident' or group[1].kind!=':':raise ValueError('unsupported CSS declaration capability')
            prop=group[0].value.lower();plain=re.sub(r'^-(webkit|moz|ms|o)-','',prop)
            if plain in TIME_PROPERTIES:dynamic=True
            elif not prop.startswith('--') and prop not in PROPERTIES:raise ValueError('unsupported CSS property capability: '+prop)
            values(group[2:]);group=[]
    def rules(items):
        nonlocal dynamic
        pre=[]
        for item in items:
            if item.kind=='{':
                if pre and pre[0].kind=='@':
                    kind=pre[1].value.lower() if len(pre)>1 else ''
                    if kind in {'media','supports','layer','container'}:rules(item.children)
                    elif kind=='font-face':declarations_in(item.children)
                    elif kind in {'keyframes','-webkit-keyframes'}:dynamic=True;rules(item.children)
                    else:raise ValueError('unsupported CSS at-rule capability: '+kind)
                else:declarations_in(item.children)
                pre=[]
            elif item.kind==';':
                if not pre:continue
                if len(pre)>2 and pre[0].kind=='@' and pre[1].value.lower()=='import':
                    ref=pre[2]
                    if ref.kind not in {'string','url'}:raise ValueError('unsupported CSS import')
                    references.append((ref.value,'css'))
                elif not(len(pre)>1 and pre[0].kind=='@' and pre[1].value.lower() in {'charset','layer'}):
                    raise ValueError('unsupported CSS statement')
                pre=[]
            else:pre.append(item)
        if pre:raise ValueError('unsupported incomplete CSS rule')
    parsed=tokens(text)
    (declarations_in if declarations else rules)(parsed)
    return dynamic,references


def srcset(value):
    # The URL token may contain commas (notably a data URI); descriptors end at
    # a comma outside whitespace-delimited URL. Do not split a data payload.
    result=[];index=0
    while index<len(value):
        while index<len(value) and (value[index].isspace() or value[index]==','):index+=1
        start=index
        while index<len(value) and not value[index].isspace():index+=1
        url=value[start:index]
        if not url:break
        if url.endswith(','):result.append(url.rstrip(','));continue
        result.append(url)
        start=index
        while index<len(value) and value[index]!=',':index+=1
        descriptor=value[start:index].strip()
        if descriptor and not re.fullmatch(r'(?:\d+(?:\.\d+)?x|\d+w)',descriptor):
            raise ValueError('unsupported srcset descriptor')
    return result


def raster_motion(data, *, required=False):
    """Inspect container structure, including alternate extensions and inline bytes."""
    if data.startswith((b'GIF87a',b'GIF89a')):
        if len(data)<13:raise ValueError('invalid GIF input')
        pos=13+(3*(2**((data[10]&7)+1)) if data[10]&128 else 0);frames=0
        def blocks(pos):
            while pos<len(data):
                n=data[pos];pos+=1
                if not n:return pos
                pos+=n
            raise ValueError('invalid GIF blocks')
        while pos<len(data):
            tag=data[pos];pos+=1
            if tag==0x3b:
                if not frames:raise ValueError('GIF has no image')
                return frames>1
            if tag==0x21:pos=blocks(pos+1)
            elif tag==0x2c:
                if pos+9>len(data):raise ValueError('invalid GIF frame')
                flags=data[pos+8];pos+=9+(3*(2**((flags&7)+1)) if flags&128 else 0)
                pos=blocks(pos+1);frames+=1
            else:raise ValueError('invalid GIF container')
        raise ValueError('invalid GIF trailer')
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        pos=8;declared_frames=0;frames=0
        while pos+12<=len(data):
            n=struct.unpack('>I',data[pos:pos+4])[0];kind=data[pos+4:pos+8]
            if pos+12+n>len(data):raise ValueError('invalid PNG chunk')
            if kind==b'acTL':
                if n != 8: raise ValueError('invalid PNG animation control')
                declared_frames=int.from_bytes(data[pos+8:pos+12],'big')
            if kind==b'fcTL':frames+=1
            pos+=12+n
            if kind==b'IEND':return max(declared_frames,frames)>1
        raise ValueError('invalid PNG container')
    if data.startswith(b'RIFF') and data[8:12]==b'WEBP':
        pos=12;frames=0
        while pos+8<=len(data):
            kind=data[pos:pos+4];n=int.from_bytes(data[pos+4:pos+8],'little')
            if pos+8+n>len(data):raise ValueError('invalid WebP chunk')
            if kind==b'ANMF':frames+=1
            pos+=8+n+(n%2)
        return frames>1
    if data.startswith(b'\xff\xd8\xff'):return False
    if required:raise ValueError('unsupported or unverifiable image capability')
    return False


def data_motion(uri):
    try:
        header,payload=uri.split(',',1)
        data=base64.b64decode(payload,validate=True) if header.lower().endswith(';base64') else unquote_to_bytes(payload)
    except (ValueError,TypeError) as error:raise ValueError('invalid inline resource') from error
    mime=header[5:].split(';',1)[0].lower()
    if mime in {'image/png','image/jpeg','image/gif','image/webp'}:return raster_motion(data,required=True)
    if mime in {'font/woff','font/woff2','font/ttf','font/otf','application/font-woff'} and data[:4] in {b'wOFF',b'wOF2',b'OTTO',b'\x00\x01\x00\x00'}:return False
    raise ValueError('unsupported active data dependency or inline resource capability')


# Hosts run only in an isolated snapshot containing the registered closure.
# Browser-level CSP adds a second boundary against remote/dynamically built
# resource URLs. Inline code/eval are necessary for the pinned Motion adapter;
# this does not attempt to prove arbitrary JavaScript behavior statically.
RENDER_CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
              "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
              "font-src 'self' data:; media-src 'self'; connect-src 'self'; "
              "worker-src 'self' blob:; base-uri 'none'; object-src 'none'; frame-src 'none'")


def guarded_host(markup):
    import html
    meta = '<meta http-equiv="Content-Security-Policy" content="' + html.escape(RENDER_CSP, quote=True) + '">' 
    return markup.replace('<head>', '<head>' + meta, 1)


def validate_render_resources(log):
    """A rejected browser dependency cannot silently publish incomplete pixels."""
    if re.search(r'Content Security Policy|content-security-policy|ERR_BLOCKED_BY_CSP|REQUESTFAILED|HTTPERROR|\[FileServer\] [45]\d\d|Failed to load resource:.*status of [45]\d\d', log, re.I):
        raise ValueError('renderer rejected a resource; inspect registered source closure and render log')
