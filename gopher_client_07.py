import socket
import time
import sys
from collections import defaultdict


def send_gopher_request(host, port, selector="", timeout=10, max_data_size=10 * 1024 * 1024, max_time=30):
    """Send a request to a Gopher server and return the response with various safety measures"""
    timestamp = time.strftime('%H:%M:%S')
    print(f"[{timestamp}] Sending request: {selector}")

    try:
        # Create a socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)  # Set timeout for each recv operation

        # Connect to the server
        s.connect((host, port))

        # Send the selector string followed by CRLF
        if selector:
            s.sendall((selector + "\r\n").encode('utf-8'))
        else:
            s.sendall("\r\n".encode('utf-8'))

        # Receive the response with safety measures
        data = b""
        start_time = time.time()
        last_progress_time = start_time

        while True:
            # Check if we've received too much data
            if len(data) > max_data_size:
                print(f"[{time.strftime('%H:%M:%S')}] Maximum data size exceeded for: {selector}")
                break

            # Check if total request time is too long
            current_time = time.time()
            if current_time - start_time > max_time:
                print(f"[{time.strftime('%H:%M:%S')}] Maximum request time exceeded for: {selector}")
                break

            try:
                chunk = s.recv(4096)
                if not chunk:  # Connection closed by server
                    break

                data += chunk
                last_progress_time = current_time  # Reset progress timer on successful receive

                # If we're receiving a huge amount of data, print progress indicators
                if len(data) % (1 * 1024 * 1024) < 4096:  # Around every 1MB
                    print(f"[{time.strftime('%H:%M:%S')}] Received {len(data) / 1024 / 1024:.2f}MB from: {selector}")

            except socket.timeout:
                # If no data received for a while but we're still within max_time, continue
                if current_time - last_progress_time > timeout:
                    print(f"[{time.strftime('%H:%M:%S')}] Receive timeout for: {selector}")
                    break

        # Close the socket
        try:
            s.shutdown(socket.SHUT_RDWR)
        except:
            pass  # Might already be closed
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
    finally:
        # Ensure socket is closed even in case of exceptions
        try:
            s.close()
        except:
            pass


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


def is_text_file(data, sample_size=4096):
    """Determine if data is a text file by attempting to decode it as UTF-8
    and checking percentage of printable characters"""
    try:
        # Only check a sample to save time and memory
        sample = data[:sample_size]
        text = sample.decode('utf-8', errors='replace')

        # Check if it's a valid text file by looking at the sample
        # Most binary files will have many unprintable characters
        printable_chars = sum(c.isprintable() or c.isspace() for c in text)
        if len(sample) > 0 and printable_chars / len(sample) > 0.8:
            return True
        return False
    except:
        return False


def check_external_server(host, port, timeout=5):
    """Check if an external server is up by attempting to connect"""
    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(timeout)
        test_socket.connect((host, port))
        test_socket.close()
        return True
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

    # Store file data and sizes
    text_file_contents = {}
    file_sizes = {}

    # Start with the root selector
    selectors_to_visit = [("", host, port)]

    # Set limits to prevent excessive resource usage
    max_queue_size = 1000
    max_items = 5000
    processed_count = 0

    # Process queue until empty or limits reached
    while selectors_to_visit and processed_count < max_items:
        # Safety check for queue size
        if len(selectors_to_visit) > max_queue_size:
            print(f"Warning: Queue size {len(selectors_to_visit)} exceeds maximum. Truncating.")
            selectors_to_visit = selectors_to_visit[:max_queue_size]

        selector, current_host, current_port = selectors_to_visit.pop(0)
        processed_count += 1

        # Skip if already visited
        if selector in visited_selectors:
            continue

        visited_selectors.add(selector)

        # Send request to the server with safety limits
        response = send_gopher_request(
            current_host,
            current_port,
            selector,
            timeout=10,  # 10 seconds for socket operations
            max_data_size=10 * 1024 * 1024,  # 10MB maximum response size
            max_time=30  # 30 seconds maximum total request time
        )

        if not response:
            invalid_references.add(selector)
            continue

        # Determine if this is a directory (menu) or a file
        is_directory = False

        # First attempt to parse as a menu - if it has valid items, treat as directory
        menu_items = parse_gopher_menu(response)
        if menu_items:
            is_directory = True
        elif not selector or selector.endswith('/'):
            # If selector suggests it's a directory but parsing failed, still treat as directory
            is_directory = True

        if is_directory:
            # It's a directory/menu
            if selector not in directories:
                directories.append(selector)

            for item in menu_items:
                item_type = item['type']
                item_selector = item['selector']
                item_host = item['host']
                item_port = item['port']

                # Skip if item looks like it might cause problems
                if len(item_selector) > 255:  # Very long selector
                    print(f"Warning: Skipping very long selector: {item_selector[:50]}...")
                    continue

                # Check if it's an external server
                if not is_same_server(current_host, current_port, item_host, item_port):
                    server_key = (item_host, item_port)
                    if server_key not in external_servers:
                        # Test if external server is up
                        external_servers[server_key] = check_external_server(item_host, item_port)
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
                    # Only store content for small text files
                    if file_size < 1024 * 1024:  # 1MB limit
                        text_file_contents[selector] = response
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
    for directory in sorted(directories):
        print(f"  {directory or '/'}")

    print(f"\nNumber of text files: {len(text_files)}")
    print("Text files:")
    for file in sorted(text_files):
        size = file_sizes.get(file, "unknown")
        print(f"  {file} ({size} bytes)")

    if smallest_text_file:
        print(f"\nSmallest text file: {smallest_text_file} ({smallest_text_size} bytes)")
        if smallest_text_file in text_file_contents:
            try:
                content = text_file_contents[smallest_text_file].decode('utf-8', errors='replace')
                print("Content:")
                print(content[:1000] + ("..." if len(content) > 1000 else ""))
            except:
                print("Unable to display content")

    if largest_text_file:
        print(f"\nLargest text file: {largest_text_file} ({largest_text_size} bytes)")

    print(f"\nNumber of binary files: {len(binary_files)}")
    print("Binary files:")
    for file in sorted(binary_files):
        size = file_sizes.get(file, "unknown")
        print(f"  {file} ({size} bytes)")

    if smallest_binary_file:
        print(f"\nSmallest binary file: {smallest_binary_file} ({smallest_binary_size} bytes)")

    if largest_binary_file:
        print(f"\nLargest binary file: {largest_binary_file} ({largest_binary_size} bytes)")

    print(f"\nNumber of invalid references: {len(invalid_references)}")
    print("Invalid references:")
    for ref in sorted(invalid_references):
        print(f"  {ref}")

    print("\nExternal servers:")
    for (host, port), is_up in external_servers.items():
        status = "up" if is_up else "down"
        print(f"  {host}:{port} - {status}")


if __name__ == "__main__":
    main()