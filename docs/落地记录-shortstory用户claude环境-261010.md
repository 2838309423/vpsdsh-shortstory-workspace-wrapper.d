# 落地记录：给 shortstory 用户配 claude（deepseek-flash 单线）

- 日期：2026-10-10
- 甲方口径（原话）：**「选 3。claude 是 shortstory 用户拿来蒸馏人物角色 和 写文 的」**
  ⇒ 只装 **① claude 官方原生本体 + ② deepseek-flash 模型接入**；
  **不装** GLM 微代理 / 模型 toggle / longxia 的 settings.json、CLAUDE.md、skills、plugins。
- 脚本（可重复执行）：
  - 安装：`/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/bin/install-claude-shortstory.sh`
  - 体检：同脚本 `--check`
  - 冒烟：`/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/bin/smoke-claude-shortstory.sh`

## 1 落地了什么（对照 longxia）

| 项 | longxia | shortstory（本次） |
|---|---|---|
| claude 本体 | `~/.local/share/claude/versions/2.1.285`（240 MB 原生 ELF） | 同版本、同 md5 `95fadb74aa30d5ac4ea77495d47bc071` |
| 入口 | `~/.local/bin/claude` → 裸软链 | `~/.local/bin/claude` → **启动器包装**（见 §2） |
| 模型 | GLM 默认 + DeepSeek toggle（两条线） | **只 deepseek-flash 一条线** |
| 端点 | — | `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`，`ANTHROPIC_MODEL=deepseek-flash[1m]` |
| 密钥 | `~/.deepseek-v4-flash.bashrc` | 同内容整文件搬运，600 |
| 环境注入 | `~/.bashrc`（交互式） | `~/.claude-env.sh`（600）+ 注入 `~/.profile` 与 `~/.bashrc` |
| 首启 | `~/.claude.json`（68 KB，含记忆/历史） | 最小 `{"hasCompletedOnboarding": true}`（600） |
| 未装 | — | GLM 微代理、toggle 脚本、settings.json（钩子/statusLine）、CLAUDE.md、skills、plugins |

shortstory 侧新增（全部属主 shortstory）：
`/data/home/shortstory/.local/share/claude/versions/2.1.285`、`/data/home/shortstory/.local/bin/claude`、
`/data/home/shortstory/.claude-env.sh`、`/data/home/shortstory/.deepseek-v4-flash.bashrc`、
`/data/home/shortstory/.claude.json`；`~/.profile` 与 `~/.bashrc` 各追加一段带标记的注入（幂等）。
占盘 230 MB（`/data` 余量 155 GB）。

## 2 关键设计：入口为什么是启动器包装，不是软链

`ssh shortstory@127.0.0.1 '<命令>'` 走的是**非登录、非交互** shell，**不读** `.profile`/`.bashrc`
⇒ `PATH` 里没有 `~/.local/bin`、`ANTHROPIC_*` 全缺（实测：`claude: command not found`、`MODEL=<unset>`）。

所以 `~/.local/bin/claude` 是一个 5 行的启动器：先 source `~/.claude-env.sh` 注入端点，再 `exec` 官方本体。
于是**绝对路径调用在任何 shell 模式下都成立**（自动化/批量蒸馏必需）：

```bash
ssh -i /home/longxia/.ssh/shortstory_ed25519 -o BatchMode=yes shortstory@127.0.0.1 \
  '/data/home/shortstory/.local/bin/claude -p "把这段人物描写蒸馏成 5 个性格标签：…"'
```

登录/交互式 shell 另走 `~/.profile` / `~/.bashrc` 的注入，`claude` 裸命令也能直接用。

## 3 两个实测踩坑（已修，值得长期记住）

1. **`cat > 软链` 会穿透写坏链接目标**。首版直接把 `~/.local/bin/claude` 从软链改写成启动器，
   `cat >` 顺着软链把 240 MB 本体**覆写**成启动器，而启动器又 `exec` 本体自己
   ⇒ **单进程 99% CPU 无限自 exec**（实测烧了 5 分钟，`ps` 里 ELAPSED 5:10、CPU 99.2%）。
   修法：写启动器前 `rm -f`，并反证「必须是普通文件、不是软链」，写完再校本体 md5。
   > 排查经验：这类死循环**不涨 PID**（`exec` 是替换进程映像），别指望看进程数发现。
