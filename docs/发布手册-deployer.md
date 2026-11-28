# deployer 发布手册（一页版）

> 服务器 39.106.203.192 · 账号 `deployer`（仅密钥登录）· 应用目录 `/opt/mine_platform/app` · 服务 `mine-app`（waitress 127.0.0.1:8000，systemd）· 对外入口 nginx `:18000`

## 1. 连接

```
ssh deployer@39.106.203.192
```

仅支持密钥登录（无密码）。登录后即在你的发布账号下，无需再切换用户。

## 2. 权限边界

| 可做 | 不可做 |
|---|---|
| 读写 `/opt/mine_platform/app`（应用代码，属主 deployer:mine） | 数据库 `mine-pg` 的启停与数据操作 |
| 写 `/opt/mine_platform/backup`（发布前备份） | nginx 配置与重启 |
| `sudo -n systemctl restart\|status\|is-active mine-app` | 改 `/opt/mine_platform/env`（服务环境变量，只读） |
| `sudo -n systemctl restart\|status mine-jobs.timer` | venv 依赖安装（pip）——需 root 配合 |
| `journalctl -u mine-app`（已入 systemd-journal 组，免 sudo） | 改 systemd unit 文件 |

## 3. 标准发布流程（代码更新，无依赖变更）

```bash
# —— 本地（Windows，项目根目录）——
git archive --format=tar.gz -o release.tar.gz HEAD
scp release.tar.gz deployer@39.106.203.192:/tmp/

# —— 服务器（deployer 登录后）——
# 1) 备份当前代码
tar -czf /opt/mine_platform/backup/app-$(date +%Y%m%d-%H%M%S).tar.gz -C /opt/mine_platform/app .
# 2) 解压覆盖（app 目录归你所有，直接写）
tar -xzf /tmp/release.tar.gz -C /opt/mine_platform/app
# 3) 权限归一（服务以 mine 运行，需组可读）
find /opt/mine_platform/app -type d -exec chmod 2775 {} +
find /opt/mine_platform/app -type f -exec chmod 0664 {} +
# 4) 重启服务
sudo -n systemctl restart mine-app
# 5) 验证
systemctl is-active mine-app
curl -s http://127.0.0.1:8000/api/v1/health   # 期望 {"code":0,...,"data":{"status":"UP"}}
journalctl -u mine-app -n 50 --no-pager        # 无 Traceback / UniqueViolation
# 6) 外网确认
curl -s http://39.106.203.192:18000/api/v1/health
```

## 4. 回滚

```bash
ls -t /opt/mine_platform/backup | head -3       # 找最近备份
tar -xzf /opt/mine_platform/backup/app-<时间戳>.tar.gz -C /opt/mine_platform/app
find /opt/mine_platform/app -type d -exec chmod 2775 {} +
find /opt/mine_platform/app -type f -exec chmod 0664 {} +
sudo -n systemctl restart mine-app
```

## 5. 注意事项

- **依赖变更**：requirements.txt 有新依赖时，pip 安装需 root（venv 属 mine）。先联系管理员执行，再发布。
- **数据库**：schema 变更随启动自动建表/补齐（create-if-missing），无需手工迁移；结构性变更先知会管理员。
- **勿动**：`/opt/mine_platform/{env,pgdata,venv,python312,uploads}`；uploads 归服务账号 mine。
- **后台任务**：mine-jobs.timer 一般无需重启；确需重启用 `sudo -n systemctl restart mine-jobs.timer`。
- **打包范围**：backend/ frontend/ run.py manage.py requirements* .env.example docs/schema_postgresql.sql（`git archive HEAD` 已含）；根目录文档/测试不入包。
- **浏览器兼容性**：前端目标为现代常青浏览器——Chrome/Edge ≥ 88、Firefox ≥ 94（依赖 ES2020 `?.`/`??`、CSS Grid/Flex、ResizeObserver）；管理端专网终端建议 Chrome 100+。不支持 IE。大屏页依赖 WebGL，禁用硬件加速的终端需开启软件渲染。
- **求助**：sudo 被拒、权限不足或服务反复重启，联系管理员（root）处理。
