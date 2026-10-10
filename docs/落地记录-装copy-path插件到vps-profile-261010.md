# 落地记录：把 `@local/dsh-copy-path.d` 装到 usavps 的 DSH（profile `vps`）—— 261010-1235Z

> 执行者：DSH（本机会话）；执行时刻 2026-10-10 12:30Z 前后（服务器本地 20:30 前后）。
> 插件源：`git@gitee.com:gushiteng/dsh-copy-abspath.d.git`（原 `dsh-copy-path.d`，gitee 侧已改名），
> 本次装的就是 **`e2afbf8`**（= 当时的远端 HEAD，逐字对上）。
> 本机对应件（分析报告）：`D:\dsk-workspace.d\vibe-server.d\收尾-插件页用户文档与copy-path装机-261010-2045.md`。

## 0. 一句话

装好了、验证过了：服务器上 `window.__dshCopyPath.installed === true`、四个挂点
（`deliverables.file.actions` / `sidebar.right.tab.document.actions` /
`sidebar.right.tab.document.unpreviewable` / `plugins.detail.section`）**全部注册成功**，
插件详情页的「使用说明」节也真的渲染出来。

## 1. 复核过的环境事实（不是假设）

| 项 | 读数 |
|---|---|
| 服务器 DSH | `@deepseek-ai/dsh@0.2.0-rc.2`，装在 `~/toolchain/node/lib/node_modules/@deepseek-ai/dsh` |
| profile | `vps`，`DSH_HOME=/home/longxia/.dsh` |
| 服务器 gitee 权限 | `ssh -T git@gitee.com` ⇒ `Hi gushiteng(@gushiteng)! successfully authenticated` |
| 服务器 python3 | `/usr/bin/python3`（改文件用，显式 utf-8） |
| 入口 | `cd ~/vpsdsh-shortstory-workspace-wrapper.d && bash bin/web.sh url` |

## 2. 做了什么（都在服务器侧）

1. `cd ~ && git clone git@gitee.com:gushiteng/dsh-copy-abspath.d.git dsh-copy-path.d`
   ⇒ HEAD `e2afbf8`，与 `git ls-remote origin HEAD` 逐字相同。
2. **先核对 slot 再装**（0.2.0-rc.2 与桌面 0.1.7-rc.1 不同版本，不假设一致）：
   在 `~/toolchain/node/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/` 下实读
   `grep -o 'renderSlot("…"'`：
   - `dsh-client-ui-deliverables/lib/client.js` ⇒ `deliverables.file.actions`、`deliverables.review.file.actions`
   - `dsh-client-ui-sidebar-documentpreview/lib/client.js` ⇒ `sidebar.right.tab.document`、
     `sidebar.right.tab.document.action`、`sidebar.right.tab.document.actions`、
     `sidebar.right.tab.document.office.pdf`、`sidebar.right.tab.document.unpreviewable`
   - `dsh-client-ui-plugin-manager/lib/client.js` ⇒ `plugins.item / detail.actions / detail.badge /
     detail.section / row.config / bundle.config / bundle.activation`
   ⇒ 插件要用到的四个键**在这个版本里都存在**，按原样装，没有改插件的 slot 列表。
   （顺带记一笔：0.2.0-rc.2 比桌面多出 `deliverables.review.file.actions` 与
   `sidebar.right.tab.document.action` 两个键 —— 插件当前没挂这两处，属后续可选增强。）
3. 装配（幂等，全部走包装仓的 `bin/apply-profile.sh`）：
   - `profile/package.json`：`dependencies` 加 `"@local/dsh-copy-path.d": "link:/home/longxia/dsh-copy-path.d"`，
     `dsh.profile.bundles` 加 `"@local/dsh-copy-path.d"`；
   - `bin/apply-profile.sh`：保链清单加 `link_local_bundle "@local/dsh-copy-path.d" "$HOME/dsh-copy-path.d"`；
   - 改动前的两份原件备份在服务器上（`*.bak-copypath-261010-123039`）。
