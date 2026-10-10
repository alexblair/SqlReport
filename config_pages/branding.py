"""config.py 拆分：站点标识（favicon / 标题前缀）配置区块与保存处理器（B9-2 纯搬移，逻辑零改动）。

共享助手与模块级常量仍留在 config.py；本模块通过 `import config` 在调用期按
属性访问它们（`config.<helper>`），因此 config.py 末尾的再导出块必须保留。
"""
import config  # noqa: F401  # 共享助手/常量仍在 config.py，调用期解析
import json
import urllib.parse
import config_db
import branding
from render import _escape

def _render_branding_section() -> str:
    """站点标识配置区块（spec site-branding）：三模式表单 + FileReader
    base64 上传 + 模式显隐联动（原生 JS，零框架）。配置存实例本地库。"""
    settings = branding.read_site_settings()
    mode = settings.get("favicon_mode") or "default"
    if mode not in ("default", "color", "custom"):
        mode = "default"
    color = settings.get("favicon_color") or ""
    prefix = settings.get("title_prefix") or ""
    color_norm = branding.normalize_color(color)
    picker_value = "#%02X%02X%02X" % color_norm if color_norm else "#4F46E5"
    return f"""<div class="card">
<div class="section-title"><span>🏷️ 站点标识</span></div>
<p>favicon 图标与标签页环境前缀，全站生效（保存后刷新页面立即生效）</p>
<form method="post" action="/config/site-branding" class="config-form" id="branding-form">
  <label>图标模式:
    <select name="favicon_mode" id="favmode" onchange="brandingModeChanged()">
      <option value="default"{' selected' if mode == 'default' else ''}>默认（内置图标）</option>
      <option value="color"{' selected' if mode == 'color' else ''}>纯色生成</option>
      <option value="custom"{' selected' if mode == 'custom' else ''}>自定义图片</option>
    </select>
  </label>
  <label id="row-color" style="display:{'' if mode == 'color' else 'none'}">颜色 (#RGB / #RRGGBB):
    <input type="color" id="favcolor" value="{picker_value}" title="鼠标点选颜色">
    <input type="text" name="favicon_color" id="favcolor-text" value="{_escape(color)}" placeholder="#FF0000">
    <span id="recent-colors" style="display:inline-flex;gap:6px;flex-wrap:wrap"></span>
  </label>
  <label id="row-file" style="display:{'' if mode == 'custom' else 'none'}">上传图片 (PNG / ICO, ≤256KB):
    <input type="file" id="favfile" accept=".png,.ico,image/png,image/x-icon">
    <input type="hidden" name="favicon_data" id="favdata">
  </label>
  <label>标题前缀 (≤20 字符，如 [DEV] ):
    <input type="text" name="title_prefix" maxlength="20" value="{_escape(prefix)}">
  </label>
  <div class="form-actions span-full">
    <button type="submit" class="btn btn-primary">保存站点标识</button>
  </div>
</form>
<script>
function brandingModeChanged() {{
  var m = document.getElementById('favmode').value;
  document.getElementById('row-color').style.display = m === 'color' ? '' : 'none';
  document.getElementById('row-file').style.display = m === 'custom' ? '' : 'none';
  if (m === 'color') renderRecentColors();
}}
(function () {{
  var file = document.getElementById('favfile');
  if (!file) return;
  file.addEventListener('change', function () {{
    var f = this.files[0];
    var data = document.getElementById('favdata');
    data.value = '';
    if (!f) return;
    if (f.size > 256 * 1024) {{ alert('图片超过 256 KB 上限'); this.value = ''; return; }}
    var r = new FileReader();
    r.onload = function () {{ data.value = r.result; }};
    r.readAsDataURL(f);
  }});
}})();
(function () {{
  var picker = document.getElementById('favcolor');
  var text = document.getElementById('favcolor-text');
  if (!picker || !text) return;
  picker.addEventListener('input', function () {{ text.value = picker.value; }});
  text.addEventListener('input', function () {{
    var rgb = window.__normalizeColor ? window.__normalizeColor(text.value) : null;
    if (rgb) picker.value = '#' + rgb;
  }});
  window.__normalizeColor = function (v) {{
    if (typeof v !== 'string') return null;
    var t = v.trim();
    if (t[0] !== '#') return null;
    var h = t.slice(1);
    if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
    else if (h.length !== 6) return null;
    if (!/^[0-9a-fA-F]{{6}}$/.test(h)) return null;
    return h.toLowerCase();
  }};
  function getRecent() {{
    try {{ return JSON.parse(localStorage.getItem('recent_colors') || '[]'); }}
    catch (e) {{ return []; }}
  }}
  function addRecentColor(hex) {{
    hex = (hex || '').toLowerCase();
    if (!/^#[0-9a-f]{{6}}$/.test(hex)) return;
    var list = getRecent().filter(function (c) {{ return c !== hex; }});
    list.unshift(hex);
    if (list.length > 10) list = list.slice(0, 10);
    localStorage.setItem('recent_colors', JSON.stringify(list));
  }}
  window.renderRecentColors = function () {{
    var box = document.getElementById('recent-colors');
    if (!box) return;
    var list = getRecent();
    if (!list.length) {{ box.style.display = 'none'; box.innerHTML = ''; return; }}
    box.style.display = 'inline-flex';
    box.innerHTML = '';
    list.forEach(function (c) {{
      var sw = document.createElement('span');
      sw.title = '点击使用 ' + c;
      sw.style.cssText = 'width:18px;height:18px;border-radius:4px;cursor:pointer;border:1px solid #cbd5e1;display:inline-block';
      sw.style.background = c;
      sw.addEventListener('click', function () {{ text.value = c; picker.value = c; }});
      box.appendChild(sw);
    }});
  }};
  var params = new URLSearchParams(location.search);
  if (params.get('saved_brand') === '1') {{
    var cur = window.__normalizeColor(text.value);
    if (cur) addRecentColor('#' + cur);
    params.delete('saved_brand');
    history.replaceState(null, '', location.pathname + (params.toString() ? '?' + params.toString() : '') + location.hash);
  }}
  renderRecentColors();
}})();
</script>
</div>"""


