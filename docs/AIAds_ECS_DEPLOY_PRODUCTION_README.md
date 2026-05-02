# AIAds ECS 正式上线与运维 README

## 1. 文档目的

本文档记录 **AIAds 当前真实生产入口**、本轮真实上线步骤、后续标准发布方式、运维与回滚方法。

**重要前提**：

- `aiads.fun` / `www.aiads.fun` 当前生产 DNS 指向 **`8.218.209.218`**
- 之前的轻量服务器与旧文档里出现的旧机器，**都不再是当前生产入口**
- 后续 AIAds 正式上线、排障、巡检，**只操作这台 ECS**

---

## 2. 当前真实生产形态

| 项 | 值 |
|---|---|
| ECS 公网 IP | `8.218.209.218` |
| SSH 用户 | `admin` |
| 代码目录 | `/opt/aiads` |
| 前端静态发布目录 | `/var/www/aiads/releases/<timestamp>` |
| 前端 current 软链 | `/var/www/aiads/current` |
| Nginx 配置 | `/etc/nginx/conf.d/aiads.conf` |
| 后端进程 | `pm2`：`aiads-api` |
| 后端端口 | `127.0.0.1:3001` |
| 正式域名 | `https://aiads.fun`、`https://www.aiads.fun` |

当前 Nginx 形态：

- `/` -> 静态目录 `/var/www/aiads/current`
- `/api/` -> `http://127.0.0.1:3001`

---

## 3. 本轮真实上线结论

上线时间：`2026-04-12`

本轮真实完成：

1. 将真实生产 ECS `/opt/aiads` 代码同步到 commit `f2ff5d2`
2. 构建后端与前端
3. 对生产库执行 Prisma schema 同步，新增 `users.google_sub`
4. 发布前端静态资源到：
   `/var/www/aiads/releases/20260412-010510`
5. 启动并保存 `pm2` 进程 `aiads-api`
6. 验证本机与公网健康检查均为 `200`

本轮用户需求对应结果：

- 首页文案已部署：`全球 KOL 广告投放平台`
- Google OAuth 代码已部署到生产
- Google OAuth 已完成生产激活，当前：
  `GET /api/v1/public/ui-config` 返回 `google_oauth_configured=true`

也就是说：

- **代码实现已上线**
- **生产 Google 登录已激活**
- 当前生产 `.env.production` 已补齐：
  - `GOOGLE_OAUTH_CLIENT_ID`
  - `GOOGLE_OAUTH_CLIENT_SECRET`
- Google Cloud Console 已为对应 OAuth Client 增加：
  - `https://aiads.fun/api/v1/auth/google/callback`
- OAuth 应用已发布为 `正式版`

当前已补入生产环境的基础值：

- `FRONTEND_PUBLIC_URL=https://aiads.fun`
- `GOOGLE_OAUTH_REDIRECT_URI=https://aiads.fun/api/v1/auth/google/callback`

---

## 4. 为什么不是旧机器

本次核对发现：

- `aiads.fun` 与 `www.aiads.fun` 实际 DNS 解析到 `8.218.209.218`
- 旧文档中的 `47.239.7.62` 并不是当前公网入口
- 因此对 `47.239.7.62` 的部署不会影响真实线上流量

结论：

- **今后 AIAds 一律以 `8.218.209.218` 为准**
- 旧轻量服务器 / 旧入口不要再访问、不要再部署

---

## 5. 当前推荐发布路径

### 5.1 已验证可用的当前路径：`git bundle` 热同步

由于当前真实 ECS 尚未配置好对 GitHub 仓库的无交互拉取能力，**本轮真实成功路径**是：

1. 本地完成代码提交并 `git push origin main`
2. 本地创建 bundle
3. 上传 bundle 到 ECS
4. ECS 在 `/opt/aiads` 执行 `git fetch /tmp/xxx.bundle main`
5. `git checkout -f FETCH_HEAD`
6. 构建后端、同步 Prisma、构建前端
7. 切静态软链
8. `pm2 start/restart aiads-api`

本轮实战已证明此路径可用。

### 5.2 后续更理想的标准路径

当 ECS 配好 GitHub 只读访问后，推荐改为：

```bash
ssh admin@8.218.209.218
cd /opt/aiads
git fetch origin
git checkout main
git pull origin main
```

然后继续执行构建与发布步骤。

