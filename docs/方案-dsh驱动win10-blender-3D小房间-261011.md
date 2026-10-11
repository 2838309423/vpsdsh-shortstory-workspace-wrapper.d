# 方案：DSH + DeepSeek 当 agent，驱动 usavps win10 里的 Blender 搭「3D 小房间短剧场所」

- 日期：2026-10-11　｜　状态：**helloworld 级 MVP 已跑通**（可复制、可重跑、带自检）
- 作者：DSH 会话（本机 usavps），甲方：人类用户
- 相关长期记忆：本仓 `AGENTS.md` §6（win10 客机）、§7（本条）

---

## 0 一句话结论

**DSH（宿主 Linux 上的 DeepSeek agent）写 bpy 脚本 → 经 qemu-guest-agent 把命令打进 win10 客机 →
客机里的 `C:\blender\blender.exe` 无头渲染 → 图片/blend/日志经 virtiofs 共享回到宿主。**
客机**没有**为此装任何"被驱动端"（无 SSH、无 WinRM、无 pywinauto、无桌面自动化），
新增的安装物只有 **Blender 便携版**一个目录。

先看成品（3 张 960×540，Cycles CPU，12 vCPU 上约 1 分钟/张）：

| 图 | 内容 |
|---|---|
| [01-establishing.png](/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/docs/assets/roomgen-hello/01-establishing.png) | 全景：左前角 19 mm，一次看全 床 / 衣柜 / 书桌 / 窗 |
| [02-medium.png](/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/docs/assets/roomgen-hello/02-medium.png) | 中景：床边 35 mm（"床上戏"常用机位） |
| [03-closeup.png](/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/docs/assets/roomgen-hello/03-closeup.png) | 特写：书桌/笔记本 45 mm（"打字戏、伏案戏"） |

房间规格（脚本参数可改）：4.2 × 3.6 × 2.7 m，73 个网格物件 / 6 盏灯 / 3 个机位；
产物目录（客机写、宿主读）：`/home/longxia/media-shared/blender-jobs/hello-01/out/`。

---

## 1 想法被拆成哪几件事（架构）

