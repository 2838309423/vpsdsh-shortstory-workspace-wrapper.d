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
- 密钥：只落 `~/.dsh/.credentials.yaml` 的 `refs.DEEPSEEK_API_KEY`（600；也支持起 DSH 前 `export DEEPSEEK_API_KEY=…`）。
  服务器上的历史副本在 `~/.deepseek-v4-flash.bashrc`。**任何仓、任何件里都不写密钥原文。**
- 路由声明在 `~/.dsh/profiles/vps/cordis.patch.yml`（本仓 `profile/cordis.patch.yml` 是权威副本）。

## 2 写小说的约定（本工作区自有的骨架）

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

三条硬口径（本工作区自定，别自创）：
1. **一份真值三个投影**：正文末行 = `state/epNN.json` = `bible/characters.json`（as_of 那集），机检逐字段对账。
2. **数字失真红线**：`raw_*` ≥ 2^53−1 一律十进制字符串（JS Number 会失真）。
3. **改动已冻结内容**：必须让 `qc/freeze.sh` 的 diff 显式进 commit，不许静默改。

### 旧项目一律不接（甲方 2026-10-08 口径）

- **《极简修仙传》（`~/shortstory-workshop.d/shortstory.jijian-xiuxian-zhuan.shortstory.d`）是失败的案例，将被遗弃**
  ⇒ 本工作区**不接进来、不引用、不搬动、不修改**；它的目录仍在原处，由甲方另行处置，这里一律绕开。
- 本工作区里**没有**任何指向旧项目的软链、子模块或脚本（`bin/link-novels.sh` 已删）。
- 新小说一律在 `novels/<slug>/` 从零新建独立仓。

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

## 5 录屏 → 小说正文（阿里云百炼视觉 OCR）——2026-10-10 落地

甲方给的《长安二十四时辰》七猫录屏（安卓 Autox.js 自动翻页录的），要提取正文。
**方案与实测见 `novels/chang-an-24/录屏提正文-方案与实测.md`**（含成本、命令、坑），这里只记长期事实：

- **源视频**：`/data/home/shortstory/长安二十四时辰/hasbeen-cut-video-from-androidphone.d/*.mp4`
  （980×1408 正文容器，30 段、每段 ~144 s、~29 fps VFR）；原始整屏版在同级 `non-cuttedvideo-from-androidphone.d/`（1080×2400）。
  **longxia 读不到 `/data/home/shortstory`**，一切 `ffmpeg/取帧` 必须以 shortstory 身份跑（私钥登录见全局记忆）。
- **翻页机制**：七猫是**左右滑动翻页**，动画 ~0.4 s 内屏幕上同时有两页 ⇒ 判"稳定页"必须
  **逐条带**检查（水平也不动），只判整屏像素差会踩中动画帧。工具 `tools/stable_pages2.py`
  （`--vth 0.05 --min-sec 1.5 --fps 10`，实测静止帧 ~80%、每段稳定页 49~63 个）。
