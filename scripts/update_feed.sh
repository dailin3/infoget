#!/bin/bash
# ============================================================
# InfoGet 定时更新脚本
# ============================================================
# 用途: 定时爬取博客文章并更新 RSS Feed
# 用法:
#   手动运行: ./scripts/update_feed.sh
#   容器内:   docker exec <容器> bash scripts/update_feed.sh --cron
#   crontab:  自动调用（已配置 cron）
#
# 日志输出:
#   --cron 模式: 追加到 /var/log/infoget-cron.log
#   手动模式:    输出到标准输出
# ============================================================

set -euo pipefail

# ---------- 配置 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CRON_MODE=false
LOG_FILE="/var/log/infoget-cron.log"
MODE="${INFOGET_MODE:-quick}"

# ---------- 参数解析 ----------
for arg in "$@"; do
    case "$arg" in
        --cron) CRON_MODE=true ;;
    esac
done

# ---------- 函数 ----------
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    if [ "$CRON_MODE" = true ]; then
        echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

check_docker() {
    if command -v docker &>/dev/null && command -v docker compose &>/dev/null; then
        echo "docker"
    elif command -v docker-compose &>/dev/null; then
        echo "docker-compose-v1"
    else
        echo "none"
    fi
}

# ---------- 主逻辑 ----------
main() {
    log "========== InfoGet 更新开始 =========="
    log "项目目录: $PROJECT_DIR"
    log "爬取模式: $MODE"

    # 进入项目目录
    cd "$PROJECT_DIR"

    # 检查 Docker 是否可用
    local docker_type
    docker_type=$(check_docker)

    if [ "$docker_type" = "docker" ]; then
        log "使用 Docker Compose (v2)"
        # 检查容器是否运行中
        if docker compose ps --services 2>/dev/null | grep -q infoget; then
            log "容器正在运行，从数据库重新生成 RSS Feed..."
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

if not articles:
    print('[错误] 数据库中没有文章，请先爬取数据')
    exit(1)

gen = RSSGenerator(
    title='Qwen Code Docs 博客',
    link='https://qwenlm.github.io/qwen-code-docs/zh/blog/',
    description='Qwen Code 官方文档博客文章的 RSS 订阅源',
    language='zh-CN',
    author='Qwen Team',
)
rss = gen.generate(articles)
gen.save_to_file(rss, 'output/feed.xml')
print(f'✅ 从数据库重新生成 RSS: {len(articles)} 篇文章')
" 2>&1 || {
                log "[错误] RSS 重新生成失败"
                return 1
            }
        else
            log "容器未运行，先启动服务..."
            docker compose up -d
            sleep 5
            docker compose exec -T infoget python main.py --"$MODE" 2>&1 || {
                log "[错误] 容器内爬虫执行失败"
                return 1
            }
        fi

    elif [ "$docker_type" = "docker-compose-v1" ]; then
        log "使用 Docker Compose (v1)"
        if docker-compose ps --services 2>/dev/null | grep -q infoget; then
            log "容器正在运行，从数据库重新生成 RSS Feed..."
            docker-compose exec -T infoget python -c "
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

if not articles:
    print('[错误] 数据库中没有文章，请先爬取数据')
    exit(1)

gen = RSSGenerator(
    title='Qwen Code Docs 博客',
    link='https://qwenlm.github.io/qwen-code-docs/zh/blog/',
    description='Qwen Code 官方文档博客文章的 RSS 订阅源',
    language='zh-CN',
    author='Qwen Team',
)
rss = gen.generate(articles)
gen.save_to_file(rss, 'output/feed.xml')
print(f'✅ 从数据库重新生成 RSS: {len(articles)} 篇文章')
" 2>&1 || {
                log "[错误] RSS 重新生成失败"
                return 1
            }
        else
            log "容器未运行，先启动服务..."
            docker-compose up -d
            sleep 5
            docker-compose exec -T infoget python main.py --"$MODE" 2>&1 || {
                log "[错误] 容器内爬虫执行失败"
                return 1
            }
        fi

    else
        log "Docker 不可用，尝试直接运行 Python..."
        if command -v python3 &>/dev/null; then
            python3 -c "
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

if not articles:
    print('[错误] 数据库中没有文章，请先爬取数据')
    exit(1)

gen = RSSGenerator(
    title='Qwen Code Docs 博客',
    link='https://qwenlm.github.io/qwen-code-docs/zh/blog/',
    description='Qwen Code 官方文档博客文章的 RSS 订阅源',
    language='zh-CN',
    author='Qwen Team',
)
rss = gen.generate(articles)
gen.save_to_file(rss, 'output/feed.xml')
print(f'✅ 从数据库重新生成 RSS: {len(articles)} 篇文章')
" 2>&1 || {
                log "[错误] Python RSS 生成失败"
                return 1
            }
            # 如果服务器未运行，启动它
            if ! curl -s "http://localhost:8080/health" &>/dev/null; then
                log "HTTP 服务器未运行，启动中..."
                nohup python3 server.py --host 0.0.0.0 --port 8080 &>/dev/null &
                sleep 3
            fi
        else
            log "[错误] 既没有 Docker 也没有 Python3，无法继续"
            return 1
        fi
    fi

    # 验证 RSS Feed 是否已更新
    local retry=0
    local max_retry=3
    while [ $retry -lt $max_retry ]; do
        sleep 2
        if curl -sf "http://localhost:8080/feed" 2>/dev/null | head -1 | grep -q "<?xml"; then
            log "✅ RSS Feed 更新成功"
            break
        fi
        ((retry++))
        log "⚠️  RSS Feed 验证中... 尝试 $retry/$max_retry"
    done
    if [ $retry -eq $max_retry ]; then
        log "⚠️  RSS Feed 验证失败，请检查日志"
    fi

    # 显示统计信息
    local stats
    stats=$(curl -s "http://localhost:8080/api/stats" 2>/dev/null || echo "无法获取统计")
    log "统计信息: $stats"

    log "========== InfoGet 更新完成 =========="
}

main "$@"
