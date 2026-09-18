/** Markdown 渲染器纯函数测试（node tests/static/test_markdown.mjs）。 */
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import path from "node:path";

const appUrl = pathToFileURL(path.resolve("static", "app.js")).href;
const { renderMarkdown } = await import(appUrl);

let passed = 0;

function check(name, fn) {
  fn();
  passed += 1;
  console.log(`[PASS] ${name}`);
}

check("XSS：脚本标签被转义", () => {
  const html = renderMarkdown("<script>alert(1)</script><img src=x onerror=alert(1)>");
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;script&gt;"));
});

check("链接白名单：javascript: 被拒绝，https 保留", () => {
  const html = renderMarkdown("[点我](javascript:alert(1)) 和 [正常](https://example.com)");
  assert.ok(!html.includes('href="javascript'));
  assert.ok(html.includes('href="https://example.com"'));
});

check("引用两种格式转换为可点击按钮", () => {
  const html = renderMarkdown("见[来源: example.md - 片段 3]与[来源: doc.md - 第5段]。");
  const buttons = html.match(/class=\\"citation\\"|class="citation"/g) || [];
  assert.ok(buttons.length >= 2 || html.includes("citation"));
  assert.ok(html.includes('data-source="example.md"'));
  assert.ok(html.includes('data-chunk="5"'));
});

check("列表与行内代码", () => {
  const html = renderMarkdown("支持：\n- **Markdown** 文档\n- `.txt` 纯文本");
  assert.ok(html.includes("<ul>"));
  assert.ok(html.includes("<strong>Markdown</strong>"));
  assert.ok(html.includes("<code>.txt</code>"));
});

check("有序列表且小数不误判", () => {
  const html = renderMarkdown("1. 第一步\n2. 第二步\n\n1.5倍不是列表");
  assert.ok(html.includes("<ol>"));
  assert.ok(html.includes("<li>第一步</li>"));
  assert.ok(!html.includes("<li>5倍"));
});

check("代码块内容安全转义", () => {
  const html = renderMarkdown('示例：\n```python\nprint("<b>hi</b>")\n```\n结束');
  assert.ok(html.includes("<pre><code>"));
  assert.ok(html.includes("&lt;b&gt;hi&lt;/b&gt;"));
});

check("标题/引用块/分隔线", () => {
  const html = renderMarkdown("## 小结\n> 引用\n---\n正文");
  assert.ok(html.includes("<h3>小结</h3>"));
  assert.ok(html.includes("<blockquote>引用</blockquote>"));
  assert.ok(html.includes("<hr>"));
});

console.log(`\nALL ${passed} PASS`);
