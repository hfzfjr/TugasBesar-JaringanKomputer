import socket
import time
import argparse
import threading
from datetime import datetime

# ============================================================
#  KONFIGURASI
# ============================================================
PROXY_HOST = "127.0.0.1"   # ganti ke IP Laptop B (Proxy) saat multi-laptop
PROXY_PORT = 8080

SERVER_HOST = "127.0.0.1"  # ganti ke IP Laptop A (Web Server) saat multi-laptop
UDP_PORT    = 9000

UDP_COUNT   = 10            # jumlah paket UDP yang dikirim
UDP_TIMEOUT = 1.0           # timeout per paket (detik)
UDP_INTERVAL = 0.5          # jeda antar paket (detik)

# ============================================================
#  HELPER: LOGGING
# ============================================================
def log(tag, message):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{tag}] {message}")

# ============================================================
#  MODE TCP - HTTP Client via Proxy
# ============================================================
def mode_tcp(path="/"):
    """Kirim HTTP GET request ke Proxy, tampilkan response."""
    print("=" * 55)
    print("  MODE TCP - HTTP via Proxy")
    print(f"  Proxy  : {PROXY_HOST}:{PROXY_PORT}")
    print(f"  Path   : {path}")
    print("=" * 55)

    try:
        # Buat koneksi TCP ke proxy
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((PROXY_HOST, PROXY_PORT))
        log("TCP", f"Terhubung ke Proxy {PROXY_HOST}:{PROXY_PORT}")

        # Kirim HTTP GET request
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {PROXY_HOST}:{PROXY_PORT}\r\n"
            f"Connection: close\r\n"
            "\r\n"
        )
        s.sendall(request.encode("utf-8"))
        log("TCP", f"Request terkirim → GET {path}")

        # Terima response
        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()

        # Pisahkan header dan body
        if b"\r\n\r\n" in response:
            header_raw, body = response.split(b"\r\n\r\n", 1)
        else:
            header_raw = response
            body = b""

        header_str  = header_raw.decode("utf-8", errors="ignore")
        status_line = header_str.split("\r\n")[0]

        print("\n─── HTTP Response ───────────────────────────────────")
        print(f"Status : {status_line}")
        print(f"Size   : {len(response)} bytes (header + body)")
        print("\n─── Header ──────────────────────────────────────────")
        print(header_str)
        print("─── Body (500 karakter pertama) ─────────────────────")
        print(body.decode("utf-8", errors="ignore")[:500])
        print("─────────────────────────────────────────────────────\n")

        log("TCP", f"Response diterima: {status_line} | {len(response)} bytes")

    except ConnectionRefusedError:
        log("TCP", f"GAGAL - Proxy {PROXY_HOST}:{PROXY_PORT} tidak bisa dijangkau")
        print("Pastikan proxy.py sudah dijalankan terlebih dahulu.")
    except socket.timeout:
        log("TCP", "GAGAL - Timeout menunggu response dari proxy")
    except Exception as e:
        log("TCP", f"Error: {e}")