---

## 6. 可复用正式上线步骤

### 6.0 全量一条链（本机编排 + 远端脚本，推荐在无法稳定 `git push` 到 GitHub 时使用）

**仓库内脚本**：

- `scripts/aiads-ecs-full-deploy.sh`：在 **ECS 上** 执行，顺序为：后端 `npm ci` + Prisma + `prisma db push` + 前端 `npm ci` + `VITE` 构建 + 静态 `rsync` + `pm2 restart`（见 §6.3–6.5 等价内容）。
- `scripts/local-ecs-push-bundle-and-apply.sh`：在 **你的笔记本** 上执行：打 `main` bundle、带重试 `scp` 到 ` /tmp/aiads-main.bundle`、`git fetch` / `checkout` 后，用 `ssh -n` 启动 `nohup` 全量任务并轮询日志。

**最近实战确认的关键前提**：

- `scripts/local-ecs-push-bundle-and-apply.sh` 打包的是 **本地 `main` 分支引用**，不是当前工作区 `HEAD` 的任意脏改动。
- 也就是说，准备发布前必须先把目标改动 **提交到本地 `main`**；若改动只停留在未提交文件、其他分支或临时 stash 中，脚本不会把这些内容带上去。
- 发布前先执行：

```bash
cd /Users/surferboy/.openclaw/workspace/AIAds
git branch --show-current
git rev-parse --short HEAD
git status --short
```

建议确认：

- 当前就在 `main`
- 除明确不发的文件外，工作区没有误发内容
- 目标提交已经存在于本地 `main`

**最近前端/UI 迭代的最小发布链**：

- 若本次是纯前端视觉、文案或交互调整，优先在本地执行 `npm run check:frontend`
- 若本次同时改了后端、接口契约或数据库相关逻辑，再执行根级 `npm run check`
- 前端/UI 连续小步迭代时，推荐顺序：

```bash
cd /Users/surferboy/.openclaw/workspace/AIAds
git status
npm run check:frontend
git add <本次确实要发的文件>
git commit -m "<release message>"
./scripts/local-ecs-push-bundle-and-apply.sh
```

注意：

- 不要用 `git add -A` 直接把交接文档、临时截图、草稿文件一起混入生产发布
- 若仓库里存在 `SESSION_HANDOFF_*.md` 之类交接文件，默认先视为 **不自动纳入发布**
- 当前这套一条链脚本适合最近多次验证通过的前端/UI 发布；若涉及高风险数据变更，仍需按本文其他章节补做数据库与链路验收

```bash
cd /Users/surferboy/.openclaw/workspace/AIAds
./scripts/local-ecs-push-bundle-and-apply.sh
```

**目录属主**（必看）：若历史上曾以 `root` 在 `/opt/aiads` 下装过依赖，`admin` 再跑 `npm ci` 会报 `EACCES: permission denied`（例如无法删除 `node_modules/.bin/...`）。在 ECS 上先执行一次：

```bash
sudo chown -R admin:admin /opt/aiads
```

**SSH 易断**：长任务请用本机的 `nohup` 脚本或手工 `nohup bash /opt/aiads/scripts/aiads-ecs-full-deploy.sh >> /tmp/aiads-deploy.log 2>&1 &`，再用 `tail -f /tmp/aiads-deploy.log` 观察，避免长会话被防火墙切断。

### 6.1 本地准备

```bash
cd /Users/surferboy/.openclaw/workspace/AIAds
git status
git push origin main
git rev-parse --short HEAD
```

### 6.2 当前可用的热同步上线

本地：

```bash
git -C /Users/surferboy/.openclaw/workspace/AIAds bundle create /tmp/aiads-main.bundle main
scp /tmp/aiads-main.bundle admin@8.218.209.218:/tmp/aiads-main.bundle
```

ECS：

```bash
ssh admin@8.218.209.218
cd /opt/aiads
git fetch /tmp/aiads-main.bundle main
git checkout -f FETCH_HEAD
```

### 6.3 后端构建与数据库同步

```bash
cd /opt/aiads/src/backend
unset NODE_ENV npm_config_production NPM_CONFIG_PRODUCTION NPM_CONFIG_INCLUDE
npm ci --include=dev
npx prisma generate
npm run build

set -a
. ./.env.production
set +a

dburl="$(python3 -c "import os,sys; sys.stdout.write(os.environ.get('DATABASE_URL',''))")"
npx prisma db push --url "$dburl" --accept-data-loss
```

