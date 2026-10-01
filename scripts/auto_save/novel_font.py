"""小说站字体反爬还原（v1.24.1，自压测修复新增）：
番茄小说等站点把常用字映射到 Unicode 私有区（PUA U+E000-U+F8FF），
页面靠 CDN 上的自定义 woff2 字体渲染出正确字形——视觉正常、innerText
提取出来却是缺字/乱码（压测实测 4465 字正文 2244 字是 PUA）。

还原原理：字形位图比对。自定义字体里 PUA 码位的字形和真字长得一样
（反爬的本质就是"看得见抄不走"），把每个 PUA 字形渲染成位图，与参考
字体（微软雅黑/宋体/黑体）渲染的常用字位图做相关度比对，取最高分。
映射按字体文件内容 md5 缓存（同一字体全站共用，只比对一次）。

依赖：fonttools+brotli（解析 woff2）、pillow（渲染位图）；numpy 可选
（矩阵加速，缺失时纯 Python 慢速路径）。缺依赖时 has_pua 照常检测、
build_mapping 返回空表并留痕——正文原样保存（诚实失败，不阻塞下载）。
"""
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

_PUA_RE = re.compile(r"[\uE000-\uF8FF]")
_FONT_URL_RE = re.compile(r"url\((['\"]?)([^)'\"\s]+\.woff2(?:\?[^)'\"\s]*)?)\1\)", re.I)

# 参考字体候选（按序尝试存在的第一个优先组合；全部缺失时功能不可用并留痕）
_REF_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]

_CACHE_DIR = Path(__file__).resolve().parents[2] / "index"

# 常用候选字表（≈3400 字，通用规范一级字近似频序）。候选只需"包含正确字"，
# 多余/错字只会落选不影响结果；个别生僻字缺失时该字保持 PUA 并计入 unresolved。
COMMON_CHARS = (
    "的一是了我不人在他有这上们来到时大地为子中你说生国年着就那和要她出也得里后自以会家"
    "可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开美总从无情"
    "己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名法间斯知世什两次使身"
    "者被高已亲其进此话常与活正感见明问力理尔点文几定本公特做外孩相西果走将月十实向声车全"
    "信重三机工物气每并别真打太新比才便夫再书部水像眼等体却加电主界门利海受听表德少克代员"
    "许稜先口由死安写性马光白或住难望教命花结乐色更拉东神记处让母父应直字场平报友关放至张"
    "认接告入笑内英军候民岁往何度山觉路带万男边风解叫任金快原吃妈变通师立象数四失满战远格"
    "士音轻目条呢病始达深完今提求清王化空业思切怎非找片罗钱语元喜曾离飞科言干流欢约各即指"
    "合反题必该论交终林请医晚制球决传画保读运及则房早院量苦火布品近坐产答星精视五连司巴奇"
    "管类未朋且婚台夜青北队久乎越观落尽形影红爸百令周吧识步希亚术留市半热送兴造谈容极随演"
    "收首根讲整式取照办强石古华拿计您装似足双妻尼转诉米称丽客南领节衣站黑刻统断福城故历惊"
    "脸选包紧争另建维绝树系伤示愿持千史谁准联妇纪基买志静阿诗独复痛消社算义竟确酒需单治卡"
    "幸兰念举标共封强毛候甚校啊忙省坏苦预快斯注广京若展班试二保圆列股久物字状迷称皇土城练"
    "武护妹站群望擂台凶残暴恶斗杀场兄弟姐妹族长幼尊卑先后老少高低远近深浅大小多少南北上下"
    "左右前后内外东西春夏秋冬晨昏昼夜晨夕朝暮今明昨去年月日时分秒季岁纪元刻更宵晓晨曦旭日"
    "月星辰云雾雨雪风霜雷电虹露霜霞冰雹江河湖海洋溪流泉瀑波涛浪潮汐岛屿峰岭峦坡崖谷洞岩"
    "砂尘土石砖瓦泥沙灰烬煤铁铜金银锡铝钢玉珠宝翠玛瑙珊瑚琥珀水晶琉璃翡翠钻玛瑙玻璃陶瓷"
    "搪瓷珐琅砖瓦石灰水泥沥青油漆涂料颜彩漆染色泽光彩辉烂灼烁闪烁耀晖晓曦旭昊昊晗昱旻曜"
    "春夏秋冬梅兰竹菊松柏柳杨槐榆梧桐枫桦楠樟桂檀檀香草兰荷菊梅花朵花瓣蕊蓓蕾奇葩卉园圃"
    "田野山川原野荒漠沙漠戈壁草原牧草地禾苗庄稼稻麦玉米高粱谷穗黍稷稻菽麦黍稷豆薯芋蔗糖"
    "茶酒饮料茶水咖啡奶茶果汁汽水果蔬菜瓜果桃李杏枣梨柿橙橘柚柑桔莓葡萄西瓜冬瓜南瓜黄瓜"
    "丝瓜苦瓜茄子辣椒番茄萝卜白菜菠菜芹菜韭菜蒜葱姜蒜香料调料酱油醋盐糖味精鸡精胡椒花椒"
    "八角桂皮香叶丁香薄荷茴香孜然咖喱芥末酱醋茶酒烟糖早餐午餐晚餐夜宵饭菜粥面条面包糕点"
    "饼干蛋糕甜点冰淇淋巧克力糖果蜜饯果脯腊肠火腿培根肉牛肉羊肉猪肉鸡肉鸭肉鹅肉鱼肉虾蟹"
    "贝类海参鲍鱼扇贝蛤蜊鱿鱼章鱼海带紫菜豆腐豆浆豆芽豆皮腐竹粉丝粉条淀粉面粉米粉糯米大米"
    "小米黑米紫米薏米燕麦荞麦玉米面粉淀粉红薯马铃薯土豆山药芋头莲藕竹笋芦笋茭白荸荠菱角"
    "芡实莲子百合银耳木耳香菇蘑菇草菇金针菇猴头菇竹荪羊肚菌牛肝菌松茸鸡枞菌口蘑平菇杏鲍菇"
    "茶树菇滑菇金针菇鸡腿菇香菇草菇平菇口蘑木耳银耳竹荪羊肚菌牛肝菌松茸鸡枞菌"
)

