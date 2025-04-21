import socket
import time


def send_gopher_request(host, port, selector=""):
    """Send a request to a Gopher server and return the response"""
    print(f"[{time.strftime('%H:%M:%S')}] Sending request: {selector}")

    # Create a socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

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
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk

    # Close the socket
    s.close()

    return data


def parse_gopher_menu(menu_data):
    """Parse a Gopher menu into a list of items"""
    lines = menu_data.decode('utf-8', errors='replace').split('\r\n')
    items = []

    for line in lines:
        # Skip empty lines or the ending period line
        if not line or line == '.':
            continue

        if len(line) < 2:
            continue

        # Extract item type, display string, selector, host, and port
        item_type = line[0]
        parts = line[1:].split('\t')

        if len(parts) >= 4:
            display_string = parts[0]
            selector = parts[1]
            host = parts[2]
            try:
                port = int(parts[3])
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
    return host1 == host2 and port1 == port2


def main():
    # Server configuration - update these values
    host = "comp3310.ddns.net"  # Change to your Gopher server
    port = 70  # Default Gopher port

    # Track visited selectors to avoid loops
    visited_selectors = set()

    # Track directories, text files, and binary files
    directories = []
    text_files = []
    binary_files = []

    # Start with the root selector
    selectors_to_visit = [("", host, port)]

    while selectors_to_visit:
        selector, current_host, current_port = selectors_to_visit.pop(0)

        # Skip if already visited
        if selector in visited_selectors:
            continue

        visited_selectors.add(selector)

        try:
            # Send request to the server
            response = send_gopher_request(current_host, current_port, selector)

            # For directories (menus), parse the response and add new selectors to visit
            if not selector or selector.endswith('/'):
                directories.append(selector)
                items = parse_gopher_menu(response)

                for item in items:
                    item_type = item['type']
                    item_selector = item['selector']
                    item_host = item['host']
                    item_port = item['port']

                    # Only follow links to the same server
                    if is_same_server(current_host, current_port, item_host, item_port):
                        if item_type == '1':  # Directory
                            selectors_to_visit.append((item_selector, item_host, item_port))
                        elif item_type == '0':  # Text file
                            text_files.append(item_selector)
                            selectors_to_visit.append((item_selector, item_host, item_port))
                        elif item_type not in ['i', '3']:  # Binary file (not info or error)
                            binary_files.append(item_selector)
                            selectors_to_visit.append((item_selector, item_host, item_port))
            else:
                # This was a file download, check if text or binary
                try:
                    response.decode('utf-8')
                    # If we can decode it as UTF-8, it's probably a text file
                    if selector not in text_files:
                        text_files.append(selector)
                except UnicodeDecodeError:
                    # If we can't decode it as UTF-8, it's probably a binary file
                    if selector not in binary_files:
                        binary_files.append(selector)

        except Exception as e:
            print(f"Error processing {selector}: {e}")
            continue

    # Print summary
    print("\n--- Summary ---")
    print(f"Number of directories: {len(directories)}")
    print(f"Number of text files: {len(text_files)}")
    print("Text files:")
    for file in text_files:
        print(f"  {file}")

    print(f"Number of binary files: {len(binary_files)}")
    print("Binary files:")
    for file in binary_files:
        print(f"  {file}")


if __name__ == "__main__":
    main()