```
┌─────────────────────────── 宿主 usavps (Ubuntu 22.04) ───────────────────────────┐
│                                                                                  │
│   你（浏览器 / DSH GUI）                                                          │
│        │ 自然语言                                                                 │
│        ▼                                                                         │
│   DSH agent（DeepSeek-V4.1-Flash）                                               │
│        │ ① 写 python（bpy 脚本）       ② 跑 bash（管道脚本）      ④ 读图/验收      │
│        ▼                                    ▼                        ▲           │
│   tools/roomgen/*.py                bin/win10-blender.sh             │           │
│                                            │ ③ 送脚本 + 下命令        │           │
│                                            ▼                        │           │
│                             ┌──────── 控制面 ────────┐    ┌─── 数据面 ───┐        │
│                             │ qemu-guest-agent      │    │ virtiofs     │        │
│                             │  guest-exec (SYSTEM)  │    │ /home/longxia│        │
│                             └───────────┬───────────┘    │ /media-shared│        │
└─────────────────────────────────────────┼────────────────┼─────────────┼─────────┘
                                          ▼                ▼             │
┌────────────────────────── win10 客机（甲方桌面，KVM）────────────────────┼─────────┐
│  cmd.exe /c Z:\blender-jobs\<job>\run.bat                              │          │
│        └─► C:\blender\blender.exe -b --factory-startup                 │          │
│              --python-exit-code 1 --python Z:\...\room_hello.py -- ...  │          │
│                    │ 读脚本/写图                                        │          │
│                    ▼                                                    ▼          │
│              Z: (= 宿主 media-shared)  ── out/*.png  *.blend  logs/run.log ────────┘
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **DSH 只做三件事**：写脚本、发命令、验收（读回日志/图片）。
- **客机只做一件事**：跑 Blender。它不需要知道 DSH 的存在。
- **控制面与数据面分开**：命令走 guest-agent（小、可靠、无认证负担），文件走 virtiofs（大、直接、宿主可读）。

---

## 2 MVP 现在有什么（四件套，可直接用）

| 文件（绝对路径） | 作用 | 用法 |
|---|---|---|
| `/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/bin/win10-exec.sh` | **客机执行器**：把一条命令丢进 win10 并等它结束，回 stdout/stderr/退出码 | `bin/win10-exec.sh cmd.exe /c ver`；`--timeout 1800`；`--kill-last` 停上一次的任务 |
| `.../bin/win10-blender.sh` | **job 运行器**：送 .py 进客机 → 生成 run.bat → 无头跑 Blender → 回读 run.log | `bin/win10-blender.sh <脚本.py> [--job 名] [-- 脚本参数]` |
| `.../tools/roomgen/room_hello.py` | **样板场景**：一间带门/窗/家具的卧室 + 3 机位 + 出图 + 自检 | 由上面那条命令驱动，参数 `--w --d --h --samples --res --shots --outdir` |
| `.../docs/assets/roomgen-hello/` | 首轮产物留档（3 png + `scene_report.json`） | 直接看 |

客机侧唯一的新增物：**`C:\blender\blender.exe`（Blender 4.5.14 LTS 便携版）**，
装包缓存在宿主 `/home/longxia/media-shared/_dl/`（398,661,046 B，sha256 已留档）。

---

## 3 关键取舍（为什么这么搭，别改的那些）

| 决策点 | 选了 | 为什么 | 代价/边界 |
|---|---|---|---|
| 怎么指挥 win10 | **qemu-guest-agent `guest-exec`** | 客机**零安装**；以 SYSTEM/session 0 跑 ⇒ 天然无桌面无 GUI，正好是 Blender 的 `-b` 模式；host 侧一条 `virsh` 命令搞定 | 输出 base64 回传会截断 ⇒ 长任务必须重定向到文件；没有交互式 stdin；中文控制台是 cp936 |
| 文件怎么过 | **virtiofs 共享**（宿主 `media-shared` ⇄ 客机 `Z:`） | 宿主直接 `read`/`cp` 产物，不用再"下载"；送脚本零成本 | 客机里是 `Z:`，**不是** `\\shared`（UNC 名实测不可用） |
| 渲染器 | **Cycles CPU** | KVM 无 GPU 直通，EEVEE 无头要 GL 上下文，客机拿不到；Cycles CPU 纯算力，12 vCPU 够用 | 960×540/48spp ≈ 1 分钟/张；4K 或动画要另想办法 |
| Blender 怎么装 | **官方 Windows 便携版 zip** 解到 `C:\blender` | 免管理员、免注册表、免安装向导；整包可复制/回滚/多版本并存 | 客机落地 **892.8 MB**（实测）；不会出现在开始菜单（也不需要） |
| 交互方式 | **脚本 + 文件交换**，不做 GUI 自动化 | 可版本化、可复现、可批量化；agent 最擅长写代码而不是点鼠标 | 看不见 Blender 窗口（想看就用 `bin/win10.sh rdp` 隧道接进去） |
| 脚本入口口径 | 一律 `-b --factory-startup --python-exit-code 1` | 出厂配置 ⇒ 渲染结果不受客机里被人改过的偏好设置影响；脚本抛异常 ⇒ 退出码非 0，**不会把"静默失败"当成功** | 需要显式设置的东西（渲染器/色彩管理）都得写在脚本里 |
| 验收方式 | 脚本末行 `__SELFTEST__ <断言数> <失败数>` + 机检图片平均亮度 | 与本工作区既有 QC 口径一致；"图是不是全黑"这种错能自动抓到 | 断言是人写的，覆盖不到审美 |

---

## 4 从零到跑通的实测时间线

| # | 动作 | 命令/落点 | 实测 |
|---|---|---|---|
| 1 | 盘客机 | `bin/win10-exec.sh cmd.exe /c ver` | win10 22H2 19045.2965；**无** Blender；无 python；有 powershell/curl/tar；C: 剩 55.4 GB |
| 2 | 验共享 | 宿主写 `media-shared/x.txt` → 客机 `type Z:\x.txt`；反向同理 | 双向 OK（`\\shared` 报"找不到网络路径"） |
| 3 | 下载 Blender | `download.blender.org/release/Blender4.5/blender-4.5.14-windows-x64.zip` | 398,661,046 B，**~28 s（14 MB/s）**；zip 可读、6312 项 |
| 4 | 客机内解压安装 | `tar -xf Z:\_dl\…zip -C C:\` + `move` → `C:\blender` | **78.8 s**；`blender.exe --version` → `Blender 4.5.14 LTS` |
| 5 | 冒烟（小样） | `bin/win10-blender.sh tools/roomgen/room_hello.py --job smoke -- --samples 8 --res 320x180` | 3 张图 **24 s**（≈2.2 s/张）；`__SELFTEST__ 13 0` |
| 6 | 正式画质 | `… --job hello-01 -- --samples 48 --res 960x540` | 3 张图 **≈3 分钟**（≈1 分钟/张，含降噪）；`__SELFTEST__ 13 0` |
| 7 | 产物 | `media-shared/blender-jobs/hello-01/out/` | 3×PNG（~390 KB）+ `room-hello.blend`（1.5 MB）+ `scene_report.json` |

**agent 闭环（DSH 自己写脚本、自己跑、自己看图改稿）**：见 §5.2 —— 一轮 3.3 分钟出图，`__SELFTEST__ 13 0`。

---

## 5 怎么自己再跑一次

### 5.1 三条命令（宿主上，任何 shell 都行）

```bash
cd /home/longxia/vpsdsh-shortstory-workspace-wrapper.d

