# novels/ —— 小说正文落点

**一部小说 = 这里的一个目录 = 一个独立 git 仓。** 本包装仓不吞正文，只钉「哪几部小说、什么状态」。

## 从零开始（甲方 2026-10-08 口径）

- 旧项目《极简修仙传》**是失败的案例、将被遗弃** ⇒ **不接进来、不引用、不搬动、不修改**。
  它的目录仍留在 `/home/longxia/shortstory-workshop.d/shortstory.jijian-xiuxian-zhuan.shortstory.d`，由甲方另行处置。
- 本目录里**没有**任何指向旧项目的软链或子模块；`bin/link-novels.sh` 已删除（它当初就是把旧项目软链进来的）。

## 新开一部小说

```bash
cd ~/vpsdsh-shortstory-workspace-wrapper.d/novels
mkdir my-novel && cd my-novel && git init -b master
mkdir -p bible plan manuscript continuity state qc tasks
# 骨架约定见本仓 AGENTS.md §2；qc/run.sh 末行必须是 `__SELFTEST__ <断言> <失败>`，退出码即判定
git remote add origin git@gitee.com:gushiteng/my-novel.d.git
```

新小说的目录**默认不入本包装仓**（`.gitignore` 里 `novels/*` 已被排除），
它们各自是独立仓；本包装仓只保留这份说明与 `.gitkeep`。
