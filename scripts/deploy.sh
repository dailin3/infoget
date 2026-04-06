#!/bin/bash
# ============================================================
# InfoGet 服务器一键部署脚本
# ============================================================
# 用途: 在服务器上首次部署 InfoGet 服务
# 用法:
#   ssh user@your-server "bash -s" < scripts/deploy.sh
#   或在服务器上直接运行: bash scripts/deploy.sh
# ============================================================

set -euo pipefail

# ---------- 颜色输出 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------- 配置 ----------
DEPLOY_DIR="${INFOGET_DEPLOY_DIR:-/opt/infoget}"
SERVER_PORT="${INFOGET_SERVER_PORT:-8080}"

# ---------- 检查依赖 ----------
check_prerequisites() {
    info "检查运行环境..."

    if [ "$(id -u)" -ne 0 ]; then
        error "请使用 root 用户或 sudo 运行此脚本"
        exit 1
    fi

    # 检查 Docker
    if ! command -v docker &>/dev/null; then
        warn "Docker 未安装，正在安装..."
        curl -fsSL https://get.docker.com | sh
        systemctl enable docker
        systemctl start docker
    fi
    info "Docker 版本: $(docker --version)"

    # 检查 Docker Compose
    if ! docker compose version &>/dev/null; then
        warn "Docker Compose v2 未安装，正在安装..."
        apt-get update && apt-get install -y docker-compose-plugin 2>/dev/null || {
            warn "无法通过包管理器安装 Docker Compose，尝试手动安装..."
            local compose_url="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)"
            curl -fsSL "$compose_url" -o /usr/local/lib/docker/cli-plugins/docker-compose
            chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
        }
    fi
    info "Docker Compose 版本: $(docker compose version 2>/dev/null || echo '未安装')"
}

# ---------- 部署项目 ----------
deploy_project() {
    info "部署项目到 $DEPLOY_DIR ..."

    # 创建目录
    mkdir -p "$DEPLOY_DIR"

    # 检查项目文件是否存在
    if [ ! -f "$DEPLOY_DIR/Dockerfile" ]; then
        error "项目文件不存在于 $DEPLOY_DIR"
        error "请先将项目文件上传到此目录，再运行此脚本"
        exit 1
    fi

    # 创建必要的目录
    mkdir -p "$DEPLOY_DIR/data" "$DEPLOY_DIR/output"

    # 设置权限
    chmod +x "$DEPLOY_DIR/scripts/update_feed.sh"
    chmod +x "$DEPLOY_DIR/scripts/deploy.sh"

    info "项目文件检查通过"
}

# ---------- 启动服务 ----------
start_services() {
    info "启动 InfoGet 服务..."

    cd "$DEPLOY_DIR"

    # 构建并启动
    docker compose up -d --build
    if [ $? -ne 0 ]; then
        error "Docker Compose 启动失败"
        exit 1
    fi

    # 等待服务就绪
    info "等待服务启动 (10 秒)..."
    sleep 10

    # 健康检查
    local retries=5
    local attempt=1
    while [ $attempt -le $retries ]; do
        if curl -sf "http://localhost:${SERVER_PORT}/health" &>/dev/null; then
            info "✅ 服务健康检查通过"
            break
        fi
        warn "健康检查失败，尝试 $attempt/$retries，等待 5 秒..."
        sleep 5
        ((attempt++))
    done

    if [ $attempt -gt $retries ]; then
        error "服务健康检查最终失败，请查看日志: docker compose logs"
        exit 1
    fi
}

# ---------- 初始化数据 ----------
initialize_data() {
    info "首次爬取博客文章并写入数据库..."

    docker compose exec -T infoget python main.py --quick
    if [ $? -eq 0 ]; then
        info "✅ 初始数据爬取成功，已写入数据库"

        # 从数据库重新生成 RSS，确保一致性
        info "从数据库重新生成 RSS Feed..."
        docker compose exec -T infoget python -c "
from scraper.database import InfoGetDB
from scraper.rss_generator import RSSGenerator
from scraper.scraper import Article

db = InfoGetDB('data/infoget.db')
articles_data = db.get_all_articles(order_by='pub_date DESC')
# 过滤掉数据库字段 id、created_at、updated_at，只保留 Article 需要的字段
articles = []
for a in articles_data:
    articles.append(Article(
        title=a['title'],
        url=a['url'],
        pub_date=a['pub_date'],
        author=a.get('author', ''),
        summary=a.get('summary', ''),
    ))

gen = RSSGenerator(
    title='Qwen Code Docs 博客',
    link='https://qwenlm.github.io/qwen-code-docs/zh/blog/',
    description='Qwen Code 官方文档博客文章的 RSS 订阅源',
    language='zh-CN',
    author='Qwen Team',
)
rss = gen.generate(articles)
gen.save_to_file(rss, 'output/feed.xml')
print(f'✅ 从数据库生成 RSS: {len(articles)} 篇文章')
"
    else
        warn "初始爬取失败，您可以稍后手动运行:"
        warn "  docker compose exec infoget python main.py --quick"
    fi
}

# ---------- 提示容器内定时任务 ----------
setup_cron() {
    info "定时任务已内置于 Docker 容器中，无需在宿主机配置"
    info "查看容器内定时任务: docker exec infoget crontab -l"
    info "查看容器内 Cron 日志: docker exec infoget cat /var/log/infoget-cron.log"
}

# ---------- 创建日志文件 ----------
setup_logging() {
    info "设置日志文件..."
    local log_file="/var/log/infoget-crawl.log"
    touch "$log_file"
    chmod 644 "$log_file"
    info "日志文件: $log_file"
}

# ---------- 显示部署信息 ----------
show_summary() {
    echo ""
    info "=========================================="
    info "  InfoGet 部署完成！"
    info "=========================================="
    echo ""
    info "访问地址:"
    info "  📰 状态页面: http://<服务器IP>:$SERVER_PORT/"
    info "  📄 RSS Feed:  http://<服务器IP>:$SERVER_PORT/feed"
    info "  💚 健康检查:  http://<服务器IP>:$SERVER_PORT/health"
    info "  📊 统计信息:  http://<服务器IP>:$SERVER_PORT/api/stats"
    echo ""
    info "常用命令:"
    info "  查看日志:      docker compose logs -f"
    info "  重新爬取:      docker compose exec infoget python main.py --quick"
    info "  重启服务:      docker compose restart"
    info "  停止服务:      docker compose down"
    info "  手动更新:      bash $DEPLOY_DIR/scripts/update_feed.sh"
    echo ""
    info "=========================================="
}

# ---------- 主函数 ----------
main() {
    echo ""
    info "=========================================="
    info "  InfoGet 一键部署脚本"
    info "=========================================="
    echo ""

    check_prerequisites
    deploy_project
    start_services

    # 检查是否已有数据
    if ! curl -sf "http://localhost:${SERVER_PORT}/feed" | grep -q "<item>"; then
        initialize_data
    else
        info "RSS Feed 已存在文章，跳过初始爬取"
    fi

    setup_cron
    setup_logging
    show_summary
}

main "$@"