2. **远端 `bash -s` 的 stdin 会被子进程吞掉**。`claude -p` 在 stdin 非 TTY 时会去读 stdin，
   于是把脚本**剩下的行**当输入吃掉 ⇒ 补全跑成功了、脚本却在半路 EOF 退出，
   末行 `__SELFTEST__` 凭空消失（首版实测：7 条断言后静默结束、退出码 0）。
   修法：远端脚本里每条 `claude` 调用都显式 `</dev/null`。

## 4 验收读数（2026-10-10）

`bash bin/smoke-claude-shortstory.sh` ⇒ **`__SELFTEST__ 8 0`，退出码 0**：

```
[✓] 裸命令模式可执行: 2.1.285 (Claude Code)
[✓] BASE_URL=https://api.deepseek.com/anthropic
[✓] MODEL=deepseek-flash[1m]
[✓] 密钥已注入登录态
[✓] 权限 600: .deepseek-v4-flash.bashrc / .claude-env.sh / .claude.json
[✓] 真实补全 1s 返回: 蒸馏就绪
    实际模型: deepseek-flash[1m] | tokens in=15092 out=4
```

- **真实补全**（ssh 命令模式 + 绝对路径，一发过）：`"result":"蒸馏就绪"`，`duration_api_ms=1017`，
  `modelUsage` 键 = `deepseek-flash[1m]`，`contextWindow=1000000`。
- **交互式 TUI**：`claude` 能正常起界面，**没有登录/首启向导**；只有 Claude Code 例行的
  「信任此目录？」一次性确认（每个新目录问一次，选 `Yes, I trust this folder`）。
- ⚠ **客户端告警**：`[claude-code:unrecognized_model] {"model":"deepseek-flash[1m]","query_source":"sdk"}`
  —— Claude Code 自己的模型注册表不认这个 ID，**不阻断使用**（补全正常返回）。
  longxia 切到 `dsk-flash` 时用的是同一个模型名，会有同样的告警；
  另有一条「auto mode 分类器计费」提示，同属网关兼容性说明，不影响主流程。
- ⚠ **成本口径**：`claude -p` 每次调用固定带 ~15 k input tokens 的系统提示与工具定义
  （实测 in=15092）。所以**少量多次调用很吃亏**，批量蒸馏应尽量合并成一次长提示。
  JSON 里的 `total_cost_usd` 是客户端按自家价目表估的，对 DeepSeek 端点**不准**，别拿它记账。

## 5 日常怎么用

```bash
K=/home/longxia/.ssh/shortstory_ed25519
# 交互式（人用）
ssh -i $K shortstory@127.0.0.1                 # 登录后直接 claude
# 一次性问答（非交互）
ssh -i $K -o BatchMode=yes shortstory@127.0.0.1 '/data/home/shortstory/.local/bin/claude -p "问题"'
# 体检
bash /home/longxia/vpsdsh-shortstory-workspace-wrapper.d/bin/install-claude-shortstory.sh --check
# 重装/升级本体：改脚本里 CLAUDE_VERSION 后重跑（md5 判重，幂等）
```

改端点/密钥：改 `/data/home/shortstory/.deepseek-v4-flash.bashrc`（600）；
改环境变量：改 `/data/home/shortstory/.claude-env.sh`（600）。
**别手改** `~/.profile`/`~/.bashrc` 里带 `claude (shortstory)` 标记的注入段。

## 6 明确没做的事（甲方要就再说）

- GLM 端点与 `glm-anthropic-proxy.py` 微代理、`~/.toggle-claude-model.start-claude.sh` 模型切换
- longxia 的 `settings.json`（8 个 vibe 钩子 + statusLine）、`CLAUDE.md` 记忆、`skills/`、`plugins/`
- `~/.vibe` 编排运行时（调度器/mailbox/handover）——往 shortstory 名下复制等于**再起一条编排线**
- shortstory 侧的 node（系统只有 v12.22.9；原生 claude 不需要 node，未装新 node）

## 7 安全边界

- 密钥只以「整文件 tar 过 ssh 管道」搬运，**未出现在任何命令行、日志、本记录或仓里**；
  shortstory 侧为 600，`.gitignore` 也已排除 `.env`/`.credentials.yaml`/`api-key*.txt`。
- 未改 `/home/longxia` 任何文件；未改甲方数据的属主/权限；`/home/longxia` 对 shortstory 仍是
  进不去的 0750（shortstory 侧一切自足，不依赖 longxia 家目录）。
