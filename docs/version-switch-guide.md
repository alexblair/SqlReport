# V1 ↔ V2 版本切换指南

> 适用仓库：<https://github.com/alexblair/SqlReport>
> 本文所有分支、tag、提交号均由 `git ls-remote` / GitHub API 实测核对，见文末「证据」一节。

---

## 0. 一句话结论

- **`V2` 是 GitHub 默认分支**（持续更新）：不带参数的 `git clone` 拿到的就是 V2。
- **`V1` 是冻结分支**（提交 `9a975b9`）：已加 GitHub 仓库规则 `V1-freeze`，**任何人（含管理员）都无法再向 V1 推送**，实测推送被拒。
- 两条线共享同一段历史：**V2 是 V1 的直接后代**（初始增量 45 个提交 / 289 个文件，本文落笔时）。
- **切换版本 = 在同一次 clone 里 `git checkout V1` / `git checkout V2`**。你的数据文件（`config.db`、`audit.db`、`app_config.json`、`venv/`、`run-logs/`）都不在 git 管理范围内，切分支不会动它们。

---

## 1. 版本线总览

| 版本线 | 分支 | 固定标签 | 当前提交 | 状态 | 建议谁用 |
|--------|------|----------|----------|------|----------|
| **V1** | `V1` | `v1-final` | `9a975b9` | **冻结**：规则保护，禁更新/禁删除/禁强推；不再有任何修复 | 想停在旧行为、不打算跟进新功能的部署 |
| **V2** | `V2`（默认分支） | `v2.0.0`（含本指南） | 分支头（持续前进） | **活跃主干**：以后所有提交、修复、发版都进 V2 | 新装用户、想拿新功能与新修复的部署 |

补充说明：

- 旧名 `main` 已随 V1 改名而终止。**GitHub 的分支改名重定向对网页/API 生效，但对 `git` 协议的 refspec 不生效**——老 clone 里的 `origin/main` 不会再收到更新（详见 §5）。
- `v1-final`、`v2.0.0` 都是**附注标签（annotated tag）**，指向固定提交；分支头会随开发前进，tag 永不移动。要「精确复现某一版」就用 tag。

### 1.1 怎么一眼确认自己在哪一版（指纹）

| 判定命令 | V1 | V2 |
|----------|----|----|
| `git rev-parse --abbrev-ref HEAD` | `V1` | `V2` |
| `git describe --tags` | `v1-final` | `v2.0.0` |
| `git rev-parse HEAD` | `9a975b9…`（冻结不变） | 不固定（用 tag / 分支判定） |
| `ls docs scripts test_env.sh` | 三项都不存在 | 三项都存在 |

> 第 4 条最直观：V1 是「只有 `server.py` 等初始文件」的旧树，V2 多了 `docs/`（文档与知识库）、`scripts/`（性能与运维脚本）、`test_env.sh`（本地 8099 测试环境）。

---

## 2. 只取某一版（四种取法）

四种取法的后续安装步骤完全相同：`./install.sh && source venv/bin/activate && python server.py`。

### 2.1 只取 V2（最新版，推荐新用户）

```bash
git clone https://github.com/alexblair/SqlReport.git
cd SqlReport
./install.sh
source venv/bin/activate
python server.py
```

不带 `-b` 时拿到的是 **默认分支 V2**。

### 2.2 只取 V1（冻结版）

```bash
git clone -b V1 https://github.com/alexblair/SqlReport.git SqlReport-v1
cd SqlReport-v1
./install.sh && source venv/bin/activate && python server.py
```

建议把目录命名为 `SqlReport-v1`，与 V2 部署区分开（§3.2 的并存方案就依赖这个约定）。

### 2.3 精确固定到某个版本（tag：永不受后续提交影响）

```bash
# V1 的最终版
git clone -b v1-final --depth 1 https://github.com/alexblair/SqlReport.git SqlReport-v1

# V2 的首个正式版（V2 继续提交后，仍有更新的 tag，如 v2.1.0）
git clone -b v2.0.0 --depth 1 https://github.com/alexblair/SqlReport.git SqlReport-v2
```

`--depth 1` 只拉该版本的单层历史，最快；需要完整历史/切换分支时去掉它。

