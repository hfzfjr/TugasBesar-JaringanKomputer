import socket
import threading
import os
import mimetypes
from datetime import datetime

# ============================================================
#  KONFIGURASI
# ============================================================
TCP_HOST = "0.0.0.0"
TCP_PORT = 8000
UDP_HOST = "0.0.0.0"
UDP_PORT = 9000

# Direktori tempat file HTML berada (sama dengan webserver.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
#  HELPER: LOGGING
# ============================================================
def log(tag, message):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{tag}] {message}")

# ============================================================
#  HELPER: BACA FILE
# ============================================================
def read_file(filepath):
    """Baca file sebagai bytes. Return (content_bytes, mime_type) atau None jika tidak ada."""
    if not os.path.exists(filepath):
        return None, None
    
    mime, _ = mimetypes.guess_type(filepath)
    if mime is None:
        mime = "application/octet-stream"
    
    with open(filepath, "rb") as f:
        return f.read(), mime

# ============================================================
#  HELPER: BUAT HTTP RESPONSE
# ============================================================
def build_response(status_code, status_text, content_type, body_bytes):
    header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        "\r\n"
    )
    return header.encode("utf-8") + body_bytes

# ============================================================
#  HELPER: PARSE HTTP REQUEST
# ============================================================
def parse_request(raw):
    """Ambil method dan path dari raw HTTP request."""
    try:
        first_line = raw.split("\r\n")[0]
        parts = first_line.split(" ")
        method = parts[0]
        path   = parts[1]
        return method, path
    except Exception:
        return None, None

# ============================================================
#  HANDLER: SATU KONEKSI TCP (dijalankan di thread terpisah)
# ============================================================
def handle_tcp_client(conn, addr):
    client_ip = addr[0]
    try:
        # Terima request (maks 4KB)
        raw = b""
        conn.settimeout(5)
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk
            if b"\r\n\r\n" in raw:
                break

        if not raw:
            return

        request_str = raw.decode("utf-8", errors="ignore")
        method, path = parse_request(request_str)

        if method is None:
            # Request tidak valid
            body = b"<h1>400 Bad Request</h1>"
            response = build_response(400, "Bad Request", "text/html", body)
            conn.sendall(response)
            log("TCP", f"{client_ip} | 400 Bad Request (malformed)")
            return

        # Hanya support GET
        if method != "GET":
            body = b"<h1>405 Method Not Allowed</h1>"
            response = build_response(405, "Method Not Allowed", "text/html", body)
            conn.sendall(response)
            log("TCP", f"{client_ip} | 405 Method Not Allowed")
            return

        # Normalize path: "/" → "/index.html"
        if path == "/":
            path = "/index.html"

        # Hapus query string jika ada
        if "?" in path:
            path = path.split("?")[0]

        # Cegah path traversal
        filepath = os.path.normpath(BASE_DIR + path)
        if not filepath.startswith(BASE_DIR):
            body = b"<h1>403 Forbidden</h1>"
            response = build_response(403, "Forbidden", "text/html", body)
            conn.sendall(response)
            log("TCP", f"{client_ip} | 403 Forbidden (path traversal)")
            return

        # Coba baca file
        content, mime = read_file(filepath)

        if content is None:
            # 404 - coba load halaman error custom
            error_path = os.path.join(BASE_DIR, "status", "404.html")
            error_content, error_mime = read_file(error_path)
            if error_content:
                response = build_response(404, "Not Found", "text/html", error_content)
            else:
                response = build_response(404, "Not Found", "text/html", b"<h1>404 Not Found</h1>")
            conn.sendall(response)
            log("TCP", f"{client_ip} | 404 Not Found → {path}")
            return

        # 200 OK
        response = build_response(200, "OK", mime, content)
        conn.sendall(response)
        log("TCP", f"{client_ip} | 200 OK → {path} ({len(content)} bytes)")

    except Exception as e:
        # 500 Internal Server Error
        try:
            error_path = os.path.join(BASE_DIR, "status", "500.html")
            error_content, _ = read_file(error_path)
            if error_content:
                response = build_response(500, "Internal Server Error", "text/html", error_content)
            else:
                response = build_response(500, "Internal Server Error", "text/html", b"<h1>500 Internal Server Error</h1>")
            conn.sendall(response)
        except Exception:
            pass
        log("TCP", f"{client_ip} | 500 Internal Server Error → {e}")

    finally:
        conn.close()

# ============================================================
#  TCP SERVER - Main loop
# ============================================================
def start_tcp_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((TCP_HOST, TCP_PORT))
    server.listen(10)
    log("TCP", f"HTTP Server listening on port {TCP_PORT}")

    while True:
        try:
            conn, addr = server.accept()
            # Spawn thread baru untuk tiap koneksi
            t = threading.Thread(target=handle_tcp_client, args=(conn, addr), daemon=True)
            t.start()
            log("TCP", f"New connection from {addr[0]} | Active threads: {threading.active_count()}")
        except Exception as e:
            log("TCP", f"Accept error: {e}")

# ============================================================
#  UDP SERVER - Echo server untuk QoS
# ============================================================
def start_udp_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((UDP_HOST, UDP_PORT))
    log("UDP", f"Echo Server listening on port {UDP_PORT}")

    while True:
        try:
            data, addr = server.recvfrom(1024)
            # Echo balik payload tanpa diubah
            server.sendto(data, addr)
            log("UDP", f"Echo → {addr[0]}:{addr[1]} | payload: {data.decode('utf-8', errors='ignore')}")
        except Exception as e:
            log("UDP", f"Error: {e}")

# ============================================================
#  MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("  WEB SERVER - Jaringan Komputer Modul 8")
    print(f"  TCP HTTP : port {TCP_PORT}")
    print(f"  UDP Echo : port {UDP_PORT}")
    print(f"  Base dir : {BASE_DIR}")
    print("=" * 55)

    # Jalankan UDP server di thread terpisah
    udp_thread = threading.Thread(target=start_udp_server, daemon=True)
    udp_thread.start()

    # Jalankan TCP server di main thread
    start_tcp_server()
