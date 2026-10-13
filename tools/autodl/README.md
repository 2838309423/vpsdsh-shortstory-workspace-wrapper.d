# AutoDL 渲染实例：环境包（一次性准备，之后每支片子只换 .blend）

这是一套**与具体影片无关**的环境准备件：跑一遍就把 AutoDL 的系统盘变成"Blender 4.5.14 + ffmpeg + 自检"
的可用渲染机；随后在控制台「保存镜像」，以后每个新实例都可以跳过这一整套。

| 文件 | 在哪跑 | 干什么 |
|---|---|---|
| `bootstrap.sh` | 实例内（root） | 装系统库（apt）→ 取/校验 Blender 4.5.14 tar.xz（sha256 内嵌）→ 解到 `$PREFIX` → 建 `blender` 软链 → 版本断言。幂等，`--check` 只体检 |
| `selftest.sh` | 实例内 | 8 类断言（PATH/版本/缺库/内嵌 python/ffmpeg/数据盘挂载/GPU 信息/**真跑一次 Cycles CPU 出图**），末行 `__SELFTEST__ <总数> <失败数>` |
| `smoke_cpu.py` | 由 selftest 调用 | 无 GPU 的 Cycles 冒烟（默认启动场景，320×180/8spp） |
| `render_job.py` | 由 run-job 调用 | 正式渲染：显式 `--device CUDA\|OPTIX\|CPU`，设分辨率/采样/降噪/帧范围，写 `render_report.json`，末行 `__RENDER__ ...` |
| `run-job.sh` | 实例内 | 一站渲染：调 Blender（帧序列写**数据盘**）→ 可选 ffmpeg 封 mp4 → 可选 `/usr/bin/shutdown` 自动关机 |
| `push-payload.sh` | **usavps 上** | 一条命令：推环境包（+ 可选 Blender tar.xz、可选 job 目录）→ 实例内引导 → 自检 |

关键口径（别踩）：

- **帧序列一律写 `/root/autodl-tmp/...`**（数据盘，默认免费 50 GB，且**不进镜像**）。
  写系统盘（30 GB）会把几千张 PNG 打进你要保存的镜像，白占镜像免费额度。
- **`--device CUDA` 找不到卡就退出码 4**，绝不悄悄退回 CPU 白付 GPU 钱。
- `--shutdown` 收尾 ⇒ 渲完自动关机，按秒计费停止。
- 无卡模式（0.5 核 / 2 GB / ¥0.1 每小时）里 `nvidia-smi` 报错是**正常的**，selftest 不把它算失败。

完整施工手册：`D:\dsk-workspace.d\vibe-server.d\` 下的《施工手册-AutoDL系统盘准备与镜像固化-*.md`
