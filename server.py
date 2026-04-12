#!/usr/bin/env python3
"""
RSS Feed 服务器启动入口
=====================
独立的服务器启动脚本，可以单独运行。

使用方法:
    # 默认启动（端口 8080）
    python server.py

    # 指定端口
    python server.py --port 9000

    # 指定绑定地址
    python server.py --host 127.0.0.1

    # 指定 RSS 文件路径
    python server.py --feed output/feed.xml

依赖:
    仅使用 Python 标准库，无需额外安装依赖
"""

import argparse
import os
import sys
from datetime import datetime

# 将项目根目录添加到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from scraper.scraper import QwenBlogScraper
from scraper.rss_generator import RSSGenerator
from scraper.server import run_server


def check_and_generate_feed(feed_path: str) -> bool:
    """
    检查 RSS 文件是否存在，不存在则运行爬虫生成

    参数:
        feed_path: RSS 文件路径

    返回:
        True 表示文件存在或生成成功，False 表示生成失败
    """
    if os.path.exists(feed_path):
        print(f"✅ RSS 文件已存在: {feed_path}")
        # 显示文件信息
        stat = os.stat(feed_path)
        file_size = stat.st_size
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"   大小: {file_size / 1024:.1f} KB")
        print(f"   修改时间: {modified}")
        return True

    print("\n⚠️  RSS 文件不存在，正在运行爬虫生成...")
    print(f"   目标路径: {feed_path}")

    try:
        # 运行爬虫
        scraper = QwenBlogScraper(delay=1.0)
        try:
            articles = scraper.scrape(scrape_detail=False)

            if not articles:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [错误] 爬虫未获取到文章，无法生成 RSS")
                return False

            # 生成 RSS
            generator = RSSGenerator(
                title="Qwen Code Docs 博客",
                link="https://qwenlm.github.io/qwen-code-docs/zh/blog/",
                description="Qwen Code 官方文档博客文章的 RSS 订阅源",
                language="zh-CN",
                author="Qwen Team",
            )

            rss_content = generator.generate(articles)
            generator.save_to_file(rss_content, feed_path)

            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ RSS 文件生成成功: {feed_path}")
            return True

        finally:
            scraper.close()

    except Exception as e:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [错误] 生成 RSS 文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="启动本地 RSS Feed 服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python server.py                      # 默认启动（端口 8080）
  python server.py --port 9000          # 指定端口
  python server.py --host 127.0.0.1     # 仅本地访问
  python server.py --feed my_feed.xml   # 指定 RSS 文件
        """,
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="服务器监听端口（默认: 8080）",
    )

    parser.add_argument(
        "--host", "-H",
        type=str,
        default="0.0.0.0",
        help="服务器绑定地址（默认: 0.0.0.0，仅本地访问请使用 127.0.0.1）",
    )

    parser.add_argument(
        "--feed", "-f",
        type=str,
        default="output/feed.xml",
        help="RSS 文件路径（默认: output/feed.xml）",
    )

    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="跳过 RSS 文件检查（不自动生成，直接启动）",
    )

    parser.add_argument(
        "--db",
        type=str,
        default="data/infoget.db",
        help="SQLite 数据库路径（默认: data/infoget.db，留空 \"\" 禁用）",
    )

    return parser.parse_args()


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()

    print("=" * 60)
    print("🚀 Qwen Code Docs RSS Feed 服务器")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"绑定地址: {args.host}")
    print(f"监听端口: {args.port}")
    print(f"Feed 路径: {args.feed}")
    print("=" * 60)

    # 检查 RSS 文件
    if not args.skip_check:
        if not check_and_generate_feed(args.feed):
            print("\n[错误] 无法继续：RSS 文件不存在且生成失败")
            print("提示: 请先运行 python main.py 生成 RSS 文件")
            return 1
    else:
        if not os.path.exists(args.feed):
            print(f"\n[警告] RSS 文件不存在: {args.feed}")
            print("提示: 访问 /feed 将返回 404 错误")

    # 启动服务器
    try:
        db_path = args.db if args.db else None
        run_server(
            host=args.host,
            port=args.port,
            feed_path=args.feed,
            db_path=db_path,
            block=True,
        )
        return 0
    except Exception as e:
        print(f"\n[错误] 服务器启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
