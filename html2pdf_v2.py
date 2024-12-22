import fitz  # PyMuPDF
import pdfkit
import requests
import markdown
import bs4
import html2text
import os
import logging
from pathlib import Path

def parse_markdown(markdown_file):
    """Extract chapter links from markdown file."""
    with open(markdown_file, 'r', encoding='utf-8') as f:
        content = f.read()
    soup = bs4.BeautifulSoup(markdown.markdown(content), 'html.parser')
    
    # Find all links that could be chapters
    chapter_links = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if not href:
            continue
            
        # Clean up URL and verify it's a chapter link
        if href.endswith('.html') or 'index.html' in href or 'aosabook.org' in href:
            chapter_links.append(link)
    
    chapters = []
    for idx, link in enumerate(chapter_links, 1):
        chapters.append({
            'name': link.text.strip(),
            'url': link.get('href'),
            'index': idx
        })
        print(f"Found chapter {idx}: {link.text.strip()} - {link.get('href')}")  # Debug print
    
    if not chapters:
        raise ValueError("No chapters found in markdown file")
        
    return chapters

def download_as_markdown(url, output_dir):
    """Download HTML and convert to markdown, including images."""
    # Clean up URL if needed
    if not url.startswith(('http://', 'https://')):
        url = f"https://aosabook.org/en/{url}"
    
    base_url = '/'.join(url.split('/')[:-1])
    response = requests.get(url)
    response.raise_for_status()
    
    # Create images directory
    images_dir = Path(output_dir).parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse HTML and download images
    soup = bs4.BeautifulSoup(response.text, 'html.parser')
    for img in soup.find_all('img'):
        try:
            img_url = img['src']
            if not img_url.startswith(('http://', 'https://')):
                img_url = f"{base_url}/{img_url.lstrip('/')}"
            
            # Download image
            img_response = requests.get(img_url)
            img_response.raise_for_status()
            
            # Create a safe filename
            img_filename = Path(img_url).name
            safe_filename = "".join(c for c in img_filename if c.isalnum() or c in ('.','-','_')).strip()
            img_path = images_dir / safe_filename
            
            # Save image
            with open(img_path, 'wb') as f:
                f.write(img_response.content)
            
            # Update image src to relative path
            img['src'] = f"../images/{safe_filename}"
            
        except Exception as e:
            print(f"Error downloading image {img_url}: {str(e)}")
            continue
    
    # Convert HTML to markdown
    h2t = html2text.HTML2Text()
    h2t.ignore_links = False
    h2t.ignore_images = False
    h2t.body_width = 0  # Don't wrap lines
    markdown_content = h2t.handle(str(soup))
    
    return markdown_content

def markdown_to_pdf(markdown_content, output_path):
    """Convert markdown content to PDF."""
    # Convert markdown to HTML with images
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            img {{
                max-width: 100%;
                height: auto;
            }}
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                padding: 20px;
            }}
        </style>
    </head>
    <body>
        {markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])}
    </body>
    </html>
    """
    
    # Configure pdfkit options
    options = {
        'quiet': '',
        'no-outline': None,
        'disable-smart-shrinking': '',
        'print-media-type': None,
        'no-background': None,
        'encoding': 'UTF-8',
        'enable-local-file-access': True,
        'images': True,
        'load-error-handling': 'ignore',
        'allow': ["./", "../images/"],  # Allow loading from these paths
        'zoom': 1.0,  # Default zoom level
        'image-quality': 100,  # Maximum image quality
        'image-dpi': 300,  # DPI for images
        'enable-javascript': True,  # Some markdown might include JS for images
        'minimum-font-size': 16,
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in'
    }
    
    try:
        # Convert HTML to PDF with options
        pdfkit.from_string(
            html_content, 
            output_path,
            options=options,
            verbose=False
        )
    except Exception as e:
        print(f"PDF generation warning (can be ignored if PDF was created): {str(e)}")
        
        # Fallback to WeasyPrint if pdfkit fails
        try:
            from weasyprint import HTML, CSS
            css = CSS(string='''
                @page {
                    margin: 2cm;
                    size: A4;
                }
                img {
                    max-width: 100%;
                    height: auto;
                }
                body {
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                }
            ''')
            HTML(string=html_content).write_pdf(output_path, stylesheets=[css])
        except Exception as e2:
            print(f"Both PDF conversion methods failed: {str(e2)}")
            raise

def combine_pdfs(pdf_files, output_path):
    """Combine multiple PDFs into one."""
    if not pdf_files:
        raise ValueError("No PDF files provided for combining")
        
    # Sort PDF files by chapter number
    pdf_files.sort(key=lambda x: int(Path(x).stem.split('_')[0]))
    
    print(f"Combining PDFs in order: {[Path(f).stem for f in pdf_files]}")  # Debug print
    
    combined_pdf = fitz.open()
    for pdf in pdf_files:
        try:
            with fitz.open(pdf) as mfile:
                combined_pdf.insert_pdf(mfile)
                print(f"Added {Path(pdf).stem} to final PDF")  # Debug print
        except Exception as e:
            print(f"Error adding {pdf}: {str(e)}")
    
    combined_pdf.save(output_path)
    combined_pdf.close()

def main(markdown_file):
    # Create output directories with absolute paths
    base_dir = Path.cwd()
    output_dir = base_dir / "output"
    markdown_dir = output_dir / "markdown"
    pdf_dir = output_dir / "pdf"
    images_dir = output_dir / "images"  # Add images directory
    
    # Create directories if they don't exist
    for dir_path in [output_dir, markdown_dir, pdf_dir, images_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # Parse chapters from markdown
    try:
        chapters = parse_markdown(markdown_file)
        print(f"Total chapters found: {len(chapters)}")  # Debug print
    except Exception as e:
        print(f"Error parsing chapters: {str(e)}")
        return
    
    pdf_files = []
    
    for chapter in chapters:
        try:
            # Generate filenames with sanitized names
            safe_name = "".join(c for c in chapter['name'] if c.isalnum() or c in (' ', '-', '_')).strip()
            md_filename = f"{chapter['index']:03d}_{safe_name}.md"
            pdf_filename = f"{chapter['index']:03d}_{safe_name}.pdf"
            md_path = markdown_dir / md_filename
            pdf_path = pdf_dir / pdf_filename
            
            # Download and save markdown
            markdown_content = download_as_markdown(chapter['url'], markdown_dir)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            # Convert to PDF with error handling
            try:
                markdown_to_pdf(markdown_content, str(pdf_path))
                if pdf_path.exists():  # Verify PDF was created
                    pdf_files.append(str(pdf_path))
                    print(f"Successfully processed chapter {chapter['index']}: {chapter['name']}")
                else:
                    print(f"PDF not created for chapter {chapter['index']}: {chapter['name']}")
            except Exception as e:
                print(f"Error converting to PDF for {chapter['name']}: {str(e)}")
                continue
            
        except Exception as e:
            print(f"Error processing chapter {chapter['name']}: {str(e)}")
    
    if pdf_files:
        print(f"Found {len(pdf_files)} PDFs to combine")  # Debug print
        final_pdf_path = output_dir / "final_book.pdf"
        try:
            combine_pdfs(pdf_files, str(final_pdf_path))
            print(f"Final PDF created at: {final_pdf_path}")
        except Exception as e:
            print(f"Error combining PDFs: {str(e)}")
    else:
        print("No PDFs were generated to combine")

if __name__ == "__main__":
    main("chapters.md")