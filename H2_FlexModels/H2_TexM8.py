import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
import numpy as np

M8MIPS: Final = 16

@dataclass
class m8_colordef:
    R: int = 0
    G: int = 0
    B: int = 0

@dataclass
class m8_header:
    version: int = 0
    name: str = ""  #32 char limit
    Width: list = field(default_factory=list)  #array of uint32_t
    Height: list = field(default_factory=list)  #array of uint32_t
    Offsets: list = field(default_factory=list)  #array of uint32_t
    AnimName: str = ""  #32 char limit
    palette: list = field(default_factory=list)  #array of m8_colordef
    Flags: int = 0
    Contents: int = 0
    Value: int = 0

def ReadM8(inpath: str | Path):
    inpath = Path(inpath)
    print(f"Loading M8 texture: \"{inpath}\"")
    NewM8Header = m8_header()

    with (open(inpath, "rb") as f):
        NewM8Header.version = struct.unpack("i", f.read(4))[0]
        NewM8Header.name = f.read(32).split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        NewM8Header.Width = list(struct.unpack(f"{M8MIPS}I", f.read(M8MIPS*4)))
        NewM8Header.Height = list(struct.unpack(f"{M8MIPS}I", f.read(M8MIPS*4)))
        NewM8Header.Offsets = list(struct.unpack(f"{M8MIPS}I", f.read(M8MIPS*4)))
        NewM8Header.AnimName = f.read(32).split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        for _ in range(256):
            colour =  m8_colordef()
            colour.R, colour.G, colour.B = struct.unpack("3B", f.read(3))
            NewM8Header.palette.append(colour)
        NewM8Header.Flags,NewM8Header.Contents,NewM8Header.Value = struct.unpack("3i", f.read(12))
        PixelArraySize = NewM8Header.Width[0]*NewM8Header.Height[0]
        pixels = list(struct.unpack(f"{PixelArraySize}B", f.read(PixelArraySize)))
    f.close()
    return NewM8Header, pixels

def M8ToRGBA(inpath: str | Path):
    header, pixels = ReadM8(inpath)
    W, H = header.Width[0], header.Height[0]
    palette = np.array([[c.R, c.G, c.B] for c in header.palette], dtype=np.uint8)
    rgb = palette[np.array(pixels, dtype=np.uint8).reshape(H, W)]
    rgba = np.ones((H, W, 4), dtype=np.float32)
    rgba[..., :3] = rgb / 255.0
    rgba = np.flipud(rgba)
    return W, H, rgba.ravel()

def WriteM8(outpath: str | Path, name: str, mipmaps: list, palette: np.ndarray):
    widths, heights, offsets = [0] * M8MIPS, [0] * M8MIPS, [0] * M8MIPS
    offset = 1040
    mipmaps = mipmaps[:M8MIPS]
    for i, m in enumerate(mipmaps):
        heights[i], widths[i] = m.shape
        offsets[i] = offset
        offset += m.size
    with open(outpath, "wb") as f:
        f.write(struct.pack("i", 2))
        f.write(name.encode("ascii", errors="ignore").ljust(32, b"\x00")[:32])
        f.write(struct.pack(f"{M8MIPS}I", *widths))
        f.write(struct.pack(f"{M8MIPS}I", *heights))
        f.write(struct.pack(f"{M8MIPS}I", *offsets))
        f.write(b"Exported by Python script".ljust(32, b"\x00"))
        f.write(np.asarray(palette, dtype=np.uint8).tobytes())
        f.write(struct.pack("3i", 0, 0, 0))
        for m in mipmaps:
            f.write(m.tobytes())

def _median_cut(colors, counts, n=256):
    if len(colors) <= n:
        return colors
    boxes = [np.arange(len(colors))]
    while len(boxes) < n:
        best, best_score = None, -1
        for bi, idx in enumerate(boxes):
            if len(idx) < 2:
                continue
            c = colors[idx].astype(np.int32)
            score = counts[idx].sum() * (c.max(0) - c.min(0)).max()
            if score > best_score:
                best, best_score = bi, score
        if best is None:
            break
        idx = boxes.pop(best)
        c = colors[idx].astype(np.int32)
        ch = int(np.argmax(c.max(0) - c.min(0)))
        order = idx[np.argsort(colors[idx, ch], kind="stable")]
        cum = np.cumsum(counts[order])
        cut = int(np.searchsorted(cum, cum[-1] / 2)) + 1
        cut = min(max(cut, 1), len(order) - 1)
        boxes += [order[:cut], order[cut:]]
    pal = [np.average(colors[idx], axis=0, weights=counts[idx]) for idx in boxes]
    return np.rint(np.array(pal)).astype(np.uint8)

def _nearest(pal, px):
    p = pal.astype(np.float32)
    p2 = (p * p).sum(axis=1)
    out = np.empty(len(px), dtype=np.uint8)
    for i in range(0, len(px), 65536):
        c = px[i:i + 65536]
        out[i:i + 65536] = np.argmin(p2[None, :] - 2.0 * (c @ p.T), axis=1)
    return out

def _halve(a):
    h, w = a.shape[:2]
    if h > 1:
        a = (a[0:h - h % 2:2] + a[1:h - h % 2:2]) * 0.5
    if w > 1:
        a = (a[:, 0:w - w % 2:2] + a[:, 1:w - w % 2:2]) * 0.5
    return a

def RGBToM8Data(rgb: np.ndarray):
    keys = ((rgb[..., 0].astype(np.uint32) << 16) |
            (rgb[..., 1].astype(np.uint32) << 8) |
             rgb[..., 2].astype(np.uint32)).ravel()
    uniq, counts = np.unique(keys, return_counts=True)
    colors = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], axis=1).astype(np.uint8)
    used_pal = _median_cut(colors, counts, 256)

    palette = np.full((256, 3), (255, 0, 255), dtype=np.uint8) #unused slots become magenta
    palette[:len(used_pal)] = used_pal

    level = rgb.astype(np.float32)
    mipmaps = []
    while True:
        h, w = level.shape[:2]
        mipmaps.append(_nearest(used_pal, level.reshape(-1, 3)).reshape(h, w))
        if (h == 1 and w == 1) or len(mipmaps) == M8MIPS:
            break
        level = _halve(level)
    return mipmaps, palette