__all__ = ["has_pua", "extract_font_urls", "build_mapping", "load_or_build_mapping",
           "translate_text", "font_deps_ok"]


def font_deps_ok() -> bool:
    try:
        import fontTools.ttLib  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except Exception:
        return False


def has_pua(text: str) -> bool:
    """正文是否含私有区码位（字体混淆特征）。"""
    return bool(_PUA_RE.search(text or ""))


def extract_font_urls(css_texts: List[str]) -> List[str]:
    """从页面 @font-face CSS 文本里抽 woff2 URL（去重保序）。"""
    out: List[str] = []
    for css in css_texts or []:
        for m in _FONT_URL_RE.finditer(css or ""):
            u = m.group(2)
            if u not in out:
                out.append(u)
    return out


def _glyph_vec(font, ch: str, size: int = 64):
    """渲染单字符 → 归一化展平向量（裁 bbox 缩放 + 轻模糊抗笔画差）。
    v1.24.1 二次调参：48px/blur1.5 把"个/半"错认成"全"（近似字糊成一团），
    提到 64px/blur1.0 后笔画细节可分。"""
    from PIL import Image, ImageFilter
    try:
        mask = font.getmask(ch, mode="L")
    except Exception:
        return None
    if mask.size[0] == 0 or mask.size[1] == 0:
        return None
    img = Image.frombytes("L", mask.size, bytes(mask))
    bbox = img.getbbox()
    if not bbox:
        return None
    img = img.crop(bbox).resize((size, size)).filter(ImageFilter.GaussianBlur(1.0))
    data = list(img.getdata())
    mean = sum(data) / len(data)
    var = (sum((x - mean) ** 2 for x in data)) ** 0.5
    if var == 0:
        return None
    return [(x - mean) / var for x in data]


def _load_ref_fonts():
    from PIL import ImageFont
    fonts = []
    for path in _REF_FONT_CANDIDATES:
        try:
            fonts.append(ImageFont.truetype(path, 96))
        except Exception:
            continue
    return fonts


