# 落地记录：usavps 上的 DeepSeek Harness（DSH）文本服务 —— 小说写作工作区

- 日期：**2026-10-08**（服务器时钟 `2026-10-08T10:29Z`）
- 目标机：`usavps` = `ssh -i C:\Users\Administrator\.ssh\termius_ed25519 longxia@156.238.255.110`（Ubuntu 22.04 / x86_64 / 16 vCPU / 16 GB / 根盘 49 GB）
- 工作区外包装目录：**`/home/longxia/vpsdsh-shortstory-workspace-wrapper.d`**
- gitee 远端：`git@gitee.com:gushiteng/vpsdsh-shortstory-workspace-wrapper.d.git`
- 一句话结论：**服务器上的 DeepSeek 文本服务已经接到 DSH 上，浏览器文本服务在 Tailscale 内网可用，工作区落在外包装目录，源码已推 gitee。**

---

## 一、交付面（现在怎么用）

| 入口 | 值 |
|---|---|
| 浏览器文本服务（手机/电脑） | `bash bin/web.sh url` 取，形如 `http://100.85.190.17:19387/?token=<43 字符>`（**令牌每次启动都换**） |
| 一次性问答（不开浏览器） | `cd ~/vpsdsh-shortstory-workspace-wrapper.d && dsh headless "写第 12 集开头 300 字"` |
| 文本服务探活 | `bash bin/probe-text-service.sh` |
| 服务状态 | `bash bin/web.sh status` |
| 写小说的地方 | `novels/<slug>/`（一部小说一个独立仓；《极简修仙传》已软链为 `novels/jijian-xiuxian-zhuan`） |

打开浏览器那一步的实测时序（服务器侧 curl 复现）：
`GET /?token=…` ⇒ **303** + `Set-Cookie: dsh-auth-…` ⇒ 带 cookie `GET /` ⇒ **200 / 34846 B**（DSH SPA，含 `window.__DSH_BOOT__` 壳）。
没令牌时一律 **401 `dsh web authentication required`**。

## 二、装了什么（实测读数）

| 项 | 值 | 证据 |
|---|---|---|
| Node | **v24.21.0**（`$HOME` 自装：`/home/longxia/toolchain/node`；系统 `/usr/bin/node` 只有 v12.22.9，**不能用**） | `node -v` |
| npm | 11.19.0 | `npm -v` |
| DSH | **`@deepseek-ai/dsh@0.2.0-rc.2`**（npm 公网包）→ `/home/longxia/toolchain/node/bin/dsh` | `dsh --version` |
| DSH 自带束 | 全局装里含 **288 个** `@deepseek-ai/*` 包（base / web-app / headless 等束都随 dsh 包落地） | `ls …/dsh/node_modules/@deepseek-ai \| wc -l` |
| `DSH_HOME` | `/home/longxia/.dsh`（`AGENTS.md` 4777 B、`.credentials.yaml` 600/251 B、`profiles/{web,headless,vps}`） | `ls -la ~/.dsh` |
| profile | **`vps`**（由自带 `web` 模板派生），用户 patch 层 `profiles/vps/cordis.patch.yml`（1417 B） | `dsh --profile vps --dump-config` |
| 模型路由 | `provider: deepseek-official` / `model: deepseek-flash`（DeepSeek-V4.1-Flash，1M ctx / 393216 输出） | 组合后的树 line 50-55 |
| 压缩阈值 | `compaction-basic: thresholdRatio 0.35 / retainRatio 0.06`（长跑写小说会话） | 组合后的树 line 274-279 |
| 权限档 | `DSH_PERMISSION_MODE=danger-full-access`（**只能 export**，见 §五 坑 2） | `bin/env.sh` |
| 监听面 | `127.0.0.1:19387`（dsh 本体）+ `100.85.190.17:19387`（Tailscale 门面）；**公网 IP 上零监听** | `ss -ltnp \| grep 19387` |
| 常驻 | tmux socket `dsh-vps`：会话 `dsh-web` + `dsh-proxy`；用户 crontab `@reboot` + `*/2 * * * *` 跑 `web.sh ensure` | `tmux -L dsh-vps ls`、`crontab -l` |
| 仓规模 | 18 个文件 / 116 KB（含 `state/` 运行件） | `du -sh` |

