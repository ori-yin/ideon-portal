# ideon 中台 (路由页)

5 个工具的启停控制 + 状态展示，30 分钟闲置自动停止。

## 目录结构

```
ideon-portal/
├── app.py              # FastAPI 主逻辑
├── config.py           # 5 个工具注册表（改这里加/删工具）
├── requirements.txt
├── templates/
│   └── index.html      # 中台首页
├── portal.service      # systemd 单元文件（VM 用）
└── README.md
```

## 本地验证 (Windows)

```cmd
cd C:\Users\a952462\ideon-portal
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set PORTAL_DB_PATH=portal.db
uvicorn app:app --reload
```

浏览器访问 http://127.0.0.1:8001/

**预期**：5 张卡片全部显示"未部署"（Windows 没有 systemctl）。
- 页面能正常渲染 → 前端 OK
- 点"启动"按钮 → 弹出"未部署"错误 → API OK
- 访问 `/api/status` 返回 JSON → API OK

## 部署到 VM (Ubuntu 24.04)

```bash
# 1. 上传源码（scp / 企业微信传压缩包）
# 假设解压在 /tmp/portal-source/

sudo mkdir -p /opt/ideon/portal/templates /var/log/ideon
sudo cp -r /tmp/portal-source/* /opt/ideon/portal/
sudo chown -R root:root /opt/ideon/portal /var/log/ideon

# 2. 建 venv
cd /opt/ideon/portal
python3 -m venv venv
source venv/bin/activate
pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 3. 写 systemd 单元
sudo cp /tmp/portal-source/portal.service /etc/systemd/system/portal.service

# 4. 启动
sudo systemctl daemon-reload
sudo systemctl enable portal
sudo systemctl start portal
sudo systemctl status portal

# 5. 验证
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/
# 期望: 200
curl -s http://127.0.0.1:8001/api/status | python3 -m json.tool
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORTAL_PORT` | 8001 | 监听端口 |
| `PORTAL_DB_PATH` | /opt/ideon/portal/portal.db | SQLite 路径（Windows 测试时改成相对路径） |
| `IDLE_TIMEOUT_MINUTES` | 30 | 闲置多少分钟自动停止 |
| `CHECK_INTERVAL_SECONDS` | 60 | 闲置检测间隔 |

## 5 个工具的 systemd 服务名

| Key | systemd 服务 | 路径前缀 |
|---|---|---|
| content-rank | ideon.service | /content-rank/ |
| copy-analyzer | copy-analyzer.service | /copy-analyzer/ |
| reach-trend | reach-trend.service | /reach-trend/ |
| ctr-predictor | ctr-predictor.service | /ctr-predictor/ |
| library | traffic-library.service | /library/ |

修改 → 改 `config.py`，重启 portal：`sudo systemctl restart portal`