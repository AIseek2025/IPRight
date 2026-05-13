# IPRight 清理策略与瘦身结果

## 1. 文档目的

本文档用于沉淀 `IPRight` 项目一次真实执行过的瘦身方案，明确：

- 哪些内容必须长期保留
- 哪些内容属于缓存、构建产物或历史现场，可直接清理
- 本地工作区与 ECS 服务器的实际清理结果
- 后续重复执行时应遵循的边界与步骤

本文档是运维与仓库维护文档，不替代部署手册。

## 2. 清理总原则

本次采用以下四条原则：

1. 保留所有 `md` 文档
2. 保留全部必要源码与运行必需依赖
3. 删除缓存、构建产物、历史运行现场、临时目录、无效备份
4. 删除非必要二进制文档样本，减少仓库与服务器磁盘占用

## 3. 保留边界

### 3.1 必须保留

- 仓库源码：
  - `backend/`
  - `frontend/`
  - `workers/`
  - `examples/` 中的示例源码骨架
- 文档：
  - `docs/**/*.md`
- 生产运行必需依赖：
  - `/opt/ipright/backend/.venv`
- Playwright 浏览器：
  - `/opt/ipright/shared/ms-playwright`
- 字体资源：
  - `assets/fonts/IPRightCJK.ttf`
- 生产部署与 systemd 相关文件：
  - `deploy/`
  - `scripts/ipright-ecs-*.sh`

### 3.2 可清理

- 前端依赖缓存：
  - `frontend/node_modules`
  - `examples/demo_app/frontend/node_modules`
- 前端构建产物：
  - `frontend/dist`
  - `examples/demo_app/frontend/dist`
- 本地与线上临时目录：
  - `tmp`
- Python 测试与解释器缓存：
  - `.pytest_cache`
  - `__pycache__`
  - `.mypy_cache`
  - `.ruff_cache`
- 前端增量编译缓存：
  - `frontend/tsconfig.tsbuildinfo`
- 历史运行现场：
  - `/opt/ipright/shared/workspace/tasks/*`
- 热修备份目录与备份包：
  - `/opt/ipright/_hotfix_backup`
  - `/opt/ipright/_hotfix_backup_20260504_082521.tar.gz`
- `docs/` 下非必需二进制样本文档：
  - `*.pdf`
  - `*.doc`
  - `*.docx`

## 4. 本次实际清理内容

### 4.1 本地工作区

已删除：

- `frontend/node_modules`
- `frontend/dist`
- `examples/demo_app/frontend/node_modules`
- `examples/demo_app/frontend/dist`
- `tmp`
- `backend/.pytest_cache`
- `frontend/tsconfig.tsbuildinfo`
- `docs/` 下全部 `pdf/doc/docx`

### 4.2 ECS 服务器

已删除：

- `/opt/ipright/frontend/node_modules`
- `/opt/ipright/frontend/dist`
- `/opt/ipright/examples/demo_app/frontend/node_modules`
- `/opt/ipright/examples/demo_app/frontend/dist`
- `/opt/ipright/tmp`
- `/opt/ipright/_hotfix_backup`
- `/opt/ipright/_hotfix_backup_20260504_082521.tar.gz`
- `/opt/ipright/shared/workspace/tasks/*`
- `/opt/ipright/docs` 下全部 `pdf/doc/docx`
- 各类 Python 与测试缓存目录

## 5. 本次清理结果

### 5.1 本地清理后

主要目录体积降至：

- `assets`：约 `22M`
- `docs`：约 `392K`
- `examples`：约 `264K`
- `backend`：约 `700K`
- `frontend`：约 `180K`

### 5.2 ECS 清理后

关键目录体积为：

- `/opt/ipright`：约 `997M`
- `/opt/ipright/shared`：约 `631M`
- `/opt/ipright/shared/ms-playwright`：约 `631M`
- `/opt/ipright/shared/workspace`：约 `8.0K`
- `/opt/ipright/backend/.venv`：约 `320M`
- `/opt/ipright/assets`：约 `23M`
- `/opt/ipright/examples`：约 `344K`
- `/opt/ipright/docs`：约 `228K`
- `/opt/ipright/frontend`：约 `208K`

结论：

- ECS 项目目录已从 `8G+` 级别压缩到约 `997M`
- 最大保留项已经收敛为真正不可缺少的运行依赖：
  - Python 虚拟环境
  - Playwright 浏览器
  - 必需字体资源

## 6. 清理后验证

本次清理后已确认：

- `ipright-api` 为 `active`
- `ipright-worker` 为 `active`
- `curl http://127.0.0.1:18000/health` 返回正常

这说明本次清理没有破坏线上最小可运行能力。

## 7. 后续执行建议

### 7.1 建议保留的周期性清理项

每次完成一轮部署或阶段验收后，建议周期性清理：

- `node_modules`
- `dist`
- `tmp`
- `.pytest_cache`
- `__pycache__`
- `shared/workspace/tasks/*`

### 7.2 不建议清理的项目

除非重新部署，否则不要删除：

- `/opt/ipright/backend/.venv`
- `/opt/ipright/shared/ms-playwright`
- `assets/fonts/IPRightCJK.ttf`

### 7.3 建议的长期策略

- 仓库只保留 `md` 文档，不再长期存放 PDF/Word 样本文档
- 运行现场产物默认不长期留存在 `shared/workspace`
- 大体积依赖只保留“当前运行必需”的最小集合

## 8. 风险提示

执行本策略后，需要接受以下影响：

- 前端开发前需重新安装依赖
- 历史任务的 workspace 现场将不再保留
- 被删除的 PDF/Word 样本文档将不再作为仓库内容存在

因此本策略适合：

- 磁盘紧张环境
- 运行优先于历史留存的生产服务器
- 代码与设计资料优先、二进制样本次要的仓库治理场景