说明：

- 当前这台 ECS 上，`prisma db push` 直接依赖 `prisma.config.ts` 读 `DATABASE_URL` 有兼容问题
- 已验证可用的方式是显式加 `--url "$dburl"`

### 6.4 前端构建与静态发布

```bash
cd /opt/aiads/src/frontend
NODE_ENV=development npm ci --include=dev
VITE_API_URL=https://aiads.fun/api/v1 npm run build

release_ts="$(date +%Y%m%d-%H%M%S)"
static_release="/var/www/aiads/releases/$release_ts"
sudo mkdir -p "$static_release"
sudo rsync -a --delete dist/ "$static_release"/
sudo ln -sfn "$static_release" /var/www/aiads/current
```

### 6.5 启动 / 重启后端

```bash
cd /opt/aiads/src/backend
set -a
. ./.env.production
set +a

if pm2 describe aiads-api >/dev/null 2>&1; then
  NODE_ENV=production pm2 restart aiads-api --update-env
else
  NODE_ENV=production pm2 start dist/index.js --name aiads-api --cwd /opt/aiads/src/backend --update-env
fi

pm2 save
```

---

## 7. 上线后验证

### 7.1 本机验证

```bash
curl -fsSL -H 'X-Forwarded-Proto: https' http://127.0.0.1:3001/api/v1/health
pm2 status aiads-api
```

若不带 `X-Forwarded-Proto: https`，本机对明文 `http://127.0.0.1:3001` 可能看到 **HTTP 302** 到 `https://...` 同路径，属正常；勿与「进程未起」混淆。**勿**对 3001 使用 `curl -k`（无 TLS 端口会报 `SSL: wrong version number`）。更完整的说明见 **§12.1、§12.6**。

### 7.2 公网验证

```bash
curl -fsSL https://aiads.fun/api/v1/health
curl -I https://aiads.fun/
curl -I https://www.aiads.fun/
```

### 7.3 本轮已验证结果

- `/opt/aiads` 当前 commit：`f2ff5d2`
- `pm2 aiads-api`：`online`
- `https://aiads.fun/api/v1/health`：`200`
- `https://aiads.fun/`：`200`
- 当前静态目录：`/var/www/aiads/releases/20260412-010510`
- `https://aiads.fun/api/v1/public/ui-config`：`google_oauth_configured=true`
- `https://aiads.fun/api/v1/auth/google`：可正确 `302` 到 Google
- Google 真实账号已验证登录成功

### 7.4 Google 配置检查

```bash
curl -fsSL https://aiads.fun/api/v1/public/ui-config
```

重点看：

- `google_oauth_configured`

当前生产预期应为 `true`；若变成 `false`，说明 PM2 当前环境未正确加载 Google OAuth 凭据。

### 7.5 最近多轮 UI 发布后的附加核对

除健康检查外，最近几轮前端 UI 上线后，建议补做以下回读，避免“脚本跑完了，但不清楚线上到底切到了哪一版”：

```bash
ssh admin@8.218.209.218 \
  "git -C /opt/aiads rev-parse --short HEAD; readlink -f /var/www/aiads/current"
```

建议把以下结果记到发布备注中：

- 线上 commit short sha
- 当前静态目录真实路径
- 本次是否为纯前端/UI 发布
- 本次本地执行的是 `npm run check:frontend` 还是根级 `npm run check`

若本次改的是首页、公开广场、登录页或其他明显可见页面，建议再用浏览器抽查至少以下页面：

- `/`
- `/marketplace`
- `/login`
- `/admin/login`

对 UI 类发布，重点看：

- 首页是否已切到最新文案/布局，不是旧包
- 首屏视频、图片、poster 是否正常显示，尤其是手机端
- 静态页和公共广场是否存在白屏、黑屏、资源 404
- 浅色主题下文字对比度是否仍清晰

---

## 8. Google OAuth 生产配置基线

在 ECS `/opt/aiads/src/backend/.env.production` 中补齐：

```bash
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=https://aiads.fun/api/v1/auth/google/callback
FRONTEND_PUBLIC_URL=https://aiads.fun
```

Google Cloud Console 对应 OAuth Client 应保持：

```text
https://aiads.fun/api/v1/auth/google/callback
```

