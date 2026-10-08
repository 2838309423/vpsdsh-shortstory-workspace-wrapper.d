# novels/ —— 小说正文落点

**一部小说 = 这里的一个目录 = 一个独立 git 仓。** 本包装仓不吞正文，只钉「哪几部小说、什么状态」。

## 已接进来的小说

| slug | 目录 | 远端 |
|---|---|---|
| `jijian-xiuxian-zhuan` | 《极简修仙传》业务仓（claude 团队线的既有仓，**软链**进来，不复制） | `git@gitee.com:gushiteng/shortstory.jijian-xiuxian-zhuan.shortstory.d.git` |

```bash
bash bin/link-novels.sh        # 扫描 ~/shortstory-workshop.d/*.shortstory.d 建软链（幂等）
```

## 新开一部小说

```bash
cd ~/vpsdsh-shortstory-workspace-wrapper.d/novels
mkdir my-novel && cd my-novel && git init
mkdir -p bible plan manuscript continuity state qc tasks
# 骨架约定见本仓 AGENTS.md §2；qc/run.sh 末行必须是 `__SELFTEST__ <断言> <失败>`，退出码即判定
git remote add origin git@gitee.com:gushiteng/my-novel.d.git
```

新小说的目录**默认不入本包装仓**（`.gitignore` 里 `novels/*` 已被排除），
它们各自是独立仓；本包装仓只保留这份说明与 `.gitkeep`。
