import socket
import time
from urllib.parse import urlparse

class GopherClient:
    def __init__(self, host, port=70):
        self.host = host
        self.port = port
        self.visited_selectors = set()
        self.text_files = []
        self.binary_files = []
        self.directories = []
        self.invalid_refs = set()
        self.external_servers = {}
        self.smallest_text = None
        self.largest_text_size = 0
        self.smallest_binary_size = float('inf')
        self.largest_binary_size = 0

    def log_request(self, selector):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"[{timestamp}] Sending request: {selector}")

    def send_request(self, host, port, selector):
        try:
            with socket.create_connection((host, port), timeout=5) as s:
                self.log_request(selector)
                s.sendall((selector + '\r\n').encode())
                response = b''
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                return response.decode(errors='ignore')
        except Exception as e:
            print(f"Error connecting to {host}:{port} with selector '{selector}': {e}")
            return None

    def crawl(self, selector=''):
        if selector in self.visited_selectors:
            return
        self.visited_selectors.add(selector)
        response = self.send_request(self.host, self.port, selector)
        if not response:
            return
        lines = response.strip().split('\n')
        for line in lines:
            if not line or line.startswith('.'):
                continue
            item_type = line[0]
            parts = line[1:].split('\t')
            if len(parts) < 4:
                self.invalid_refs.add(line)
                continue
            name, path, host, port = parts[:4]
            if item_type == '1':  # Directory
                self.directories.append(path)
                if host == self.host and int(port) == self.port:
                    self.crawl(path)
                else:
                    self.check_external_server(host, port)
            elif item_type == '0':  # Text file
                self.handle_text(path)
            elif item_type == '9':  # Binary file
                self.handle_binary(path)
            elif item_type == 'i':
                continue  # Info line, ignore
            elif item_type == '3':  # Error
                self.invalid_refs.add(line)
            else:
                self.invalid_refs.add(line)

    def handle_text(self, selector):
        data = self.send_request(self.host, self.port, selector)
        if data:
            size = len(data.encode())
            self.text_files.append((selector, size))
            if self.smallest_text is None or size < len(self.smallest_text.encode()):
                self.smallest_text = data
            if size > self.largest_text_size:
                self.largest_text_size = size

    def handle_binary(self, selector):
        try:
            with socket.create_connection((self.host, self.port), timeout=5) as s:
                self.log_request(selector)
                s.sendall((selector + '\r\n').encode())
                data = b''
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            size = len(data)
            self.binary_files.append((selector, size))
            if size > self.largest_binary_size:
                self.largest_binary_size = size
            if size < self.smallest_binary_size:
                self.smallest_binary_size = size
        except Exception as e:
            self.invalid_refs.add(selector)

    def check_external_server(self, host, port):
        key = f"{host}:{port}"
        if key in self.external_servers:
            return
        try:
            with socket.create_connection((host, int(port)), timeout=5):
                self.external_servers[key] = 'up'
        except Exception:
            self.external_servers[key] = 'down'

    def print_summary(self):
        print("\n--- Gopher Index Summary ---")
        print(f"Number of directories: {len(self.directories)}")
        print(f"Number of text files: {len(self.text_files)}")
        print("Text files:")
        for path, _ in self.text_files:
            print(f"  {path}")
        print(f"Number of binary files: {len(self.binary_files)}")
        print("Binary files:")
        for path, _ in self.binary_files:
            print(f"  {path}")
        print(f"Smallest text file content:\n{self.smallest_text[:500]}")  # Trimmed
        print(f"Largest text file size: {self.largest_text_size}")
        print(f"Smallest binary file size: {self.smallest_binary_size}")
        print(f"Largest binary file size: {self.largest_binary_size}")
        print(f"Invalid references ({len(self.invalid_refs)}):")
        for ref in self.invalid_refs:
            print(f"  {ref}")
        print("External servers:")
        for server, status in self.external_servers.items():
            print(f"  {server} - {status}")

if __name__ == '__main__':
    client = GopherClient('comp3310.ddns.net')
    #client = GopherClient('127.0.0.1')
    client.crawl()
    client.print_summary()
