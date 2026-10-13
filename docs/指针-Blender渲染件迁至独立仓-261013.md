# 指针：Blender 渲染件已迁到独立仓（2026-10-13）

- 新仓：`git@gitee.com:gushiteng/blender-usavps-prepare-and-gpuserver-render.d.git`（私有）
- 本机路径：`/home/longxia/blender-usavps-prepare-and-gpuserver-render.d`
- 从本仓**迁走**的东西（本仓已删，别在这里找）：
  - `tools/autodl/*`（环境件 7 件）
  - `docs/施工手册-AutoDL系统盘准备与镜像固化-261013.md`
  - `docs/接续提示词-AutoDL系统盘准备-261013.md`
  - `docs/assets/autodl/usavps-selftest-261013.log`
- 迁走原因：DSH 工作区仓不该被渲染件与产物撑肥；换机器时 `git clone` 一个仓就能拿走整套渲染件。
- **本仓仍是 DSH 文本服务的工作区**（cwd 不变），只是渲染件改用新仓的绝对路径。
- 接续注入行（旧的已失效）：

```
读 /home/longxia/blender-usavps-prepare-and-gpuserver-render.d/docs/接续提示词-AutoDL系统盘准备-261013.md 按它干活。
```
