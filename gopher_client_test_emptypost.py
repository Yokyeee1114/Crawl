import socket

def fetch_gopher_root():
    host = 'comp3310.ddns.net'
    port = 70
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        print("Connecting to Gopher server...")
        s.connect((host, port))
        s.sendall(b'\r\n')  # 空请求 = 请求根目录
        data = s.recv(4096)
        print("Response from server:\n")
        print(data.decode(errors='ignore'))

if __name__ == '__main__':
    fetch_gopher_root()