def build_mapping(font_bytes: bytes, progress_cb=None) -> Dict[int, str]:
    """解析字体 → PUA 码位 → 字形比对 → {码位: 真字}。
    相关度 <0.45 的码位不入表（宁缺勿错，计数留给调用方报告）。"""
    if not font_deps_ok():
        return {}
    from fontTools.ttLib import TTFont

    try:
        tt = TTFont(io.BytesIO(font_bytes))
        cmap = tt.getBestCmap()
    except Exception as exc:
        sys.stderr.write(f"[novel-font] 字体解析失败: {exc}\n")
        return {}
    pua_codes = [c for c in cmap if 0xE000 <= c <= 0xF8FF]
    if not pua_codes:
        return {}
    # 码位 → 实际字形存在性由渲染兜底；未含真字映射的码位（cmap 直通）跳过比对：
    # 有些字体把 PUA 之外的正常字符也带上，可用来做"同源风格参考"，不必依赖系统字体
    try:
        from PIL import ImageFont
        pua_font = ImageFont.truetype(io.BytesIO(font_bytes), 96)
    except Exception as exc:
        sys.stderr.write(f"[novel-font] PIL 无法渲染该字体: {exc}\n")
        return {}

    candidates = [c for c in dict.fromkeys(COMMON_CHARS) if not _PUA_RE.match(c)]
    refs = _load_ref_fonts()
    if not refs:
        sys.stderr.write("[novel-font] 无可用参考字体（Windows 字体缺失），跳过还原\n")
        return {}

    # 参考位图缓存（每参考字体 × 每候选字一次）
    ref_vecs: List[tuple] = []
    for rf in refs:
        for ch in candidates:
            v = _glyph_vec(rf, ch)
            if v is not None:
                ref_vecs.append((ch, v))

    mapping: Dict[int, str] = {}
    unresolved = 0
    try:
        import numpy as np
        R = np.array([v for _, v in ref_vecs], dtype=np.float32)
        Rn = R / np.linalg.norm(R, axis=1, keepdims=True).clip(1e-9)
        for i, code in enumerate(pua_codes):
            q = _glyph_vec(pua_font, chr(code))
            if q is None:
                continue
            qv = np.array(q, dtype=np.float32)
            qn = qv / max(float(np.linalg.norm(qv)), 1e-9)
            sims = Rn @ qn
            j = int(np.argmax(sims))
            if float(sims[j]) >= 0.45:
                mapping[code] = ref_vecs[j][0]
            else:
                unresolved += 1
            if progress_cb and (i + 1) % 100 == 0:
                progress_cb(i + 1, len(pua_codes))
    except ImportError:
        # 纯 Python 慢速路径（362×候选 全量比对，几十秒级）
        for code in pua_codes:
            q = _glyph_vec(pua_font, chr(code))
            if q is None:
                continue
            best, best_s = "", 0.0
            for ch, v in ref_vecs:
                s = sum(a * b for a, b in zip(q, v))
                if s > best_s:
                    best, best_s = ch, s
            if best_s >= 0.45:
                mapping[code] = best
            else:
                unresolved += 1

    sys.stderr.write(f"[novel-font] 字体映射构建完成: {len(mapping)}/{len(pua_codes)} 码位"
                     f"（{unresolved} 个低置信未收）\n")
    return mapping


def _cache_path(font_bytes: bytes) -> Path:
    h = hashlib.md5(font_bytes).hexdigest()[:16]
    return _CACHE_DIR / f"novel_font_map_{h}.json"


def load_or_build_mapping(font_bytes: bytes) -> Dict[int, str]:
    """带磁盘缓存的映射构建（缓存按字体内容 md5 键控，全站共用只建一次）。"""
    path = _cache_path(font_bytes)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            mp = {int(k): v for k, v in raw.items()}
            if mp:
                sys.stderr.write(f"[novel-font] 命中缓存: {path.name}（{len(mp)} 码位）\n")
                return mp
        except Exception:
            pass
    mp = build_mapping(font_bytes)
    if mp:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(mp, ensure_ascii=False, sort_keys=True),
                            encoding="utf-8")
        except Exception:
            pass
    return mp


def translate_text(text: str, mapping: Dict[int, str]) -> str:
    """应用映射还原正文（str.translate 级性能，长文本无感）。"""
    if not mapping or not text:
        return text
    return text.translate(str.maketrans({chr(k): v for k, v in mapping.items()}))