# ① 换参数重跑同一间房（改尺寸/采样/分辨率）
bash bin/win10-blender.sh tools/roomgen/room_hello.py --job room-b -- --samples 32 --res 1280x720 --w 5.0 --d 4.0

# ② 在客机里跑任意 Windows 命令（看状态、看进程、看目录）
bash bin/win10-exec.sh cmd.exe /c "dir /b C:\blender & tasklist /fi \"imagename eq blender.exe\""

# ③ 停掉上一次还在客机里跑的 Blender（宿主 Ctrl-C 是停不掉它的！）
bash bin/win10-exec.sh --kill-last
```

产物永远在 `/home/longxia/media-shared/blender-jobs/<job>/{out,logs,script}/`。

### 5.2 让 agent 自己改一版（这就是你要的"DSH+DeepSeek 驱动"）

一次性问答、不开浏览器：

```bash
cd /home/longxia/vpsdsh-shortstory-workspace-wrapper.d
source bin/env.sh
dsh headless "读 tools/roomgen/room_hello.py，复制成 tools/roomgen/room_living.py 改成一间小客厅
（沙发/茶几/落地灯/电视墙/地毯），保留 3 机位和末行 __SELFTEST__ 自检；
用 bash bin/win10-blender.sh tools/roomgen/room_living.py --job agent-demo -- --samples 24 --res 640x360 跑出来，
报错就看 media-shared/blender-jobs/agent-demo/logs/run.log 改到过为止。最后只回 4 行结论。"
```

或者直接在 DSH GUI 里用自然语言说同一句话 —— 效果一样，只是能看着它一步步干。

**本次实测（agent-demo，2026-10-11 13:31→13:35，全程无人干预）**：

- 一轮跑完，**1 turn / 13 step / 17 次工具调用**：`read`×3、`bash`×8、`write`×1、`edit`×3、**`read_image`×3**。
- 它的实际动作链：读样板 → 摸环境 → **写出 496 行 `tools/roomgen/room_living.py`** → 送进客机渲染 →
  **自己把 3 张图看了一遍** → 按看到的问题改 3 处 → 再渲一遍 → 再看一遍 → 验收汇报。
  （能看到"看图 → 改 → 再渲"这一步，说明闭环是**视觉闭环**，不是盲跑。）
- 产物：`tools/roomgen/room_living.py`（496 行，83 个物件 / 5 盏灯）、
  图在 `/home/longxia/media-shared/blender-jobs/agent-demo/out/`（已留档 `docs/assets/roomgen-agent/`）。
- 读数：**`__SELFTEST__ 13 0`**（13 条断言全过）。
- 墙钟 **≈3.3 分钟**（含 2 次客机渲染）；token：input 78,434 / cache-read 1,373,696 / output 54,204（13 次模型调用求和）。

它渲出来的小客厅（agent 自己写的脚本、自己改的）：
[01-establishing.png](/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/docs/assets/roomgen-agent/01-establishing.png) ·
[02-medium.png](/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/docs/assets/roomgen-agent/02-medium.png) ·
[03-closeup.png](/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/docs/assets/roomgen-agent/03-closeup.png)

### 5.3 想看 Blender 的窗口（可选）

客机是甲方桌面，`C:\blender\blender.exe` 双击就能出 GUI。远程看：
`ssh -N -L 5900:127.0.0.1:5900 longxia@156.238.255.110` + `remote-viewer spice://127.0.0.1:5900`（宿主无 X，
得在你自己机器上转发）。**但平时不要开 GUI**：无头跑才是可复现、可并行的那条路。

