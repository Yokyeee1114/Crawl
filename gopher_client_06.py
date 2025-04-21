import socket
import time
import sys
from collections import defaultdict


def send_gopher_request(host, port, selector="", timeout=10):
    """Send a request to a Gopher server and return the response"""
    timestamp = time.strftime('%H:%M:%S')
    print(f"[{timestamp}] Sending request: {selector}")

    try:
        # Create a socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)  # Set timeout to avoid hanging

        # Connect to the server
        s.connect((host, port))

        # Send the selector string followed by CRLF
        if selector:
            s.sendall((selector + "\r\n").encode('utf-8'))
        else:
            s.sendall("\r\n".encode('utf-8'))

        # Receive the response
        data = b""
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                print(f"[{time.strftime('%H:%M:%S')}] Receive timeout for: {selector}")
                break

        # Close the socket
        s.close()

        return data

    except socket.timeout:
        print(f"[{time.strftime('%H:%M:%S')}] Connection timeout for: {selector}")
        return b""
    except socket.error as e:
        print(f"[{time.strftime('%H:%M:%S')}] Socket error for {selector}: {e}")
        return b""
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error for {selector}: {e}")
        return b""


def parse_gopher_menu(menu_data):
    """Parse a Gopher menu into a list of items"""
    try:
        lines = menu_data.decode('utf-8', errors='replace').split('\r\n')
    except:
        # If decode fails completely, return empty list
        return []

    items = []

    for line in lines:
        # Skip empty lines or the ending period line
        if not line or line == '.':
            continue

        # Make sure line has at least an item type character
        if len(line) < 1:
            continue

        # Extract item type, display string, selector, host, and port
        item_type = line[0]
        parts = line[1:].split('\t')

        # Need at least 4 parts for a valid item
        if len(parts) >= 4:
            display_string = parts[0]
            selector = parts[1]
            host = parts[2]

            # Handle possible port issues
            try:
                port = int(parts[3])
                if port <= 0 or port > 65535:
                    port = 70  # Use default port if out of range
            except ValueError:
                port = 70  # Default Gopher port

            items.append({
                'type': item_type,
                'display': display_string,
                'selector': selector,
                'host': host,
                'port': port
            })

    return items


def is_same_server(host1, port1, host2, port2):
    """Check if two server references point to the same server"""
    return host1.lower() == host2.lower() and port1 == port2


def is_text_file(data):
    """Determine if data is a text file by attempting to decode it as UTF-8
    and checking percentage of printable characters"""
    try:
        text = data.decode('utf-8', errors='replace')
        # Check if it's a valid text file by looking at the first chunk
        # Most binary files will have many unprintable characters
        sample = text[:4096]
        printable_chars = sum(c.isprintable() or c.isspace() for c in sample)
        if len(sample) > 0 and printable_chars / len(sample) > 0.8:
            return True
        return False
    except:
        return False