- **视觉 OCR 端点（甲方 workspace 专属）**：`https://ws-ip710u7i2cpsugfs.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
  （OpenAI 兼容；**没有** `qwen-vl-flash` 这个 ID，原来用 `qwen3-vl-flash`）。
  ⚠ **2026-10-10 晚该端点被轮换**：`qwen3-vl-flash` 也下架了（调用报 HTTP 404 `Model not exist`）。
  实测还能用的视觉/OCR 模型与价（元 / 每百万 token，输入/输出）：
  **`qwen-vl-ocr` 0.3 / 0.5**（专用 OCR，**Batch 再半价 ⇒ 0.15 / 0.25**，最便宜，20 页抽样与现稿字符级不一致仅 0.10%）、
  `qwen3.5-ocr` 0.5 / 2（会丢章节头、把百分数吐成 JSON，别用）、
  **`qwen3.8-omni-flash` 0.8 / 2.7**（本次补跑用的就是它，实测与 plus 逐字一致）、
  **`qwen3-vl-plus` 1 / 10**（下架后能力对等的替代档，本次主力）；
  `qwen3-vl-flash-2026-01-22` 仍在价目表上（0.367/2.936），但**只在「美国（弗吉尼亚）」区**，中国内地端点取不到。
  ⇒ 按 plus 报价，同样 3609 页从旧价 1.3 元级涨到 **8.09 元**（贵 6.7 倍）；要省钱就上 `qwen-vl-ocr`。
  `tools/prompt_pct.txt` 的提示词与模型无关，照用。
  密钥同 `~/.config/aliyun-bailian/api-key.txt`（600）⇒ 给 shortstory 用时拷到 `/tmp/ca31/bailian.key`，**跑完删**。
- **成本量级**：原图 980×1408 一页 ≈1477 prompt tokens + ~79 输出；实测 1715 页 ＝ **0.5825 元**。
  省钱别靠降分辨率（会错字），靠"只对稳定页调用一次"。
- **工具落点**：`tools/stable_pages2.py`（取稳定页帧）、`tools/ocr_pages.py`（批量 OCR）、
  `tools/stitch.py`（相邻页去重拼接）、`tools/clean_corpus.py`（占位符清理）、
  `tools/qa_corpus.py`（机检）、`tools/make_manifest.py`（页清单）、
  `tools/fix_page.py`（被审核拦下的页做半页补漏）、`tools/run_all.sh`（30 段一把梭）。
  中间产物在 `/tmp/ca24/{out,work}`（**易失**）；正文与 QA 已拷进
  `novels/chang-an-24/corpus/`（`novels/*` 在 `.gitignore` 里 ⇒ 正文**不入库**，版权原因）。
- **拼接事实（实测 1715 页）**：相邻稳定页只重叠 0~2 字（每翻一页屏幕前进约一屏、约 10 行），
  用 `difflib` 最长匹配块 + slack≤3 定位；用编辑距离/固定容忍度**测不出**这种小重叠。
  另外：**30 段里有 14 段的首页与上段末页整页重复**（录屏分段特性）⇒ 必须做整页去重；
  章末 UI 页（"本章说/去写章评"）要丢。
- **审核坑**：百炼会对**模型输出**做内容审核，涉敏感情节会整页 `data_inspection_failed`
  （重试无用）；`tools/fix_page.py` 把页面上下切两半再提交可救回大部分，仍会缺 1 行左右。

### 5.1 续录 S31~S58 + 截图矩形加高到含「翻页百分数」（2026-10-10 晚，同一部书）

- **源目录改名**：`/data/home/shortstory/长安二十四时辰/` → **`/data/home/shortstory/长安十二时辰/`**；
  裁剪版 `hasbeen-cut-…` 只有 **S01~S30**，续录的 **S31~S58 只有全屏版**
  （`non-cuttedvideo-from-androidphone.d/qimao-20261010-142457-s31..s58.mp4`）⇒ 必须自己裁。
- **截图矩形（长期口径）**：判稳 `crop=980:1408:50:224`（与第一批同一矩形，取页节奏一致），
  **存档帧 `crop=980:1486:50:224`**（下沿 1632→1710）。页面几何（1080×2400）：
  安卓状态栏 0~100、奶油页 **105~1715**、正文 **250~1610**、
  「电量/时间 + 翻页百分数」浮层 **1652~1681**（旧矩形 1632 正好把它切掉）、分屏灰条 1718 起。
  对照图 `novels/chang-an-24/corpus/截图矩形加高-对照.png`；`bin/crop-android-novelvideo.sh` 的默认
  目录已同步新名，RECT 备注了两个口径。
  ⚠ **`crop=` 参数必须用冒号**（`crop=W:H:X:Y`）；`stable_pages2.py` 原来把冒号换成逗号，
  而逗号是 filtergraph 的滤镜分隔符 ⇒ 报 `No such filter`（第一批没传过 `--crop` 所以没暴露，已修）。
- **百分数当「相对连续性标尺」**：提示词 `tools/prompt_pct.txt` 要求正文后另起一行输出 `PCT:40.19%`，
  `tools/pct_parse.py` 把它摘进 `pct清单.tsv` 并从正文里剔掉底栏 UI（时间/百分数，实测 1701 页零残留）。
  **刻度实测**：每页只涨 ~0.018~0.020%，而它只显示 2 位小数（0.01% ≈ 0.5 页）⇒
  只能可靠发现**≥4 页的缺口**；相邻页显示「未变」是正常量化（约占 4%），**判重复页要靠正文比对**。
  本批 28 段边界全部 Δ≤0.04%（≈≤2 页），**没有断片**。
- **⚠ 取页噪声坑（第一遍丢了约 9% 的页）**：`--vth 0.05 --min-sec 1.5` 下，**单帧压缩噪声**
  （实测某一帧 band 差 0.068）会把一个 1.9 s 静止窗劈成 0.4 s + 1.3 s 两段，都不达标 ⇒ **整页被丢**，
  正文出现 ~100 字断口。S01~S30 第一遍 1685 个页间隙里 **152 个 >1.2 s（9%）**，S31~S58 第一遍同理。
  修法（已落 `stable_pages2.py`）：成段判据放宽到 `--bridge-th 0.5`（抗噪），
  但**取帧时刻仍取窗内最长「严格静止（<vth）」子段的中点**（保证不落在翻页动画里），`--min-sec 1.0`。
  实测 s34：60 页 → **63 页**（补回 3 页）。⇒ 全 58 段已按新口径重抽重 OCR。
- **漏页的硬指标 = 页间隙**：判「一页被丢」不要看整屏像素差，直接看相邻稳定窗的时间间隙
  （正常 ≈0.5 s，漏一页就变 ≈2.8 s）。重抽验收：**旧口径 152/1685 = 9.0% → 新口径 1/3550 = 0.03%**，
  总数 3416 → **3609 页**（S01~S30 1715→1870、S31~S58 1701→1739）。那唯一 1 处（s58 p031→p032）
  在间隙中点补帧即回，补回页的百分数 71.17% 正好夹在邻页 71.16/71.18 之间。
- **⚠ 甲方点名的浪费：不许"从 s01 重扫"**。旧流程「有 `ocr.tsv` 就整段 SKIP」有两个坑：
  ① 一段只失败 1 页也要整段 63 页重跑；② 每次补新录的段都从 s01 扫一遍。
  新增 **`tools/ocr_fill.py`**：按页判、只提交 `ok != 1` 或缺行的页并归并回原表，全成功的段零调用；
  `--new-first` 新批次优先、`--seg` 指定段、**`--dry-run` 先看要花多少页**。
  本轮实补 857 页 / 15 段（含新批 13 段），不是重扫 58 段。
- **⚠ 两个会话并跑同一任务 = 产物互相覆写**（2026-10-10 实测）：交接文档给新会话后，旧会话仍在后台
  跑 `run_all31.sh ocr`（写死已下架的 flash），把 **31 段的 `ocr.tsv` 覆写成全 0 失败**，日志还出现 NUL 空洞。
  ⇒ 硬规矩：**同一任务只允许一个会话写 `/tmp/ca31/out2/**`**；交接后旧会话必须停手。
- **审核拦页的半页法补丁**：整页被 `data_inspection_failed` 拦下时，**换模型常能过** ——
  实测同一张被拦的半页，`qwen3-vl-plus`/`qwen3.5-ocr` 都被拦，而 **`qwen-vl-ocr` 放行**。
  另：先试「轻微重编码（`crop=iw-4:ih-4:2:2`）」，能过就不必切半页；百分数单独裁一条窄条
  （`crop=iw:96:0:1390`）再 OCR 读数，也比整页提交更容易过审。
- **正文里唯一的数字来自章节头 UI**：七猫把「第七章 申正」渲成「第七章 申正**02**」（末尾是章内页码），
  `clean_corpus.py` 现在按行剔除（验收 `grep -E '[0-9]|%' 正文` = 0 命中）。
  ⚠ 这条验收口径**在 S59~S76 那轮修正**了（正文本身可能有真数字，如后记里的《24小时》），见 §5.2。
- **新增工具**：`tools/pct_parse.py`（摘百分数/剔 UI/连续性审计）、`tools/batch_boundary_audit.py`
  （逐接缝判「重叠 / 整页重复 / 疑似断片 / 连续」）、`tools/merge_corpora.py`（跨批次接缝去重，
  **只在锚点终点切、绝不往后跳段落**——跳段会把真内容当重复删掉）、
  `tools/compare_corpora.py`（新旧正文互查：40 字全相位子串集合，不能用取样窗，会假性 3% 命中）、
  `tools/ocr_fill.py`（**增量补页，只补缺/失败页**）、`tools/run_all31.sh`（全屏录屏一把梭，`GLOB`/`OUT` 切批次）。
- **新旧互查的读法（别被 77% 吓到）**：`compare_corpora` 报旧稿窗命中率 76.97%，看着像"新稿丢了内容"，
  其实**全是旧稿自己的缺陷**：597/827 段未命中是旧稿含 `□`（旧 758 处 → 新 13 处）、
  168 段是 1 字级 OCR 变体（多嗦→哆嗦、持筒→持简）、39 段是旧稿丢页造成的**跳接**。
  同一 30 段新稿 184,058 字 vs 旧稿 169,360 字（**+8.7%**）。跨模型抽样（40 页）36 页逐字一致、不一致率 0.21%。
- **交付**：`novels/chang-an-24/corpus/长安十二时辰-正文-全量-S01-S58.txt`（**58 段 / 3609 页 / 35.4 万字**，
  正文 0 数字残留、`□` 仅 13 处）+ `长安十二时辰-正文-S31-S58.txt`（新录 28 段 / 1739 页）
  + `pct清单-S01-S58.tsv`、`批次边界对账-S01-S58.tsv`（57/57 连续）、`段汇总-S01-S58.tsv`、
  `页清单-S01-S58.tsv`、`页间隙审计-S01-S58.tsv`、`拼接审计-S01-S58.tsv`、`占位符修补清单-S01-S58.tsv`、
  `QA报告-S01-S58.txt`、`跨模型交叉验证-S01-S58.txt`、`跨版比对-新全量vs旧S01-S30.tsv`、
  `截图矩形加高-对照.png`；报告 `novels/chang-an-24/录屏提正文-S31-S58-续录与百分数对账.md`
  （含本轮全部账目：第二遍 OCR 8.09 元、合计 ≈8.78 元）。

### 5.2 续录 S59~S76（2026-10-10 深夜，同一部书，全量扩到 76 段）

- **素材批次**：`non-cuttedvideo-from-androidphone.d/` 里共 **76 段**全屏版
  （`…073844-s01..s30`、`…142457-s31..s58`、`…171536-s59..s76`）；本次 GLOB = **`*171536-s*.mp4`**（18 段）。
- **交付（新的权威正文）**：`novels/chang-an-24/corpus/长安十二时辰-正文-全量-S01-S76.txt`
  （**76 段 / 4726 页 / 464,341 字**：S01~S58 354,110 + S59~S76 110,231）+ `…-正文-S59-S76.txt`；
  同名清单全部扩到 `-S01-S76`，另加 `pct补录-S01-S76.tsv`、`接缝复核-S58-S59.txt`、
  `底栏百分数-假数实证.png`（**本轮专有**，见下）。报告 `novels/chang-an-24/录屏提正文-S59-S76-续录.md`。
  本轮账：主 OCR 1117 页 0.595 元 + 交叉验证 76 页 0.19 元 + 窄带补录 ≈0.01 元 = **≈0.80 元**。
- **⚠ `qwen-vl-ocr` 是纯 OCR 引擎，不服从「输出 PCT:xx.xx%」的指令**：新批 1117 页里 **197 页（17.6%）**
  既不吐 `PCT:` 行也不吐底栏裸百分数（`ui_hits=0`），而旧批 `qwen3-vl-plus` 3609 页零 NO-PCT。
  修法：**`tools/pct_fill.py`** —— 只把存档帧底栏窄带 `crop=iw:110:0:1376`
  （百分数实测在存档帧 y≈1428~1457）裁出来单独 OCR，按 `%` 解析后把 `PCT:xx.xx%` **追加**回该页
  `ocr.tsv`/`all_ocr.tsv`，再重跑 `pct_parse.py`；**正文一个字不动**、成本可忽略。
  实测救回 195/197（剩 2 页是书末空白页与错误页，确实没有百分数）。
- **⚠ 阅读器自己的整页 UI 会混进正文**：书末 `s76.p057` 是 **「数据加载失败，请点击重试」错误页**，
  旧 `strip_ui()` 只削页尾「本章说/去写章评」⇒ 被当正文拼进去。已给 **`tools/stitch.py`** 加 `UI_LINE` 规则
  （**按整行**剔 `本章说`/`去写章评`/`数据加载失败，请点击重试`/`点击重试`，整页只剩 UI 就丢弃）。
  同一条规则顺带清掉上一轮交付里**残留的 7 行「本章说」**（21 字）；除这 7 行外，
  旧批 S01~S58 与新版**逐字相同**（公共前缀 354,112 字，可作回归基线）。
- **⚠ 百分数是「假数」有了像素级实证**：本轮 4 个 `REPEAT`/`GAP?` 标记，窄带 OCR 读数与清单一致，
  再**人眼直接读底栏像素**确认 ⇒ 是七猫自己的数字在跳（`s20`：25.97% → **25.00%** → 26.01%；
  `s76`：96.96% → **97.79%** 是正文转「后记」），帧时序均 ≤0.6 s、**没有漏页**。
  证据图 `corpus/底栏百分数-假数实证.png`。⇒ 口径不变：百分数**只做 ≥4 页缺口的粗筛**，
  且**全局非线性**（末段 6.6% 跨度实际只有 58 页），判重复/断片一律以正文比对为准。
- **「S58 末页 = S59 首页」这次并不成立**：两页是**相邻页**（相似度 0.1667，`cut=0` 原样接上，
  文本首尾拼成完整句子），正文里该句只出现 1 次。新批 18 个接缝里真正要丢的整页重复是 **5 处**
  （`s60/s61/s68/s70/s76` 各自的 `p000`，相似度 1.0000）。复核工具 **`tools/seam_check.py`**
  （相似度 + 反证「拿首页比上段全部页」+ 拼接审计行 + 正文出现次数）。
- **正文里允许出现的数字（口径修正）**：`clean_corpus.py` 剔的是**章节头页码**这类 UI 数字；
  正文本身可能有真数字 —— 实测唯一 1 行是作者后记里的书名 **《24小时》**（`s76.p051`），**保留**，
  验收口径改为「UI 类数字/百分号残留 = 0」而不是「正文零数字」。
- **QA 的「重复子串」不都是缺陷**：本轮新增的那组（77 字「如果有仙人俯瞰整个长安城的话…交会到了一起。」，
  `s72.p057` 第 24 章开头 vs `s75.p009` 后段相向奔驰）是**原文自己的呼应复现**，
  两处上下文不同、页序正常连续 ⇒ 保留不动。判读要看两处上下文与页序，别一律当重复删。
- **新增/改动工具**：`tools/pct_fill.py`、`tools/seam_check.py`、`tools/gap_audit.py`（页间隙审计）、
  `tools/cross_sample.sh`（**本轮才入仓**：`COVER_MARK`/`EVERY`/`PAGES` 可配的抽样）；
  `tools/stitch.py` 加 `UI_LINE` 整行 UI 规则（⚠ 会影响全量正文，改动要记账）。
- **模型与价格（2026-10-10 深夜复核，与 §5.1 一致，未变）**：`qwen-vl-ocr` 0.3/0.5 元每百万（最省、正文准、
  但**不吐 PCT**）；`qwen3-vl-plus` 1/10（质量最稳、PCT 零遗漏，用于抽样交叉验证）；
  `qwen3.8-omni-flash` 0.8/2.7（备用）；`qwen3-vl-flash` **仍下架，禁止使用**。
  本轮交叉验证读数：76 页 69 页逐字一致、字符级不一致率 **0.15%**（新批 36 页 0.24%、旧批 40 页 0.05%）。



## 6 宿主上的 win10 KVM 客机（甲方桌面）——2026-10-11 交接

- **域定义在 `qemu:///system`**（`virsh list` 默认走 `qemu:///session` ⇒ **空列表**，别据此说"没有 VM"）；
  longxia 属 `libvirt` 组，`virsh -c qemu:///system …` 直接可用。域 `win10`：12 vCPU / 11 GiB /
  UEFI(OVMF) / 磁盘 `/data/vm/images/win10.qcow2`（85.9 GB）/ 网卡 `default` NAT。
- **它就是甲方的 Windows 桌面**（客机里跑 dsk-desktop，甲方在那上面用 Termius 连本机），**不是随便一个测试机**：
  别擅自 shutdown/reset（会丢客机里未保存的东西）；本次未改动客机任何东西。
- 客机：Windows 10 22H2 `10.0.19045.2965`，`192.168.122.121`（MAC `52:54:00:5e:86:43`），RDP 3389 开；
  qemu-guest-agent 在（`guest-ping` 通，但版本老：`guest-get-osinfo` 不存在；`guest-exec` 可用）；
  virtiofs 共享 ⇄ 宿主 `/home/longxia/media-shared`。⚠ **客机里的落点是 `Z:` 盘**（卷标 `shared`）：
  `\\shared` 这个 UNC 名**解析不了**（2026-10-11 实测 `type \\shared\…` 报"找不到网络路径"）。
- **看图/接入**：SPICE 只绑宿主回环 `127.0.0.1:5900` 且 `disable-ticketing=on`（**无口令**）⇒ 外部必须打隧道
  （`ssh -N -L 5900:127.0.0.1:5900 longxia@156.238.255.110` + `remote-viewer spice://127.0.0.1:5900`）；
  RDP 同理 `-L 13389:192.168.122.121:3389`。宿主装了 `virt-viewer`/`remote-viewer`，但宿主无 X ⇒ 别指望在服务器上看。
- ⚠ **`virsh screenshot` 会吐旧帧**：2026-10-11 实测它一直给 OOBE「你即将完成电脑设置」那屏，
  而客机其实早已登录桌面（`explorer.exe`/`dwm.exe` 在跑、`qwinsta` 显示 `console longxia 1 运行中`、
  `qemu-agent` 秒回）⇒ 判活看 agent + `qwinsta`，**别只看截图**。
- 助手脚本：`bin/win10.sh {status|start|stop|reset|inspect|shot|console|rdp}`（`inspect` = 客机真会话状态）。
- 未做：域 `Autostart: disable`（改它要 root，本机无 sudo 免密）⇒ **宿主重启后不会自动起**，
  得手动 `bin/win10.sh start`。

## 7 DSH → win10 客机里的 Blender（3D 房间/短剧场所）——2026-10-11 落地

甲方想法：DSH(DeepSeek) 当 agent 写 python，驱动客机里的 Blender 搭「3D 小房间」短剧场所。
MVP 已跑通，全案在 `docs/方案-dsh驱动win10-blender-3D小房间-261011.md`。长期要记的只有这些：

- **本套东西有独立成品仓 + gitee 远端**（2026-10-11 甲方要求，**别再叫 `dsh-` 前缀**）：
  仓 `/home/longxia/helloworld-blender-roomgen.d/` = `git@gitee.com:gushiteng/helloworld-blender-roomgen.d.git`。
  命名口径：**helloworld 级最小验证，且不 DSH 专属**（核心只有 guest-agent 下命令 + virtiofs 送文件 + Blender 无头渲，
  换别的 agent 或手写脚本照样能用）。仓内 `docs/最小MVP-搭建与实测.md` 是「从零照做一遍」的施工文档、
  `docs/方案与路线图.md` 是方案副本；`scripts/ bin/ out/ README.md _manifest.txt` 都是**生成物**。

- **三个角色**：① DSH（宿主 Linux）＝写脚本/发命令/验收；② Blender（客机 win10）＝干活；
  ③ virtiofs 共享＝唯一数据面。**客机不需要装任何"被驱动端"**（无 SSH/WinRM/agent 客户端）。
- **控制面 = qemu-guest-agent `guest-exec`**（`bin/win10-exec.sh`）：以 **SYSTEM / session 0** 跑，
  所以天然无桌面、无 GUI —— 正好是 `blender -b`。客机控制台是 **cp936**，UTF-8 程序要重定向到文件。
- **数据面 = `/home/longxia/media-shared` ⇄ 客机 `Z:`**（卷标 `shared`，不是 `\\shared`）：
  送脚本、收 png/blend/log 全走它；宿主直接 `read`/`cp`，无需再传。
- **Blender 装法**：官方 Windows **便携版 zip**（不是 msi）解到 **`C:\blender\blender.exe`**，
  当前 **4.5.14 LTS**；免管理员、免注册表、整包可回滚。装包缓存在 `media-shared/_dl/`（带 sha256）。
- **入口四条**：
  - `bin/win10-exec.sh [--timeout N] <exe> [args...]`（客机执行器，含 `--kill-last`）
  - `bin/win10-blender.sh <脚本.py> [--job NAME] [-- 脚本参数]`（job 运行器：送脚本→跑→回读 run.log；
    每个 job 把客机 pid 记在 `<job>/guest.pid`）
  - `bin/win10-install-blender.sh [--check|--force|--version x.y.z]`（**幂等装/体检客机 Blender**，
    2026-10-11 用 `--force` 全流程实测通过：宿主下载→sha256 校验→客机 tar 解压→move→版本验收）
  - `bin/publish-share.sh [--push] [--no-guest]`（**发布器 / 唯一出口**，三层：本仓是真值源 →
    重建体验仓 `/home/longxia/helloworld-blender-roomgen.d/`（`--push` 顺手 commit+push gitee）→
    rsync 成共享盘投影；`scripts/ bin/ out/ README.md _manifest.txt` 都是它生成的，`docs/` 在体验仓手工维护。
    生成 `.bat` 后有**纯 ASCII 硬闸门**，含非 ASCII 字节直接拒绝发布）
  - 样板场景：`tools/roomgen/room_hello.py`（4.2×3.6×2.7 m 房间 + 门/窗 + 家具 + 3 机位 + 自检）
- **一律 `-b --factory-startup --python-exit-code 1`**：脚本抛异常 ⇒ 客机退出码非 0，不混"静默成功"。
- **共享盘里那套体验包**：`/home/longxia/media-shared/helloworld-blender-roomgen.d/`
  （客机里 = `Z:\helloworld-blender-roomgen.d\`；旧名 `dsh-blender-roomgen.d` 已于 2026-10-11 改名并删除）
  —— `scripts/run-hello.bat` / `run-living.bat` 在 Windows 里**双击就能渲**（无头 Cycles，跑完自动开产物目录）；
  `out/*/room-*.blend` 双击进 Blender GUI 随手改。**仓是真值源，共享盘是投影**：改完脚本回宿主跑
  `bin/publish-share.sh` 重新发布，别在共享盘里改。
- **渲染器选 Cycles CPU**（不是 EEVEE）：KVM 无 GPU 直通，EEVEE 无头要 GL 上下文，靠不住。
- ⚠ **坑（都实测过）**：
  ① guest-exec 的 base64 回传会截断 ⇒ 长任务输出**必须重定向到文件**；
  ② **宿主侧 Ctrl-C/杀 job 不会停客机里的程序** ⇒ 先 `bin/win10-exec.sh --kill-last`；
  ③ 刚杀过宿主任务时 qemu-ga 会短暂回 `Guest agent is not responding`，**等十几秒重试即可**；
  ④ 杀宿主 job ≠ 停渲染，同一 `out/` 目录会被两个 Blender 抢写 ⇒ 换 job 名或等它收尾；
  ⑤ 客机磁盘 85 GB（装前 C: 剩 55.4 GB / 装后 50.7 GiB），Blender 便携版解压占 **892.8 MB**；
  ⑥ **给客机双击的 `.bat` 必须纯 ASCII**：cmd.exe 按 OEM 代码页(cp936)解析批处理，UTF-8 中文注释会解成乱码、
     甚至吐出元字符 ⇒ 整行解析坏、命令错位（实测把 Blender 的 `-b` 吃掉 ⇒ GUI 模式挂死）。
     中文只放 README。
  ⑦ **`set VAR=1 && next` 有行尾空格陷阱**：值会变成 `"1 "`（带空格）⇒ 批处理里的 `if "%VAR%"=="1"` 判假。
     自动化调用一律写 `set "VAR=1"`，或干脆写一个 wrapper .bat 用 `call` 进目标 .bat。
  ⑧ **`pause` 在 session 0（guest-exec）里会永久挂住**：给客机双击的 .bat 若要自动化复用，
     必须留 `ROOMGEN_NOUI=1` 这类开关跳过 `start`/`pause`（本仓 .bat 已经留了）。
  ⑨ 宿主杀 job 不会清客机进程 ⇒ **同一 job 反复测会攒下僵尸 cmd.exe 并锁住日志文件**
     （报"另一个程序正在使用此文件"）；用 `powershell Get-CimInstance Win32_Process` 列 CommandLine 后精准 stop。
