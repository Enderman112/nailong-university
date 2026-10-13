#!/usr/bin/env python3
"""素材流水线：从「官方校徽 + 一张奶龙原图」生成整套图片素材。

    python3 tools/build-assets.py                # 按 config.json 全做
    python3 tools/build-assets.py ring core      # 只做某几步 (ring|core|page)
    python3 tools/build-assets.py --config other.json

输入  config.json 里指定的两张原图
输出  site/ring.webp site/core.webp site/favicon.png site/og.jpg site/mascot.png
      assets-src/nailong-cutout.png   （抠好的奶龙，方便别处复用）

要做页面 HTML 就跑 tools/build-site.py，它会调用这里的 build_all()。
只依赖 Pillow：python3 -m pip install Pillow
"""

import argparse
import json
import os
import re
from collections import deque

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RING_BLUR = 1.0       # 内/外缘抗锯齿羽化（像素）
KEY_THRESHOLD = 238   # 抠图时判定「接近白」的阈值
CUTOUT_BLUR = 0.7

DEFAULTS = {
    "site_title": "中国奶龙大学",
    "school_name_cn": "某某大学",
    "school_name_en": "Some University",
    "school_motto": "",
    "target_url": "https://example.edu.cn/",
    "domain": "example.org",
    "og_subtitle": ["奶龙正在护送你前往", "{school}官网"],
    "ink_rgb": [254, 206, 14],
    "logo_file": "assets-src/logo.png",
    "logo_emblem_box": [0, 0, 1182, 1182],
    "nailong_file": "assets-src/nailong-src.webp",
    "ring_canvas": 720,
    "ring_outer": 355.0,
    "ring_cut_ratio": 0.686,
    "core_canvas": 720,
    "core_width": 392,
    "core_max_radius": 232.0,
    "core_fade_from": 0.80,
}

