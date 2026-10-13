#!/usr/bin/env python3
"""一条命令，从 config.json 生成整套站点（图片素材 + 两个页面）。

    python3 tools/build-site.py                 # 全做
    python3 tools/build-site.py --no-assets     # 只按模板重生成 HTML
    python3 tools/build-site.py --config other.json

先改 config.json（要问用户哪些东西见 docs/02-design-workflow.md），再跑这个。
"""

import argparse
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 文件名带连字符，不能直接 import，用 importlib 按路径加载
_spec = importlib.util.spec_from_file_location("build_assets", os.path.join(HERE, "build-assets.py"))
ba = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ba)

build_all, fill, load_config = ba.build_all, ba.fill, ba.load_config
punycode, site_dir = ba.punycode, ba.site_dir


def school_with_del(cfg):
    """把「湖州师范大学」写成「湖州<del>奶</del>师范大学」那种玩笑。

    about_del_after = 在哪个前缀后面插，about_del_text = 插进去并被划掉的字。
    前缀对不上就原样返回，不会把页面搞坏。
    例：大连理工大学 + after=大连 + text=奶 → 大连<del>奶</del>理工大学
    """
    name = cfg["school_name_cn"]
    pre, hit = cfg.get("about_del_after", ""), cfg.get("about_del_text", "")
    if not pre or not hit or not name.startswith(pre):
        return name
    return f"{name[:len(pre)]}<del>{hit}</del>{name[len(pre):]}"


def fill_all(text, cfg):
    return fill(str(text).replace("{school_del}", school_with_del(cfg)), cfg)


def context(cfg):
    p = punycode(cfg["domain"])
    school, site = cfg["school_name_cn"], cfg["site_title"]
    motto = cfg.get("school_motto", "")
    return {
        "site_title": site,
        "site_title_en": cfg.get("site_title_en") or cfg["school_name_en"],
        "target_url": cfg["target_url"],
        "canonical": f"https://{p}/",
        "og_image": f"https://{p}/og.jpg",
        "description": f"奶龙正在护送你前往{site}，随后自动前往{school}官网。",
        "og_description": f"奶龙正在护送你前往{site}",
        "intro_line": fill_all(cfg["intro_line"], cfg),
        "about_p1": fill_all(cfg["about_p1"], cfg),
        "about_p2": fill_all(cfg["about_p2"], cfg),
        "credit": fill_all(cfg["credit"], cfg),
        "mascot_title": f"{site} · 正在前往{school}官网",
        "motto_line": f'<p class="motto">校训：{motto}</p>' if motto else "",
        "steps_json": json.dumps([fill_all(s, cfg) for s in cfg["steps"]], ensure_ascii=False),
    }


# 本仓库自带的实例值。哪一项还是这些值、但别的项已经不是了，就说明大概率漏问了用户。
EXAMPLE = {
    "site_title": "中国奶龙大学",
    "school_name_cn": "湖州师范大学",
    "domain": "中国奶龙大学.org",
    "target_url": "https://www.huznu.edu.cn/",
}


def self_check(cfg):
    """生成前把「必须由用户拍板」的几项列出来，并检查有没有沿用示例值。

    这里只警告、不报错 —— 用户如果就是想要「中国奶龙大学」这个名字，也说得通。
    但如果域名/跳转目标已经换成了别的学校，站名却还是示例值，那几乎肯定是漏问了。
    """
    print("\n  将要生成的站点 —— 请逐项确认是用户要的，不是本仓库的示例：")
    print("    （首页顶着的那个大标题 = 恶搞名；文案里说「送到 XX 官网」的 = 正式名）")
    for label, key in (("恶搞学校名", "site_title"),
                       ("正式学校名", "school_name_cn"),
                       ("学校英文名", "school_name_en"),
                       ("域名", "domain"),
                       ("跳转目标", "target_url"),
                       ("校训", "school_motto")):
        v = cfg.get(key, "")
        mark = "   ← 还是示例值" if EXAMPLE.get(key) and v == EXAMPLE[key] else ""
        print(f"    {label:<12} {v}{mark}")

    # 只要这个站点已经不是本仓库那份实例了，就检查两个名字有没有漏改
    moved = (cfg["domain"] != EXAMPLE["domain"]
             or cfg["target_url"] != EXAMPLE["target_url"]
             or cfg["school_name_cn"] != EXAMPLE["school_name_cn"])
    warn = []
    if moved:
        if cfg["site_title"] == EXAMPLE["site_title"]:
            warn.append("「恶搞名」还是示例的「%s」—— 首页大标题就是它，必须问用户：\n"
                        "      沿用「%s」，还是改成 XX 奶龙大学？" % (EXAMPLE["site_title"], EXAMPLE["site_title"]))
        if cfg["school_name_cn"] == EXAMPLE["school_name_cn"]:
            warn.append("「正式名」还是示例的「%s」—— 网页里「把你送到 ___ 官网」用的是它，\n"
                        "      确认这是用户要的学校，不是上一所。" % EXAMPLE["school_name_cn"])
        if (cfg["site_title"] == EXAMPLE["site_title"]) != (cfg["school_name_cn"] == EXAMPLE["school_name_cn"]):
            warn.append("两个名字只改了一个 —— 会出现「哈尔滨奶龙大学」的页面写着\n"
                        "      「把你送到湖州师范大学官网」这种混搭，回去把另一个也问一遍。")
    else:
        print("    （就是本仓库自带的「中国奶龙大学.org」实例，忽略下面的话）")

    if warn:
        print("\n  ⚠️  配置自检：")
        for w in warn:
            print("    · " + w)
        print("    确认无误就继续；要改就改 config.json，然后重跑。")
    print()


def render(text, ctx):
    for k, v in ctx.items():
        text = text.replace("{{%s}}" % k, v)
    left = [l for l in text.splitlines() if "{{" in l]
    if left:
        raise SystemExit("模板里还有没替换的占位符：\n  " + "\n  ".join(left[:5]))
    return text


def build_pages(cfg):
    ctx = context(cfg)
    out = site_dir(cfg)
    os.makedirs(out, exist_ok=True)
    for tmpl, name in (("index.html.tmpl", "index.html"), ("mascot.html.tmpl", "mascot.html")):
        src = os.path.join(ROOT, "templates", tmpl)
        with open(src, encoding="utf-8") as fh:
            html = render(fh.read(), ctx)
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"  {name}  ← templates/{tmpl}")
    print(f"  域名 {cfg['domain']} → punycode {punycode(cfg['domain'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--no-assets", action="store_true", help="只重生成 HTML，不动图片")
    args = ap.parse_args()
    cfg = load_config(args.config)

    self_check(cfg)
    if not args.no_assets:
        print("[assets]")
        build_all(cfg)
    print("[pages]")
    build_pages(cfg)
    print("done →", site_dir(cfg))


if __name__ == "__main__":
    main()