# ============================================================
#  MODE UDP - QoS Pinger
# ============================================================
def mode_udp():
    """Kirim UDP ping ke Web Server, hitung RTT, packet loss, jitter."""
    print("=" * 55)
    print("  MODE UDP - QoS Measurement")
    print(f"  Target : {SERVER_HOST}:{UDP_PORT}")
    print(f"  Paket  : {UDP_COUNT} | Timeout: {UDP_TIMEOUT}s")
    print("=" * 55)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(UDP_TIMEOUT)

    rtt_list    = []
    sent        = 0
    received    = 0
    timeout_cnt = 0

    for seq in range(1, UDP_COUNT + 1):
        t_send  = time.time()
        payload = f"Ping {seq} {t_send:.6f}".encode("utf-8")

        try:
            s.sendto(payload, (SERVER_HOST, UDP_PORT))
            sent += 1

            data, _ = s.recvfrom(1024)
            t_recv  = time.time()

            rtt_ms = (t_recv - t_send) * 1000
            rtt_list.append(rtt_ms)
            received += 1

            log("UDP", f"Seq {seq:>2} | RTT: {rtt_ms:.3f} ms | Echo: {data.decode('utf-8', errors='ignore')[:30]}")

        except socket.timeout:
            timeout_cnt += 1
            log("UDP", f"Seq {seq:>2} | Request timed out")

        except Exception as e:
            log("UDP", f"Seq {seq:>2} | Error: {e}")

        time.sleep(UDP_INTERVAL)

    s.close()

    # ── STATISTIK ────────────────────────────────────────────
    lost        = sent - received
    loss_pct    = (lost / sent * 100) if sent > 0 else 0.0

    if rtt_list:
        rtt_min = min(rtt_list)
        rtt_avg = sum(rtt_list) / len(rtt_list)
        rtt_max = max(rtt_list)

        # Jitter = standar deviasi selisih RTT berturut-turut
        if len(rtt_list) >= 2:
            diffs   = [abs(rtt_list[i] - rtt_list[i-1]) for i in range(1, len(rtt_list))]
            jitter  = (sum(d**2 for d in diffs) / len(diffs)) ** 0.5
        else:
            jitter  = 0.0

        # Throughput: total payload / durasi pengujian (kbps)
        total_payload_bytes = sum(len(f"Ping {i} {0:.6f}".encode()) for i in range(1, sent + 1))
        duration_s          = sent * UDP_INTERVAL
        throughput_kbps     = (total_payload_bytes * 8 / 1000) / duration_s if duration_s > 0 else 0
    else:
        rtt_min = rtt_avg = rtt_max = jitter = throughput_kbps = 0.0

    print("\n" + "=" * 55)
    print("  STATISTIK QoS")
    print("=" * 55)
    print(f"  Dikirim      : {sent} paket")
    print(f"  Diterima     : {received} paket")
    print(f"  Hilang       : {lost} paket ({loss_pct:.1f}%)")
    print(f"  RTT Min      : {rtt_min:.3f} ms")
    print(f"  RTT Avg      : {rtt_avg:.3f} ms")
    print(f"  RTT Max      : {rtt_max:.3f} ms")
    print(f"  Jitter       : {jitter:.3f} ms")
    print(f"  Throughput   : {throughput_kbps:.2f} kbps")
    print("=" * 55)

# ============================================================
#  MODE MULTI - Jalankan beberapa HTTP request bersamaan
# ============================================================
def single_request(thread_id, path):
    """Satu HTTP request untuk uji concurrent."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((PROXY_HOST, PROXY_PORT))

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {PROXY_HOST}:{PROXY_PORT}\r\n"
            f"Connection: close\r\n"
            "\r\n"
        )
        t_start = time.time()
        s.sendall(request.encode())

        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()

        elapsed = (time.time() - t_start) * 1000
        status  = response.split(b"\r\n")[0].decode("utf-8", errors="ignore")
        log("MULTI", f"Thread-{thread_id} | {path} | {status} | {elapsed:.1f} ms | {len(response)} bytes")

    except Exception as e:
        log("MULTI", f"Thread-{thread_id} | ERROR: {e}")

def mode_multi(count=5):
    """Jalankan beberapa request HTTP secara bersamaan."""
    paths = ["/", "/osi.html", "/tcpip.html", "/qos.html", "/implementation.html"]
    print("=" * 55)
    print(f"  MODE MULTI - {count} Client Concurrent")
    print(f"  Proxy : {PROXY_HOST}:{PROXY_PORT}")
    print("=" * 55)

    threads = []
    for i in range(count):
        path = paths[i % len(paths)]
        t = threading.Thread(target=single_request, args=(i + 1, path))
        threads.append(t)

    t_start = time.time()

    # Start semua thread hampir bersamaan
    for t in threads:
        t.start()

    # Tunggu selesai
    for t in threads:
        t.join()

    elapsed = (time.time() - t_start) * 1000
    print(f"\n[DONE] Semua {count} request selesai dalam {elapsed:.1f} ms\n")

# ============================================================
#  MAIN + ARGUMENT PARSER
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Client Jaringan Komputer Modul 8")
    parser.add_argument(
        "-mode",
        choices=["tcp", "udp", "multi"],
        required=True,
        help="tcp = HTTP via proxy | udp = QoS measurement | multi = concurrent test"
    )
    parser.add_argument(
        "-path",
        default="/",
        help="Path HTTP untuk mode tcp (default: /)"
    )
    parser.add_argument(
        "-n",
        type=int,
        default=5,
        help="Jumlah client concurrent untuk mode multi (default: 5)"
    )
    parser.add_argument(
        "-proxy",
        default=PROXY_HOST,
        help=f"IP Proxy (default: {PROXY_HOST})"
    )
    parser.add_argument(
        "-server",
        default=SERVER_HOST,
        help=f"IP Web Server untuk UDP (default: {SERVER_HOST})"
    )

    args = parser.parse_args()

    # Override host dari argumen
    PROXY_HOST  = args.proxy
    SERVER_HOST = args.server

    if args.mode == "tcp":
        mode_tcp(args.path)
    elif args.mode == "udp":
        mode_udp()
    elif args.mode == "multi":
        mode_multi(args.n)