### 文本服务（模型）实测

```
GET  https://api.deepseek.com/v1/models            → 200，deepseek-flash ctx=1048576 max_out=393216 (text+image)
POST https://api.deepseek.com/anthropic/v1/messages → 200，deepseek-flash 返回含 thinking 块
```

## 三、架构与「为什么这么接」

```
手机/电脑（Tailscale 网内）
   │  http://100.85.190.17:19387/?token=…
   ▼
bin/ts-proxy.py             ← 只在 Tailscale 网卡监听；纯标准库 TCP 转发
   │  127.0.0.1:19387
   ▼
dsh --profile vps（DSH web）← 只肯绑 127.0.0.1/0.0.0.0，且**自带无 TLS/认证/来源策略**
   │  provider: deepseek-official + refs.DEEPSEEK_API_KEY
   ▼
https://api.deepseek.com     ← 服务器上的文本服务（1M 上下文）
```

四条设计决定与依据：

1. **不绑 `0.0.0.0`**：`@deepseek-ai/dsh-host-webserver` 的 README 明写 `0.0.0.0` 是「有意向网络开放——服务器自身不携带 TLS、认证或来源策略」。
   而 `--host` 只接受 `127.0.0.1`/`0.0.0.0` 两个值（实测别的值直接 `ValidationError`）⇒ 只能自己加一层只监听 Tailscale 网卡的门面。
2. **不自建模型路由**：DSH 自带 web 模板的缺省就是 `deepseek-official`/`deepseek-flash`；缺密钥时它自己报
   `MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"` ⇒ 只需把密钥放进凭据服务，不必写 `llm-pi-ai`。
3. **工作区根 = 启动时 cwd**：profile 里 `sandbox-policy.workspaceRoot = process.cwd()`，所以「外包装目录」就是**在哪个目录起 dsh**，`bin/web.sh` 固定 `cd` 到本仓根。
4. **cron 而不是 systemd --user**：`longxia` 无 sudo 免密 ⇒ `loginctl enable-linger` 不可用，用户级 systemd 会随登录退出被带走；cron 的 `@reboot` + 常驻条目不受影响。

## 四、仓内件一览

| 路径 | 作用 |
|---|---|
| `AGENTS.md` | 工作区长期记忆（DSH 每会话注入）：小说骨架、三条真值口径、交付与 git 口径 |
| `profile/AGENTS.md` | **服务器侧全局记忆**权威副本 → 落地为 `~/.dsh/AGENTS.md` |
| `profile/cordis.patch.yml` | 模型路由（deepseek-official / deepseek-flash）+ 压缩阈值 |
| `profile/package.json` | profile 束注册表（base + web-app） |
| `bin/env.sh` | 统一环境：PATH（node24）、`DSH_HOME`、权限档、监听地址与 token URL 口径 |
| `bin/apply-profile.sh` | 幂等落地 profile / 全局记忆 / 凭据骨架 |
| `bin/web.sh` | `start\|stop\|restart\|ensure\|status\|url\|token\|logs`（两个 tmux 会话） |
| `bin/web-run.sh` / `bin/proxy-run.sh` | 两个 tmux 会话的前台运行体 |
| `bin/ts-proxy.py` | Tailscale 门面（纯标准库 TCP 转发，绑不上就报错退出，不静默降级） |
| `bin/probe-text-service.sh` | 文本服务探活（**不打印密钥**） |
| `bin/link-novels.sh` | 把既有 `*.shortstory.d` 小说仓软链进 `novels/` |
| `bin/install-cron.sh` | `install\|verify\|uninstall` 开机自启 + 2 分钟看门狗 |
| `novels/` | 小说落点（一部一仓，各自独立；本仓 `.gitignore` 排除正文） |
| `docs/` | 本件与后续排障记录 |