---

## 6 往「短剧场所」走的路线图（L0 → L4）

| 级别 | 内容 | 关键动作 | 验收口径（机检） |
|---|---|---|---|
| **L0 ✅ 已做** | helloworld：一间房 + 3 机位 + 出图 | 本文四件套 | `__SELFTEST__ n 0` + 图片非全黑 |
| **L1 参数化场景库** | 房间尺寸/风格/道具由 **外部 JSON/YAML** 驱动，一份 `room_hello.py` 生 N 种房 | 把脚本里的常量抽成 spec 文件；加 `--spec x.json` | 同 spec 两次渲染 md5 一致；spec 字段与报告逐项对账 |
| **L2 场次表 = 一份真值三个投影** | 「剧本场次 → 场景+机位+道具状态」，与本工作区 `novels/<slug>/state/epNN.json` 同口径 | 每场一个 `scene.json`；渲染脚本只读它 | `scene.json` = 报告 JSON = 图内可见物件清单（机检逐字段） |
| **L3 镜头运动** | 相机关键帧 → 序列帧 → 宿主 ffmpeg 合成 mp4（ffmpeg 已在本机：`~/toolchain/ffmpeg/...`） | Cycles 逐帧；先 720p/24fps/2~4 s/镜 | 帧数、时长、丢帧、黑帧机检；抽帧回看 |
| **L4 资产库与自动摆放** | 家具/道具模型库 + 材质库 + HDRI；用几何约束自动摆放（贴墙、门要开得开） | 资产走 `media-shared/assets/`；Blender 里 link/append | 无穿模、无悬空、门净宽 ≥0.8 m 之类的几何断言 |
| （更远）| 人物角色、口型、分镜表 | 另立方案 | —— |

**关键判断**：L1、L2 才是这套东西真正值钱的地方 —— **"一份场次表驱动 N 个场景"**。
L0 只是证明管道通；真正用在短剧生产上，必须先有 spec（场次表），再谈渲染。

---

## 7 坑与硬口径（都实测过，写脚本必守）