并确保：

- JavaScript 来源包含 `https://aiads.fun`
- JavaScript 来源包含 `https://www.aiads.fun`
- OAuth 应用发布状态为 `正式版`

环境变量更新后执行：

```bash
cd /opt/aiads/src/backend
set -a
. ./.env.production
set +a
NODE_ENV=production pm2 restart aiads-api --update-env
```

然后验证：

```bash
curl -fsSL https://aiads.fun/api/v1/public/ui-config
```

预期：

- `google_oauth_configured=true`

前端发布时建议显式执行：

```bash
cd /opt/aiads/src/frontend
VITE_API_URL=https://aiads.fun/api/v1 npm run build
```

说明：

- 当前前端代码已增加同源 `/api/v1` 兜底
- 但生产构建仍建议显式注入 `VITE_API_URL`，避免缓存或旧包带来歧义

---

## 9. 日常运维命令

### 9.1 查看线上版本

```bash
git -C /opt/aiads rev-parse HEAD
git -C /opt/aiads rev-parse --short HEAD
readlink -f /var/www/aiads/current
```

### 9.2 查看 PM2

```bash
pm2 status aiads-api
pm2 show aiads-api
pm2 logs aiads-api --lines 200
```

### 9.3 查看 Nginx

```bash
sudo sed -n '1,220p' /etc/nginx/conf.d/aiads.conf
sudo nginx -t
```

### 9.4 查看健康状态

```bash
curl -fsSL -H 'X-Forwarded-Proto: https' http://127.0.0.1:3001/api/v1/health
curl -fsSL https://aiads.fun/api/v1/health
curl -I https://aiads.fun/
```

### 9.5 API 出现 502 时的快速处置

如果首页静态资源仍能打开，但 `/api/v1/*` 全部返回 `502`，优先按下面顺序排查：

```bash
pm2 status aiads-api
pm2 logs aiads-api --lines 120
curl -fsSL -H 'X-Forwarded-Proto: https' http://127.0.0.1:3001/api/v1/health
```

本项目在 `2026-04-21` 真实出现过一次同类事故，根因是：

- PM2 进程被重新拉起后，shell 中导出的环境变量丢失
- 后端启动时拿不到 `DATABASE_URL`
- `aiads-api` 启动失败，Nginx 对 `/api/` 统一返回 `502`

当前修复状态：

- 后端已增加启动时自动加载 `.env.production`
- 即使 PM2 重启，也不应再因为遗漏 `source .env.production` 而直接离线

若仍需人工恢复，可执行：

```bash
cd /opt/aiads/src/backend
set -a
. ./.env.production
set +a
NODE_ENV=production pm2 restart aiads-api --update-env
pm2 save
```

恢复后建议立即复测：

```bash
curl -fsSL https://aiads.fun/api/v1/health
curl -fsSL https://aiads.fun/api/v1/public/ui-config
```

### 9.6 发布刚完成时短暂 502 的判断

最近实战中，`scripts/local-ecs-push-bundle-and-apply.sh` 在远端日志已经出现 `Full deploy done` 后，公网健康检查仍可能短暂读到一次 `502`。这通常出现在：

- `pm2 delete aiads-api` 后刚重新 `pm2 start`
- Nginx 已经对外服务，但后端新进程还在启动窗口

判断方式：

- 若 `pm2 status aiads-api` 很快恢复为 `online`
- 且 30-60 秒内 `https://aiads.fun/api/v1/health` 重新回到 `200`

则优先判断为 **短暂启动窗口**，不是最终发布失败。

建议处理顺序：

```bash
pm2 status aiads-api
curl -I --max-time 15 https://aiads.fun/api/v1/health
curl -I --max-time 15 https://aiads.fun/
```

若首次仍为 `502`，等待 20-60 秒后再试一次；若多次重试仍失败，再按 §9.5 的 `pm2 logs` 与本机 3001 健康检查继续排障。

补充说明：

- 当前本机脚本尾部的公网 `curl` 更接近“快速烟测”，不是最终唯一判定
- 对最近这种前端/UI 发布，推荐以“`Full deploy done` + PM2 online + 复测公网健康为 200 + 页面抽查正常”作为最终完成信号

---

## 10. 回滚

### 10.1 回滚代码

如果服务器 GitHub 访问仍未修好，可继续使用 bundle 回滚到旧 commit：

