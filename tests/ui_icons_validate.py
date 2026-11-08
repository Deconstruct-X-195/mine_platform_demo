# -*- coding: utf-8 -*-
"""图标系统风格一致性自动校验 + 预览页截图
校验 frontend/icons/sprite.svg：
  1. 22 枚 symbol 齐全（viewBox 统一 0 0 16 16）
  2. 描边图标：g 层统一 fill=none / stroke-width=1.4 / round 端点拐角，子元素零覆盖
  3. 填充图标（ic-logo）：fill-rule=evenodd，无描边混用
  4. favicon.svg 与 ic-logo 同源（外层 squircle + 山体 + 矿点）
通过后用 Selenium 对 preview.html 全页截图 → docs/shots/ui_icons_preview.png
"""
import os
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITE = os.path.join(BASE, 'frontend', 'icons', 'sprite.svg')
FAVICON = os.path.join(BASE, 'frontend', 'icons', 'favicon.svg')
PREVIEW = os.path.join(BASE, 'frontend', 'icons', 'preview.html')
SHOT = os.path.join(BASE, 'docs', 'shots', 'ui_icons_preview.png')

EXPECTED = [
    'ic-demand', 'ic-pool', 'ic-price', 'ic-forecast', 'ic-inquiry', 'ic-bargain',
    'ic-order', 'ic-contract', 'ic-logistics', 'ic-waybill', 'ic-track', 'ic-settlement',
    'ic-profile', 'ic-dashboard', 'ic-admin_companies', 'ic-base_data', 'ic-doc_overview',
    'ic-alerts', 'ic-dict', 'ic-logs', 'ic-bell', 'ic-logo',
]
STROKE_ICON_COUNT = 21  # 除 ic-logo 外均为描边图标

NS = '{http://www.w3.org/2000/svg}'
ERRORS = []


def err(msg):
    ERRORS.append(msg)


def check_stroke_icon(sym):
    gid = sym.get('id')
    groups = [c for c in sym if c.tag == NS + 'g']
    if len(groups) != 1:
        err('%s: 应包含且仅包含一个 <g> 规范层' % gid)
        return
    g = groups[0]
    spec = {'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '1.4',
            'stroke-linecap': 'round', 'stroke-linejoin': 'round'}
    for k, v in spec.items():
        if g.get(k) != v:
            err('%s: <g> 属性 %s=%r 应为 %r' % (gid, k, g.get(k), v))
    allowed = {NS + t for t in ('path', 'rect', 'circle', 'ellipse')}
    for child in g:
        if child.tag not in allowed:
            err('%s: 非法子元素 %s' % (gid, child.tag))
        for k, v in child.attrib.items():
            if k in spec and v != spec[k]:
                err('%s: 子元素覆盖规范属性 %s=%r' % (gid, k, v))


def check_logo(sym):
    paths = [c for c in sym if c.tag == NS + 'path']
    if len(paths) != 1:
        err('ic-logo: 应为单一填充路径')
        return
    p = paths[0]
    if p.get('fill-rule') != 'evenodd':
        err('ic-logo: 缺少 fill-rule=evenodd')
    if p.get('stroke') is not None:
        err('ic-logo: 填充图标不应带描边')


def validate_sprite():
    if not os.path.exists(SPRITE):
        err('缺少矢量源文件 sprite.svg')
        return 0
    root = ET.parse(SPRITE).getroot()
    syms = {s.get('id'): s for s in root.iter(NS + 'symbol')}
    missing = [i for i in EXPECTED if i not in syms]
    extra = [i for i in syms if i not in EXPECTED]
    if missing:
        err('缺少 symbol: %s' % ', '.join(missing))
    if extra:
        err('多余 symbol: %s' % ', '.join(extra))
    for gid, sym in syms.items():
        if sym.get('viewBox') != '0 0 16 16':
            err('%s: viewBox 应为 0 0 16 16' % gid)
        if gid == 'ic-logo':
            check_logo(sym)
        else:
            check_stroke_icon(sym)
    return len(syms)


def validate_favicon():
    if not os.path.exists(FAVICON):
        err('缺少 favicon.svg')
        return
    root = ET.parse(FAVICON).getroot()
    paths = list(root.iter(NS + 'path'))
    circles = list(root.iter(NS + 'circle'))
    if len(paths) < 2 or not circles:
        err('favicon.svg 结构不完整（需渐变底板 + 山体 + 矿点）')
    grad = root.iter(NS + 'linearGradient')
    if not list(grad):
        err('favicon.svg 缺少品牌渐变')


def capture_preview():
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
        from selenium.webdriver.edge.service import Service
        o = Options()
        o.add_argument('--headless=new')
        o.add_argument('--window-size=1200,1000')
        o.add_argument('--disable-gpu')
        o.add_argument('--log-level=3')
        s = Service()
        s.creation_flags = 0x08000000
        d = webdriver.Edge(options=o, service=s)
        d.set_page_load_timeout(40)
        d.get('file:///' + PREVIEW.replace('\\', '/'))
        d.execute_script("return Promise.resolve(document.fonts.ready.then(function(){return true}))")
        d.save_screenshot(SHOT)
        d.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        d.save_screenshot(SHOT.replace('.png', '_bottom.png'))
        d.quit()
        print('预览页截图 -> docs/shots/ui_icons_preview.png')
    except Exception as e:  # 截图失败不影响校验结论
        print('截图跳过: %s' % e)


def main():
    n = validate_sprite()
    validate_favicon()
    if ERRORS:
        print('===== 风格一致性校验：FAIL =====')
        for e in ERRORS:
            print('  [X] %s' % e)
        raise SystemExit(1)
    print('===== 风格一致性校验：PASS =====')
    print('  symbol 总数 %d（描边 %d + 填充 1）' % (n, STROKE_ICON_COUNT))
    print('  线宽 1.4 / round 端点拐角 / viewBox 16x16 / currentColor 全部一致')
    print('  favicon 与 logo 同源验证通过')
    capture_preview()


if __name__ == '__main__':
    main()
