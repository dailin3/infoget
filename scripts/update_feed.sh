#!/bin/bash
# ============================================================
# InfoGet 定时更新脚本
# ============================================================
# 用途: 定时爬取博客文章并更新 RSS Feed
# 用法:
#   手动运行: ./scripts/update_feed.sh
#   或通过 crontab 自动调用
#
# 日志输出到: /var/log/infoget-crawl.log (cron模式) 或 标准输出 (手动模式)
# ============================================================

set -euo pipefail

# ---------- 配置 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/var/log/infoget-crawl.log"
MODE="${INFOGET_MODE:-quick}"
SERVER_HOST="${INFOGET_SERVER_HOST:-0.0.0.0}"
SERVER_PORT="${INFOGET_SERVER_PORT:-8080}"

# ---------- 函数 ----------
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    # 如果以 cron 方式运行（无终端），追加到日志文件
    if [ ! -t 1 ]; then
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
            log "容器正在运行，在容器内执行爬虫..."
            docker compose exec -T infoget python main.py --"$MODE" 2>&1 || {
                log "[错误] 容器内爬虫执行失败"
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
            log "容器正在运行，在容器内执行爬虫..."
            docker-compose exec -T infoget python main.py --"$MODE" 2>&1 || {
                log "[错误] 容器内爬虫执行失败"
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
            python3 main.py --"$MODE" 2>&1 || {
                log "[错误] Python 爬虫执行失败"
                return 1
            }
            # 如果服务器未运行，启动它
            if ! curl -s "http://localhost:${SERVER_PORT}/health" &>/dev/null; then
                log "HTTP 服务器未运行，启动中..."
                nohup python3 server.py --host "$SERVER_HOST" --port "$SERVER_PORT" &>/dev/null &
                sleep 3
            fi
        else
            log "[错误] 既没有 Docker 也没有 Python3，无法继续"
            return 1
        fi
    fi

    # 验证 RSS Feed 是否已更新
    if curl -s "http://localhost:${SERVER_PORT}/feed" | head -1 | grep -q "<?xml"; then
        log "✅ RSS Feed 更新成功"
    else
        log "⚠️  RSS Feed 验证失败，请检查日志"
    fi

    # 显示统计信息
    local stats
    stats=$(curl -s "http://localhost:${SERVER_PORT}/api/stats" 2>/dev/null || echo "无法获取统计")
    log "统计信息: $stats"

    log "========== InfoGet 更新完成 =========="
}

main "$@"
