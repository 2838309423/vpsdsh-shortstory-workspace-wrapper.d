# 交接：七猫录屏「小说文本区」裁剪（2026-10-10）

## 0 状态：任务已完成并验收通过

把甲方手机录屏（七猫免费小说，分屏录制）裁成纯小说正文区。

| 项 | 值 |
|---|---|
| 源目录 | `/data/home/shortstory/长安二十四时辰/non-cuttedvideo-from-androidphone.d/` |
| 源文件 | 30 个 `qimao-20261010-073844-sNN.mp4`，1080×2400 竖屏，各约 143 s，**无音轨**（只有 h264 + 一条 codec=unknown 的 data 轨） |
| 输出目录 | `/data/home/shortstory/长安二十四时辰/hasbeen-cut-video-from-androidphone.d/` |
| 输出文件 | 30 个同名 mp4，**980×1408**，x264 crf18 + faststart，共 447 MB |
| 验收 | 30/30 成功、0 失败；分辨率全为 980,1408；时长与源逐条一致（最大差 0.06 s） |

**裁剪矩形 `RECT=980:1408:50:224`**（源 1080×2400 的左上角 x=50, y=224）。

## 1 矩形是怎么定出来的（结论的可信度）

不是靠肉眼估的：对全部 30 条视频按每 3 秒抽帧，共 **1439 帧**，逐帧用 ffmpeg 取原始像素算
「奶油底页面范围 / 正文行范围 / 正文列范围」，再取全量极值。逐帧结果在
`/tmp/vidtool/work/sweep.tsv`（列：`video idx page_y0 page_y1 body_y0 body_y1 x0 x1 darkrows`）。

页面几何（**1439 帧全部一致**）：

| 区域 | 源像素 y | 说明 |
|---|---|---|
| 安卓状态栏 | 0 – 100 | 白底，含两个图标 |
| 奶油阅读页 | **105 – 1715** | 全宽 x 0–1080 |
| └ header（`< 第九章 酉正` + `¥` + `菜单`） | 155 – **199** | 灰褐色，非正文 |
| └ **正文文本** | **250 – 1610** | 行距约 150 px；x 范围 **75 – 1005** |
| └ 时间/百分比浮层（`08:47` `37.43%` + 电池） | **1654 – 1681** | 灰色 UI，非正文 |
| Autox.js 分屏（绿条 + 文件列表） | 1715 – | 另一 App，非小说 |
| 底部导航栏（主页/管理/文档） | 约 2060 – | 非小说 |

由此：
- **top = 224**：header 底 199 之下 25 px，正文顶 250 之上 26 px。
- **bottom = 224+1408 = 1632**：正文最深 1610 之下 22 px，浮层顶 1654 之上 22 px。
- **left = 50 / right = 1030**：正文 75–1005，左右各留 25 px。

三处边界都用抽帧图人工复核过（含「正文最深 1610」的 s16 t=45 与「页面近空」的 s04 t=78 两张极端帧）。

### 一个已知且可接受的现象

翻页动画帧（水平滑动，约 190/1439 帧）里当前页左移、右侧露出下一页边缘，
这类帧会被裁掉一点字。这是过渡帧（不到半秒），无法兼顾；稳态阅读帧不裁字。

## 2 工具与复现

裁剪脚本（已入库并推送，`dd57c6e`）：

```
/home/longxia/vpsdsh-shortstory-workspace-wrapper.d/bin/crop-android-novelvideo.sh
```

两种模式：

```bash
# 取帧 + 元数据（人工定矩形用）
FFMPEG=... FFPROBE=... WORK_DIR=/tmp/vidtool/work bin/crop-android-novelvideo.sh probe

# 按矩形批量裁剪（JOBS 并行，默认 4）
RECT=980:1408:50:224 JOBS=6 bin/crop-android-novelvideo.sh crop
```

注意：脚本**必须以 `shortstory` 身份跑**（源文件 `rw-rw---- shortstory:shortstory`，longxia 读不到），
且 `FFMPEG`/`FFPROBE`/`WORK_DIR` 要显式指到 shortstory 能读的位置。

ffmpeg：系统**没有** ffmpeg，是本次下的静态版
`/home/longxia/toolchain/ffmpeg/ffmpeg-7.0.2-amd64-static/{ffmpeg,ffprobe}`（7.0.2）。

## 3 环境事实（新会话必读）

- **登录 shortstory**：私钥 `/home/longxia/.ssh/shortstory_ed25519`（600，甲方 2026-10-10 提供）
  ⇒ `ssh -i /home/longxia/.ssh/shortstory_ed25519 shortstory@127.0.0.1`。
  `/data/home/shortstory` 是 0750 `shortstory:shortstory`，**longxia 无任何读权限**，sudo 需密码
  （NOPASSWD 只有 `systemctl {status,start,stop,restart} longxia` 和 `openclaw`）。
- **共享工具目录 `/tmp/vidtool/`**（263 MB，tmp 易失）：
  `bin/{ffmpeg,ffprobe}`（copy 出来并 `a+rX` 给 shortstory 用）、`scripts/`、`work/`（777）、
  分析脚本 `analyze*.py`、逐帧数据 `work/sweep.tsv`、90 张抽帧 PNG、裁剪日志 `work/crop.log`。
  **丢了就照第 2 节重建**（ffmpeg 静态版在 longxia 家目录里还在）。
- 本次对甲方数据**只做了新增**：新建了输出目录，未改动任何源文件、未改任何权限/ACL。

## 4 遗留事项（按需）

1. `/tmp/vidtool` 263 MB 可清（`rm -rf /tmp/vidtool`），清掉前先把 `sweep.tsv` 留档（若要留证据）。
2. **私钥处置**：`/home/longxia/.ssh/shortstory_ed25519` 是长期可写凭证，甲方可决定保留或删除。
3. 可考虑把「RECT 与页面几何」写进工作区 `AGENTS.md` 长期记忆（本次未写）。
4. 下游用途（OCR 取正文 / 生成字幕 / 喂状态机）未做，甲方未提。

## 5 复现命令（从零重来）

```bash
# 1) 装 ffmpeg（若 /tmp/vidtool 已丢）
curl -sSL -o /tmp/ff.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
mkdir -p /home/longxia/toolchain/ffmpeg && tar xf /tmp/ff.tar.xz -C /home/longxia/toolchain/ffmpeg

# 2) 铺共享工具
D=/tmp/vidtool; mkdir -p $D/{bin,work,scripts}; chmod 777 $D/work
cp /home/longxia/toolchain/ffmpeg/ffmpeg-7.0.2-amd64-static/{ffmpeg,ffprobe} $D/bin/
cp /home/longxia/vpsdsh-shortstory-workspace-wrapper.d/bin/crop-android-novelvideo.sh $D/scripts/
chmod -R a+rX $D

# 3) 以 shortstory 跑裁剪
ssh -i /home/longxia/.ssh/shortstory_ed25519 shortstory@127.0.0.1 \
  'env FFMPEG=/tmp/vidtool/bin/ffmpeg FFPROBE=/tmp/vidtool/bin/ffprobe JOBS=6 \
       RECT=980:1408:50:224 WORK_DIR=/tmp/vidtool/work \
       /tmp/vidtool/scripts/crop-android-novelvideo.sh crop'
```
