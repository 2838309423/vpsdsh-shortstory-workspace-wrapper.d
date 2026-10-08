# vpsdsh-shortstory-workspace-wrapper.d

**usavps 上的 DeepSeek Harness（DSH）文本服务 —— 小说写作工作区「外包装」仓。**

本仓是 DSH 在 usavps 上的**工作区根目录**（`workspace root`）。DSH 以「启动时所在目录」为工作区
（profile 里 `sandbox-policy.workspaceRoot = process.cwd()`），所以**在这个目录里起 DSH，工作区就是它**。
仓内同时存放**可复现整台 DSH 实例所需的东西**：DSH profile 层（模型路由）、启停脚本、密钥安装位置说明、
工作区级 AGENTS.md。

- 服务器：`usavps` = `ssh -i C:\Users\Administrator\.ssh\termius_ed25519 longxia@156.238.255.110`（Ubuntu 22.04）
- 服务器上的落点：`/home/longxia/vpsdsh-shortstory-workspace-wrapper.d`
- 文本服务：**服务器上的 DeepSeek 文本服务**（`https://api.deepseek.com`，模型 `deepseek-flash`，1M 上下文）
- 浏览器入口：见 `docs/` 里的落地记录（Tailscale 内网地址 + 端口）

## 目录

| 路径 | 作用 |
|---|---|
| `AGENTS.md` | **工作区级长期记忆**：DSH 每个会话都会注入，写小说前先读它 |
| `profile/` | DSH profile 层（`cordis.patch.yml` = 模型路由与权限；`AGENTS.md` = 全局记忆副本） |
| `bin/` | 启停/探活/落地脚本（`web.sh`、`apply-profile.sh`、`probe-text-service.sh`、`link-novels.sh`） |
| `novels/` | 小说正文落点：**一部小说一个目录**（各自独立仓；既有《极简修仙传》用软链接进来） |
| `docs/` | 落地记录、排障与验收读数 |
| `state/` | 运行时（日志/pid），**不入库** |

## 三条规矩

1. **密钥不入库**：文本服务密钥只落 `~/.dsh/.env`（600）与 `~/.dsh/.credentials.yaml`，
   profile 里只写 `apiKeyEnv: DEEPSEEK_API_KEY` 这种**引用**。
2. **小说正文各自成仓**：`novels/<slug>/` 是独立 git 仓（远端 `git@gitee.com:gushiteng/<slug>.d.git`），
   本包装仓只钉它的可用状态，不吞正文。
3. **本仓的改动要 `commit` + `push`**（DSH 侧各仓口径）；推送后对账 `git status -sb` 无待推、
   `git ls-remote` HEAD 与本地一致。

## 快速上手

```bash
ssh -i C:\Users\Administrator\.ssh\termius_ed25519 longxia@156.238.255.110
cd ~/vpsdsh-shortstory-workspace-wrapper.d
bash bin/apply-profile.sh          # 落地 profile（模型路由 + 全局记忆），幂等
bash bin/web.sh start              # 起 DSH 浏览器文本服务（tmux 常驻）
bash bin/web.sh status             # 状态 + 入口 URL
bash bin/probe-text-service.sh     # 探活服务器文本服务（不打印密钥）
```
