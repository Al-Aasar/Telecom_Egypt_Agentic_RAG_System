import argparse
import time
import urllib.robotparser as robotparser
from collections import deque
from urllib.parse import urljoin, urlparse
import os
from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup
import psycopg2

START_URL = "https://www.te.eg/"

ALLOWED_NETLOCS = {"te.eg", "www.te.eg"}
CANONICAL_NETLOC = "te.eg"
USER_AGENT = "Mozilla/5.0 (compatible; RAGResearchBot/1.0; +mailto:you@example.com)"
SKIP_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".mp4", ".mp3", ".css", ".js",
)

def can_fetch(url: str) -> bool:
    rp = robotparser.RobotFileParser()
    rp.set_url(urljoin(url, "/robots.txt"))
    try:
        rp.read()
    except Exception:
        return True
    return rp.can_fetch(USER_AGENT, url)

def clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    for selector in ["nav", "footer", "header"]:
        for el in soup.select(selector):
            el.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc in ALLOWED_NETLOCS:
        netloc = CANONICAL_NETLOC

    path = parsed.path
    for index_name in ("/index.html", "/index.htm"):
        if path.endswith(index_name):
            path = path[: -len(index_name)] or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    if path == "":
        path = "/"

    normalized = f"{scheme}://{netloc}{path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized

def extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        full = urljoin(base_url, href)
        full = full.split("#")[0] 
        parsed = urlparse(full)
        if parsed.netloc.lower() not in ALLOWED_NETLOCS:
            continue
        if full.lower().endswith(SKIP_EXTENSIONS):
            continue
        links.append(normalize_url(full))
    return links

def crawl(start_url: str, max_pages: int, max_depth: int, delay: float, db_config: dict):
    start_url = normalize_url(start_url)

    if not can_fetch(start_url):
        print("robots.txt disallows fetching the start URL. Aborting.")
        return

    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
    except Exception as e:
        print(f"Database connection error: {e}")
        return

    cur.execute("""
        CREATE TABLE IF NOT EXISTS crawled_pages (
            id SERIAL PRIMARY KEY,
            url TEXT UNIQUE,
            title TEXT,
            meta_description TEXT,
            body_text TEXT,
            depth INTEGER,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    visited = set()
    queue = deque([(start_url, 0)])
    saved = 0

    while queue and saved < max_pages:
        url, depth = queue.popleft()
        if url in visited or depth > max_depth:
            continue
        visited.add(url)

        if not can_fetch(url):
            continue

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                continue
        except requests.RequestException as e:
            print(f"  [skip] {url} -> {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
        meta_desc = meta_desc_tag["content"].strip() if meta_desc_tag and meta_desc_tag.get("content") else ""
        body_text = clean_text(soup)

        if body_text:
            cur.execute("""
                INSERT INTO crawled_pages (url, title, meta_description, body_text, depth)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE 
                SET title = EXCLUDED.title,
                    meta_description = EXCLUDED.meta_description,
                    body_text = EXCLUDED.body_text,
                    depth = EXCLUDED.depth,
                    scraped_at = CURRENT_TIMESTAMP;
            """, (url, title, meta_desc, body_text, depth))
            conn.commit() 

            saved += 1
            print(f"[{saved}/{max_pages}] depth={depth} {url} (Saved to DB)")

        if depth < max_depth:
            for link in extract_links(soup, url):
                if link not in visited:
                    queue.append((link, depth + 1))

        time.sleep(delay)

    cur.close()
    conn.close()
    print(f"\nDone. Saved {saved} pages to PostgreSQL Database.")

if __name__ == "__main__":

    load_dotenv()

    parser = argparse.ArgumentParser(description="Crawl te.eg")
    parser.add_argument("--start-url", default=START_URL)
    parser.add_argument("--max-pages", type=int, default=5000)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    
    parser.add_argument("--db-name", default=os.getenv("DB_NAME", "postgres"))
    parser.add_argument("--db-user", default=os.getenv("DB_USER", "postgres"))
    parser.add_argument("--db-pass", default=os.getenv("DB_PASS", ""))
    parser.add_argument("--db-host", default=os.getenv("DB_HOST", "localhost"))
    parser.add_argument("--db-port", default=os.getenv("DB_PORT", "5432"))
    
    args = parser.parse_args()

    db_config = {
        "dbname": args.db_name,
        "user": args.db_user,
        "password": args.db_pass,
        "host": args.db_host,
        "port": args.db_port
    }

    crawl(args.start_url, args.max_pages, args.max_depth, args.delay, db_config)