```bash
git bundle create /tmp/aiads-rollback.bundle <old-commit>
scp /tmp/aiads-rollback.bundle admin@8.218.209.218:/tmp/aiads-rollback.bundle
ssh admin@8.218.209.218
cd /opt/aiads
git fetch /tmp/aiads-rollback.bundle <old-commit>
git checkout -f FETCH_HEAD
```

### 10.2 回滚后重新构建

按本文第 6 节重新执行：

- 后端构建
- `prisma db push`
- 前端构建
- 切静态软链
- `pm2 restart aiads-api`

---

## 11. 注意事项

1. 不要再去旧轻量服务器或旧错误目标机发版
2. 当前真实生产入口只看 `8.218.209.218`
3. `/opt/aiads` 是真实线上代码目录，不是 `/opt/aiads-current`
4. 当前真实 ECS 还没有稳定的 GitHub 无交互拉取能力，发布优先用 `git bundle`
5. `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` 当前已在生产配置并验证通过；若后续轮换 Secret，记得同步更新 `.env.production` 后重启 `pm2`
6. `FRONTEND_PUBLIC_URL` 应保持为 `https://aiads.fun`
7. `GOOGLE_OAUTH_REDIRECT_URI` 应保持为 `https://aiads.fun/api/v1/auth/google/callback`
8. 若出现“首页可访问但所有 `/api` 都是 `502`”，优先检查 `pm2` 中的 `aiads-api` 是否正常在线，以及 `.env.production` 是否被后端成功加载
9. `scripts/local-ecs-push-bundle-and-apply.sh` 当前只打包本地 `main`；若目标改动未提交到本地 `main`，就不会被发布
10. 纯前端/UI 发布默认先跑 `npm run check:frontend`；只有后端、接口或数据形态也改动时，再补根级 `npm run check`
11. 发布完成后，不要只看脚本输出；至少补记一次线上 commit、当前静态目录和公网健康检查结果

---

## 12. 典型故障与排障（2026-04-22 生产实录）

本节记录 **真实生产 ECS** 上曾出现过的现象、根因与可复用处理步骤，与 §6 标准发布链互补。代码栈：**Node 后端 + Prisma 7 + `pm2` + Nginx 反代**。

### 12.1 现象摘要

| 现象 | 说明 |
|------|------|
| `502` 或 `curl: (7) Failed to connect to 127.0.0.1 port 3001` | 本机 Node 未监听 / 进程已崩溃。 |
| `pm2` 中 `aiads-api` 为 `errored`，`↺`（重启次数）持续增加 | 启动阶段抛错，进程无法常驻。 |
| `pm2` 显示 `online`，但 `curl http://127.0.0.1:3001/...` 仍失败 | 多为未执行 `npm run build` 或进程秒退，需看日志。 |
| 本机对 `http://127.0.0.1:3001/api/v1/health` 得到 **HTTP 302**，`Location: https://127.0.0.1:3001/...` | **正常**：生产下中间件对明文 HTTP 请求会要求 HTTPS。 |
| `curl -kfsSL "http://127.0.0.1:3001/..."` 报 `SSL: wrong version number` | 3001 上为**明文 HTTP**，无 TLS；`-k` 仅用于 HTTPS。勿对纯 HTTP 端口误用。 |
| 首页白屏、`index.html` 里 script 指向 `/src/frontend/dist/assets/...` | Nginx 根下无该路径，**try_files** 回退成 HTML；见 **§12.9**，需用 `base: '/'` 重编静态并发布。 |

### 12.2 根因一：Prisma 7 与 `database.ts` / `schema` 不同步

**错误日志（节选）**：

```text
PrismaClientConstructorValidationError: Using engine type "client" requires either "adapter" or "accelerateUrl" to be provided to PrismaClient constructor.
  at .../src/config/database.ts:22:16
```

**含义**：

- 生成物若按 **driver adapter / `engineType = "client"`** 路径生成，则 **`new PrismaClient()` 必须带 `adapter`（或 Accelerate）**。
- 仅把 `schema.prisma` 在笔记本上改好，**未同步** `src/backend/src/config/database.ts`（及依赖版本）到 ECS 时，线上仍是旧版工厂代码，会触发上述错误。
- 本仓库的推荐组合为：`schema.prisma` 中 `generator client` 使用 **`engineType = "library"`**（与团队约定一致时），并保证 **`npx prisma generate` + `npm run build` 在 ECS 上已执行**。

