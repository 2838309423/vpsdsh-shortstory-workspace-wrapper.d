# DSH 长期记忆（usavps 服务器侧全局） 

> 本文件 = `$DSH_HOME/AGENTS.md`（usavps: `/home/longxia/.dsh/AGENTS.md`）。
> DSH 在**本服务器上**每个新会话的第一条请求都会注入它，先于项目链（工作区 AGENTS.md）。
> 权威副本在 `~/vpsdsh-shortstory-workspace-wrapper.d/profile/AGENTS.md`（改这份要 `apply-profile.sh` 落地）。
> 约定：只记**跨会话长期有效**的事实；每条带交代日期；失效条目就地改写或删除，不堆历史。

## 甲方 = 人类用户（2026-10-08 随本实例建立）

- 对话里自称**人类用户**，也即 claude 团队所称的**甲方**——同一个人，不必再问。
- **回复里提到任何文件一律给绝对路径**（甲方 2026-10-11 要求）：甲方同时跑多个项目，相对路径找不到件。
- **交付形态**：分析/调研/评估类成果**落盘成 md 文件**，回复里只给绝对路径 + 3~5 行摘要，
  **不许把长文、大段清单、表格倒进对话**。
- 甲方偏好：**能自己办的一律自己办，能看盘上文件答的不发问**；同一件事只说一次。

## 本机 = usavps（美国 VPS）

- 登录：`ssh -i C:\Users\Administrator\.ssh\termius_ed25519 longxia@156.238.255.110`（Ubuntu 22.04，x86_64）。
- **无 sudo 免密**（`sudo -n true` ⇒ password required）⇒ 一切安装落 `$HOME`，别指望 apt/systemd 系统级。
- 资源：16 vCPU / 16 GB RAM / 根盘 49 GB（已用 ~21 GB）。
- Tailscale：本机 `100.85.190.17`，MagicDNS `ser542085963120.tailcd1620.ts.net`；
  既有 `tailscale serve` 把 `https://…ts.net/` 反代到 `127.0.0.1:18789`（**别动那条**）。
- **两条既有线，勿混**：
  1. **claude 团队线**：`~/hello-world.d`、`~/claudes-workflow-runtime.d`、`~/shortstory-workshop.d`
     （`VIBE_HOME=~/.vibe-shortstory`，tmux socket `vibe`/`vibe-shortstory`，systemd unit `vibe-*`）。
     ⚠ 其中的旧小说项目《极简修仙传》**是失败的案例、将被遗弃**（甲方 2026-10-08 口径）⇒
     本 DSH 线**不接、不引用、不改动**它。
  2. **本 DSH 线**：`~/vpsdsh-shortstory-workspace-wrapper.d`（本文件所在实例，tmux socket `dsh-vps`）。
  两线**不共用**家目录、钩子、socket、unit。

## 本实例：DSH（DeepSeek Harness）——文本服务在服务器上（2026-10-08 落地）

- Node：`/home/longxia/toolchain/node/bin/node` = **v24.21.0**（`$HOME` 自装；系统 `/usr/bin/node` 只有 v12.22.9，**别用**）。
- DSH：`/home/longxia/toolchain/node/bin/dsh` = `@deepseek-ai/dsh@0.2.0-rc.2`（npm 公网包，`--allow-scripts=…` 装全原生依赖）。
- `DSH_HOME=/home/longxia/.dsh`；profile 名 **`vps`**（模板 web 派生），用户 patch 层 `profiles/vps/cordis.patch.yml`。
- **文本服务（模型）**：服务器上的 DeepSeek 官方 API —— provider 路由 `deepseek-official`，模型 `deepseek-flash`
  （DeepSeek-V4.1-Flash，1M ctx / 393216 输出，支持 text+image）。密钥在 `~/.dsh/.credentials.yaml` 的
  `refs.DEEPSEEK_API_KEY`（600），或起 DSH 前 `export DEEPSEEK_API_KEY=…`；**密钥永不入仓、永不打印**。
- 启动（工作区根 = 启动时 cwd，profile 里 `sandbox-policy.workspaceRoot = process.cwd()`）：
  `cd ~/vpsdsh-shortstory-workspace-wrapper.d && bash bin/web.sh start`
  ⇒ 浏览器文本服务：**入口 URL 带令牌**，用 `bash bin/web.sh url` 取（每次启动换新令牌）；
  实测样例 `http://100.85.190.17:19387/?token=…`（打开即 303 换 cookie，之后 200 出 SPA）。
  **端口只开在 Tailscale 网卡 + 回环**：`dsh web --host` 只接受 `127.0.0.1`/`0.0.0.0`，
  而它自带无 TLS/无认证 ⇒ 由 `bin/ts-proxy.py` 在 `100.85.190.17:19387` 转发到 `127.0.0.1:19387`；
  **公网 IP 上零监听**（`ss -ltn | grep 19387` 只有这两条）。
- 一次性问答（不开浏览器）：`dsh headless "你的问题"`（带 `--json` 出机器可读事件）。
- 权限档：`DSH_PERMISSION_MODE=danger-full-access`（**只能 export，写进 `.env` 会被启动器拒绝**）；
  本机是甲方独占 VPS ⇒ 不额外收窄沙箱。
- 服务自愈：用户 crontab 有 `@reboot` + `每 2 分钟` 的 `bin/web.sh ensure`（`bin/install-cron.sh verify` 查看）。

## git 托管约定：gitee（2026-10-03 甲方交代；本机实测可推）

- 远端一律 **SSH**：`git@gitee.com:gushiteng/<仓>.git`（本机 `ssh -T git@gitee.com` 实测认证为 `gushiteng`）。
- 身份：`user.name=gushiteng`、`user.email=bosancao@163.com`。
- **DSH 侧各仓该 commit 就 commit、该 push 就 push**（只有 claude 团队的沙盒仓才「只 commit 不 push」）；
  推完对账：`git status -sb` 无待推 + `git ls-remote` HEAD ＝ 本地 HEAD。

## 大尺寸日志：先蒸馏再读（甲方 2026-10-04 立规，硬性）

- 日志 > 20 KB 或 > 200 行 ⇒ **禁止直接读进上下文**：原始日志只落盘、只传路径，只读蒸馏件（≤ 4 千字）。
- 现成工具：`python3 ~/tools/qwen-distill.py <log> --stats -o <log>.distilled.md`
  （阿里云百炼 Qwen3.7；密钥 `~/.config/aliyun-bailian/api-key.txt`，600）。
- 自测类脚本先看**退出码**与末行 `__SELFTEST__ <断言数> <失败数>`：绿 ⇒ 零日志阅读；红 ⇒ 只取失败段。
