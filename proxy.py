import socket
import threading
import os
from datetime import datetime

# ============================================================
#  KONFIGURASI
# ============================================================
PROXY_HOST = "0.0.0.0"
PROXY_PORT = 8080

# Alamat Web Server tujuan
SERVER_HOST = "127.0.0.1"   # ganti ke IP Laptop A saat multi-laptop
SERVER_PORT = 8000

# Timeout saat menghubungi web server (detik)
SERVER_TIMEOUT = 10

# Direktori penyimpanan cache (relatif terhadap proxy.py)
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_cache")

# Lock untuk proteksi cache dari race condition
cache_lock = threading.Lock()

# ============================================================
#  HELPER: LOGGING
# ============================================================
def log(tag, message):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{tag}] {message}")

# ============================================================
#  HELPER: INISIALISASI CACHE
# ============================================================
def init_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)
    log("CACHE", f"Cache directory: {CACHE_DIR}")

# ============================================================
#  HELPER: UBAH URL PATH → NAMA FILE CACHE
# ============================================================
def path_to_cache_key(path):
    """
    Contoh: /index.html → cache_index.html
            /css/style.css → cache_css_style.css
    """
    key = path.strip("/").replace("/", "_")
    if not key:
        key = "index.html"
    return "cache_" + key

# ============================================================
#  HELPER: CEK CACHE
# ============================================================
def get_from_cache(path):
    """Return bytes isi cache, atau None jika tidak ada."""
    key      = path_to_cache_key(path)
    filepath = os.path.join(CACHE_DIR, key)
    with cache_lock:
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                return f.read()
    return None

# ============================================================
#  HELPER: SIMPAN KE CACHE
# ============================================================
def save_to_cache(path, data):
    """Simpan raw HTTP response (bytes) ke file cache."""
    key      = path_to_cache_key(path)
    filepath = os.path.join(CACHE_DIR, key)
    with cache_lock:
        with open(filepath, "wb") as f:
            f.write(data)

# ============================================================
#  HELPER: PARSE HTTP REQUEST
# ============================================================
def parse_request(raw):
    try:
        first_line = raw.split("\r\n")[0]
        parts      = first_line.split(" ")
        method     = parts[0]
        path       = parts[1]
        return method, path
    except Exception:
        return None, None

# ============================================================
#  HELPER: FORWARD REQUEST KE WEB SERVER
# ============================================================
def forward_to_server(raw_request):
    """
    Kirim raw request ke web server, return raw response bytes.
    Raise Exception jika gagal / timeout.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(SERVER_TIMEOUT)
    s.connect((SERVER_HOST, SERVER_PORT))
    s.sendall(raw_request)

    response = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        response += chunk
    s.close()
    return response

# ============================================================
#  HELPER: BUAT RESPONSE ERROR SEDERHANA
# ============================================================
def make_error_response(code, text, description=""):
    body = f"<h1>{code} {text}</h1><p>{description}</p>".encode()
    header = (
        f"HTTP/1.1 {code} {text}\r\n"
        f"Content-Type: text/html\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        "\r\n"
    )
    return header.encode() + body

# ============================================================
#  HANDLER: SATU KONEKSI CLIENT (dijalankan di thread terpisah)
# ============================================================
def handle_client(conn, addr):
    client_ip = addr[0]
    try:
        # Terima request dari client
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

        if method is None or path is None:
            conn.sendall(make_error_response(400, "Bad Request", "Malformed HTTP request"))
            return

        log("PROXY", f"{client_ip} → {method} {path}")

        # ── CEK CACHE ────────────────────────────────────────
        cached = get_from_cache(path)
        if cached:
            conn.sendall(cached)
            log("CACHE", f"HIT  | {path} ({len(cached)} bytes) → {client_ip}")
            return

        # ── CACHE MISS: FORWARD KE WEB SERVER ───────────────
        log("CACHE", f"MISS | {path} → forwarding ke server {SERVER_HOST}:{SERVER_PORT}")
        try:
            response = forward_to_server(raw)
        except socket.timeout:
            log("PROXY", f"504 Gateway Timeout saat menghubungi server ({path})")
            conn.sendall(make_error_response(504, "Gateway Timeout",
                         f"Server {SERVER_HOST}:{SERVER_PORT} tidak merespons dalam {SERVER_TIMEOUT}s"))
            return
        except ConnectionRefusedError:
            log("PROXY", f"502 Bad Gateway - server menolak koneksi ({path})")
            conn.sendall(make_error_response(502, "Bad Gateway",
                         f"Tidak dapat terhubung ke server {SERVER_HOST}:{SERVER_PORT}"))
            return
        except Exception as e:
            log("PROXY", f"502 Bad Gateway - error: {e} ({path})")
            conn.sendall(make_error_response(502, "Bad Gateway", str(e)))
            return

        # Cek apakah response valid (mulai dengan HTTP)
        if not response.startswith(b"HTTP"):
            conn.sendall(make_error_response(502, "Bad Gateway", "Invalid response from server"))
            return

        # Simpan ke cache & kirim ke client
        save_to_cache(path, response)
        conn.sendall(response)

        # Ambil status code dari response untuk log
        try:
            status_line = response.split(b"\r\n")[0].decode()
            status_code = status_line.split(" ")[1]
        except Exception:
            status_code = "???"

        log("PROXY", f"{client_ip} ← {status_code} | {path} ({len(response)} bytes) [stored to cache]")

    except Exception as e:
        log("PROXY", f"Handler error: {e}")
        try:
            conn.sendall(make_error_response(500, "Internal Proxy Error", str(e)))
        except Exception:
            pass
    finally:
        conn.close()

# ============================================================
#  PROXY SERVER - Main loop
# ============================================================
def start_proxy():
    init_cache()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((PROXY_HOST, PROXY_PORT))
    server.listen(20)
    log("PROXY", f"Listening on port {PROXY_PORT}")
    log("PROXY", f"Forwarding ke Web Server → {SERVER_HOST}:{SERVER_PORT}")

    while True:
        try:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
            log("PROXY", f"New client {addr[0]} | Active threads: {threading.active_count()}")
        except Exception as e:
            log("PROXY", f"Accept error: {e}")

# ============================================================
#  MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("  PROXY SERVER - Jaringan Komputer Modul 8")
    print(f"  Listening : port {PROXY_PORT}")
    print(f"  Target    : {SERVER_HOST}:{SERVER_PORT}")
    print(f"  Cache dir : {CACHE_DIR}")
    print("=" * 55)

    start_proxy()
