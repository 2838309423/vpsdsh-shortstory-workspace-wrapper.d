# vpsdsh-shortstory-workspace-wrapper.d —— 工作区长期记忆（DSH 会话注入）

> 本文件 = 本工作区的 `AGENTS.md`，DSH 每个新会话的第一条请求都会注入它。
> 约定：只记**跨会话长期有效**的事实；每条带交代日期；失效条目就地改写，不堆历史。

## 0 这是什么工作区（2026-10-08 建立）

- **usavps 上的 DSH 文本服务的工作区根**：`/home/longxia/vpsdsh-shortstory-workspace-wrapper.d`。
- 活儿：**写小说**。DSH 在这个目录里起（`cd` 到此目录再 `dsh web`/`dsh headless`），
  工作区根即本目录（profile 的 `sandbox-policy.workspaceRoot = process.cwd()`）。
- 服务器登录：`ssh -i C:\Users\Administrator\.ssh\termius_ed25519 longxia@156.238.255.110`（Ubuntu 22.04，无 sudo 免密 ⇒ 一切落 `$HOME`）。
- Node：`~/toolchain/node/bin/node`（v24.21.0，本机自装）；DSH：`~/toolchain/node/bin/dsh`（`@deepseek-ai/dsh`）。
  两个脚本都靠 `bin/env.sh` 把它们塞进 `PATH`。

## 1 文本服务（模型）——服务器上的 DeepSeek（2026-10-08 实测）

- 端点：`https://api.deepseek.com`（Anthropic 兼容路径 `/anthropic`）；模型 `deepseek-flash`（DeepSeek-V4.1-Flash）。
- 实测读数：`/v1/models` 列出 `deepseek-flash`（context_window 1048576，max_output_tokens 393216，支持 text+image）；
  `POST /anthropic/v1/messages` 200 且正文含 `thinking` 块。
- 密钥：只落 `~/.dsh/.env` 的 `DEEPSEEK_API_KEY`（600），另有历史副本 `~/.deepseek-v4-flash.bashrc`。
  **任何仓、任何件里都不写密钥原文**。
- 路由声明在 `~/.dsh/profiles/vps/cordis.patch.yml`（本仓 `profile/cordis.patch.yml` 是权威副本）。

## 2 写小说的约定（与《极简修仙传》工坊同一套骨架）

一部小说 = `novels/<slug>/` 下的独立仓，目录骨架：

| 目录 | 内容 |
|---|---|
| `bible/` | 世界观、境界/力量区间表、角色常量与动态量、场记台账 |
| `plan/` | 季纲 → 章 → 集 三层大纲（标 climax / hook） |
| `manuscript/` | **正文正典**（一文件一产物，末行＝该集状态真值） |
| `continuity/` | 场记盘点 diff 报告 |
| `state/` | 每集状态快照 `epNN.json`（视频帧数据的上游） |
| `qc/` | 质量闸门：`run.sh` 入口，末行 `__SELFTEST__ <断言> <失败>`，退出码即判定（绿=0） |
| `tasks/` | 任务规约 |
| `FREEZE.md` | 冻结声明：已冻结内容的 md5 清单 + 复现命令 |

三条硬口径（沿用既有项目，别自创）：
1. **一份真值三个投影**：正文末行 = `state/epNN.json` = `bible/characters.json`（as_of 那集），机检逐字段对账。
2. **数字失真红线**：`raw_*` ≥ 2^53−1 一律十进制字符串（JS Number 会失真）。
3. **改动已冻结内容**：必须让 `qc/freeze.sh` 的 diff 显式进 commit，不许静默改。

既有小说（claude 团队线，**本工作区不搬动它**）：`/home/longxia/shortstory-workshop.d/shortstory.jijian-xiuxian-zhuan.shortstory.d`
（《极简修仙传》）。要在这里读/写它，先跑 `bash bin/link-novels.sh` 建软链 `novels/jijian-xiuxian-zhuan`。

## 3 交付与 git 口径（甲方 2026-10-04 立规，别再问）

- **分析/调研/评估类成果一律落盘成 md 文件**，回复里只给绝对路径 + 3~5 行结论摘要，**不许把长文倒进对话**。
- 大日志先蒸馏再读（`python3 ~/tools/qwen-distill.py <log> --stats -o <log>.distilled.md`）；
  > 20 KB 或 > 200 行禁止直接读进上下文。
- git：**DSH 侧各仓该 commit 就 commit、该 push 就 push**（claude 团队沙盒才只 commit 不 push）。
  远端一律 gitee SSH：`git@gitee.com:gushiteng/<仓>.git`；推完对账。
- 回复里提到文件**一律给绝对路径**。

## 4 本工作区的实例边界

- tmux socket `dsh-vps`（`bin/web.sh` 用，两个会话：`dsh-web` + `dsh-proxy`），**不要**碰 `vibe` / `vibe-shortstory` 两条既有线的 socket 与 systemd unit。
- 监听面：`127.0.0.1:19387`（dsh 本体，它只肯绑回环/0.0.0.0）+ `100.85.190.17:19387`（`bin/ts-proxy.py` 的 Tailscale 门面）。
  **公网 IP 上零监听**是硬约束，别改成 `--host 0.0.0.0`。
- 入口 URL 带令牌且**每次启动都换**：`bash bin/web.sh url` 取（`state/url.txt`，600，不入库）。
- 不与 `~/shortstory-workshop.d`（claude 团队线，`VIBE_HOME=~/.vibe-shortstory`）共用任何家目录或钩子。
- 本工作区自己的运行时状态落 `state/`（日志、pid、url.txt），不入库。