### 2.4 不装 git 也能拿（压缩包）

```bash
curl -LO https://github.com/alexblair/SqlReport/archive/refs/tags/v1-final.tar.gz
curl -LO https://github.com/alexblair/SqlReport/archive/refs/heads/V2.tar.gz
```

浏览器直接打开同样地址即可下载。注意：压缩包方式**没有 git 元数据，之后无法用 `git pull` 更新**，也不能切版本——只适合一次性取用。

---

## 3. V1 → V2 升级

### 3.0 前置：记录现状 + 备份数据

```bash
cd SqlReport
git status --short                 # 有未提交改动先 git stash 或提交，否则切换会被拒
git rev-parse HEAD                 # 记下当前提交号，便于回退定位
cp config.db          config.db.bak-$(date +%F)          2>/dev/null || true
cp audit.db           audit.db.bak-$(date +%F)           2>/dev/null || true
cp app_config.json    app_config.json.bak-$(date +%F)    2>/dev/null || true
```

### 3.1 方案 A：在同一目录里切分支（最快，适合单实例）

```bash
cd SqlReport
git fetch origin --tags
git checkout V2
./install.sh                       # 保险起见跑一次；实测 V1→V2 的 requirements.txt 未变
source venv/bin/activate
python server.py                   # 或按 §3.4 重启服务
```

校验：

```bash
git rev-parse --abbrev-ref HEAD    # 期望输出 V2
git describe --tags                # 期望输出 v2.0.0
ls docs scripts test_env.sh        # 三项都应存在
```

回退：`git checkout V1`（数据备份见 §4.1）。

### 3.2 方案 B：两个目录并存（推荐生产环境 / 需要随时回滚）

```bash
git clone -b V1 https://github.com/alexblair/SqlReport.git SqlReport-v1
git clone -b V2 https://github.com/alexblair/SqlReport.git SqlReport-v2
```

两个目录各自 `./install.sh`，各自持有 `config.db` / `app_config.json` / `venv/`，**互不干扰**。

- 升级 = 直接用 `SqlReport-v2` 目录启动服务；
- 回滚 = 把服务切回 `SqlReport-v1` 目录重启（或让两个实例跑不同端口），**完全不用碰 git**；
- 代价：多一份磁盘占用（V2 工作区含 `docs/`，约数十 MB）。

### 3.3 方案 C：`git worktree`（一套 `.git`、两个工作区，省磁盘）

```bash
git clone -b V2 https://github.com/alexblair/SqlReport.git SqlReport
cd SqlReport
git worktree add ../SqlReport-v1 V1
```

- 两个工作区共享同一个 `.git` 对象库，磁盘占用比方案 B 小；
- 工作区文件彼此独立，`config.db` / `app_config.json` 等忽略文件**每个 worktree 各一份**；
- 方案 A 的「同一目录 `git checkout` 切换」在 worktree 里依然可用；
- 收尾：确认不再需要时 `git worktree remove ../SqlReport-v1`。

### 3.4 切换后必做清单

1. `source venv/bin/activate`——`venv/` 不在 git 里，切分支不会消失；若目录被删过就重跑 `./install.sh`。
2. 重启服务（三选一）：
   - 前台：`python server.py`
   - 本地测试环境：`./test_env.sh restart`
   - systemd：`sudo systemctl restart web-report`（首次部署用 `sudo bash manage_service.sh install`）
3. 强制刷新浏览器（Ctrl/Cmd + Shift + R）：V2 改了 UI 资源，且启动时会重建 `static/vendor/self@<hash>/` 外链目录。

---

## 4. V2 → V1 回退

### 4.1 回退前必须做的数据备份

```bash
cd SqlReport
cp config.db       config.db.pre-v1-$(date +%F)
cp audit.db        audit.db.pre-v1-$(date +%F)
cp app_config.json app_config.json.pre-v1-$(date +%F)
```

为什么必须备份：**本次 V1→V2 实测未改动 `config_db.py`（diff 中没有任何 `CREATE TABLE` / `ALTER TABLE` / `ADD COLUMN`），因此两版共用同一套配置库结构，可以直接往返切换**。但 V2 之后如果升级了表结构（新增字段/表），带着 V2 的 `config.db` 回退到 V1 可能出现「配置读不出/字段对不上」。届时的正确做法是：

