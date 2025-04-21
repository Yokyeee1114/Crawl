#!/usr/bin/env python3
"""
COMP3310 - Assignment 2: Indexing a Gopher
A Gopher client that crawls a Gopher server, follows directory links,
and provides statistics on the content found.

Default server is set to the class server: comp3310.ddns.net
"""

import socket
import re
import os
import datetime
import time
from urllib.parse import urlparse

# Configuration
DEFAULT_HOST = 'comp3310.ddns.net'  # Class server
DEFAULT_PORT = 70
TIMEOUT = 10  # seconds
BUFFER_SIZE = 4096

# Gopher item types as per RFC 1436
ITEM_TYPES = {
    '0': 'TEXT',
    '1': 'DIRECTORY',
    '3': 'ERROR',
    '5': 'ARCHIVE',
    '9': 'BINARY',
    'h': 'HTML',
    'i': 'INFO'
}


class GopherClient:
    def __init__(self, host, port=DEFAULT_PORT):
        """Initialize the Gopher client with host and port."""
        self.host = host
        self.port = port
        self.visited_paths = set()  # Keep track of visited paths
        self.visited_servers = set()  # Keep track of external servers checked
        self.directories = []
        self.text_files = []
        self.binary_files = []
        self.error_refs = []
        self.external_servers = {}  # {(host, port): is_up}

        # For statistics
        self.text_file_sizes = {}
        self.binary_file_sizes = {}
        self.downloaded_text = {}

    def send_request(self, path=""):
        """Send a request to the Gopher server and return the response."""
        try:
            # Create a socket connection
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)

            # Connect to the server
            s.connect((self.host, self.port))

            # Log the request timestamp and details
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            request = f"{path}\r\n"
            print(f"[{timestamp}] Sending: {request.strip()}")

            # Send the request
            s.sendall(request.encode('utf-8'))

            # Receive the response
            response = b""
            while True:
                data = s.recv(BUFFER_SIZE)
                if not data:
                    break
                response += data

            s.close()

            # Try to decode as UTF-8, fall back to latin-1 if that fails
            try:
                return response.decode('utf-8')
            except UnicodeDecodeError:
                return response.decode('latin-1')

        except socket.timeout:
            print(f"[{timestamp}] Timeout connecting to {self.host}:{self.port}{path}")
            return None
        except ConnectionRefusedError:
            print(f"[{timestamp}] Connection refused to {self.host}:{self.port}{path}")
            return None
        except Exception as e:
            print(f"[{timestamp}] Error: {e}")
            return None

    def check_external_server(self, host, port):
        """Check if an external server is up by attempting to connect."""
        if (host, port) in self.visited_servers:
            return self.external_servers[(host, port)]

        self.visited_servers.add((host, port))

        try:
            # Create a socket connection
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)

            # Connect to the server
            s.connect((host, port))

            # Log the check
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] Checking external server: {host}:{port} - UP")

            # Close the connection
            s.close()

            self.external_servers[(host, port)] = True
            return True

        except Exception:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] Checking external server: {host}:{port} - DOWN")
            self.external_servers[(host, port)] = False
            return False

    def parse_gopher_line(self, line):
        """Parse a line from the Gopher response into its components."""
        if not line or line.startswith('.'):
            return None

        try:
            item_type = line[0]

            # Split the remaining parts by tabs
            parts = line[1:].split('\t')

            if len(parts) < 4:
                # Malformed line, add padding
                parts.extend([''] * (4 - len(parts)))

            display_string = parts[0]
            selector = parts[1]
            host = parts[2]
            port = int(parts[3]) if parts[3].strip() else DEFAULT_PORT

            return {
                'type': item_type,
                'display': display_string,
                'selector': selector,
                'host': host,
                'port': port
            }
        except Exception as e:
            print(f"Error parsing line: {line} - {e}")
            return None

    def get_file_content(self, path):
        """Get the content of a file from the Gopher server."""
        return self.send_request(path)

    def crawl(self):
        """Crawl the Gopher server starting from the root."""
        self.process_directory("")  # Start with root directory

        # Print summary after crawling is completed
        self.print_summary()

    def is_binary_content(self, content):
        """Check if the content is binary based on null bytes or non-printable chars."""
        if content is None:
            return False

        # Check for null bytes which indicates binary content
        if '\x00' in content:
            return True

        # Check if most characters are printable
        non_printable = sum(1 for c in content if not (32 <= ord(c) <= 126) and c not in '\r\n\t')
        ratio = non_printable / len(content) if content else 0

        return ratio > 0.1  # If more than 10% are non-printable, consider it binary

    def process_directory(self, path):
        """Process a directory path and all its contents."""
        # Avoid visiting the same path multiple times
        if path in self.visited_paths:
            return

        self.visited_paths.add(path)

        # Request the directory listing
        content = self.send_request(path)
        if not content:
            return

        # Add to directories list if it's not root
        if path:
            self.directories.append(path)

        # Parse each line in the response
        for line in content.split('\r\n'):
            if not line or line == '.':
                continue

            item = self.parse_gopher_line(line)
            if not item:
                continue

            # Check if this is on the same server
            if item['host'] == self.host and item['port'] == self.port:
                # Process based on item type
                if item['type'] == '1':  # Directory
                    self.process_directory(item['selector'])
                elif item['type'] == '0':  # Text file
                    self.process_text_file(item['selector'])
                elif item['type'] in ['9', '5']:  # Binary file
                    self.process_binary_file(item['selector'])
                elif item['type'] == '3':  # Error
                    if item['selector'] not in self.error_refs:
                        self.error_refs.append(item['selector'])
            else:
                # External server reference
                if (item['host'], item['port']) not in self.external_servers:
                    self.check_external_server(item['host'], item['port'])

    def process_text_file(self, path):
        """Process a text file and record its statistics."""
        if path in self.visited_paths:
            return

        self.visited_paths.add(path)

        content = self.send_request(path)
        if not content:
            return

        # If the content looks binary despite being marked as text, treat it as binary
        if self.is_binary_content(content):
            self.process_binary_file(path)
            return

        # Store text file info
        self.text_files.append(path)
        size = len(content.encode('utf-8'))  # Size in bytes
        self.text_file_sizes[path] = size
        self.downloaded_text[path] = content

    def process_binary_file(self, path):
        """Process a binary file and record its statistics."""
        if path in self.visited_paths:
            return

        self.visited_paths.add(path)

        content = self.send_request(path)
        if not content:
            return

        # Store binary file info
        self.binary_files.append(path)
        size = len(content.encode('utf-8'))  # Size in bytes, approximation for binary
        self.binary_file_sizes[path] = size

    def print_summary(self):
        """Print the summary of the crawl as required by the assignment."""
        print("\n" + "=" * 60)
        print("GOPHER CRAWL SUMMARY")
        print("=" * 60)

        # Number of directories
        print(f"\nNumber of Gopher directories: {len(self.directories)}")

        # Text files
        print(f"\nNumber of text files: {len(self.text_files)}")
        if self.text_files:
            print("Text files:")
            for path in sorted(self.text_files):
                print(f"  {path}")

            # Smallest text file
            if self.text_file_sizes:
                min_path = min(self.text_file_sizes, key=self.text_file_sizes.get)
                min_size = self.text_file_sizes[min_path]
                print(f"\nSmallest text file: {min_path} ({min_size} bytes)")
                print("Contents:")
                print("-" * 60)
                print(self.downloaded_text[min_path])
                print("-" * 60)

                # Largest text file
                max_path = max(self.text_file_sizes, key=self.text_file_sizes.get)
                max_size = self.text_file_sizes[max_path]
                print(f"\nLargest text file: {max_path} ({max_size} bytes)")

        # Binary files
        print(f"\nNumber of binary files: {len(self.binary_files)}")
        if self.binary_files:
            print("Binary files:")
            for path in sorted(self.binary_files):
                print(f"  {path}")

            # Smallest binary file
            if self.binary_file_sizes:
                min_path = min(self.binary_file_sizes, key=self.binary_file_sizes.get)
                min_size = self.binary_file_sizes[min_path]
                print(f"\nSmallest binary file: {min_path} ({min_size} bytes)")

                # Largest binary file
                max_path = max(self.binary_file_sizes, key=self.binary_file_sizes.get)
                max_size = self.binary_file_sizes[max_path]
                print(f"\nLargest binary file: {max_path} ({max_size} bytes)")

        # Invalid references
        print(f"\nNumber of unique invalid references: {len(self.error_refs)}")

        # External servers
        print(f"\nExternal servers referenced:")
        for (host, port), is_up in self.external_servers.items():
            status = "UP" if is_up else "DOWN"
            print(f"  {host}:{port} - {status}")

        print("\n" + "=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Gopher client for COMP3310 Assignment 2')
    parser.add_argument('--host', default=DEFAULT_HOST, help=f'Gopher server hostname (default: {DEFAULT_HOST})')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Gopher server port (default: {DEFAULT_PORT})')

    args = parser.parse_args()

    print(f"Starting Gopher crawl of {args.host}:{args.port}")
    client = GopherClient(args.host, args.port)
    client.crawl()


if __name__ == "__main__":
    main()