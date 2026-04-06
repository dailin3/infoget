"""
Qwen Code Docs 博客爬虫
----------------------
用于爬取 Qwen Code Docs 博客列表页面，提取文章信息。

主要功能：
1. 请求博客列表页面
2. 解析 HTML，提取文章链接、标题、日期等信息
3. 访问每篇文章详情页，获取完整信息（作者、摘要等）
4. 支持数据库持久化，实现增量更新和去重
"""

import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# 可选导入数据库模块
try:
    from .database import InfoGetDB
except ImportError:
    InfoGetDB = None


class Article:
    """
    文章数据类
    ----------
    用于存储单篇文章的元数据信息。
    
    属性:
        title: 文章标题
        url: 文章完整链接URL
        pub_date: 发布日期 (datetime 对象或字符串)
        author: 作者名称
        summary: 文章摘要/描述
    """
    
    def __init__(
        self,
        title: str = "",
        url: str = "",
        pub_date: str = "",
        author: str = "",
        summary: str = ""
    ):
        self.title = title
        self.url = url
        self.pub_date = pub_date
        self.author = author
        self.summary = summary
    
    def __repr__(self) -> str:
        """字符串表示，方便调试"""
        return f"Article(title='{self.title}', url='{self.url}')"
    
    def to_dict(self) -> dict:
        """转换为字典格式，便于后续处理"""
        return {
            "title": self.title,
            "url": self.url,
            "pub_date": self.pub_date,
            "author": self.author,
            "summary": self.summary,
        }