1. **宿主 Ctrl-C / 杀 job ≠ 停客机里的程序**：guest-exec 是发射后不管。要停就 `bin/win10-exec.sh --kill-last`（`taskkill /T /F`）。
2. **杀掉宿主任务后，qemu-guest-agent 会短暂回 `Guest agent is not responding`**（十几秒）⇒ 重试即可，别以为客机死了。
3. **同一个 `out/` 目录被两个 Blender 抢写**：杀宿主 job 后客机里的渲染仍在写 ⇒ 换 job 名，或等它收尾（看 `logs/run.log` 有没有 `EXITCODE=`）。
4. **guest-exec 的 stdout 会截断**：长任务一律 `> Z:\...\run.log 2>&1`，宿主再从共享读文件。
5. **客机控制台是 cp936**：`bin/win10-exec.sh` 按 GBK 解码；Blender 的 UTF-8 输出走文件通道（`chcp 65001`）。
6. **客机里共享盘是 `Z:`**，`\\shared` 这个 UNC 名解析不了。
7. **EEVEE 别用**：无 GPU 直通 + 无头 ⇒ 要 GL 上下文，靠不住；一律 Cycles CPU（`scene.cycles.device='CPU'`）。
8. **`-noaudio` 之类不重要，`--python-exit-code 1` 很重要**：没有它，脚本抛异常 Blender 也退 0，会把失败当成功。
9. **`.blend1` 是 Blender 的自动备份**（覆盖保存时生成），不是脏数据。
10. **渲染时间对得上账**：像素 × 采样数近似线性。320×180/8spp≈2.2 s → 960×540/48spp≈60 s（实测吻合）。
11. **别把 Blender 装到 `Z:`（virtiofs）上跑**：启动/加载要走 WinFsp，慢且 Multi-Process 行为不稳；装到 `C:\` 最稳。

---

## 8 成本与资源

- **钱**：管道本身 0 元（全在自家 VPS 里），Blender 免费，渲染是本地算力。
  唯一花钱的是 DeepSeek 的 token —— 本次 agent-demo 一轮实测（13 次模型调用求和）：
  **input 78,434 / cache-read 1,373,696 / output 54,204**；其中 cache-read 占大头（同一份上下文反复读，单价最低那档），
  所以"让 agent 自己写脚本+渲图"这种活，量级是**几分钱一轮**（具体以 DeepSeek 当期价目为准）。
  ⇒ 结论：**限制因素不是钱，是渲染时间与审美迭代轮数。**
- **算力**：渲染时客机 12 vCPU 基本吃满；11 GiB 内存里 Cycles 只用了几十 MB（小场景）。
- **磁盘**：宿主 `media-shared/_dl/` 里 398 MB 装包（可删）；客机 `C:\blender` **892.8 MB**（实测，装完 C: 剩 50.7 GiB）；每 job 产物几 MB。
- **时间**：装一次 Blender ≈ 2 分钟（下载+解压）；之后每轮出图 ≈ 3 分钟（960×540×3 张）。

---

## 9 未决事项（要你拍板的）

1. **分辨率与时长**：短剧成片要 1080p/竖屏 9:16 吗？现在 960×540 只是验收用。
   1080p 竖屏 + Cycles 会让单张涨到 5~10 分钟 ⇒ 届时要么降采样、要么上 GPU（需要 PCI 直通/passthrough，改 VM 配置且宿主无 sudo）。
2. **要不要人物角色**：这一版只有"场所"。有角色就要上 rigged 模型（Mixamo/CC0 资产）+ 口型链路，是另一个量级。
3. **资产从哪来**：先手搓几何体（现在这样，零版权风险）？还是买/用 CC0 模型库（Poliigon/BlenderKit/Quixel）？
   涉及"商用短剧"的授权，得你定。
4. **L1 的 spec 长什么样**：我建议 YAML（人读友好）+ 每场一个 JSON 快照（机器对账）。
   要不要直接和《长安十二时辰》那套 `state/epNN.json` 口径对齐？
5. **要不要做成"一句话出一间房"的常驻服务**：即把 prompt → 脚本 → 渲染 → 回图的链条固化成一个命令
   （`bin/roomgen-agent.sh "一句话需求"`），让你在 GUI 里说一句就出一间房。要做我就做。

---

## 附：本次落地涉及的文件（全部绝对路径）

```
/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/
├── bin/win10-exec.sh                      客机执行器（guest-exec 封装，含 --kill-last）
├── bin/win10-blender.sh                   job 运行器（送脚本→无头渲染→回读日志）
├── bin/win10.sh                           客机状态/启停/截图/RDP 隧道（上一轮交接已有）
├── tools/roomgen/room_hello.py            样板场景（4.2×3.6×2.7 m 卧室 + 3 机位 + 自检）
├── docs/方案-dsh驱动win10-blender-3D小房间-261011.md   ← 本文件
├── tools/roomgen/room_living.py           **agent 自己写的**小客厅（496 行，留档证据）
├── docs/assets/roomgen-hello/*.png        首轮产物留档（我手写样板跑的）
├── docs/assets/roomgen-agent/*.png        agent 自己跑出来的（agent-demo）
└── AGENTS.md §7                           长期口径（下次会话自动注入）

宿主共享盘（客机侧 = Z:）：
/home/longxia/media-shared/
├── _dl/blender-4.5.14-windows-x64.zip(+.sha256)   装包缓存（可删）
└── blender-jobs/<job>/{script,run.bat,logs,out}   每个 job 一份
```
