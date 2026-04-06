"""
RSS Feed 生成器
--------------
将爬取到的文章信息转换为标准 RSS 2.0 格式的 XML 文件。

支持两种方式生成 RSS：
1. 使用 feedgen 库（推荐）
2. 手动拼接 XML（备用方案，当 feedgen 不可用时）
"""

import os
from datetime import datetime
from email.utils import formatdate
from typing import Optional
from xml.sax.saxutils import escape

from .scraper import Article


class RSSGenerator:
    """
    RSS Feed 生成器
    --------------
    将 Article 对象列表转换为 RSS 2.0 格式的 XML。
    
    使用方法:
        generator = RSSGenerator()
        xml_content = generator.generate(articles)
        generator.save_to_file(xml_content, "output/feed.xml")
    """
    
    def __init__(
        self,
        title: str = "Qwen Code Docs 博客",
        link: str = "https://qwenlm.github.io/qwen-code-docs/zh/blog/",
        description: str = "Qwen Code 官方文档博客文章",
        language: str = "zh-CN",
        author: str = "Qwen Team",
    ):
        """
        初始化 RSS 生成器
        
        参数:
            title: Feed 标题
            link: Feed 链接
            description: Feed 描述
            language: 语言代码
            author: 作者/发布者
        """
        self.title = title
        self.link = link
        self.description = description
        self.language = language
        self.author = author
    
    def _try_feedgen(self, articles: list[Article]) -> Optional[str]:
        """
        尝试使用 feedgen 库生成 RSS
        
        参数:
            articles: Article 对象列表
            
        返回:
            RSS XML 字符串，如果 feedgen 不可用则返回 None
        """
        try:
            from feedgen.feed import FeedGenerator
            
            fg = FeedGenerator()
            fg.title(self.title)
            fg.link(href=self.link, rel="self")
            fg.description(self.description)
            fg.language(self.language)
            fg.author({"name": self.author})
            
            # 设置最后构建时间
            fg.lastBuildDate(datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))
            
            # 添加每篇文章作为 entry
            for article in articles:
                fe = fg.add_entry()
                fe.title(article.title or "无标题")
                fe.link(href=article.url)
                fe.description(article.summary or "")
                
                # 设置作者（如果有）
                if article.author:
                    fe.author({"name": article.author})
                
                # 设置发布日期
                if article.pub_date:
                    # 尝试解析日期并格式化
                    try:
                        # 支持多种日期格式
                        pub_date = article.pub_date
                        if isinstance(pub_date, str):
                            # 尝试解析 ISO 格式
                            if "T" in pub_date:
                                dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                            else:
                                dt = datetime.strptime(pub_date[:10], "%Y-%m-%d")
                        else:
                            dt = pub_date
                        
                        fe.pubDate(dt.strftime("%a, %d %b %Y %H:%M:%S +0000"))
                    except (ValueError, TypeError):
                        # 日期格式不匹配，使用原始值
                        pass
                
                # 设置 guid（唯一标识符）
                fe.guid(article.url, permalink=True)
            
            # 生成 RSS 2.0 XML
            return fg.rss_str(pretty=True).decode("utf-8")
            
        except ImportError:
            print("[信息] feedgen 库未安装，使用手动拼接方式生成 RSS")
            return None
        except Exception as e:
            print(f"[警告] feedgen 生成 RSS 失败: {e}，使用手动拼接方式")
            return None
    
    def _manual_rss(self, articles: list[Article]) -> str:
        """
        手动拼接 RSS 2.0 XML（备用方案）
        
        参数:
            articles: Article 对象列表
            
        返回:
            RSS XML 字符串
        """
        # RSS 2.0 头部
        rss_header = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>{escape(self.title)}</title>
    <link>{escape(self.link)}</link>
    <description>{escape(self.description)}</description>
    <language>{self.language}</language>
    <lastBuildDate>{formatdate(timeval=None, localtime=False, usegmt=True)}</lastBuildDate>
    <atom:link href="{escape(self.link)}" rel="self" type="application/rss+xml"/>
    <generator>Qwen Blog RSS Generator (Python)</generator>
'''
        
        # 生成每篇文章的 item
        items = []
        for article in articles:
            # 格式化发布日期
            pub_date = ""
            if article.pub_date:
                try:
                    pub_date_str = article.pub_date
                    if isinstance(pub_date_str, str):
                        if "T" in pub_date_str:
                            dt = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                        else:
                            dt = datetime.strptime(pub_date_str[:10], "%Y-%m-%d")
                    else:
                        dt = pub_date_str
                    pub_date = formatdate(
                        timeval=dt.timestamp(), localtime=False, usegmt=True
                    )
                except (ValueError, TypeError, AttributeError):
                    pub_date = ""
            
            # 构建 item XML
            item_parts = [
                "    <item>",
                f"      <title>{escape(article.title or '无标题')}</title>",
                f"      <link>{escape(article.url)}</link>",
                f"      <description>{escape(article.summary or '')}</description>",
            ]
            
            # 添加作者
            if article.author:
                item_parts.append(f"      <dc:creator>{escape(article.author)}</dc:creator>")
            
            # 添加发布日期
            if pub_date:
                item_parts.append(f"      <pubDate>{pub_date}</pubDate>")
            
            # 添加 guid（唯一标识符）
            item_parts.append(
                f'      <guid isPermaLink="true">{escape(article.url)}</guid>'
            )
            
            item_parts.append("    </item>")
            items.append("\n".join(item_parts))
        
        # RSS 尾部
        rss_footer = """  </channel>
</rss>"""
        
        # 拼接完整 RSS XML
        return "\n".join([rss_header, "\n".join(items), rss_footer])
    
    def generate(self, articles: list[Article]) -> str:
        """
        生成 RSS XML 字符串
        
        优先使用 feedgen 库，如果不可用则使用手动拼接方式。
        
        参数:
            articles: Article 对象列表
            
        返回:
            RSS XML 字符串
        """
        print("\n[信息] 开始生成 RSS XML...")
        
        # 优先尝试使用 feedgen
        rss_content = self._try_feedgen(articles)
        
        # 如果 feedgen 失败，使用手动拼接
        if rss_content is None:
            rss_content = self._manual_rss(articles)
        
        print(f"[信息] RSS 生成完成，共 {len(articles)} 篇文章")
        return rss_content
    
    @staticmethod
    def save_to_file(content: str, filepath: str) -> str:
        """
        将 RSS XML 保存到文件
        
        参数:
            content: RSS XML 字符串
            filepath: 输出文件路径
            
        返回:
            输出文件的绝对路径
        """
        # 确保输出目录存在
        output_dir = os.path.dirname(filepath)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 写入文件
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        abs_path = os.path.abspath(filepath)
        print(f"[信息] RSS 文件已保存: {abs_path}")
        return abs_path