**处理要点**：

1. 在**开发机仓库**确认 `prisma/schema.prisma` 的 `generator client` 块与 `src/config/database.ts` 为**同一提交、彼此匹配**。
2. 将至少以下文件同步到 ECS `/opt/aiads` 下对应路径（与 bundle / `git pull` 等发布方式二选一，见下节）  
   - `src/backend/prisma/schema.prisma`  
   - `src/backend/src/config/database.ts`  
   - 建议同时同步 `src/backend/package.json` 与 `package-lock.json`，避免 `@prisma/*`、`@prisma/adapter-pg` 版本漂移。
3. 在 ECS 上**严格顺序**执行（**每条都要真正执行到**，见 §12.5）：

   ```bash
   cd /opt/aiads/src/backend
   unset NODE_ENV npm_config_production NPM_CONFIG_PRODUCTION NPM_CONFIG_INCLUDE
   npm ci --include=dev
   npx prisma generate
   npm run build
   test -f dist/index.js && echo "dist OK"
   ```

4. 再按 §6.5 或下文 §12.4 启动 `pm2`。

### 12.3 根因二：`git pull` / `git fetch origin` 报 `Repository not found`

- 公网仓为**私有**时，ECS 上若未配置 **Deploy Key** 或 **HTTPS + Token**，会无法从 GitHub 拉取。  
- **不阻塞发布**：可继续用 §5 / §6 的 **bundle** 全量更新，或仅同步单文件（见 §12.4）。  
- 若仓库内文档提到 `scripts/aiads-ecs-full-deploy.sh` 而 **ECS 上 `ls /opt/aiads/scripts/` 无此文件**，说明线代码树**未**包含该提交，需用 bundle 或手拷补全，而非假定脚本已存在。

### 12.4 同步单文件：scp 不稳定时的替代（推荐）

`scp` 偶发 `Connection reset by peer` 或 `kex_exchange_identification` 时，可在**笔记本**上用 **单条管道** 覆盖远端文件，减少多次握手：

```bash
# 在 Mac 上执行；将路径换为你的本机仓库根
ssh admin@8.218.209.218 'mkdir -p /opt/aiads/src/backend/src/config'

cat /path/to/AIAds/src/backend/src/config/database.ts | \
  ssh admin@8.218.209.218 'cat > /opt/aiads/src/backend/src/config/database.ts'

cat /path/to/AIAds/src/backend/package.json | \
  ssh admin@8.218.209.218 'cat > /opt/aiads/src/backend/package.json'

# 若有 lock 建议一并同步
test -f /path/to/AIAds/src/backend/package-lock.json && \
  cat /path/to/AIAds/src/backend/package-lock.json | \
  ssh admin@8.218.209.218 'cat > /opt/aiads/src/backend/package-lock.json'
```

同步后仍在 ECS 上执行 `npm ci`、`prisma generate`、`npm run build` 与 `pm2`（见 §12.2）。

### 12.5 本机（Mac）与生产机（ECS）勿混淆

- **`/opt/aiads`** 只存在于 **ECS**；在 Mac 上执行 `cd /opt/aiads` 会失败。  
- **`node dist/index.js`、 `npm run build`、 `pm2`** 等**发布/验证命令**应在 **已 `ssh` 登录 ECS 之后**、在 `.../src/backend` 下执行。  
- 在 Mac 家目录直接执行 `node dist/index.js` 会解析为 **`/Users/<你>/dist/index.js`** 等错误路径，与本次部署无关。  
- 在终端**一行里只粘贴、未按回车**的 `npm run build` 等，可能**并未执行**；大段用 **`&&` 串成一条**再回车，可避免漏步。

### 12.6 健康检查：本机 curl 的正确方式

- **经 Nginx 的公网**（与真实用户一致）：

  ```bash
  curl -fsS https://aiads.fun/api/v1/health
  ```

- **直连本机 Node（HTTP）**：生产环境可能对「纯 HTTP」返回 **302** 到 `https://` 同路径，**不代表进程未启动**。应带与反代一致的头：

  ```bash
  curl -fsS -H 'X-Forwarded-Proto: https' http://127.0.0.1:3001/api/v1/health
  ```

