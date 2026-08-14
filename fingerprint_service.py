import re
import random
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("fingerprint_service")

# SADECE ANDROID (Chromium motoru). iPhone/Safari ÇIKARILDI: motor Chromium olduğundan
# 'Safari' UA + sızan navigator.userAgentData/vendor="Google Inc." anında bot sinyaliydi.
# Android UA'lar Chromium ile tutarlıdır → Client Hints override'ı ile tam eşleşir.
MOBILE_DEVICES = [
    # --- Samsung Galaxy ---
    {"name": "Galaxy S24 Ultra", "model": "SM-S928B", "av": "14", "vp": {"width": 384, "height": 824}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 750", "cores": 8, "mem": 8},
    {"name": "Galaxy S24+", "model": "SM-S926B", "av": "14", "vp": {"width": 384, "height": 832}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Samsung Xclipse 940", "cores": 8, "mem": 8},
    {"name": "Galaxy S24", "model": "SM-S921B", "av": "14", "vp": {"width": 360, "height": 780}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Samsung Xclipse 940", "cores": 8, "mem": 8},
    {"name": "Galaxy S23 Ultra", "model": "SM-S918B", "av": "14", "vp": {"width": 384, "height": 824}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 740", "cores": 8, "mem": 8},
    {"name": "Galaxy S23", "model": "SM-S911B", "av": "14", "vp": {"width": 360, "height": 780}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 740", "cores": 8, "mem": 8},
    {"name": "Galaxy S23 FE", "model": "SM-S711B", "av": "14", "vp": {"width": 360, "height": 780}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G78 MP14", "cores": 8, "mem": 8},
    {"name": "Galaxy S22", "model": "SM-S901B", "av": "14", "vp": {"width": 360, "height": 780}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Xclipse 920", "cores": 8, "mem": 8},
    {"name": "Galaxy S21", "model": "SM-G991B", "av": "13", "vp": {"width": 360, "height": 800}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G78", "cores": 8, "mem": 8},
    {"name": "Galaxy S21 FE", "model": "SM-G990B", "av": "13", "vp": {"width": 360, "height": 800}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 660", "cores": 8, "mem": 6},
    {"name": "Galaxy Note20", "model": "SM-N981B", "av": "13", "vp": {"width": 412, "height": 883}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G77", "cores": 8, "mem": 8},
    {"name": "Galaxy Z Flip5", "model": "SM-F731B", "av": "14", "vp": {"width": 360, "height": 748}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 740", "cores": 8, "mem": 8},
    {"name": "Galaxy A54", "model": "SM-A546B", "av": "14", "vp": {"width": 360, "height": 800}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G68 MC4", "cores": 8, "mem": 6},
    {"name": "Galaxy A34", "model": "SM-A346B", "av": "13", "vp": {"width": 360, "height": 800}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G68 MC4", "cores": 8, "mem": 6},
    {"name": "Galaxy A14", "model": "SM-A145F", "av": "13", "vp": {"width": 360, "height": 800}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G52 MC2", "cores": 8, "mem": 4},
    {"name": "Galaxy A73", "model": "SM-A736B", "av": "13", "vp": {"width": 384, "height": 854}, "dpr": 2.8125, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 642L", "cores": 8, "mem": 8},
    {"name": "Galaxy M34", "model": "SM-M346B", "av": "13", "vp": {"width": 360, "height": 800}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G68 MC4", "cores": 8, "mem": 6},
    # --- Google Pixel ---
    {"name": "Pixel 8 Pro", "model": "Pixel 8 Pro", "av": "14", "vp": {"width": 448, "height": 998}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G715-Immortalis MC11", "cores": 9, "mem": 8},
    {"name": "Pixel 8", "model": "Pixel 8", "av": "14", "vp": {"width": 412, "height": 915}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G715-Immortalis MC11", "cores": 9, "mem": 8},
    {"name": "Pixel 7 Pro", "model": "Pixel 7 Pro", "av": "14", "vp": {"width": 412, "height": 892}, "dpr": 3.5, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G710", "cores": 8, "mem": 8},
    {"name": "Pixel 7", "model": "Pixel 7", "av": "14", "vp": {"width": 412, "height": 915}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G710", "cores": 8, "mem": 8},
    {"name": "Pixel 7a", "model": "Pixel 7a", "av": "14", "vp": {"width": 412, "height": 915}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G710", "cores": 8, "mem": 8},
    {"name": "Pixel 6a", "model": "Pixel 6a", "av": "13", "vp": {"width": 412, "height": 915}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G78", "cores": 8, "mem": 6},
    # --- Xiaomi / Redmi / Poco ---
    {"name": "Xiaomi 14", "model": "23127PN0CG", "av": "14", "vp": {"width": 393, "height": 851}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 750", "cores": 8, "mem": 8},
    {"name": "Xiaomi 13", "model": "2211133G", "av": "14", "vp": {"width": 390, "height": 844}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 740", "cores": 8, "mem": 8},
    {"name": "Xiaomi 12", "model": "2201123G", "av": "13", "vp": {"width": 390, "height": 844}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 730", "cores": 8, "mem": 8},
    {"name": "Redmi Note 13 Pro", "model": "23117RA68G", "av": "14", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 710", "cores": 8, "mem": 8},
    {"name": "Redmi Note 12", "model": "22111317I", "av": "13", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 610", "cores": 8, "mem": 6},
    {"name": "Redmi Note 11", "model": "2201117TG", "av": "13", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 610", "cores": 8, "mem": 4},
    {"name": "Poco X5 Pro", "model": "22101320G", "av": "13", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 642L", "cores": 8, "mem": 8},
    {"name": "Poco F5", "model": "23049PCD8G", "av": "14", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 725", "cores": 8, "mem": 8},
    # --- OnePlus / Oppo / Realme / Vivo ---
    {"name": "OnePlus 11", "model": "CPH2449", "av": "14", "vp": {"width": 412, "height": 919}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 740", "cores": 8, "mem": 8},
    {"name": "OnePlus Nord 3", "model": "CPH2493", "av": "14", "vp": {"width": 412, "height": 919}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G715 MC10", "cores": 8, "mem": 8},
    {"name": "Oppo Reno10", "model": "CPH2531", "av": "14", "vp": {"width": 360, "height": 804}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G610 MC4", "cores": 8, "mem": 8},
    {"name": "Oppo Reno8", "model": "CPH2359", "av": "13", "vp": {"width": 360, "height": 804}, "dpr": 3.0, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G610 MC3", "cores": 8, "mem": 8},
    {"name": "Realme 11 Pro", "model": "RMX3771", "av": "14", "vp": {"width": 393, "height": 851}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G610 MC4", "cores": 8, "mem": 8},
    {"name": "Realme C55", "model": "RMX3710", "av": "13", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G57 MC2", "cores": 8, "mem": 6},
    {"name": "Vivo V27", "model": "V2246", "av": "13", "vp": {"width": 392, "height": 850}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G610 MC4", "cores": 8, "mem": 8},
    {"name": "Vivo Y36", "model": "V2247", "av": "13", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 610", "cores": 8, "mem": 8},
    # --- Motorola / Honor / Nothing / Tecno / Infinix ---
    {"name": "Motorola Edge 40", "model": "motorola edge 40", "av": "14", "vp": {"width": 412, "height": 915}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G68", "cores": 8, "mem": 8},
    {"name": "Moto G84", "model": "motorola g84 5G", "av": "14", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 619", "cores": 8, "mem": 8},
    {"name": "Honor 90", "model": "REA-NX9", "av": "13", "vp": {"width": 384, "height": 854}, "dpr": 2.8125, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 710", "cores": 8, "mem": 8},
    {"name": "Nothing Phone 2", "model": "A065", "av": "14", "vp": {"width": 412, "height": 915}, "dpr": 2.625, "plat": "Linux armv8l", "gpu_v": "Qualcomm", "gpu_r": "Adreno (TM) 730", "cores": 8, "mem": 8},
    {"name": "Tecno Camon 20", "model": "CK6n", "av": "13", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G57 MC2", "cores": 8, "mem": 8},
    {"name": "Infinix Note 30", "model": "X6833B", "av": "13", "vp": {"width": 393, "height": 873}, "dpr": 2.75, "plat": "Linux armv8l", "gpu_v": "ARM", "gpu_r": "Mali-G57 MC2", "cores": 8, "mem": 8},
]

# Güncel Chrome ana sürümleri (UA + Client Hints AYNI sürümü kullanır → tutarlı).
# ⚠️ BAYAT UA = TELL → ~AYLIK BUMP. Son güncelleme 2026-08-14 (stabil=152). SADQ/clicker ile aynı tut.
_ANDROID_CHROME = [149, 150, 151, 152]


@dataclass
class BrowserFingerprint:
    user_agent: str
    viewport: dict
    hardware_concurrency: int
    device_memory: int
    device_scale_factor: float = 3.0
    is_mobile: bool = True
    has_touch: bool = True
    platform: str = "Linux armv8l"
    gpu_vendor: str = "Qualcomm"
    gpu_renderer: str = "Adreno (TM) 740"
    device_name: str = ""
    os_type: str = "android"
    locale: str = "tr-TR"
    timezone_id: str = "Europe/Istanbul"
    color_scheme: str = "light"
    model: str = "SM-S911B"
    os_version: str = "14"
    browser_version: str = "152"   # Chrome ana sürüm (UA + userAgentData + Sec-CH-UA aynı) — fallback default, güncel tut
    canvas_noise: int = 1          # ESKİ zayıf gürültü (seed'siz çerezlerde geriye-uyum için tutulur)
    noise_seed: int = 0            # PER-PROFİL büyük seed → canvas/audio/webgl DE-KORELASYON (crack #1);
                                   # 0 = eski çerez (zayıf canvas_noise'a düşer, doğumuna uyumlu)


def _build_ua(dev: dict, chrome: int) -> str:
    return (
        f"Mozilla/5.0 (Linux; Android {dev['av']}; {dev['model']}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome}.0.0.0 Mobile Safari/537.36"
    )


# Xclipse (Exynos) — reconstructed eski çerezler için best-effort Vulkan sürüm eşlemesi.
# YENİ üretimde Xclipse'ten kaçınılır (Adreno/Mali tercih); bu sadece doğmuş Xclipse çerezini kurtarır.
_XCLIPSE_VK = {"920": "1.1.179", "940": "1.3.264"}


def _angle_gl(gpu_v: str, gpu_r: str):
    """UNMASKED_VENDOR(37445)/RENDERER(37446) için ANGLE-wrapped string + ALIASED_POINT_SIZE_RANGE
    üst sınırı döndürür — GPU ailesine göre (workflow-doğrulandı: modern Chrome/Android ANGLE sarar,
    bare form Chrome 124-131 UA altında SERT TELL'dir). 7936/7937/7938/35724 native bırakılır."""
    r = (gpu_r or "").strip()
    if "Xclipse" in r:                                    # Samsung Exynos → nested Vulkan formu
        m = re.search(r"(\d+)", r)
        num = m.group(1) if m else ""
        vk = _XCLIPSE_VK.get(num, "1.3.264")
        inner = ("Samsung Xclipse " + num).strip()
        return ("Google Inc. (Samsung Electronics Co., Ltd.)",
                "ANGLE (Samsung Electronics Co., Ltd., ANGLE (" + inner + ") on Vulkan " + vk + ", OpenGL ES 3.2)",
                1024)
    if gpu_v == "Qualcomm" or r.startswith("Adreno"):     # Qualcomm/Adreno
        return ("Google Inc. (Qualcomm)", "ANGLE (Qualcomm, " + r + ", OpenGL ES 3.2)", 1023)
    return ("Google Inc. (ARM)", "ANGLE (ARM, " + r + ", OpenGL ES 3.2)", 1024)  # ARM/Mali (varsayılan)


# WebGL kimliği (ANGLE-tutarlı) + font gizleme. AYRI raw string: literal { } burada JS'in kendisi;
# ana f-string'e tek {webgl_font_block} yer-tutucusu olarak gömülür (değerin brace'leri yeniden
# yorumlanmaz → doubling gerekmez). Sentinel'ler Python'da replace edilir.
_WEBGL_FONT_JS_TEMPLATE = r"""
// ===================== WEBGL KİMLİĞİ (ANGLE-tutarlı, cihaza göre; workflow-doğrulandı) =====================
try {
  var _RMset = { 'EXT_texture_compression_bptc': 1, 'EXT_texture_compression_rgtc': 1 }; // masaüstü-only BC; hiçbir mobilde yok
  var _dbgOn = new WeakSet();   // WEBGL_debug_renderer_info etkinleştirildi mi (native: ext'siz getParameter(3744x)=null)
  var _spoofGL = function (proto) {
    if (!proto || !proto.getParameter) return;
    var gp = proto.getParameter;
    _defM(proto, 'getParameter', function (p) {
      try {
        if ((p === 37445 || p === 37446) && !_dbgOn.has(this)) return gp.call(this, p); // ext yoksa native null (tell yok)
        if (p === 37445) return '__GL_VENDOR__';
        if (p === 37446) return '__GL_RENDERER__';
        if (p === 33901) { try { return new Float32Array([1, __POINT_MAX__]); } catch (e) {} } // ALIASED_POINT_SIZE_RANGE (Apple [1,64] sızıntısı)
      } catch (e) {}
      return gp.call(this, p);   // 7936/7937/7938/35724 vb. → native (Chromium sabiti, spoof YOK)
    });
    var ge = proto.getExtension;
    if (ge) _defM(proto, 'getExtension', function (name) {
      try {
        if (_RMset[name]) return null;                    // masaüstü BC uzantılarını gizle (list ile lockstep)
        var ext = ge.call(this, name);
        if (ext && name === 'WEBGL_debug_renderer_info') { try { _dbgOn.add(this); } catch (e) {} }
        return ext;
      } catch (e) { return ge.call(this, name); }
    });
    var gse = proto.getSupportedExtensions;
    if (gse) _defM(proto, 'getSupportedExtensions', function () {
      var list; try { list = gse.call(this) || []; } catch (e) { return gse.call(this); }
      try { return list.filter(function (n) { return !_RMset[n]; }); } catch (e) { return list; }
    });
  };
  _spoofGL(window.WebGLRenderingContext && WebGLRenderingContext.prototype);
  _spoofGL(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype);
} catch (e) {}

// ===================== FONT NUMARALANDIRMA (masaüstü fontlarını gizle; reflow-storm YOK) =====================
try {
  var _WL = { 'roboto':1,'roboto condensed':1,'noto sans':1,'noto serif':1,'noto color emoji':1,'droid sans mono':1,'dancing script':1,'coming soon':1,'cutive mono':1,'carrois gothic sc':1 };
  var _GEN = { 'serif':1,'sans-serif':1,'monospace':1,'cursive':1,'fantasy':1,'system-ui':1,'ui-serif':1,'ui-sans-serif':1,'ui-monospace':1,'ui-rounded':1,'math':1,'emoji':1,'fangsong':1,'inherit':1,'initial':1,'unset':1,'revert':1,'default':1,'':1 };
  var _strip = function (s) { return (s || '').trim().replace(/^["']+|["']+$/g, '').toLowerCase(); };
  var _first = function (list) { return _strip(String(list).split(',')[0]); };
  var _genOf = function (list) { var t = String(list).split(','); for (var i = 0; i < t.length; i++) { var g = _strip(t[i]); if (g && _GEN[g]) return g; } return 'sans-serif'; };
  var _isWeb = function (fam) { try { var hit = false; document.fonts.forEach(function (f) { if (!hit && _strip(f.family) === fam && f.status === 'loaded') hit = true; }); return hit; } catch (e) { return false; } };
  var _needsFB = function (fam) { var f = _first(fam); if (!f || _GEN[f] || _WL[f]) return false; if (_isWeb(f)) return false; return true; };
  var _famRe = /\d[\d.]*(?:px|pt|pc|in|cm|mm|q|%|em|rem|ex|ch|vw|vh|vmin|vmax)(?:\s*\/\s*[^\s]+)?\s+(.+)$/i;
  var _famFromFont = function (fs) { try { var m = _famRe.exec(String(fs)); return m ? m[1] : ''; } catch (e) { return ''; } };
  var _replaceFam = function (fs, g) { try { return String(fs).replace(_famRe, function (whole, fam) { return whole.slice(0, whole.length - fam.length) + g; }); } catch (e) { return fs; } };
  // Element swap: SADECE inline el.style.fontFamily okunur (ucuz, getComputedStyle YOK → reflow-storm yok).
  // Standart font-probe'lar (FingerprintJS/CreepJS) inline style kullanır → yakalanır; sıcak yol bedava kalır.
  var _swapEl = function (el, run) {
    try {
      var inl = (el && el.style) ? el.style.fontFamily : '';
      if (inl && _needsFB(inl)) {
        var g = _genOf(inl); var prev = inl; var prio = el.style.getPropertyPriority('font-family');
        el.style.setProperty('font-family', g, 'important');
        try { return run(); } finally { if (prev) el.style.setProperty('font-family', prev, prio); else el.style.removeProperty('font-family'); }
      }
    } catch (e) {}
    return run();
  };
  var _rangeEl = function (r) { try { var n = r.startContainer; if (n && n.nodeType === 3) n = n.parentElement; return (n && n.nodeType === 1) ? n : null; } catch (e) { return null; } };
  // (a) canvas measureText — this.font ucuz okunur
  try {
    var _mt = CanvasRenderingContext2D.prototype.measureText;
    _defM(CanvasRenderingContext2D.prototype, 'measureText', function (txt) {
      try { var fam = _famFromFont(this.font); if (fam && _needsFB(fam)) { var nf = _replaceFam(this.font, _genOf(fam)); var prev = this.font; this.font = nf; try { return _mt.call(this, txt); } finally { this.font = prev; } } } catch (e) {}
      return _mt.call(this, txt);
    });
  } catch (e) {}
  // (b) element ölçüm getter'ları
  try {
    var _hook = function (prop) { var d = Object.getOwnPropertyDescriptor(HTMLElement.prototype, prop); if (d && d.get) { var g = d.get; _defG(HTMLElement.prototype, prop, function () { var self = this; return _swapEl(self, function () { return g.call(self); }); }); } };
    _hook('offsetWidth'); _hook('offsetHeight'); _hook('clientWidth'); _hook('scrollWidth');
  } catch (e) {}
  // (c) element client-rect'ler
  try {
    var _gb = Element.prototype.getBoundingClientRect; _defM(Element.prototype, 'getBoundingClientRect', function () { var self = this; return _swapEl(self, function () { return _gb.call(self); }); });
    var _gc = Element.prototype.getClientRects; _defM(Element.prototype, 'getClientRects', function () { var self = this; return _swapEl(self, function () { return _gc.call(self); }); });
  } catch (e) {}
  // (d) range client-rect'ler
  try {
    var _rb = Range.prototype.getBoundingClientRect; _defM(Range.prototype, 'getBoundingClientRect', function () { var self = this; var el = _rangeEl(self); return el ? _swapEl(el, function () { return _rb.call(self); }) : _rb.call(self); });
    var _rc = Range.prototype.getClientRects; _defM(Range.prototype, 'getClientRects', function () { var self = this; var el = _rangeEl(self); return el ? _swapEl(el, function () { return _rc.call(self); }) : _rc.call(self); });
  } catch (e) {}
  // (e) queryLocalFonts — masaüstü-Chromium'a özel API; Android'de YOK + tüm font listesini döker → kaldır
  try { delete Window.prototype.queryLocalFonts; } catch (e) {}
  try { delete window.queryLocalFonts; } catch (e) {}
} catch (e) {}
"""


class FingerprintService:
    def __init__(self):
        self._use_browserforge = False

    def generate(self, seed: int | None = None) -> BrowserFingerprint:
        rng = random.Random(seed) if seed is not None else random
        dev = rng.choice(MOBILE_DEVICES)
        chrome = rng.choice(_ANDROID_CHROME)
        return BrowserFingerprint(
            user_agent=_build_ua(dev, chrome),
            viewport=dict(dev["vp"]),
            hardware_concurrency=dev["cores"],
            device_memory=dev["mem"],
            device_scale_factor=dev["dpr"],
            is_mobile=True,
            has_touch=True,
            platform=dev["plat"],
            gpu_vendor=dev["gpu_v"],
            gpu_renderer=dev["gpu_r"],
            device_name=dev["name"],
            os_type="android",
            model=dev["model"],
            os_version=dev["av"],
            browser_version=str(chrome),
            canvas_noise=rng.randint(1, 3),
            noise_seed=rng.randint(1, 2_147_483_646),   # per-profil de-korelasyon seed'i
        )

    def _ua_ch_headers(self, fp: BrowserFingerprint) -> dict:
        """Sec-CH-UA istek başlıkları — MOBİL, UA ile AYNI Chrome sürümü. UA-vs-ClientHints
        uyuşmazlığını kapatır (H1)."""
        v = fp.browser_version
        return {
            "Sec-CH-UA": f'"Chromium";v="{v}", "Google Chrome";v="{v}", "Not_A Brand";v="24"',
            "Sec-CH-UA-Mobile": "?1",
            "Sec-CH-UA-Platform": '"Android"',
            # navigator.languages ['tr-TR','tr','en-US','en'] ile TUTARLI (mismatch tell'i kapanır)
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def ua_cdp_override(self, fp: BrowserFingerprint) -> dict:
        """CDP Network.setUserAgentOverride payload'ı — userAgentMetadata ile YÜKSEK-entropi
        Client Hints'i (Sec-CH-UA-Model/-Arch/-Platform-Version/-Bitness) Android'e sabitler.
        JS userAgentData + ağ CH'i TEK KAYNAKTAN üretilir (desktop-Linux sızıntısını kapatır #3)."""
        v = fp.browser_version
        brands = [
            {"brand": "Chromium", "version": v},
            {"brand": "Google Chrome", "version": v},
            {"brand": "Not_A Brand", "version": "24"},
        ]
        full = [
            {"brand": "Chromium", "version": f"{v}.0.0.0"},
            {"brand": "Google Chrome", "version": f"{v}.0.0.0"},
            {"brand": "Not_A Brand", "version": "24.0.0.0"},
        ]
        return {
            "userAgent": fp.user_agent,
            # q-değersiz liste → navigator.languages temiz parse edilir (['tr-TR','tr','en-US','en']);
            # q-ağırlıklı gerçek başlık ayrıca extra_http_headers'ta.
            "acceptLanguage": "tr-TR,tr,en-US,en",
            "platform": "Linux armv8l",
            "userAgentMetadata": {
                "brands": brands,
                "fullVersion": f"{v}.0.0.0",
                "fullVersionList": full,
                "platform": "Android",
                "platformVersion": f"{fp.os_version}.0.0",
                "architecture": "",       # mobil ARM → boş (x86 sızıntısını kapatır)
                "model": fp.model,
                "mobile": True,
                "bitness": "",
                "wow64": False,
            },
        }

    def get_stealth_script(self, fingerprint: BrowserFingerprint | None = None) -> str:
        fp = fingerprint
        platform = fp.platform if fp else "Linux armv8l"
        gpu_v = fp.gpu_vendor if fp else "Qualcomm"
        gpu_r = fp.gpu_renderer if fp else "Adreno (TM) 740"
        mem = min(8, fp.device_memory) if fp else 8   # deviceMemory spec tavanı = 8 (12/16 imkânsız)
        cores = fp.hardware_concurrency if fp else 8
        model = fp.model if fp else "SM-S911B"
        osv = fp.os_version if fp else "14"
        cver = fp.browser_version if fp else "152"
        cnoise = fp.canvas_noise if fp else 1
        nseed = (fp.noise_seed if fp else 0) or 0
        vw = (fp.viewport or {}).get("width", 390) if fp else 390
        vh = (fp.viewport or {}).get("height", 844) if fp else 844
        # WebGL kimliği (ANGLE) + ALIASED_POINT_SIZE_RANGE + font gizleme bloğunu cihaza göre üret.
        gl_vendor, gl_renderer, point_max = _angle_gl(gpu_v, gpu_r)
        webgl_font_block = (
            _WEBGL_FONT_JS_TEMPLATE
            .replace("__GL_VENDOR__", gl_vendor)
            .replace("__GL_RENDERER__", gl_renderer)
            .replace("__POINT_MAX__", str(point_max))
        )
        return f"""
// ============ MASKE ALTYAPISI — tüm override'lar '[native code]' göstersin (#2) ============
const _patched = new WeakSet();
try {{
  const _origTS = Function.prototype.toString;
  const _proxyTS = new Proxy(_origTS, {{
    apply(t, thisArg, args) {{
      try {{ if (_patched.has(thisArg)) return 'function ' + ((thisArg && thisArg.name) || '') + '() {{ [native code] }}'; }} catch (e) {{}}
      return Reflect.apply(t, thisArg, args);
    }}
  }});
  _patched.add(_proxyTS);
  Function.prototype.toString = _proxyTS;
}} catch (e) {{}}
const _mask = (fn) => {{ try {{ _patched.add(fn); }} catch (e) {{}} return fn; }};
const _defG = (obj, prop, getter) => {{ try {{ try {{ Object.defineProperty(getter, 'name', {{ value: 'get ' + prop, configurable: true }}); }} catch (e) {{}} _patched.add(getter); Object.defineProperty(obj, prop, {{ get: getter, configurable: true }}); }} catch (e) {{}} }};
const _defM = (obj, prop, impl) => {{ try {{ var _nat = obj[prop]; try {{ Object.defineProperty(impl, 'name', {{ value: prop, configurable: true }}); }} catch (e) {{}} try {{ if (_nat && typeof _nat.length === 'number') Object.defineProperty(impl, 'length', {{ value: _nat.length, configurable: true }}); }} catch (e) {{}} _patched.add(impl); obj[prop] = impl; }} catch (e) {{}} }};

// === Otomasyon-gizleme ===
// webdriver: OVERRIDE YOK — '--disable-blink-features=AutomationControlled' Navigator.prototype'ta
// native-false yapıyor; instance own-property tell'i yaratmıyoruz (#11).
try {{
  if (!window.chrome) {{
    window.chrome = {{ runtime: {{}}, app: {{ isInstalled: false, InstallState: {{}}, RunningState: {{}} }},
      csi: _mask(function () {{}}), loadTimes: _mask(function () {{}}) }};
  }}
}} catch (e) {{}}

// === MOBİL fingerprint — PROTOTYPE üstünde + maskeli (instance own-property topolojisi yok: #11) ===
try {{ _defG(Navigator.prototype, 'platform', function () {{ return 'Linux armv8l'; }}); }} catch (e) {{}}
try {{ _defG(Navigator.prototype, 'maxTouchPoints', function () {{ return 5; }}); }} catch (e) {{}}
try {{ _defG(Navigator.prototype, 'deviceMemory', function () {{ return {mem}; }}); }} catch (e) {{}}
try {{ _defG(Navigator.prototype, 'hardwareConcurrency', function () {{ return {cores}; }}); }} catch (e) {{}}

// Ekran + PENCERE mobil ile tutarlı (outerWidth masaüstü pencereyi sızdırmasın: #10)
try {{
  _defG(Screen.prototype, 'width', function () {{ return {vw}; }});
  _defG(Screen.prototype, 'height', function () {{ return {vh}; }});
  _defG(Screen.prototype, 'availWidth', function () {{ return {vw}; }});
  _defG(Screen.prototype, 'availHeight', function () {{ return {vh}; }});
  try {{ _defG(Screen.prototype, 'availLeft', function () {{ return 0; }}); }} catch (e) {{}}
  try {{ _defG(Screen.prototype, 'availTop', function () {{ return 0; }}); }} catch (e) {{}}
  _defG(window, 'outerWidth', function () {{ return window.innerWidth; }});
  _defG(window, 'outerHeight', function () {{ return window.innerHeight; }});
  _defG(window, 'screenX', function () {{ return 0; }});
  _defG(window, 'screenY', function () {{ return 0; }});
}} catch (e) {{}}

// Mobilde EKLENTİ YOK — masaüstü PDF plugin'leri 'mobil' iddiayı ele veriyordu (#4)
try {{
  const _emptyArr = (proto) => {{
    const a = Object.create(proto);
    _defG(a, 'length', function () {{ return 0; }});
    _defM(a, 'item', function () {{ return null; }});
    _defM(a, 'namedItem', function () {{ return null; }});
    try {{ _defM(a, 'refresh', function () {{}}); }} catch (e) {{}}
    return a;
  }};
  const _pl = _emptyArr(PluginArray.prototype);
  const _mt = _emptyArr(MimeTypeArray.prototype);
  _defG(Navigator.prototype, 'plugins', function () {{ return _pl; }});
  _defG(Navigator.prototype, 'mimeTypes', function () {{ return _mt; }});
}} catch (e) {{}}

// permissions.query: OVERRIDE YOK — headful native tutarlı (eski override 'Illegal invocation'
// fırlatıyor + geçersiz 'default' state veriyordu: #8). userAgentData: CDP ile native.

// WebGL kimliği (ANGLE-tutarlı, 37445/37446 + 33901 + uzantı deltası) & font gizleme —
// cihaza göre üretilip buraya gömülür (maskeli _defM/_defG; workflow-doğrulandı).
{webgl_font_block}

// ================= PER-PROFİL DE-KORELASYON (crack #1: toplu-ban) =================
// noise_seed>0 ise: canvas/audio/webgl'e SEED'li DETERMİNİSTİK gürültü → her hesap FARKLI
// hash (linklenmez) AMA kendi içinde STABİL (birth=use korunur). Seed=0 (eski çerez) →
// eski zayıf canvas_noise (doğumuna uyumlu kalır).
try {{
  const _seed = ({nseed} >>> 0) || 0;
  if (_seed) {{
    const _mk = (s) => {{ s = s >>> 0; return () => {{ s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }}; }};
    // --- Canvas: getImageData + toDataURL TUTARLI, seed'li, tüm-kanal, seyrek ---
    const _perturb = (data, w, h) => {{
      const r = _mk((_seed ^ Math.imul(w, 73856093) ^ Math.imul(h, 19349663)) >>> 0);
      for (let i = 0; i < data.length; i += 4) {{
        if (r() < 0.06) {{
          data[i]   = (data[i]   + ((r() * 6 | 0) - 3)) & 255;
          data[i+1] = (data[i+1] + ((r() * 6 | 0) - 3)) & 255;
          data[i+2] = (data[i+2] + ((r() * 6 | 0) - 3)) & 255;
        }}
      }}
    }};
    try {{
      const _gid = CanvasRenderingContext2D.prototype.getImageData;
      _defM(CanvasRenderingContext2D.prototype, 'getImageData', function() {{
        const im = _gid.apply(this, arguments);
        try {{ _perturb(im.data, im.width, im.height); }} catch (e) {{}}
        return im;
      }});
      const _tdu = HTMLCanvasElement.prototype.toDataURL;
      _defM(HTMLCanvasElement.prototype, 'toDataURL', function() {{
        try {{
          const ctx = this.getContext('2d');
          if (ctx && this.width && this.height) {{
            // NON-DESTRUCTIVE: pristine (orig) sakla, AYRI kopyaya gürültü, geçici yaz, serialize,
            // finally'de geri yükle → tekrar toDataURL/getImageData AYNI C+Δ (drift/çelişki yok).
            const orig = _gid.call(ctx, 0, 0, this.width, this.height);
            const noisy = _gid.call(ctx, 0, 0, this.width, this.height);
            _perturb(noisy.data, this.width, this.height);
            ctx.putImageData(noisy, 0, 0);
            try {{ return _tdu.apply(this, arguments); }}
            finally {{ ctx.putImageData(orig, 0, 0); }}
          }}
        }} catch (e) {{}}
        return _tdu.apply(this, arguments);
      }});
      // toBlob (toDataURL'ün async eşi) da AYNI gürültüyü versin (yamasız kalırsa pristine C →
      // toDataURL C+Δ ile çelişki + her hesap aynı temiz hash). Detached temp-canvas → orijinal dokunulmaz.
      const _tblob = HTMLCanvasElement.prototype.toBlob;
      if (_tblob) _defM(HTMLCanvasElement.prototype, 'toBlob', function() {{
        try {{
          const ctx = this.getContext('2d');
          if (ctx && this.width && this.height) {{
            const im = _gid.call(ctx, 0, 0, this.width, this.height);
            _perturb(im.data, this.width, this.height);
            const c2 = document.createElement('canvas');
            c2.width = this.width; c2.height = this.height;
            c2.getContext('2d').putImageData(im, 0, 0);
            return _tblob.apply(c2, arguments);
          }}
        }} catch (e) {{}}
        return _tblob.apply(this, arguments);
      }});
    }} catch (e) {{}}
    // --- AudioContext: seed'li küçük perturbasyon (DRIFT-FREE) ---
    try {{
      const _ra = _mk((_seed ^ 0x9E3779B9) >>> 0);
      const _audioSeen = new WeakSet();
      const _gcd = AudioBuffer.prototype.getChannelData;
      _defM(AudioBuffer.prototype, 'getChannelData', function() {{
        const d = _gcd.apply(this, arguments);
        // İç buffer'ı YALNIZCA BİR KEZ perturbe et (spec: her çağrı aynı referans) → drift yok,
        // referans-kimliği korunur, copyFromChannel de aynı perturbe buffer'ı görür.
        try {{
          if (!_audioSeen.has(d)) {{
            const r = _mk((_seed ^ 0x9E3779B9) >>> 0);
            for (let i = 0; i < d.length; i += 100) {{ d[i] = d[i] + (r() - 0.5) * 1e-7; }}
            _audioSeen.add(d);
          }}
        }} catch (e) {{}}
        return d;
      }});
      try {{
        const _cfc = AudioBuffer.prototype.copyFromChannel;
        if (_cfc) _defM(AudioBuffer.prototype, 'copyFromChannel', function(dest, ch) {{
          try {{ this.getChannelData(ch); }} catch (e) {{}}
          return _cfc.apply(this, arguments);
        }});
      }} catch (e) {{}}
      if (window.AnalyserNode) {{
        const _ff = AnalyserNode.prototype.getFloatFrequencyData;
        _defM(AnalyserNode.prototype, 'getFloatFrequencyData', function(arr) {{
          _ff.apply(this, arguments);
          try {{ for (let i = 0; i < arr.length; i++) {{ arr[i] = arr[i] + (_ra() - 0.5) * 1e-4; }} }} catch (e) {{}}
        }});
      }}
    }} catch (e) {{}}
    // --- WebGL readPixels: seed'li perturbasyon (WebGL1 + WebGL2) ---
    try {{
      const _patchRP = (proto) => {{
        if (!proto || !proto.readPixels) return;
        const _rp = proto.readPixels;
        _defM(proto, 'readPixels', function(x, y, w, h, fmt, type, pixels) {{
          _rp.apply(this, arguments);
          try {{
            if (pixels && pixels.length) {{
              const r = _mk((_seed ^ 0x85EBCA6B) >>> 0);
              for (let i = 0; i < pixels.length; i++) {{ if (r() < 0.03) pixels[i] = (pixels[i] + ((r() * 4 | 0) - 2)) & 255; }}
            }}
          }} catch (e) {{}}
        }});
      }};
      _patchRP(window.WebGLRenderingContext && WebGLRenderingContext.prototype);
      _patchRP(window.WebGL2RenderingContext && WebGL2RenderingContext.prototype);
    }} catch (e) {{}}
  }} else {{
    // ESKİ çerez (seed yok): eski zayıf canvas gürültüsü (doğumuna uyumlu)
    const _cn = {cnoise};
    const _tdu2 = HTMLCanvasElement.prototype.toDataURL;
    _defM(HTMLCanvasElement.prototype, 'toDataURL', function(type) {{
      try {{
        if (type === 'image/png') {{
          const ctx = this.getContext('2d');
          if (ctx) {{
            const imageData = ctx.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 4) {{ imageData.data[i] = (imageData.data[i] + _cn) & 255; }}
            ctx.putImageData(imageData, 0, 0);
          }}
        }}
      }} catch (e) {{}}
      return _tdu2.apply(this, arguments);
    }});
  }}
}} catch (e) {{}}
"""

    def get_context_options(self, fingerprint: BrowserFingerprint) -> dict:
        return {
            "user_agent": fingerprint.user_agent,
            "viewport": fingerprint.viewport,
            "locale": fingerprint.locale,
            "timezone_id": fingerprint.timezone_id,
            "color_scheme": fingerprint.color_scheme,
            "device_scale_factor": fingerprint.device_scale_factor,
            "has_touch": fingerprint.has_touch,
            "is_mobile": fingerprint.is_mobile,
            # MOBİL Client Hints başlıkları → UA ile tutarlı (Google mismatch görmez).
            "extra_http_headers": self._ua_ch_headers(fingerprint),
        }
