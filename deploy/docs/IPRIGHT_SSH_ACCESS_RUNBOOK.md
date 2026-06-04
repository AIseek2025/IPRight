# IPRight ECS SSH 入口与恢复手册

## 1. 文档目的

本文档用于固定 `IPRight` 生产机的 SSH 最终入口、账号口径、日常登录方式，以及 2026-06-04 这次真实恢复过程中的关键结论。

后续若出现：

- SSH 主入口异常
- 需要给新电脑补登录能力
- 需要核查安全组、防火墙或 `sshd` 是否偏离基线

统一优先阅读本文件。

## 2. 当前最终口径

当前最终以以下入口为准：

| 项 | 值 |
|---|---|
| ECS 公网 IP | `8.218.209.218` |
| 日常登录用户 | `admin` |
| 主 SSH 端口 | `22` |
| 备用 SSH 端口 | `2222` |
| 推荐正式入口 | `admin@2222` |
| 本地私钥 | `~/.ssh/id_ed25519_ecs_shared` |
| 公钥注释 | `codemaster-ecs-shared-ed25519` |

当前实测结论：

- `admin@2222` 公钥登录已恢复并稳定可用
- `22` 端口对部分来源仍可能在早期握手阶段断开，不应作为当前唯一值班入口
- `root` 仅保留应急用途，不建议作为日常运维账号

## 3. 当前服务器配置基线

### 3.1 `sshd` 配置

服务器当前最终配置文件：

```text
/etc/ssh/sshd_config.d/90-ipright-ssh-final.conf
```

基线内容：

```text
Port 22
Port 2222

PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin prohibit-password
AuthorizedKeysFile .ssh/authorized_keys
UsePAM yes

LoginGraceTime 60
MaxStartups 100:30:200
MaxSessions 100

ClientAliveInterval 30
ClientAliveCountMax 3
```

### 3.2 本机防火墙

服务器本机 `firewalld` 当前要求：

- `ssh` 服务保持放通
- `2222/tcp` 必须显式放通

核查命令：

```bash
sudo firewall-cmd --list-all
sudo ss -ltnp | grep -E ':(22|2222)\b'
```

### 3.3 安全组

阿里云安全组中，至少需要：

- `22/tcp`
- `2222/tcp`

若后续继续采用当前口径，建议：

- `2222` 作为正式值班入口长期保留
- `22` 作为兼容入口保留，但不再依赖其作为唯一入口

## 4. 本地推荐 SSH 配置

建议在本地 `~/.ssh/config` 中写入：

```text
Host ipright-ecs
  HostName 8.218.209.218
  Port 2222
  User admin
  IdentityFile ~/.ssh/id_ed25519_ecs_shared
  IdentitiesOnly yes
  ServerAliveInterval 30
  ServerAliveCountMax 3

Host ipright-ecs-root
  HostName 8.218.209.218
  Port 2222
  User root
  IdentityFile ~/.ssh/id_ed25519_ecs_shared
  IdentitiesOnly yes
  ServerAliveInterval 30
  ServerAliveCountMax 3
```

后续日常登录统一使用：

```bash
ssh ipright-ecs
```

应急 root：

```bash
ssh ipright-ecs-root
```

## 5. 服务器侧公钥落点

当前要求以下两个文件都存在且权限正确：

```text
/home/admin/.ssh/authorized_keys
/root/.ssh/authorized_keys
```

建议核查命令：

```bash
sudo ls -ld /home/admin/.ssh /root/.ssh
sudo ls -l /home/admin/.ssh/authorized_keys /root/.ssh/authorized_keys
```

权限基线：

- 目录：`700`
- `authorized_keys`：`600`

## 6. 日常登录与恢复命令

### 6.1 日常登录

```bash
ssh -p 2222 -i ~/.ssh/id_ed25519_ecs_shared -o IdentitiesOnly=yes admin@8.218.209.218
```

### 6.2 应急 root

```bash
ssh -p 2222 -i ~/.ssh/id_ed25519_ecs_shared -o IdentitiesOnly=yes root@8.218.209.218
```

### 6.3 服务器侧核查

```bash
sudo systemctl status sshd --no-pager
sudo sshd -t
sudo sshd -T | egrep 'port|maxstartups|maxsessions|permitrootlogin|passwordauthentication|pubkeyauthentication'
sudo firewall-cmd --list-all
sudo ss -ltnp | grep -E ':(22|2222)\b'
sudo journalctl -u sshd -n 200 --no-pager
```

## 7. 2026-06-04 真实恢复结论

本轮真实排障已确认：

1. `sshd` 主进程本身并未崩溃
2. 早期真正阻塞点是：
   - `firewalld reload` 因 `/etc/firewalld/direct.xml` 中的 IPv6 direct rules 失败
   - `2222` 虽监听，但未真正通过防火墙 reload 生效
3. 通过移走旧的 `direct.xml` 后，`firewall-cmd --reload` 恢复成功
4. 在补齐：
   - `Port 2222`
   - `2222/tcp` 防火墙规则
   - `admin/root authorized_keys`
   - `PasswordAuthentication no`
   - `PermitRootLogin prohibit-password`
   之后，`admin@2222` 公钥入口已恢复
5. 从本地 Mac 已真实验证：

```bash
ssh -p 2222 -i ~/.ssh/id_ed25519_ecs_shared -o IdentitiesOnly=yes admin@8.218.209.218
```

可成功登录。

## 8. 当前运维建议

- 日常值班统一优先用 `admin@2222`
- 远程发布、线上复跑、systemd 巡检都优先走 `2222`
- 若 `22` 恢复稳定后，可继续保留，但不建议删除 `2222`
- 若后续要收紧安全面，优先通过安全组白名单，而不是移除 `2222`

## 9. 变更后必做验收

任何 SSH 相关变更后，都至少执行一次：

```bash
ssh -p 2222 -i ~/.ssh/id_ed25519_ecs_shared -o IdentitiesOnly=yes admin@8.218.209.218 'hostname && whoami'
```

并在服务器上补查：

```bash
sudo journalctl -u sshd -n 50 --no-pager
```

如果这里不通过，不要继续做生产发布或真实任务复跑。
