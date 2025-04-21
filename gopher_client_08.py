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
        # Try UTF-8 first
        lines = menu_data.decode('utf-8', errors='replace').split('\r\n')
    except:
        # If that fails completely, try Latin-1 as a fallback
        try:
            lines = menu_data.decode('latin-1', errors='replace').split('\r\n')
        except:
            # If all decoding fails, return empty list
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
    # Clean up hostnames before comparison (remove whitespace, convert to lowercase)
    host1 = host1.strip().lower() if isinstance(host1, str) else ""
    host2 = host2.strip().lower() if isinstance(host2, str) else ""
    return host1 == host2 and port1 == port2


def is_text_file(data, sample_size=4096):
    """Determine if data is a text file by attempting to decode it and
    checking percentage of printable characters"""
    if not data:
        return False

    try:
        # Only check a sample to save time and memory
        sample = data[:sample_size]

        # Try UTF-8 decoding first
        try:
            text = sample.decode('utf-8', errors='strict')
            # If we can decode as strict UTF-8, it's very likely text
            return True
        except UnicodeDecodeError:
            # Try a more lenient approach with ASCII/Latin-1
            try:
                text = sample.decode('latin-1', errors='replace')

                # Check if it's mostly printable characters
                printable_chars = sum(c.isprintable() or c.isspace() for c in text)
                if len(sample) > 0 and printable_chars / len(sample) > 0.8:
                    # It's probably text
                    return True

                # Check for common binary file signatures
                if (data[:2] == b'PK' or  # ZIP
                        data[:4] == b'\x89PNG' or  # PNG
                        data[:3] == b'GIF' or  # GIF
                        data[:2] == b'BM' or  # BMP
                        data[:4] == b'\xFF\xD8\xFF\xE0' or  # JPEG
                        data[:5] == b'%PDF-'):  # PDF
                    return False

                # If we're not sure, lean toward text for human readability
                return True
            except:
                return False
    except:
        return False


def check_external_server(host, port, timeout=5):
    """Check if an external server is up by attempting to connect"""
    try:
        # Clean up hostname
        if not isinstance(host, str) or not host.strip():
            return False

        host = host.strip()

        # Check for invalid characters in hostname
        if any(c < ' ' or c > '~' for c in host):
            return False

        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(timeout)
        test_socket.connect((host, port))
        test_socket.close()
        return True
    except:
        return False


def is_problematic_resource(selector, file_size, download_time):
    """Identify problematic resources based on behavior"""
    # Resources that are known to be problematic
    problem_keywords = ['firehose', 'tarpit', 'godot']

    # Check for known problem keywords
    if any(keyword in selector.lower() for keyword in problem_keywords):
        return True

    # Very large files (>1MB) with unusual timing patterns
    if file_size > 1024 * 1024 and download_time > 15:
        return True

    # Resources that timeout or exceed limits
    if download_time >= 25:  # Close to our 30s limit
        return True

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
    problematic_resources = set()  # Track resources that caused issues

    # Store file data and sizes
    text_file_contents = {}
    file_sizes = {}
    download_times = {}  # Track how long each request took

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
        start_request_time = time.time()
        response = send_gopher_request(
            current_host,
            current_port,
            selector,
            timeout=10,  # 10 seconds for socket operations
            max_data_size=10 * 1024 * 1024,  # 10MB maximum response size
            max_time=30  # 30 seconds maximum total request time
        )
        request_duration = time.time() - start_request_time
        download_times[selector] = request_duration

        if not response:
            invalid_references.add(selector)
            continue

        # Check if this is a problematic resource
        if is_problematic_resource(selector, len(response), request_duration):
            problematic_resources.add(selector)

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
                    if item_selector not in text_files and item_selector not in binary_files:
                        text_files.append(item_selector)
                        selectors_to_visit.append((item_selector, item_host, item_port))
                elif item_type == '3':  # Error
                    invalid_references.add(item_selector)
                elif item_type != 'i':  # Binary file (not info)
                    if item_selector not in binary_files and item_selector not in text_files:
                        binary_files.append(item_selector)
                        selectors_to_visit.append((item_selector, item_host, item_port))
        else:
            # It's a file
            file_size = len(response)
            file_sizes[selector] = file_size

            # Determine if it's text or binary
            if is_text_file(response):
                if selector not in binary_files:  # Don't reassign binary files
                    if selector not in text_files:
                        text_files.append(selector)
                    # Only store content for small text files
                    if file_size < 1024 * 1024:  # 1MB limit
                        text_file_contents[selector] = response
            else:
                if selector not in text_files:  # Don't reassign text files
                    if selector not in binary_files:
                        binary_files.append(selector)

    # Remove problematic resources from consideration
    clean_text_files = [f for f in text_files if f not in problematic_resources]
    clean_binary_files = [f for f in binary_files if f not in problematic_resources]

    # Calculate file statistics - only consider "clean" files
    smallest_text_file = None
    largest_text_file = None
    smallest_text_size = float('inf')
    largest_text_size = 0

    for file in clean_text_files:
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

    for file in clean_binary_files:
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
    print(f"a. The number of Gopher directories on the server: {len(directories)}")

    print(f"\nb. The number of simple text files: {len(clean_text_files)}")
    print("List of all simple text files (full path):")
    for file in sorted(clean_text_files):
        size = file_sizes.get(file, "unknown")
        print(f"  {file} ({size} bytes)")

    print(f"\nc. The number of binary (i.e. non-text) files: {len(clean_binary_files)}")
    print("List of all binary files (full path):")
    for file in sorted(clean_binary_files):
        size = file_sizes.get(file, "unknown")
        print(f"  {file} ({size} bytes)")

    if smallest_text_file:
        print(f"\nd. The contents of the smallest text file ({smallest_text_file}, {smallest_text_size} bytes):")
        if smallest_text_file in text_file_contents:
            try:
                content = text_file_contents[smallest_text_file].decode('utf-8', errors='replace')
                print(content)
            except:
                print("Unable to display content")
        else:
            print("Content not available")

    if largest_text_file:
        print(f"\ne. The size of the largest text file: {largest_text_file} ({largest_text_size} bytes)")

    if smallest_binary_file:
        print(f"\nf. The size of the smallest binary file: {smallest_binary_file} ({smallest_binary_size} bytes)")

    if largest_binary_file:
        print(f"\ng. The size of the largest binary file: {largest_binary_file} ({largest_binary_size} bytes)")

    print(f"\nh. The number of unique invalid references: {len(invalid_references)}")

    print("\ni. External servers referenced and their status:")
    for (host, port), is_up in sorted(external_servers.items(), key=lambda x: str(x[0])):
        if not isinstance(host, str) or any(ord(c) > 127 for c in host):
            continue  # Skip entries with non-ASCII characters
        status = "up" if is_up else "down"
        print(f"  {host}:{port} - {status}")

    if problematic_resources:
        print("\nProblematic resources detected (excluded from statistics):")
        for resource in sorted(problematic_resources):
            print(f"  {resource}")


if __name__ == "__main__":
    main()