def main():
    # Server configuration - update these values
    host = "comp3310.ddns.net"  # Change to your Gopher server
    port = 70  # Default Gopher port

    # Track visited selectors to avoid loops
    visited_selectors = set()

    # Track directories, text files, binary files, and errors
    directories = []
    text_files = []
    binary_files = []
    invalid_references = set()
    external_servers = {}  # format: (host, port): is_up

    # Store file data for analysis
    file_contents = {}
    file_sizes = {}

    # Start with the root selector
    selectors_to_visit = [("", host, port)]

    # Process queue until empty
    while selectors_to_visit:
        selector, current_host, current_port = selectors_to_visit.pop(0)

        # Skip if already visited
        if selector in visited_selectors:
            continue

        visited_selectors.add(selector)

        # Send request to the server
        response = send_gopher_request(current_host, current_port, selector)

        if not response:
            invalid_references.add(selector)
            continue

        # Determine if this is a directory (menu) or a file
        is_directory = False

        # First character is a Gopher type, typically directories start with 1
        # Also root selector is always a directory
        if not selector or selector.endswith('/'):
            # Assume it's a directory if selector is empty or ends with /
            is_directory = True
        else:
            # Try to parse as menu, if successful and has items, it's a directory
            menu_items = parse_gopher_menu(response)
            is_directory = len(menu_items) > 0

        if is_directory:
            # It's a directory/menu
            if selector not in directories:
                directories.append(selector)

            menu_items = parse_gopher_menu(response)

            for item in menu_items:
                item_type = item['type']
                item_selector = item['selector']
                item_host = item['host']
                item_port = item['port']

                # Check if it's an external server
                if not is_same_server(current_host, current_port, item_host, item_port):
                    server_key = (item_host, item_port)
                    if server_key not in external_servers:
                        # Test if external server is up
                        try:
                            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            test_socket.settimeout(5)
                            test_socket.connect((item_host, item_port))
                            test_socket.close()
                            external_servers[server_key] = True
                        except:
                            external_servers[server_key] = False
                    continue

                # Process based on item type
                if item_type == '1':  # Directory
                    selectors_to_visit.append((item_selector, item_host, item_port))
                elif item_type == '0':  # Text file
                    if item_selector not in text_files:
                        text_files.append(item_selector)
                        selectors_to_visit.append((item_selector, item_host, item_port))
                elif item_type == '3':  # Error
                    invalid_references.add(item_selector)
                elif item_type != 'i':  # Binary file (not info)
                    if item_selector not in binary_files:
                        binary_files.append(item_selector)
                        selectors_to_visit.append((item_selector, item_host, item_port))
        else:
            # It's a file
            file_size = len(response)
            file_sizes[selector] = file_size

            # Determine if it's text or binary
            if is_text_file(response):
                if selector not in text_files:
                    text_files.append(selector)
                    file_contents[selector] = response
            else:
                if selector not in binary_files:
                    binary_files.append(selector)

    # Calculate file statistics
    smallest_text_file = None
    largest_text_file = None
    smallest_text_size = float('inf')
    largest_text_size = 0

    for file in text_files:
        if file in file_sizes:
            size = file_sizes[file]
            if size < smallest_text_size:
                smallest_text_size = size
                smallest_text_file = file
            if size > largest_text_size:
                largest_text_size = size
                largest_text_file = file

    smallest_binary_file = None
    largest_binary_file = None
    smallest_binary_size = float('inf')
    largest_binary_size = 0

    for file in binary_files:
        if file in file_sizes:
            size = file_sizes[file]
            if size < smallest_binary_size:
                smallest_binary_size = size
                smallest_binary_file = file
            if size > largest_binary_size:
                largest_binary_size = size
                largest_binary_file = file

    # Print summary
    print("\n--- Summary ---")
    print(f"Number of directories: {len(directories)}")
    print("Directories:")
    for directory in directories:
        print(f"  {directory or '/'}")

    print(f"\nNumber of text files: {len(text_files)}")
    print("Text files:")
    for file in text_files:
        print(f"  {file}")

    if smallest_text_file:
        print(f"\nSmallest text file: {smallest_text_file} ({smallest_text_size} bytes)")
        try:
            content = file_contents[smallest_text_file].decode('utf-8', errors='replace')
            print("Content:")
            print(content[:1000] + ("..." if len(content) > 1000 else ""))
        except:
            print("Unable to display content")

    if largest_text_file:
        print(f"\nLargest text file: {largest_text_file} ({largest_text_size} bytes)")

    print(f"\nNumber of binary files: {len(binary_files)}")
    print("Binary files:")
    for file in binary_files:
        print(f"  {file}")

    if smallest_binary_file:
        print(f"\nSmallest binary file: {smallest_binary_file} ({smallest_binary_size} bytes)")

    if largest_binary_file:
        print(f"\nLargest binary file: {largest_binary_file} ({largest_binary_size} bytes)")

    print(f"\nNumber of invalid references: {len(invalid_references)}")

    print("\nExternal servers:")
    for (host, port), is_up in external_servers.items():
        status = "up" if is_up else "down"
        print(f"  {host}:{port} - {status}")


if __name__ == "__main__":
    main()