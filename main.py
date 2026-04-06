#!/usr/bin/env python3
"""
Qwen Code Docs 博客 RSS 生成器 - 主入口
======================================
爬取 Qwen Code Docs 博客文章，生成标准 RSS 2.0 格式的 XML 文件。

使用方法:
    # 默认模式：爬取列表页 + 访问每篇文章详情页（信息更完整）
    python main.py
    
    # 快速模式：仅爬取列表页，不访问详情页（速度更快）
    python main.py --quick
    
    # 指定输出文件路径
    python main.py --output my_feed.xml
    
    # 调整请求延迟（秒）
    python main.py --delay 2.0

依赖安装:
    pip install -r requirements.txt
"""

import argparse
import os
import sys
from datetime import datetime

# 将项目根目录添加到 Python 路径
# 这样可以直接运行 python main.py 而不需要修改 sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from scraper.scraper import QwenBlogScraper
from scraper.rss_generator import RSSGenerator


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="爬取 Qwen Code Docs 博客文章，生成 RSS Feed",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                      # 默认模式（访问详情页）
  python main.py --quick              # 快速模式（不访问详情页）
  python main.py --output feed.xml    # 指定输出文件名
  python main.py --delay 3            # 设置请求延迟为 3 秒
        """,
    )
    
    parser.add_argument(
        "--quick",
        action="store_true",
        help="快速模式：仅爬取列表页，不访问文章详情页（速度更快，但信息可能不完整）",
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="output/feed.xml",
        help="输出文件路径（默认: output/feed.xml）",
    )
    
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=1.0,
        help="每次请求之间的延迟（秒），默认: 1.0",
    )
    
    return parser.parse_args()


def print_articles(articles):
    """打印爬取到的文章信息，方便调试和查看结果"""
    print("\n" + "=" * 60)
    print("爬取结果预览:")
    print("=" * 60)
    
    for i, article in enumerate(articles, 1):
        print(f"\n[{i}] {article.title or '无标题'}")
        print(f"    链接: {article.url}")
        if article.pub_date:
            print(f"    日期: {article.pub_date}")
        if article.author:
            print(f"    作者: {article.author}")
        if article.summary:
            # 摘要太长时截断显示
            summary = article.summary
            if len(summary) > 100:
                summary = summary[:100] + "..."
            print(f"    摘要: {summary}")
    
    print("\n" + "=" * 60)


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    print("=" * 60)
    print("Qwen Code Docs 博客 RSS 生成器")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模式: {'快速模式（仅列表页）' if args.quick else '完整模式（访问详情页）'}")
    print(f"输出: {args.output}")
    print(f"请求延迟: {args.delay}s")
    print("=" * 60)
    
    # 步骤 1：创建爬虫实例
    scraper = QwenBlogScraper(delay=args.delay)
    
    try:
        # 步骤 2：执行爬取
        # scrape_detail=False 表示不访问每篇文章的详情页
        scrape_detail = not args.quick
        articles = scraper.scrape(scrape_detail=scrape_detail)
        
        # 检查是否爬取到文章
        if not articles:
            print("\n[错误] 未爬取到任何文章，请检查:")
            print("  1. 网络连接是否正常")
            print("  2. 目标网站是否可访问")
            print("  3. 页面结构是否发生变化")
            return 1
        
        # 步骤 3：打印预览
        print_articles(articles)
        
        # 步骤 4：生成 RSS
        generator = RSSGenerator(
            title="Qwen Code Docs 博客",
            link="https://qwenlm.github.io/qwen-code-docs/zh/blog/",
            description="Qwen Code 官方文档博客文章的 RSS 订阅源",
            language="zh-CN",
            author="Qwen Team",
        )
        
        rss_content = generator.generate(articles)
        
        # 步骤 5：保存到文件
        output_path = generator.save_to_file(rss_content, args.output)
        
        # 完成
        print("\n" + "=" * 60)
        print("✅ 全部完成！")
        print(f"   文章数量: {len(articles)}")
        print(f"   RSS 文件: {output_path}")
        print("=" * 60)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n[中断] 用户取消了操作")
        return 1
    except Exception as e:
        print(f"\n[错误] 发生未预期的异常: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # 确保关闭爬虫的 Session
        scraper.close()


if __name__ == "__main__":
    sys.exit(main())
