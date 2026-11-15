"""页面选择器与脚本：平台改版时，改这一个文件就够。

旧版把这些字符串散在主流程里（`div[style='color:red']`、`//span[text()='预览课件']`），
一改版就要翻半天；现在集中在这里，并且都留了"更抗改版"的备选。
"""
from __future__ import annotations

# 课件卡片上的按钮（默认值，.env / --xpath 可覆盖）
DEFAULT_COURSE_BUTTON_XPATH = "//*[@class='aK9HC-ZsTCNapKFaNj5fN']/button"

# 点开卡片后弹出的操作菜单里的「预览课件」
PREVIEW_MENU_TEXT = "预览课件"

# 预览 iframe（ow365 在线预览）
PREVIEW_IFRAME_XPATH = "//iframe[contains(@src, 'ow365.cn')]"

# 预览页里直链所在的元素。旧版写死 div[style='color:red']，样式一改就全废；
# 现在先用通用扫描（找"文本像直链"的元素），这条只作为快速路径。
DIRECT_LINK_CSS = "div[style='color:red']"

# 登录态失效的迹象：跳回登录/扫码页
LOGIN_HINTS: tuple[str, ...] = ("login", "passport", "qrcode", "扫码", "登录")

# 在页面里扫「看起来像直链」的文本（返回前若干个候选）
FIND_LINK_CANDIDATES_JS = """
const out = [];
const re = /^https?:\\/\\/[^\\s]+$/i;
const okExt = ['.ppt','.pptx','.pdf','.doc','.docx','.xls','.xlsx','.txt',
               '.csv','.zip','.rar','.7z','.caj','.mp4'];
for (const el of document.querySelectorAll('body *')) {
  if (el.children.length) continue;          // 只看叶子节点，避免整段文本
  const t = (el.textContent || '').trim();
  if (!t || t.length > 2048 || !re.test(t)) continue;
  const path = t.split('?')[0].toLowerCase();
  if (okExt.some(ext => path.endsWith(ext))) out.push(t);
  if (out.length >= 12) break;
}
return out;
"""