1. 回退代码到 V1；
2. **同时**恢复与 V1 匹配的 `config.db` 备份（即升级当天的 `.bak`），
3. 或走 `config_db.py` 中对应的迁移路径，不要手工改表。

### 4.2 回退步骤

方案 A（同目录）：

```bash
cd SqlReport
git fetch origin --tags
git checkout V1
source venv/bin/activate
python server.py
```

方案 B（双目录）：把服务切回 `SqlReport-v1` 目录重启即可；`SqlReport-v2` 保留不动，随时可再切回 V2。

### 4.3 校验回退成功

```bash
git rev-parse --abbrev-ref HEAD    # V1
ls docs 2>/dev/null                # 应报「不存在」
```

再打开页面确认报表、配置、API 均正常。

---

## 5. 老用户：本地还挂在 `main` 上怎么办

远程 `main` 已于 2026-10-05 改名为 `V1`。GitHub 的改名重定向只覆盖网页与 API，**`git` 协议按 refspec 精确匹配**，因此：

- `git pull`：默认 refspec 会把全部远程分支取回，但 `origin/main` 这个远程跟踪引用**不会再更新**（表现为「永远 Already up to date」的假更新）；
- `git fetch --prune` 之后，`origin/main` 会被删除，再 `git pull` 会直接报「no such remote ref / no tracking information」；
- `git clone -b main <url>`：**失败**（远程已无 `main` 引用）。

### 5.1 想继续用 V1（冻结版）

```bash
cd SqlReport
git fetch origin --prune
git checkout -B V1 origin/V1
git branch -u origin/V1 V1
git branch -d main 2>/dev/null || true     # 确认已切到 V1 后再删本地旧名
```

### 5.2 想升级到 V2（推荐）

```bash
cd SqlReport
git fetch origin --tags --prune
git checkout -b V2 origin/V2
git branch -u origin/V2 V2
./install.sh
source venv/bin/activate
python server.py
```

两个操作都要求工作区干净；有未提交改动先 `git stash`（`git stash pop` 可取回）。

---

## 6. 常见问题（FAQ）

**Q1：我 `git clone` 下来的是哪一版？**
默认是 **V2**。用 §1.1 的指纹命令确认。

**Q2：我还能 `git clone -b main` 吗？**
不能。远程已无 `main` 分支，`git` 协议不跟随分支改名重定向，请改用 `-b V1` 或 `-b V2`。若你的部署脚本里写死了 `-b main`，把它改成 `-b V2`（或 `-b v2.0.0` 固定版）。

**Q3：切完分支页面还是老样子？**
① 确认服务真的重启过（`./test_env.sh status` / `systemctl status web-report`）；② 强刷浏览器；③ 确认 `git rev-parse --abbrev-ref HEAD` 输出符合预期（有多个部署目录时最容易搞错的是「改了 A 目录、起的是 B 目录」）。

**Q4：`git checkout` 报 “Your local changes to the following files would be overwritten”？**
工作区有未提交的**被跟踪文件**改动。先 `git stash`（或提交）再切；切换完成后 `git stash pop`。

**Q5：切分支会不会丢报表、配置、审计日志？**
不会。`config.db`、`audit.db`、`*.debug.db`、`app_config.json`、`app_config.debug.json`、`venv/`、`static_cache/`、`run-logs/`、`perf-logs/`、`.env` 全部在 `.gitignore` 中，git 不管它们。**唯一的跨版本风险是配置库表结构变更**，按 §4.1 处理。

**Q6：V1 还会收到修复吗？**
不会。V1 已冻结并加规则保护，所有修复只进 V2。需要旧行为又想要修复，只能自行在 V1 基础上开自己的分支/派生仓库。

**Q7：我确实要给 V1 打个补丁，怎么办？**
两选一：① 管理员在 GitHub 页面 Settings → Rules → `V1-freeze` 临时停用规则，推完再启用（规则 id `24514074`）；② 不动 V1，直接从 `v1-final` 拉出自己的分支开发。**推荐 ②**，V1 的只读性才是它作为「可信历史基准」的价值。

