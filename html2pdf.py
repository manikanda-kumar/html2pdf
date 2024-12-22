import sys
import threading
import logging
from collections import namedtuple
from functools import cached_property
from pathlib import Path
from typing import List
import datetime

import bs4
import requests
from PyPDF2 import PdfMerger
import markdown
from weasyprint import HTML, CSS

# logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(logging.Formatter("%(asctime)-15s: %(message)s"))
logger.addHandler(ch)

Chapter = namedtuple("Chapter", ["order", "url", "title"])

class HTMLBook:
    def __init__(self, markdown_file: str, output_dir: str = "./output", output_file: str = "book.pdf"):
        self.markdown_file = Path(markdown_file)
        self.output_dir = Path(output_dir)
        self.output_file = output_file
        self.timeout = 180

    def parse_markdown_chapters(self) -> List[Chapter]:
        """Parse chapter information from markdown file"""
        logger.info(f"Parsing chapters from {self.markdown_file}")
        
        with open(self.markdown_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Parse markdown to get links
        soup = bs4.BeautifulSoup(markdown.markdown(content), 'html.parser')
        chapter_links = soup.find_all('a')
        
        chapters = []
        for idx, link in enumerate(chapter_links, 1):
            # Skip if it's not a chapter link (you might want to adjust this condition)
            if not link.get('href'):
                continue
                
            chapters.append(Chapter(
                order=idx,
                url=link['href'],
                title=link.text.strip()
            ))
            
        logger.info(f"Found {len(chapters)} chapters")
        return chapters

    @cached_property
    def chapters(self) -> List[Chapter]:
        return self.parse_markdown_chapters()

    def download_chapters(self):
        logger.info("downloading chapters ...")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        def download(ch: Chapter):
            # Clean up URL if needed
            url = ch.url.replace('index.html', '')
            if not url.startswith(('http://', 'https://')):
                url = f"https://aosabook.org/en/{url}"
                
            logger.info(f" ... downloading: {url}")
            try:
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()

                if response.ok:
                    file_name = self.output_dir / f"{ch.order:03d}-{ch.title}.html"
                    logger.info(f" saving into: {file_name}")
                    
                    # Process HTML to make it self-contained
                    soup = bs4.BeautifulSoup(response.text, 'html.parser')
                    
                    # Handle relative URLs
                    base_url = url.rsplit('/', 1)[0]
                    for tag in soup.find_all(['img', 'link', 'script']):
                        for attr in ['src', 'href']:
                            if tag.get(attr):
                                if not tag[attr].startswith(('http://', 'https://', 'data:')):
                                    tag[attr] = f"{base_url}/{tag[attr].lstrip('/')}"

                    with open(file_name, "w", encoding='utf-8') as f:
                        f.write(str(soup))
            except Exception as e:
                logger.error(f"Error downloading {url}: {e}")

        threads = []
        for ch in self.chapters:
            t = threading.Thread(target=download, args=(ch,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()
        logger.info("download chapters - done.")

    @property
    def downloaded_chapters(self) -> List[Path]:
        return sorted(self.output_dir.glob("*.html"))

    def convert_and_merge(self):
        logger.info("converting and merging chapters ...")
        merger = PdfMerger()
        
        # Add metadata
        dt = datetime.datetime.now().strftime("%Y%m%d%H%M%S%z")
        merger.add_metadata({
            "/Creator": "HTML2PDF Converter",
            "/Producer": "html2pdf.py with WeasyPrint",
            "/CreationDate": dt,
            "/ModDate": dt,
        })

        # Common styling for all pages
        css = CSS(string='''
            @page {
                margin: 20mm;
                size: A4;
                @top-center {
                    content: string(chapter-title);
                }
            }
            h1 { string-set: chapter-title content() }
        ''')

        for idx, html_file in enumerate(self.downloaded_chapters):
            logger.info(f"Converting {html_file}")
            
            temp_pdf = html_file.with_suffix('.pdf')
            try:
                # Convert HTML to PDF with styling
                HTML(filename=str(html_file)).write_pdf(
                    target=str(temp_pdf),
                    stylesheets=[css]
                )
                
                chapter_title = html_file.stem.split('-', 1)[1]
                merger.append(
                    str(temp_pdf),
                    outline_item=chapter_title,
                )
            finally:
                # Clean up temporary PDF
                if temp_pdf.exists():
                    temp_pdf.unlink()

        # Write final PDF
        with open(self.output_file, "wb") as book:
            merger.write(book)
        
        merger.close()
        logger.info("merging chapters - done. (%s)", self.output_file)

    def build(self):
        self.download_chapters()
        self.convert_and_merge()

if __name__ == "__main__":
    book = HTMLBook(
        markdown_file="chapters.md",
        output_file="AOSA.pdf"
    )
    book.build() 