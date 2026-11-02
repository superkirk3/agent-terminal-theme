"""Scale indexed frames to terminal cells and encode them without Pillow."""
from functools import lru_cache
from pathlib import Path
import struct
import zlib


@lru_cache(maxsize=96)
def load_frame(path):
    raw = Path(path).with_suffix('.sxp').read_bytes()
    magic, width, height, count = struct.unpack_from('>4sHHH', raw)
    if magic != b'SXP1' or not 0 < count < 255:
        raise ValueError('Invalid indexed frame')
    end = 10+count*3
    palette = [tuple(raw[i:i+3]) for i in range(10,end,3)]
    pixels = zlib.decompress(raw[end:])
    if len(pixels) != width*height:
        raise ValueError('Invalid frame dimensions')
    return width, height, palette, pixels


def runs(values):
    out, last, count = [], None, 0
    for value in [*values, None]:
        if value == last:
            count += 1
            continue
        if last is not None:
            char = chr(last+63)
            out.append(f'!{count}{char}' if count>3 else char*count)
        last, count = value, 1
    return ''.join(out)


@lru_cache(maxsize=160)
def render_frame(path, width, height, matte=None):
    """Fit the complete source in a cell-sized canvas with consistent padding."""
    sw, sh, palette, source = load_frame(path)
    width, height = max(1,min(width,512)), max(1,min(height,512))
    scale = min(width/sw,height/sh)*.94
    dw, dh = max(1,round(sw*scale)), max(1,round(sh*scale))
    ox, oy = (width-dw)//2, (height-dh)//2
    palette = list(palette)
    background = 255
    if matte is not None:
        background = len(palette)
        palette.append(tuple(matte))
    pixels = bytearray([background])*(width*height)
    xs = [min(sw-1,(2*x+1)*sw//(2*dw)) for x in range(dw)]
    for y in range(dh):
        start = min(sh-1,(2*y+1)*sh//(2*dh))*sw
        row = bytes(source[start+x] if source[start+x]!=255 else background for x in xs)
        offset = (oy+y)*width+ox
        pixels[offset:offset+dw] = row
    out = [f'\x1bP0;1;0q"1;1;{width};{height}']
    for i,color in enumerate(palette):
        out.append(f'#{i};2;'+';'.join(str(round(c*100/255)) for c in color))
    for y in range(0,height,6):
        bands = {}
        for dy in range(min(6,height-y)):
            offset = (y+dy)*width
            for x in range(width):
                color = pixels[offset+x]
                if color == 255:
                    continue
                band = bands.get(color)
                if band is None:
                    band = [0]*width
                    bands[color] = band
                band[x] |= 1<<dy
        for index,(color,values) in enumerate(bands.items()):
            while values and not values[-1]:
                values.pop()
            out.append(('$' if index else '')+f'#{color}'+runs(values))
        if y+6<height:
            out.append('-')
    return ''.join(out).encode()+b'\x1b\\'
