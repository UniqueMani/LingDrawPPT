/**
 * verify-fixes.mjs
 * 自动化验证本次修复的关键逻辑
 * 运行: node scripts/verify-fixes.mjs
 */

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dir = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dir, "..");

let passed = 0;
let failed = 0;

function assert(name, condition, detail = "") {
  if (condition) {
    console.log(`  PASS  ${name}`);
    passed++;
  } else {
    console.error(`  FAIL  ${name}${detail ? " - " + detail : ""}`);
    failed++;
  }
}

function read(rel) {
  return readFileSync(resolve(root, rel), "utf-8");
}

// ─────────────────────────────────────────────
console.log("\n[1] ChartPreview.vue - 响应式修复");
const cp = read("src/components/ChartPreview.vue");
assert("移除固定 width prop 默认值 900", !cp.includes("width: 900"));
assert("移除固定 styleWidth computed", !cp.includes("styleWidth"));
assert("容器使用 width: 100%", cp.includes("width: 100%"));
assert("使用 ResizeObserver 监听容器", cp.includes("ResizeObserver"));
assert("ResizeObserver 回调中调用 chart.resize()", cp.includes("chart?.resize()") || cp.includes("chart.resize()"));
assert("onBeforeUnmount 中 disconnect ResizeObserver", cp.includes("ro?.disconnect()") || cp.includes("ro.disconnect()"));

// ─────────────────────────────────────────────
console.log("\n[2] HomeView.vue - 废弃变量清理");
const hv = read("src/views/HomeView.vue");
assert("删除 regFullName ref", !hv.includes("regFullName"));
assert("删除 regEmail ref", !hv.includes("regEmail"));
assert("删除 regOrg ref", !hv.includes("regOrg"));
assert("注册请求不含 full_name", !hv.includes("full_name:"));
assert("注册请求不含 organization", !hv.includes("organization:"));
assert("regConfirmPwd 仍保留", hv.includes("regConfirmPwd"));

// ─────────────────────────────────────────────
console.log("\n[3] WorkspaceView.vue - 三项修复");
const wv = read("src/views/WorkspaceView.vue");
assert("上传成功后清空 uploadMessage", /uploadMessage\.value\s*=\s*["']{2}/.test(wv) && wv.includes("uploadMessage.value = \"\";  // 上传成功后清空状态消息"));
assert("更换文件前有 confirm 确认", wv.includes("window.confirm("));
assert("generateBoth 使用 Promise.allSettled", wv.includes("Promise.allSettled"));
assert("图表失败不影响配图状态（分开判断）", wv.includes("analyzeResult.status === \"fulfilled\"") && wv.includes("illusResult.status === \"fulfilled\""));

// ─────────────────────────────────────────────
console.log("\n[4] ChartCodePanel.vue - Chart.js canvas 响应式");
const ccp = read("src/components/ChartCodePanel.vue");
assert("移除 canvas 固定 width=420 属性", !ccp.includes('width="420"'));
assert("移除 canvas 固定 height=260 属性", !ccp.includes('height="260"'));
assert(".cj 容器使用 width: 100%", ccp.includes("width: 100%"));

// ─────────────────────────────────────────────
console.log("\n[5] ProfileView.vue - 头像空值保护");
const pv = read("src/views/ProfileView.vue");
assert("头像使用 || 空字符串兜底而非 ?? null 兜底", pv.includes("(store.currentUser?.username || \"?\")"));
assert("头像代码中不存在可能导致 undefined[0] 的 ?? \"?\" 方式", !pv.includes('?? "?")[0]'));

// ─────────────────────────────────────────────
console.log("\n[6] App.vue - 移动端汉堡菜单");
const av = read("src/App.vue");
assert("新增 navOpen ref", av.includes("navOpen"));
assert("汉堡按钮 .hamburger 存在", av.includes("hamburger"));
assert("移动菜单 .mobile-menu 存在", av.includes("mobile-menu"));
assert("桌面导航在窄屏隐藏（desktop-nav + display:none）", av.includes("desktop-nav") && av.includes("display: none"));
assert("≤640px 断点存在", av.includes("max-width: 640px"));

// ─────────────────────────────────────────────
console.log("\n" + "─".repeat(48));
if (failed === 0) {
  console.log(`全部通过 (${passed}/${passed + failed})`);
} else {
  console.log(`${passed} 通过 / ${failed} 失败`);
  process.exit(1);
}