def handle_site_branding_save(form_body: str,
                              session_user=None) -> tuple[int, str, dict]:
    """保存站点标识（spec site-branding）。

    整单校验：任一项非法则全部不落库、已传旧图不动（矩阵 M34）；
    成功后失效渲染缓存并写审计 update_site_setting（含前后快照）。
    存储为实例本地库（branding.write_site_settings），与配置库引擎无关。
    """
    form = urllib.parse.parse_qs(form_body or "", keep_blank_values=True)
    mode = (form.get("favicon_mode", [""])[0] or "").strip()
    color = (form.get("favicon_color", [""])[0] or "").strip()
    prefix = form.get("title_prefix", [""])[0] or ""
    image_b64 = form.get("favicon_data", [""])[0] or ""

    before = branding.read_site_settings()

    errors = []
    if mode not in branding.ALLOWED_MODES:
        errors.append(f"未知的图标模式: {mode}")
    if not errors and mode == "color" and branding.normalize_color(color) is None:
        errors.append("颜色值无效，仅支持 #RGB 或 #RRGGBB 形态")
    if len(prefix) > 20:
        errors.append("标题前缀不能超过 20 个字符")
    new_image = False
    if not errors and mode == "custom" and image_b64.strip():
        try:
            branding.save_custom_favicon(image_b64)
            new_image = True
        except branding.BrandingError as e:
            errors.append(str(e))
    if errors:
        msg = "错误: " + "；".join(errors)
        return 302, f"/config?flash={urllib.parse.quote(msg)}", {}

    values = {"favicon_mode": mode, "favicon_color": color,
              "title_prefix": prefix}
    branding.write_site_settings(values)
    branding.invalidate_site_branding_cache()

    config_db._write_audit_log(
        session_user, "update_site_setting", "site_setting",
        entity_name="站点标识",
        before_value=json.dumps(before, ensure_ascii=False) if before else None,
        after_value=json.dumps(values, ensure_ascii=False))

    flash = "站点标识已更新"
    if mode == "custom" and not new_image and not branding.load_custom_favicon():
        flash += "（提示：尚未上传自定义图片，当前显示默认图标）"
    target = f"/config?flash={urllib.parse.quote(flash)}"
    # 纯色模式保存生效：带标记，前端据标记把生效色写入最近 10 色
    if mode == "color":
        target += "&saved_brand=1"
    return 302, target, {}


def _render_branding_anchor() -> str:
    """站点标识区块（锚点 #branding-section；内层自带 card，此处不再包 card）。"""
    return ('<div id="branding-section">'
            + _render_branding_section() + '</div>')