class QwenBlogScraper:
    """
    Qwen Code Docs 博客爬虫
    ----------------------
    负责爬取博客列表页面和文章详情页。
    
    使用方法:
        scraper = QwenBlogScraper()
        articles = scraper.scrape()
    """
    
    # 基础 URL，用于拼接相对路径
    BASE_URL = "https://qwenlm.github.io"
    
    # 博客列表页 URL
    BLOG_LIST_URL = "https://qwenlm.github.io/qwen-code-docs/zh/blog/"
    
    def __init__(self, delay: float = 1.0, db_path: str = None, use_db: bool = True):
        """
        初始化爬虫

        参数:
            delay: 每次请求之间的延迟（秒），避免对服务器造成压力
            db_path: 数据库文件路径，如果为 None 则使用默认路径
            use_db: 是否启用数据库持久化，默认 True
        """
        self.delay = delay
        self.use_db = use_db and InfoGetDB is not None
        self.db: Optional[InfoGetDB] = None

        if self.use_db:
            try:
                self.db = InfoGetDB(db_path) if db_path else InfoGetDB()
                print(f"[数据库] 已连接: {self.db.db_path}")
            except Exception as e:
                print(f"[警告] 数据库初始化失败，将禁用数据库功能: {e}")
                self.use_db = False
                self.db = None

        # 创建 Session 对象，复用 TCP 连接，提高性能
        self.session = requests.Session()
        # 设置 User-Agent，模拟浏览器访问
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
    
    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        获取网页内容并解析为 BeautifulSoup 对象
        
        参数:
            url: 要抓取的网页 URL
            
        返回:
            BeautifulSoup 对象，如果请求失败则返回 None
        """
        try:
            print(f"  [请求] {url}")
            response = self.session.get(url, timeout=30)
            # 检查 HTTP 状态码
            response.raise_for_status()
            # 使用 lxml 解析器（性能更好）
            soup = BeautifulSoup(response.text, "lxml")
            return soup
        except requests.RequestException as e:
            print(f"  [错误] 请求失败: {e}")
            return None
    
    def _extract_date_from_url(self, url: str) -> str:
        """
        从 URL 中提取日期（如果 URL 包含日期信息）
        
        许多博客 URL 格式为: /blog/2024/01/15/some-title/
        或文件名包含日期: 2024-01-15-some-title.md
        
        参数:
            url: 文章 URL
            
        返回:
            提取到的日期字符串，格式为 YYYY-MM-DD；如果无法提取则返回空字符串
        """
        # 尝试匹配 URL 中的日期模式 YYYY/MM/DD 或 YYYY-MM-DD
        date_patterns = [
            r"(\d{4})/(\d{2})/(\d{2})",
            r"(\d{4})-(\d{2})-(\d{2})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, url)
            if match:
                return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return ""
    
    def _parse_list_page(self, soup: BeautifulSoup) -> list[dict]:
        """
        解析博客列表页，提取文章链接和基本信息

        参数:
            soup: 列表页的 BeautifulSoup 对象

        返回:
            包含文章信息的字典列表，每个字典包含:
                - title: 文章标题
                - url: 文章 URL（可能是相对路径）
                - date: 发布日期（如果有）
                - summary: 摘要（如果有）
                - author: 作者（如果有）
        """
        articles = []

        # 查找所有文章链接
        # 该网站使用 Nextra 框架，每篇文章是一个 <a> 标签包裹整个卡片
        # <a class="group flex items-start gap-6 ..." href="/qwen-code-docs/zh/blog/...">
        #   <div> 日期卡片 </div>
        #   <div>
        #     <div> 标签 </div>
        #     <h3> 标题 </h3>
        #     <p> 摘要 </p>
        #     <div> 作者 </div>
        #   </div>
        # </a>
        article_links = []

        # 尝试查找 main 区域内的文章卡片链接
        for selector in [
            "main > div > div > a[href*='/blog/']",  # Nextra 博客卡片链接
            "main a[href*='/blog/']",                 # 兜底：所有包含 /blog/ 的链接
        ]:
            links = soup.select(selector)
            if links:
                article_links = links
                print(f"  [信息] 使用选择器 '{selector}' 找到 {len(links)} 个链接")
                break

        # 去重：避免重复提取相同链接
        seen_urls = set()

        for link in article_links:
            href = link.get("href", "").strip()

            # 跳过空链接、锚点链接、外部链接、JavaScript 链接
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            if href.startswith("http") and not href.startswith(self.BASE_URL):
                continue

            # 确保是博客文章链接
            if "/blog/" not in href:
                continue

            # 去重
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # 构建完整 URL
            full_url = urljoin(self.BASE_URL, href) if not href.startswith("http") else href

            # --- 提取标题：优先查找 <h3> 标签 ---
            title = ""
            h3 = link.find("h3")
            if h3:
                title = h3.get_text(strip=True)
            else:
                # 兜底：使用链接文本
                title = link.get_text(strip=True)

            # --- 提取摘要：查找 <p> 标签 ---
            summary = ""
            p_tag = link.find("p")
            if p_tag:
                summary = p_tag.get_text(strip=True)

            # --- 提取作者：查找包含用户图标的兄弟元素中的 span ---
            author = ""
            # 作者信息通常在包含 lucide-user 图标的 div 内的 span 中
            user_icon = link.find("svg", class_=lambda c: c and "lucide-user" in c)
            if user_icon:
                # 找到图标旁边的 span
                author_span = user_icon.find_next_sibling("span")
                if author_span:
                    author = author_span.get_text(strip=True)

            # --- 提取日期 ---
            date = ""
            # 桌面版：27 和 3月 分别在两个 span 中
            date_spans = link.select("div.hidden.sm\\/flex span")
            if len(date_spans) >= 2:
                day = date_spans[0].get_text(strip=True)
                month = date_spans[1].get_text(strip=True)
                if day and month:
                    date = f"{month}{day}日"
            else:
                # 移动版：直接找包含日期的 span
                mobile_date = link.select_one("span.sm\\:hidden")
                if mobile_date:
                    date = mobile_date.get_text(strip=True)

            # 也尝试从 URL 提取标准日期格式作为补充
            url_date = self._extract_date_from_url(href)
            if not date and url_date:
                date = url_date

            articles.append({
                "title": title,
                "url": full_url,
                "date": date,
                "summary": summary,
                "author": author,
            })

        return articles
    
    def _parse_article_detail(
        self, soup: BeautifulSoup, article: Article
    ) -> Article:
        """
        解析文章详情页，提取更多信息（作者、完整摘要等）
        
        参数:
            soup: 文章详情页的 BeautifulSoup 对象
            article: 已有的 Article 对象（包含基本信息）
            
        返回:
            更新后的 Article 对象
        """
        # 提取标题（如果之前没有）
        if not article.title:
            # 尝试从 <h1> 或 <title> 标签获取
            h1 = soup.find("h1")
            if h1:
                article.title = h1.get_text(strip=True)
            else:
                title_tag = soup.find("title")
                if title_tag:
                    article.title = title_tag.get_text(strip=True)
        
        # 提取作者
        if not article.author:
            # 常见的作者位置
            for selector in [
                ".author",
                ".post-author",
                ".byline",
                "meta[name='author']",
                "[rel='author']",
            ]:
                if selector.startswith("meta"):
                    meta = soup.find("meta", attrs={"name": "author"})
                    if meta and meta.get("content"):
                        article.author = meta["content"]
                        break
                else:
                    author_elem = soup.select_one(selector)
                    if author_elem:
                        article.author = author_elem.get_text(strip=True)
                        break
            
            # 如果还是没找到，尝试从 Open Graph meta 标签获取
            if not article.author:
                og_author = soup.find("meta", attrs={"property": "og:author"})
                if og_author and og_author.get("content"):
                    article.author = og_author["content"]
        
        # 提取摘要/描述（如果之前没有）
        if not article.summary:
            # 尝试从 meta description 获取
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                article.summary = meta_desc["content"]
            
            # 尝试从 Open Graph description 获取
            if not article.summary:
                og_desc = soup.find("meta", attrs={"property": "og:description"})
                if og_desc and og_desc.get("content"):
                    article.summary = og_desc["content"]
            
            # 尝试从文章开头的 <p> 标签获取
            if not article.summary:
                article_elem = soup.find("article") or soup.find("main")
                if article_elem:
                    first_p = article_elem.find("p")
                    if first_p:
                        article.summary = first_p.get_text(strip=True)[:300]  # 限制长度
        
        # 提取发布日期（如果之前没有）
        if not article.pub_date:
            # 尝试从 <time> 标签获取
            time_tag = soup.find("time")
            if time_tag:
                # 优先使用 datetime 属性
                if time_tag.get("datetime"):
                    article.pub_date = time_tag["datetime"]
                else:
                    article.pub_date = time_tag.get_text(strip=True)
            
            # 尝试从 meta 标签获取
            if not article.pub_date:
                meta_date = soup.find("meta", attrs={"property": "article:published_time"})
                if meta_date and meta_date.get("content"):
                    article.pub_date = meta_date["content"]
            
            # 尝试从 Open Graph 获取
            if not article.pub_date:
                og_date = soup.find("meta", attrs={"property": "og:article:published_time"})
                if og_date and og_date.get("content"):
                    article.pub_date = og_date["content"]
        
        return article
    
    def scrape(self, scrape_detail: bool = True) -> list[Article]:
        """
        执行爬取任务的主方法

        参数:
            scrape_detail: 是否访问每篇文章的详情页获取更多信息
                          设为 False 可以加快爬取速度，但信息可能不完整

        返回:
            Article 对象列表
        """
        print("=" * 60)
        print("开始爬取 Qwen Code Docs 博客...")
        print("=" * 60)

        # 记录爬取开始时间
        start_time = time.time()
        crawl_id = None
        mode = "full" if scrape_detail else "quick"

        # 如果启用数据库，创建爬取记录
        if self.use_db and self.db:
            crawl_id = self.db.begin_crawl(mode=mode)
            print(f"[数据库] 爬取记录 ID: {crawl_id}")

        # 统计信息
        stats = {
            "total_found": 0,
            "new_count": 0,
            "updated_count": 0,
            "exists_count": 0,
            "failed_count": 0,
        }

        try:
            # 步骤 1：获取列表页
            print("\n[步骤 1] 获取博客列表页...")
            soup = self._fetch_page(self.BLOG_LIST_URL)
            if not soup:
                print("[错误] 无法获取列表页，请检查网络连接或 URL 是否正确")
                if self.use_db and self.db and crawl_id:
                    duration = time.time() - start_time
                    self.db.finish_crawl(crawl_id, status="failed",
                                         error_detail="无法获取列表页", duration=duration)
                return []

            # 步骤 2：解析列表页
            print("\n[步骤 2] 解析列表页，提取文章链接...")
            raw_articles = self._parse_list_page(soup)
            stats["total_found"] = len(raw_articles)
            print(f"  [结果] 共找到 {len(raw_articles)} 篇文章")

            if not raw_articles:
                print("[警告] 未找到文章，可能是页面结构发生变化")
                print(f"  [调试] 页面标题: {soup.title.string if soup.title else '未知'}")
                if self.use_db and self.db and crawl_id:
                    duration = time.time() - start_time
                    self.db.finish_crawl(crawl_id, status="success", duration=duration)
                    self.db.update_crawl_stats(crawl_id, **stats)
                return []

            # 更新数据库统计
            if self.use_db and self.db and crawl_id:
                self.db.update_crawl_stats(crawl_id, total_found=stats["total_found"])

            # 步骤 3：访问详情页（可选）
            articles = []
            if scrape_detail and len(raw_articles) > 0:
                print(f"\n[步骤 3] 访问每篇文章详情页，获取完整信息...")
                for i, raw in enumerate(raw_articles, 1):
                    print(f"\n  [{i}/{len(raw_articles)}] 处理: {raw['title'] or raw['url']}")

                    # 创建 Article 对象
                    article = Article(
                        title=raw["title"],
                        url=raw["url"],
                        pub_date=raw["date"],
                        summary=raw["summary"],
                        author=raw.get("author", ""),
                    )

                    # 访问详情页
                    detail_soup = self._fetch_page(raw["url"])
                    if detail_soup:
                        article = self._parse_article_detail(detail_soup, article)

                    # 如果启用数据库，保存或更新文章
                    if self.use_db and self.db:
                        try:
                            result = self.db.upsert_article(article.to_dict())
                            if result == "new":
                                stats["new_count"] += 1
                                print(f"    [数据库] ✅ 新增文章")
                            elif result == "updated":
                                stats["updated_count"] += 1
                                print(f"    [数据库] 🔄 更新文章")
                            else:
                                stats["exists_count"] += 1
                                print(f"    [数据库] ⏭️  已存在，跳过")
                        except Exception as e:
                            stats["failed_count"] += 1
                            print(f"    [数据库] ❌ 保存失败: {e}")
                            if crawl_id:
                                self.db.add_failure(raw["url"], str(e), crawl_id)
                    else:
                        # 不启用数据库，直接添加到列表
                        pass

                    articles.append(article)

                    # 礼貌延迟，避免对服务器造成压力
                    if i < len(raw_articles):
                        time.sleep(self.delay)
            else:
                # 不访问详情页，直接使用列表页信息
                print("\n[步骤 3] 跳过详情页，使用列表页信息...")
                for raw in raw_articles:
                    article = Article(
                        title=raw["title"],
                        url=raw["url"],
                        pub_date=raw["date"],
                        summary=raw["summary"],
                        author=raw.get("author", ""),
                    )

                    # 如果启用数据库，保存或更新文章
                    if self.use_db and self.db:
                        try:
                            result = self.db.upsert_article(article.to_dict())
                            if result == "new":
                                stats["new_count"] += 1
                            elif result == "updated":
                                stats["updated_count"] += 1
                            else:
                                stats["exists_count"] += 1
                        except Exception as e:
                            stats["failed_count"] += 1
                            if crawl_id:
                                self.db.add_failure(raw["url"], str(e), crawl_id)

                    articles.append(article)

            # 爬取完成，更新数据库
            duration = time.time() - start_time
            if self.use_db and self.db and crawl_id:
                # 确定最终状态
                status = "success" if stats["failed_count"] == 0 else "partial"
                self.db.finish_crawl(crawl_id, status=status, duration=duration)
                self.db.update_crawl_stats(crawl_id, **stats)

            print(f"\n{'=' * 60}")
            print(f"爬取完成！共获取 {len(articles)} 篇文章")
            if self.use_db:
                print(f"  新增: {stats['new_count']} | 更新: {stats['updated_count']} | 已存在: {stats['exists_count']} | 失败: {stats['failed_count']}")
                print(f"  耗时: {duration:.2f} 秒")
            print(f"{'=' * 60}")

            return articles

        except Exception as e:
            # 发生异常，记录失败
            duration = time.time() - start_time
            if self.use_db and self.db and crawl_id:
                self.db.finish_crawl(crawl_id, status="failed",
                                     error_detail=str(e), duration=duration)
            raise
    
    def close(self):
        """关闭 Session 和数据库连接，释放资源"""
        self.session.close()
        if self.db:
            self.db.close()
