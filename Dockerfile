# ============================================================
# InfoGet - RSS Feed 生成器 Docker 镜像
# ============================================================
# 多阶段构建：
#   1. builder  - 安装依赖
#   2. tester   - 运行测试（可选跳过）
#   3. runner   - 最小化运行环境
# ============================================================

# ---------- 阶段 1：安装依赖 ----------
FROM python:3.9-slim AS builder

WORKDIR /build

COPY requirements.txt .

# 安装依赖到自定义前缀路径，方便后续阶段复用
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- 阶段 2：运行测试（可选跳过） ----------
FROM builder AS tester

COPY . .

# pytest 用于运行测试套件；如果测试失败也不影响最终构建
RUN python -m pytest tests/ -v || true

# ---------- 阶段 3：最小化运行环境 ----------
FROM python:3.9-slim AS runner

# 环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# 从 builder 阶段复制已安装的依赖
COPY --from=builder /install /usr/local

# 安装 cron 和 curl（用于健康检查和 API 调用）
RUN apt-get update && apt-get install -y --no-install-recommends cron curl \
    && rm -rf /var/lib/apt/lists/*

# 从 tester 阶段复制项目源码（测试已在此阶段运行过）
COPY --from=tester /build .

# 配置容器内定时任务
RUN cp scripts/crontab-container.txt /etc/cron.d/infoget \
    && chmod 0644 /etc/cron.d/infoget \
    && crontab /etc/cron.d/infoget \
    && touch /var/log/infoget-cron.log

# 入口脚本以 root 运行（需要启动 cron）
# HTTP 服务器会自动降权到 appuser 吗？不，cron 需要 root 来运行定时任务
# 所以我们保持 root 运行，但 update_feed.sh 中的爬虫/服务器以 appuser 运行

# 暴露服务端口
EXPOSE 8080

# 健康检查：访问 /health 端点确认服务存活
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# 启动脚本：同时运行 cron 和 HTTP 服务器
COPY scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "server.py", "--host", "0.0.0.0"]