**Q8：V1/V2 的依赖和 Python 版本要求一样吗？**
实测本次 V1→V2 **`requirements.txt` 零差异**，Python 要求同为 3.11+，MySQL 同为 5.7/8.0，所以切换不需要重装依赖。后续若 V2 加依赖，`install.sh` 会同步安装（改依赖时三处会一起更新：`requirements.txt` + 双 README + `install.sh`）。

**Q9：服务起不来 / 端口被占？**
本地测试环境用 `./test_env.sh status → stop → start`；`HOST` / `PORT` 环境变量优先级最高，可用 `TEST_PORT=9100 TEST_HOST=127.0.0.1 ./test_env.sh start` 换端口。

---

## 7. 维护者侧：以后怎么发版

- **开发一律在 `V2` 上**，提交后 `git push origin V2`（V2 是默认分支，PR 默认也指向它）。
- **发版打 tag**：`git tag -a v2.1.0 -m "v2.1.0: <摘要>" && git push origin v2.1.0`。语义化版本；分支头继续前进，tag 永久固定，用户可用 tag 精确复现。
- **不要向 `V1` 推送**：会被 GitHub 规则 `V1-freeze`（id `24514074`）拒绝（实测报 `GH013: Repository rule violations found`）。也不要「在 V1 上开分支修完再合回 V2」——V1 是死线，V2 是唯一前进方向。
- **V1 的唯一可信基准是 tag `v1-final`（`9a975b9`）**。万一规则被误停用且 V1 被改动，用 `v1-final` 恢复。
- 每次新增/调整版本线或 tag，同步更新：本文 §1 表格 + `docs/compose/knowledge/01-architecture.md` 的「版本线与分支策略」小节 + 双 README 的版本说明。

---

## 证据（2026-10-05 实测，**交付前快照**）

> 快照中的 `V2` 分支头与 `v2.0.0` 标签对象号，会因「提交本指南」这一步再前进一格（`v2.0.0` 已重新指向含本指南的提交）；**`V1` 与 `v1-final` 的值永久不变**。实时值自行跑 `git ls-remote --heads --tags origin` 核对。

```text
$ git ls-remote --heads --tags origin
9a975b98089352383376cbd46dd3b7fa7b02ce1e	refs/heads/V1
1e0ea3a26f57e18ada082099be0d6412071f4248	refs/heads/V2
4283fb67ef3f010d4275dbafec211a75db1829ec	refs/tags/v1-final
9a975b98089352383376cbd46dd3b7fa7b02ce1e	refs/tags/v1-final^{}
d31c4d50b33389c9105ff9190e869be5d6c7b83c	refs/tags/v2.0.0
1e0ea3a26f57e18ada082099be0d6412071f4248	refs/tags/v2.0.0^{}
```

```text
$ curl -s .../repos/alexblair/SqlReport | jq .default_branch
"V2"

$ curl -s .../repos/alexblair/SqlReport/rules/branches/V1
{"type":"update","ruleset_id":24514074}
{"type":"deletion","ruleset_id":24514074}
{"type":"non_fast_forward","ruleset_id":24514074}

$ git push origin 1e0ea3a:refs/heads/V1        # 冻结实证（真实推送尝试）
remote: error: GH013: Repository rule violations found for refs/heads/V1.
remote: - Cannot update this protected ref.
 ! [remote rejected] ... (push declined due to repository rule violations)
```

```text
$ git fetch --dry-run origin main          # 老 refspec：远程已无 main
fatal: couldn't find remote ref main          （退出码 128）

$ curl -r 0-0 -o /dev/null -w '%{http_code}' …/SqlReport/tar.gz/refs/<ref>
HTTP 200  refs/tags/v1-final
HTTP 200  refs/heads/V2
HTTP 200  refs/heads/V1
HTTP 404  refs/heads/main     ← 旧 main 的压缩包地址同样失效（按 §5 迁移）
```

V1 → V2 增量（`git diff --stat 9a975b9 1e0ea3a`）：

```text
289 files changed, 54731 insertions(+), 2783 deletions(-)
45 commits
requirements.txt: 无差异        config_db.py: 无差异（无建表/改表语句）
```