# 字体候选清单（按顺序找第一个能用的）。原来只写死 macOS 路径，
# 在 Windows / Linux 上 og.jpg 的中文就变成豆腐块（docs/02 第 7 节那个坑）。
FONT_CN = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",          # macOS
    "/System/Library/Fonts/PingFang.ttc",                  # macOS
    "C:/Windows/Fonts/msyh.ttc",                           # Windows 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",                         # Windows 黑体
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",   # Linux
)
FONT_LATIN = (
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


# --------------------------------------------------------------------------- 配置
def _strip_jsonc(text):
    """支持 // 注释和尾逗号的 JSON，方便把 config.json 写成自带说明的样子。"""
    out, i, n, in_str, esc = [], 0, len(text), False, False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load_config(path=None):
    path = path or os.path.join(ROOT, "config.json")
    with open(path, encoding="utf-8") as fh:
        cfg = json.loads(_strip_jsonc(fh.read()))
    merged = dict(DEFAULTS)
    merged.update(cfg)
    merged["_root"] = ROOT
    merged["_config_path"] = path
    return merged


def fill(text, cfg):
    """把 {school} {site} {domain} 这些占位符替掉。"""
    return (str(text).replace("{school}", cfg["school_name_cn"])
                     .replace("{site}", cfg["site_title"])
                     .replace("{domain}", cfg["domain"]))


def punycode(domain):
    """中国奶龙大学.org -> xn--fiqs8srwb9iv6f6w9n.org；本来就是 ASCII 就原样返回。"""
    try:
        return domain.encode("idna").decode()
    except Exception:
        return domain


def site_dir(cfg):
    return os.path.join(cfg["_root"], "site")


def src_path(cfg, key):
    p = cfg[key]
    return p if os.path.isabs(p) else os.path.join(cfg["_root"], p)


def _font(paths, size, index=0):
    """按候选清单挑第一个装得上的字体；都没有再退回 Pillow 自带的位图字体。

    index 是 .ttc 里第几个字面（macOS 上 y 用 1）；该 index 不存在时退回 0。
    """
    if isinstance(paths, str):
        paths = (paths,)
    for path in paths:
        for idx in ([index, 0] if index else [0]):
            try:
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default(size)


# --------------------------------------------------------------------------- 1. 校徽外环
def build_ring(cfg):
    img = Image.open(src_path(cfg, "logo_file")).convert("RGBA")
    bx0, by0, bx1, by1 = cfg["logo_emblem_box"]
    w, h = bx1 - bx0, by1 - by0
    sub = np.array(img)[:, :, 3].astype(float)[by0:by0 + h, bx0:bx0 + w] / 255.0

    # 粗圆心 = 裁剪框中心；逐角度取最外缘，再用最小二乘（Kasa）拟合真正的圆心与外径
    yy, xx = np.mgrid[0:h, 0:w]
    c = (w - 1) / 2.0
    r = np.hypot(xx - c, yy - c)
    th = np.arctan2(yy - c, xx - c)
    ink = sub > 0.25
    pts = []
    for k in range(360):
        lo, hi = np.deg2rad(k - 0.5), np.deg2rad(k + 0.5)
        sel = ink & (th >= lo) & (th < hi) & (r > 0.42 * w)
        if sel.any():
            i = np.argmax(r[sel])
            pts.append((xx[sel][i], yy[sel][i]))
    if len(pts) < 30:
        raise SystemExit("校徽外缘点太少：检查 config.json 的 logo_emblem_box 有没有框住校徽")
    pts = np.asarray(pts, float)
    A = np.c_[2 * pts[:, 0], 2 * pts[:, 1], np.ones(len(pts))]
    s, *_ = np.linalg.lstsq(A, pts[:, 0] ** 2 + pts[:, 1] ** 2, rcond=None)
    ox, oy = float(s[0]), float(s[1])
    R = float(np.sqrt(s[2] + ox ** 2 + oy ** 2))
    resid = float(np.sqrt(((np.hypot(pts[:, 0] - ox, pts[:, 1] - oy) - R) ** 2).mean()))
    print(f"  校徽圆心 ({ox:.1f},{oy:.1f})  外径 {R:.1f}px  拟合残差 {resid:.2f}px")
    if resid > 3:
        print("  ! 拟合残差偏大：校徽可能不是正圆，或 logo_emblem_box 没框准")

    canvas_n = int(cfg["ring_canvas"])
    outer = float(cfg["ring_outer"])

    # 以拟合圆心为中心裁正方形（留 pad 保证整圆都在），缩放到外径 = ring_outer
    half = int(np.ceil(R)) + 2
    left, top = int(round(bx0 + ox - half)), int(round(by0 + oy - half))
    em = img.crop((left, top, left + half * 2, top + half * 2))
    a = np.array(em)[:, :, 3].astype(float) / 255.0

    sc = outer / R
    ink_rgb = tuple(cfg["ink_rgb"])
    art = np.zeros((*a.shape, 4), np.uint8)
    art[..., 0], art[..., 1], art[..., 2] = ink_rgb
    art[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    n = int(round(art.shape[0] * sc))
    im = Image.fromarray(art, "RGBA").resize((n, n), Image.LANCZOS)

    # 裁框中心未必正好是拟合圆心，按「圆心 → 画布中心」换算实际摆放位置
    cxr = (bx0 + ox - left) * n / (half * 2.0)
    cyr = (by0 + oy - top) * n / (half * 2.0)
    canvas = Image.new("RGBA", (canvas_n, canvas_n), (0, 0, 0, 0))
    canvas.alpha_composite(im, (int(round(canvas_n / 2.0 - cxr)), int(round(canvas_n / 2.0 - cyr))))

    # 墨色压在白环面上 → 白底 + 彩色文字；中心挖空
    arr = np.array(canvas).astype(float)
    al = arr[..., 3:4] / 255.0
    comp = arr[..., :3] * al + 255.0 * (1 - al)
    yy2, xx2 = np.mgrid[0:canvas_n, 0:canvas_n]
    rr = np.hypot(xx2 - (canvas_n - 1) / 2.0, yy2 - (canvas_n - 1) / 2.0)
    cut = float(cfg["ring_cut_ratio"]) * R * sc
    mask = (np.clip((rr - cut) / RING_BLUR + 0.5, 0, 1)
            * np.clip((outer + 0.5 - rr) / RING_BLUR, 0, 1))
    out = np.zeros((canvas_n, canvas_n, 4), np.uint8)
    out[..., :3] = np.clip(comp, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(mask * 255, 0, 255).astype(np.uint8)
    _save_webp(Image.fromarray(out, "RGBA"), os.path.join(site_dir(cfg), "ring.webp"))
    print(f"  ring.webp   外径 {outer:.0f} / 挖空内径 {cut:.0f} / 画布 {canvas_n}")


# --------------------------------------------------------------------------- 2. 奶龙抠图
def cutout(cfg):
    im = Image.open(src_path(cfg, "nailong_file")).convert("RGB")
    a = np.array(im).astype(int)
    h, w = a.shape[:2]
    near = a.min(2) >= KEY_THRESHOLD
    bg = np.zeros((h, w), bool)
    dq = deque()
    for x in range(w):                      # 从四边洪水填充，内部的白色高光不会被误伤
        for y in (0, h - 1):
            if near[y, x] and not bg[y, x]:
                bg[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near[y, x] and not bg[y, x]:
                bg[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not bg[ny, nx] and near[ny, nx]:
                bg[ny, nx] = True
                dq.append((ny, nx))
    am = Image.fromarray(((~bg) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(CUTOUT_BLUR))
    al = np.array(am).astype(float) / 255.0
    rgb = np.array(im).astype(float)
    out = np.zeros_like(rgb)
    nz = al > 0.02
    out[nz] = (rgb[nz] - 255.0 * (1.0 - al[nz])[:, None]) / al[nz][:, None]   # 反预乘，去白边
    img = Image.fromarray(np.dstack([np.clip(out, 0, 255), al * 255]).astype(np.uint8), "RGBA")
    img = img.crop(img.getbbox())
    os.makedirs(os.path.join(cfg["_root"], "assets-src"), exist_ok=True)
    img.save(os.path.join(cfg["_root"], "assets-src", "nailong-cutout.png"))
    print(f"  奶龙抠图 ok  {img.size[0]}x{img.size[1]}  背景占比 {bg.mean()*100:.0f}%")
    return img


# --------------------------------------------------------------------------- 3. 徽章中心
def build_core(cfg, na):
    a = np.array(na).astype(float)
    ys = np.arange(a.shape[0]) / max(1, a.shape[0] - 1)
    k = np.clip((ys - cfg["core_fade_from"]) / (1 - cfg["core_fade_from"]), 0, 1)
    k = k * k * (3 - 2 * k)                 # smoothstep：下缘淡出，圆里才不像被切断
    a[..., 3] *= (1 - k)[:, None]
    dn = Image.fromarray(a.astype(np.uint8), "RGBA")

    canvas_n = int(cfg["core_canvas"])
    w = int(cfg["core_width"])
    h = int(round(dn.size[1] * w / dn.size[0]))
    dn = dn.resize((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (canvas_n, canvas_n), (0, 0, 0, 0))
    canvas.alpha_composite(dn, ((canvas_n - w) // 2, int(canvas_n * 0.494) - h // 2))

    al = np.array(canvas)[:, :, 3]
    ys2, xs2 = np.where(al > 8)
    rmax = float(np.hypot(xs2 - (canvas_n - 1) / 2.0, ys2 - (canvas_n - 1) / 2.0).max())
    limit = float(cfg["core_max_radius"])
    if rmax > limit:                        # 超出就整体缩一点，保证不压到会旋转的文字环
        k2 = limit / rmax
        small = canvas.resize((int(canvas_n * k2),) * 2, Image.LANCZOS)
        canvas = Image.new("RGBA", (canvas_n, canvas_n), (0, 0, 0, 0))
        canvas.alpha_composite(small, ((canvas_n - small.size[0]) // 2,) * 2)
        print(f"  奶龙半径 {rmax:.0f} > {limit:.0f}，缩到 {k2*100:.0f}%")
    _save_webp(canvas, os.path.join(site_dir(cfg), "core.webp"))
    print(f"  core.webp   ok  画布 {canvas_n}")


# --------------------------------------------------------------------------- 4. 页面素材
def _badge(ring, core, size=720):
    b = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    e = size * 0.014
    ImageDraw.Draw(d).ellipse([e, e, size - 1 - e, size - 1 - e], fill=(255, 255, 255, 255))
    b.alpha_composite(d)
    b.alpha_composite(core.resize((size, size), Image.LANCZOS))
    b.alpha_composite(ring.resize((size, size), Image.LANCZOS))
    return b


def build_page_assets(cfg, na, ring, core):
    site = site_dir(cfg)
    ink = tuple(cfg["ink_rgb"])

    # favicon：16~32px 下文字环就是一团糊，只留白盘 + 奶龙
    f = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(f)
    d.ellipse([6, 6, 505, 505], fill=(255, 255, 255, 255), outline=ink + (255,), width=16)
    c = na.resize((408, int(round(na.size[1] * 408 / na.size[0]))), Image.LANCZOS)
    f.alpha_composite(c, ((512 - c.size[0]) // 2, 252 - c.size[1] // 2))
    f.save(os.path.join(site, "favicon.png"))

    # og 卡片
    W, H = 1200, 630
    og = Image.new("RGB", (W, H), (255, 251, 239))
    d = ImageDraw.Draw(og)
    d.ellipse([-260, -330, 700, 630], fill=(255, 244, 209))
    d.ellipse([W - 520, H - 380, W + 180, H + 320], fill=(255, 247, 222))
    b = _badge(ring, core, 720).resize((470, 470), Image.LANCZOS)
    og.paste(b, (86, 80), b)
    d.text((610, 168), cfg["site_title"], font=_font(FONT_CN, 76, 1), fill=(58, 44, 0))
    for i, line in enumerate(cfg["og_subtitle"]):
        d.text((614, 288 + i * 42), fill(line, cfg), font=_font(FONT_CN, 30), fill=(143, 122, 69))
    d.text((614, 400), "." + cfg["domain"].rsplit(".", 1)[-1],
           font=_font(FONT_LATIN, 22, 1), fill=(214, 174, 20))
    og.save(os.path.join(site, "og.jpg"), "JPEG", quality=88, optimize=True)

    # 校徽 + 旁边一只奶龙（「哈尔滨奶龙大学」那种摆法）
    emblem = Image.open(src_path(cfg, "logo_file")).convert("RGBA").crop(tuple(cfg["logo_emblem_box"]))
    m = Image.new("RGBA", (860, 640), (0, 0, 0, 0))
    m.alpha_composite(emblem.resize((536, 536), Image.LANCZOS), (8, 52))
    dw = 404
    dn = na.resize((dw, int(round(na.size[1] * dw / na.size[0]))), Image.LANCZOS)
    m.alpha_composite(dn, (452, 640 - dn.size[1] - 2))
    m.save(os.path.join(site, "mascot.png"))

    print("  favicon.png / og.jpg / mascot.png ok")


# ---------------------------------------------------------------------------
def _save_webp(img, path):
    img.save(path, "WEBP", quality=92, method=6)


def build_all(cfg, steps=("ring", "core", "page")):
    os.makedirs(site_dir(cfg), exist_ok=True)
    os.makedirs(os.path.join(cfg["_root"], "assets-src"), exist_ok=True)
    na = None
    if "ring" in steps:
        print("[1/4] ring.webp")
        build_ring(cfg)
    if "core" in steps or "page" in steps:
        print("[2/4] 奶龙抠图")
        na = cutout(cfg)
    if "core" in steps:
        print("[3/4] core.webp")
        build_core(cfg, na)
    if "page" in steps:
        print("[4/4] favicon / og / mascot")
        site = site_dir(cfg)
        build_page_assets(cfg, na,
                          Image.open(os.path.join(site, "ring.webp")).convert("RGBA"),
                          Image.open(os.path.join(site, "core.webp")).convert("RGBA"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="*", choices=["ring", "core", "page"])
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    build_all(cfg, tuple(args.steps) if args.steps else ("ring", "core", "page"))
    print("done →", site_dir(cfg))


if __name__ == "__main__":
    main()
