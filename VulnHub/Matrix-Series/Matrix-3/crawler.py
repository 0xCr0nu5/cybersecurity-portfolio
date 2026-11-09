import requests		# HTTP library to fetch web pages
from urllib.parse import urljoin	# Smart URL concatenation
from bs4 import BeautifulSoup		# HTML parser to extract links
import sys		# Command-line argument handling

# Takes a starting URL and a max recursion depth 
def crawl(base_url, max_depth=10):
    # breadth-first search queue
    visited = set()		# tracks URL already seen to avoid loops
    queue = [(base_url, 0)]	# (url, depth) pairs to process
    
    while queue:
        url, depth = queue.pop(0)		# FIFO -> first in first out
        if url in visited or depth > max_depth:
            continue
        visited.add(url)
        
        # sends a HTTP GET rquest with a 5-sec timeout
        try:
            r = requests.get(url, timeout=5)
            content_type = r.headers.get('Content-Type', '')
            
            # Skip if it's a download (application/octet-stream) or something interesting
            if 'text/html' not in content_type and r.status_code == 200:
                print(f"[FILE] {url} (type: {content_type}, size: {len(r.content)})")
                # Download it
                fname = url.rstrip('/').split('/')[-1] or 'index'
                with open(fname, 'wb') as f:
                    f.write(r.content)
                continue
            
            # HTML parsing (directory listing pages)
            soup = BeautifulSoup(r.text, 'html.parser')
            for link in soup.find_all('a'):
                href = link.get('href')
                if href and href not in ('/', '../', '.'):
                    next_url = urljoin(url + '/', href)
                    queue.append((next_url, depth + 1))
                    
	# catches any errors and prints them without crashing(network errors, timeouts, parsing failures)
        except Exception as e:
            print(f"[ERROR] {url}: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <base_url>")
        print(f"Example: {sys.argv[0]} http://target_ip/Matrix/")
        sys.exit(1)
    crawl(sys.argv[1])
