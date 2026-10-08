# profile/ —— DSH profile「vps」的权威副本

DSH 的 profile = 「插件束注册表 + 用户 patch 层」。本目录只放**手写、权威**的两件：

| 文件 | 落地到 | 作用 |
|---|---|---|
| `package.json` | `$DSH_HOME/profiles/vps/package.json` | `dsh.profile.bundles` = 装哪些束（base + web-app） |
| `cordis.patch.yml` | `$DSH_HOME/profiles/vps/cordis.patch.yml` | **模型路由**（deepseek-official / deepseek-flash）+ 压缩阈值 |
| `AGENTS.md` | `$DSH_HOME/AGENTS.md` | 服务器侧全局长期记忆（DSH 每个会话注入；已存在则不覆盖，加 `--force`） |

**刻意不入库**：`profiles/vps/cordis.yml`（DSH 每次启动重写的生成物）、`cordis.patch.yml.bak-*`（脚本备份）、
`$DSH_HOME/.credentials.yaml`（密钥）、`$DSH_HOME/.env`、`$DSH_HOME/sessions|storages`（会话数据）。
口径与甲方既有 `administrator_dsh.d_profiles.d` 一致：**「用哪个、启用没启用」这半边信息在 profile 里，
只备份插件源码救不回来** ⇒ 所以这几件必须入仓。

## 落地 / 校验

```bash
cd ~/vpsdsh-shortstory-workspace-wrapper.d
bash bin/apply-profile.sh              # 变成 $DSH_HOME/profiles/vps/{package.json,cordis.patch.yml}
bash bin/web.sh restart                # 重启生效
dsh --profile vps --dump-config | head -20   # 看组合后的树（含本条 patch 是否生效）
```

## 模型路由为什么是 `deepseek-official`

DSH 自带 web 模板的 `agent-default-model` 就是 `provider: deepseek-official, model: deepseek-flash`
（由 `@deepseek-ai/dsh-llm-deepseek` 提供），密钥读**凭据服务**的 `DEEPSEEK_API_KEY`
（`$DSH_HOME/.credentials.yaml` 的 `refs`，或启动环境变量）。缺密钥时的原话：
`MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"`。
所以本实例**不需要**自建 `llm-pi-ai` 路由；patch 只是把它显式写下来，并把长跑会话的压缩阈值下调。