4. `bash bin/apply-profile.sh && bash bin/web.sh restart`
   ⇒ 链已建：`node_modules/@local/dsh-copy-path.d -> /home/longxia/dsh-copy-path.d`；
   重启后 `web.sh status`：`dsh 监听 127.0.0.1:19387 ；门面监听 100.85.190.17:19387`，两个 tmux 会话 running。

## 3. 验证读数（无头 Edge + CDP，本机打 `http://100.85.190.17:19387/?token=…`）

```
window.__dshCopyPath = {
  build: "r2-2026-10-10",
  installed: true,
  slots: ["deliverables.file.actions","sidebar.right.tab.document.actions",
          "sidebar.right.tab.document.unpreviewable"],
  registered: ["plugins.detail.section","deliverables.file.actions",
               "sidebar.right.tab.document.actions","sidebar.right.tab.document.unpreviewable"]
}
console: [dsh-copy-path.d] client half loaded (r2-2026-10-10): slots = plugins.detail.section
```

- 插件列表行：`@local/dsh-copy-path.d` 显示的是 **locale 的标题「复制绝对路径」**（不是包名），
  描述也是 `locale/zh.json` 里那条长文案 ⇒ 0.2.0-rc.2 上 `readPluginMeta` 读 locale 正常。
- 详情页：`[data-plugin-detail="@local/dsh-copy-path.d"]` 打开成功，
  `[data-dsh-copy-path-guide]` **found = true**，节内文本就是 GUIDE 那几段（按钮在哪 / 怎么自检 / 已知限制…）。

### 3.1 剪贴板那条路：VPS 上是「非安全上下文」，走的不是 Clipboard API

实读（无头 Edge，同一 URL）：

```json
{"isSecureContext": false, "origin": "http://100.85.190.17:19387",
 "clipboardApi": "undefined", "execCommandCopySupported": true, "execCommand": "function"}
```

`navigator.clipboard` 在纯 http 源下**不存在**（安全上下文才有），所以插件走它自己那份回落：
`document.execCommand('copy')`（`client.js` 的 `writeClipboardText`，与宿主 ui-primitives 那份行为一致）。

- **无用户激活**时（CDP `Runtime.evaluate` 直接调 `.write()`）⇒ 返回 `false`（浏览器本来的要求，不算缺陷）；
- **真实可信点击**时（CDP `Input.dispatchMouseEvent` 点一个按钮，`navigator.userActivation.isActive === true`）
  ⇒ 同一句 `window.__dshCopyPath.write('D:/dsk-workspace.d/dsh-copy-path.d/README.md')` 返回 **`true`**。

### 3.2 没做到的一步（如实记）

「真点一处**真实交付卡片**上的复制按钮」这一步**没做**：vps profile 里的会话不含 present 卡片
（侧栏 4 个会话都是小说活），交付卡片 slot 没有 subject 可渲染，所以没有真按钮可点。
补偿证据是三条：① 四个挂点注册成功；② `cardPathOf` 在卡片形状 DOM 上取到正确绝对路径
（`D:/dsk-workspace.d/样例.txt`）；③ 上面 3.1 的可信点击写剪贴板 = `true`。
**其余与桌面完全相同的那段代码在桌面已由甲方肉眼验过**（按钮出现、点了能复制）。
⇒ 结论按「装载+solt 注册+详情页说明节 = 绿」记，卡片按钮留到有真实 present 卡片时复验。

## 4. 复跑/更新方法

```bash
# 更新插件代码
cd ~/dsh-copy-path.d && git pull
# client.js 改动：刷新页面（F5）；index.js 改动：本 profile 没开 hmr root ⇒ 重启
cd ~/vpsdsh-shortstory-workspace-wrapper.d && bash bin/web.sh restart
# 验证
bash bin/web.sh url          # 取带 token 的 URL
```

## 5. 边界（没碰的东西）

- 没碰小说工作区（`~/shortstory-workshop.d/...`、wrapper 里的 `novels` 口径）——只动 profile 装配。
- 没动 `~/.dsh/.credentials.yaml`，没打印任何 key。
- 没在服务器上装/用 pnpm（服务器没有 pnpm，本来就不走 `dsh plugin add`）。
- 插件不 require 任何宿主 Client 包，服务器上零依赖安装。