## 五、踩过的坑（都留了机制）

1. **`dsh web --host` 只收两个字面值**：`100.85.190.17` 直接 `ValidationError: $.host expected "127.0.0.1" | "0.0.0.0"` ⇒ 用 `ts-proxy.py`（见 §三.1）。
2. **`DSH_PERMISSION_MODE` 不能写进 `$DSH_HOME/.env`**：启动器报
   `sets "DSH_PERMISSION_MODE", which only the launching environment may set` ⇒ 只能 export（`bin/env.sh` 做）。
3. **npm 11 默认不跑 install scripts**：首次 `npm i -g` 跳过 5 个包的脚本（含 `dsh-subprocess-local` 的 spawn helper、`node-pty`、`koffi`、`protobufjs`）⇒
   必须 `--allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs` 重装一次。
4. **入口令牌每次启动都换**：实测两次重启 token 不同（都 43 字符）⇒ `bin/web.sh` 从日志抓最新 token 写到 `state/url.txt`（600），别把老 URL 存成书签就算了。
5. **`bin/web.sh` 只管 tmux，不管 SSH 会话**：关掉 SSH 不影响服务；但服务器重启后由 crontab 的 `@reboot` 拉起（最长 2 分钟内由看门狗兜底）。

## 六、验收（本次实跑）

| # | 断言 | 读数 |
|---|---|---|
| 1 | 服务器文本服务直连可用 | `/v1/models` 200 + `deepseek-flash`；`/anthropic/v1/messages` 200 含 thinking |
| 2 | DSH 真实模型调用（走本仓 patch 覆盖层） | `dsh headless --patch profile/cordis.patch.yml --json "…"` ⇒ **rc=0**，末行 `final:` 文本自述路由与端点 |
| 3 | 浏览器文本服务起来且**能认证** | `/?token=…` ⇒ **303 + Set-Cookie** ⇒ 带 cookie `GET /` ⇒ **200 / 34846 B** |
| 4 | 令牌确实是闸门 | 不带令牌 `GET /` ⇒ **401** `dsh web authentication required` |
| 5 | Tailscale 路径从甲方电脑可达 | Windows 侧 `curl http://100.85.190.17:19387/` ⇒ **401**（通、无令牌） |
| 6 | 公网面零监听 | `ss -ltn` 里 19387 只有 `127.0.0.1` 与 `100.85.190.17` 两条 |
| 7 | 常驻与自愈 | `tmux -L dsh-vps ls` 两个会话 running；`crontab -l` 两条 `vpsdsh-shortstory-web` |
| 8 | profile 组合生效 | `--dump-config` 里 `agent-default-model: deepseek-official/deepseek-flash/high`、`compaction-basic 0.35/0.06` |
| 9 | 密钥不入仓 | 仓内 `grep -r 'sk-'` 零命中；密钥只在 `~/.dsh/.credentials.yaml`（600） |

## 七、下一步（留给甲方决定）

1. **开写**：手机上打开 `bash bin/web.sh url` 给的 URL（Tailscale 网内），新建会话直接说「写《…》第 1 集」。
2. 若要让**新小说**也自成仓：`novels/<slug>/` 里 `git init` + gitee 远端（骨架见 `AGENTS.md` §2）。
3. 若要**双模型**（例如把服务器上的 GLM 或百炼也接进来）：在 `profile/cordis.patch.yml` 加 `llm-pi-ai` 路由
   （写法照甲方桌面端那套：`api: anthropic-messages` + `apiKeyEnv`），**密钥同样只进凭据服务**。
4. 若要 HTTPS 域名：本机已有 `tailscale serve` 占着 443 → 127.0.0.1:18789（另一条线，**没动**）；
   要再挂一条得在 443 之外开端口，且需 tailscale 的操作权限（当前 `longxia` 无 sudo 免密，未尝试）。
