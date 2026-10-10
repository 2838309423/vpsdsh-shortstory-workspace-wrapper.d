# 落地记录：把 dsh-statusline.d 装到 usavps 上的 DSH（2026-10-10 12:35 北京时间）

> 任务：把甲方桌面端在用的底部状态栏插件 `@local/dsh-statusline.d` 应用到 usavps 的 DSH（profile `vps`）。
> 本文只记**服务器侧怎么装的、怎么验的、以后怎么更新**；插件本身的设计与调参看插件仓
> `D:\dsk-workspace.d\dsh-statusline.d\HANDOFF.md`（服务器上是 `/home/longxia/dsh-statusline.d/HANDOFF.md`）。

## 1. 结果（一句话）

插件已装进 usavps 的 profile `vps` 并在真实浏览器里渲染出底部状态栏：数据行 + 上拉明细（5 行）+
三级任务区；`data-sl-build=r12-2026-09-28`、`data-wire-rev=9`（宿主半投影在跑），无报错横幅。

## 2. 装了什么（三处，都在服务器上）

| # | 位置 | 内容 |
|---|---|---|
| 1 | `/home/longxia/dsh-statusline.d` | 插件源码：`git clone git@gitee.com:gushiteng/dsh-statusline.d.git`，HEAD `cd394eb`（r12） |
| 2 | `/home/longxia/.dsh/profiles/vps/node_modules/@local/dsh-statusline.d` | 软链 → `/home/longxia/dsh-statusline.d` |
| 3 | `/home/longxia/.dsh/profiles/vps/package.json` | `dependencies` 加 `"@local/dsh-statusline.d": "link:/home/longxia/dsh-statusline.d"`；`dsh.profile.bundles` 追加 `"@local/dsh-statusline.d"` |

第 3 条的**权威副本**是本仓 `profile/package.json`（`bin/apply-profile.sh` 会用它覆盖 live 那份），
所以本仓那份也一起改了；第 2 条由 `bin/apply-profile.sh` 新增的 `link_local_bundle()` 幂等保证。

## 3. 为什么不用 `dsh plugin --profile vps add link:…`

`dsh plugin` 只是把参数转发给 **pnpm**（`profile-boot` 的 `runPluginCommand`，pnpm 按 `PATH` 解析）；
服务器上**没有 pnpm**（只有 `corepack`，没启用），会以 `pnpm-missing` 失败。

而 DSH 找 `dsh.profile.bundles` 里的包名走的是 **Node 自己的 node_modules 查找**
（`dsh-app-boot/lib/index.js` 的 `resolveBundleDir` → `createRequire(profileDir/package.json).resolve.paths`，
安装锚点 → profile 目录两段），`package.json` 里的 `link:` 依赖只是登记。
⇒ 上面第 1+2+3 条与桌面端 `plugin_manager install_bundle` 的产物等价（桌面端就是
`link:` 依赖 + `dsh.profile.bundles` + profile 里的 junction）。

## 4. 生效与实测（2026-10-10 04:26–04:31 UTC）

```bash
# 重启文本服务（入口令牌每次重启都会换）
cd ~/vpsdsh-shortstory-workspace-wrapper.d && bash bin/web.sh restart
bash bin/web.sh url        # 取带令牌的入口 URL
```

| 证据 | 读数 |
|---|---|
| 组合后的 profile 树 | `dsh --profile vps --dump-config` rc=0，1269 行，含 `# == @local/dsh-statusline.d` → `- id: dsh-statusline.d / name: '@local/dsh-statusline.d'` |
| 启动日志 | `state/web.log` 无 `cannot resolve profile bundle` / 无 skipped 警告（这次重启只有两行：web-run 与令牌 URL） |
| 客户端下发 | 带 cookie 取 `/` → 200 / 35135 B，`__DSH_BOOT__` 里含 `@local/dsh-statusline.d/client.js&rev=bbc82969971f` |
| 真渲染（无头 Chrome + CDP 走 Tailscale `100.85.190.17:19387`） | `dockPresent=true`、dock 占用者 **2**（内置 stats + 状态栏）、`data-sl-build=r12-2026-09-28`、`data-wire-rev=9`、`data-sl-props` 含 `useProjection`；明细弹窗 **1 个 / 5 行**（identity·budget·usage·cost·progress）；任务区三槽 `总任务 / 小阶段任务 / 大阶段任务`；`hasNotLoadedHint=false`、`banner=null` |

实测截图与探针（Windows 侧，只读，不改服务器状态）：
`D:\dsk-workspace.d\vibe-server-by-win-dsh-without-claude.d\_sl_vps\usavps-statusline.png`
（探针脚本同目录 `verify-usavps-statusline.js` / `dom-row-probe.js`）。

> 远端页面有个「预览版说明」模态 + 遮罩会吃掉 CDP 的真实鼠标事件（`elementFromPoint` 命中 `_mask_*`），
> 所以探针先关弹窗、再用 DOM `.click()` 开会话（React 的委托 onClick 照样收到）。这条对以后写探针有用。

## 5. 以后怎么更新插件

```bash
cd /home/longxia/dsh-statusline.d && git pull      # 改 client.js：HMR 约 0.5s 生效，不用重载
bash ~/vpsdsh-shortstory-workspace-wrapper.d/bin/web.sh restart   # 改 index.js（宿主半）或 package.json 后重启最稳
```

`profile/package.json` 已把本插件列进 `dsh.profile.bundles`，**不需要**在 `cordis.patch.yml` 里
再写 `disabled: false`（桌面端那条 `- id: dsh-statusline.d / disabled: false` 是 plugin_manager 的副产品，
本插件 bundle 自带的 `cordis.patch.yml` 已经 `insert` 了 `id: dsh-statusline.d`）。

## 6. 边界与遗留

- **不装 pnpm**：本次没给服务器装 pnpm/corepack 的 pnpm；插件装卸走上面的软链法。
  以后真要 `dsh plugin`，得先 `corepack enable pnpm`（要能连 npm registry）。
- **备份**：改动前的 live `profile/package.json` 与本仓 `profile/package.json` 都留了
  `*.bak-statusline-<戳>`（本仓那份事后删掉了，live 那份留在 `~/.dsh/profiles/vps/`）。
- **重启会换入口令牌**：`bash bin/web.sh url` 重新取；手机/浏览器里存的旧 URL 会 401。
- **观察（未复现、未定性）**：刚打开会话的第一帧，明细弹窗里出现过**两行「进度」**（其中一行缺
  transcript/事件字段），11 秒轮询后稳定为 5 行、结构正确。同一份 `client.js` r12 在桌面端也在跑，
  疑为宿主投影到达前的一次过渡渲染，本次**未**在本地复现，留待需要时在插件仓查。