- **勿**对 `http://127.0.0.1:3001` 使用 `curl -k` 去模拟 TLS，否则易出现 `SSL: wrong version number`（因该端口为明文 HTTP，见 §12.1）。

与 §7.1、§9.4 中的 `X-Forwarded-Proto` 写法一致，可互为引用。

### 12.7 PM2 与环境的补充说明

- 首次在 shell 中 `set -a; . ./.env.production; set +a; export NODE_ENV=production` 后，若使用 **`pm2 delete aiads-api` 再 `pm2 start ...`**，子进程更可能继承当前会话环境；**仅** `pm2 restart` 在部分场景下**不会**重读你刚在 shell 里 `export` 的变量（以实际 `pm2` 行为为准，异常时以 `delete` + `start` 为兜底）。  
- 后端 `src/index.ts` 会加载 `load-env`，生产仍建议 **`NODE_ENV=production` 与完整 `.env.production`** 一致，并优先用与 §6.5 相同的启动方式。

### 12.8 已验证的恢复结果（同轮排查）

- `curl -H 'X-Forwarded-Proto: https' http://127.0.0.1:3001/api/v1/health` 返回 `success: true`。  
- `curl https://aiads.fun/api/v1/health` 返回 `success: true`。  
- `pm2` 中 `aiads-api` 为 `online`，`↺` 不再持续增加。  

（上述用于对照排障，**非**对 commit 与静态目录的审计结论；以当时服务器 `git rev-parse` 与 `readlink /var/www/aiads/current` 为准。）

### 12.9 白屏：首页 `200` 但无界面（Vite 资源路径错误）

**现象**：浏览器打开 `https://aiads.fun/` 为白屏，开发者工具 **Network** 里主入口 JS 可能仍显示 **200**，但 **Response 实为整页 HTML**（`<!doctype html>…`），控制台常见「Unexpected token '<'」等。

**根因**：`dist/index.html` 中 `<script src="...">` 使用了 **`/src/frontend/dist/assets/...`** 之类路径；Nginx 的站点根是 **`/var/www/aiads/current`（即 `dist` 的目录内容）**，磁盘上只有 **`/assets/*.js`**，没有 `/src/...`。常见 `try_files` 会**回退到 `index.html`**，故长路径也返回 **200**，但 MIME 与内容错误，**无法作为 ES module 执行** → 白屏。

**本仓库基线**：`src/frontend/vite.config.ts` 中 **`base: '/'`**，正确产物应引用 **`/assets/<hash>.js`** 与 **`/favicon.svg`**。

**若你在 ECS 上已执行 `npm run build`，`grep /src/frontend/dist/ dist/index.html` 仍为 BAD**：说明 **ECS 上 `vite.config.ts` 与 Git 仓库不一致**（常见为历史遗留的 `base: '/src/frontend/dist/'`），仅重编**不会**自愈。请先用 bundle / `scp` / `cat | ssh` **覆盖**本仓库中的 `src/frontend/vite.config.ts`（以及与之匹配的 `index.html` 等），**再** build。可先在服务器执行 `grep -n "base" /opt/aiads/src/frontend/vite.config.ts` 对照本地仓库。

**修复后**按 §6.4 执行 `VITE_API_URL=... npm run build` 并 `rsync` 到 `releases/` + 更新 `current`；`scripts/aiads-ecs-full-deploy.sh` 在构建后也会检测错误路径并失败（仓库内 Vite 插件对错误 `base` 会直接**中止构建**）。

**快速自测**（公网，将 `index.html` 里抄出的主入口路径代入）：

```bash
# 若返回以 <!doctype 开头，即错误（应返回以 const 或 import 开头的 JS）
curl -sS 'https://aiads.fun/src/frontend/dist/assets/index.XXXXX.js' | head -c 40

# 正确短路径应返回 JS
curl -sS 'https://aiads.fun/assets/index.XXXXX.js' | head -c 40
```

---

## 13. 相关文档

- `docs/ECS_DEPLOY_PRODUCTION_README.md`：本文
- `docs/PRODUCTION_OPERATIONS_README.md`：旧版生产手册（若与本文冲突，以本文为准）
- `DEPLOY_PROD.md`：历史发布说明
- AIInvestor：`docs/ECS_MIGRATION_HANDOVER_README.md`
- AINews：`docs/ECS_DEPLOY_PRODUCTION_README.md`
