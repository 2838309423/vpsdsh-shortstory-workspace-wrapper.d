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

## 本机第二个账号 shortstory：怎么登、怎么干活（2026-10-10 甲方给私钥）

- `shortstory` = uid 1001，家目录 **`/data/home/shortstory`**，`shortstory:shortstory` **0750**
  ⇒ longxia **进不去**（无 r 无 x）；`sudo` 要密码（NOPASSWD 只有 `systemctl {status,start,stop,restart} longxia`、`openclaw`），
  `usermod`/`setfacl`/`su` 一条都用不了。**唯一入口是甲方给的长期私钥。**
- **登录命令**（本机回环，非交互必须带 `-o BatchMode=yes`，否则会卡在密码提示）：
  `ssh -i /home/longxia/.ssh/shortstory_ed25519 -o BatchMode=yes shortstory@127.0.0.1 '<命令>'`
  私钥 `/home/longxia/.ssh/shortstory_ed25519`（600，公钥注释 `shortstory-login-from-win10-dsh`）。
  **私钥永不入仓、永不打印**，与 DEEPSEEK 密钥同等对待。
- **干活方式：涉及 `/data/home/shortstory/**` 的一切（ffmpeg / 脚本）都必须以 shortstory 身份跑**，
  因为 longxia 读不到它的文件：
  1. longxia 的 `$HOME` 也是 0750，**shortstory 反过来也进不去** ⇒ 工具不能放 longxia 家目录。
     把 ffmpeg 等可执行文件拷到两者都能读的地方再 `chmod -R a+rX`（本次用 `/tmp/vidtool/`，**易失**）。
  2. 脚本同理；**脚本里的默认路径可能落在 longxia 家目录 ⇒ 会 Permission denied**，
     必须显式用环境变量改到 shortstory 可写处（如 `WORK_DIR=/tmp/vidtool/work`，chmod 777）。
  3. 产出物属主是 shortstory ⇒ **longxia 和 DSH GUI 都预览不了**，要看得先拷出来。
  4. **只新增、别改**甲方数据的属主/权限/ACL。
- ffmpeg：系统**没装**，已落静态版 `/home/longxia/toolchain/ffmpeg/ffmpeg-7.0.2-amd64-static/{ffmpeg,ffprobe}`。

### shortstory 也有了 claude —— 但只有 deepseek-flash 一条线（2026-10-10 落地）

- 甲方口径（原话）：「**claude 是 shortstory 用户拿来蒸馏人物角色 和 写文 的**」，并明确**只配 deepseek-flash**。
  ⇒ 只装了 ① claude 官方原生本体（2.1.285，与 longxia 同 md5）② deepseek 端点与密钥；
  **没装** GLM 微代理 / 模型 toggle / longxia 的 `settings.json`（钩子+statusLine）/ `CLAUDE.md` / skills / plugins。
- 装/体检/冒烟三个入口（都在本仓 `bin/`，幂等可重跑）：
  `bin/install-claude-shortstory.sh`（`--check` 只体检）、`bin/smoke-claude-shortstory.sh`（末行 `__SELFTEST__ 8 0`）。
- **shortstory 侧的 claude 本体独立自足**，不依赖 longxia 家目录（后者仍 0750 进不去）：
  本体 `/data/home/shortstory/.local/share/claude/versions/2.1.285`；
  端点 `/data/home/shortstory/.deepseek-v4-flash.bashrc`（600，`ANTHROPIC_MODEL=deepseek-flash[1m]`）；
  环境 `/data/home/shortstory/.claude-env.sh`（600），注入 `~/.profile` 与 `~/.bashrc`。
- ⚠ **`~/.local/bin/claude` 是启动器脚本，不是裸软链**：`ssh … '<命令>'` 走非登录 shell、不读
  `.profile`/`.bashrc` ⇒ 启动器自己注入环境再 exec 本体，所以**绝对路径调用在任何 shell 模式下都成立**。
  自动化一律用 `'/data/home/shortstory/.local/bin/claude -p "…"'`。
- ⚠ 两个踩过的坑（写脚本必守）：① `cat > 软链` 会**穿透**写坏链接目标（曾把 240 MB 本体覆写成启动器
  ⇒ 自 exec 死循环、单进程 99% CPU，且**不涨 PID**）；② 远端 `bash -s` 的 stdin 会被 `claude -p` 吞掉
  ⇒ 脚本半路 EOF、`__SELFTEST__` 行消失，必须 `</dev/null`。
- 单据：`docs/落地记录-shortstory用户claude环境-261010.md`（含验收读数、成本口径、未做项）。

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
  ⚠ 令牌**每次重启都换** ⇒ 手机里存的旧链接一律 401 `dsh web authentication required`（甲方 2026-10-12 踩的就是这条）；
  但 cookie 签名密钥是持久的（`~/.dsh/.credentials.yaml`）⇒ 认证过的设备重开一次新令牌链接即可，之后开干净 URL 也行。
  会话 cookie 寿命已从默认 30 天调到 10 年（`profile/cordis.patch.yml` 的 `connection.cookieMaxAgeDays`，**下次重启生效**）。
  **端口只开在 Tailscale 网卡 + 回环**：`dsh web --host` 只接受 `127.0.0.1`/`0.0.0.0`，
  而它自带无 TLS/无认证 ⇒ 由 `bin/web-gate.py` 在 `100.85.190.17:19387` 转发到 `127.0.0.1:19387`；
  **公网 IP 上零监听**（`ss -ltn | grep 19387` 只有这两条）。
- **入口鉴权门**（`bin/web-gate.py`，2026-10-12 落地，取代纯转发的 `bin/ts-proxy.py`）：
  **书签统一是 `http://100.85.190.17:19387/`**（干净 URL，不带令牌）；令牌轮换由门自动补，重启也不怕。
  三档写在 `state/gate.conf`，`bash bin/web.sh gate {off|tailnet|password}` 切换（**不用重启**，门每条连接现读）：
  `off` 纯直通（回滚档）｜`tailnet` 网内直通（**当前生效**，甲方方案①）｜
  `password` 网内 + 登录页，只认 **longxia / shortstory 的真 Linux 口令**（longxia 走 `sudo -S -k`，
  shortstory 走 `su` + PTY；**root 拒绝，连 PAM 都不碰**），失败 5 次/5 分钟 限速（甲方方案②）。
  ⚠ 这是**身份门不是权限边界**：web 里一切仍以 `longxia` 跑，用 shortstory 登录不会换 uid。
  ⚠ **锁死退路**：password 档下若登录页不收口令，从 Windows SSH 进来跑
  `cd ~/vpsdsh-shortstory-workspace-wrapper.d && bash bin/web.sh gate tailnet`（或删 `state/gate.conf`）。
  自测：`python3 bin/selftest-web-gate.py` ⇒ 末行 `__SELFTEST__ 25 0`；单据 `docs/方案-入口鉴权门-261012.md`。
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
