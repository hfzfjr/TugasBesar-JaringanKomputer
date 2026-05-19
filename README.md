🗂️ Cara Pakai

```bash
# Terminal 1 (jalankan di folder HTML/)
python webserver.py

# Terminal 2
python proxy.py

# Terminal 3
python client.py -mode tcp -path /
python client.py -mode tcp -path /osi.html
python client.py -mode udp
python client.py -mode multi -n 5
```

🔧 Saat Pindah ke 3 Laptop
Cukup ubah 2 baris di proxy.py:

```bash
SERVER_HOST = "192.168.1.10"  # IP Laptop A (Web Server)
```

Dan 2 baris di client.py:

```bash
PROXY_HOST  = "192.168.1.11"  # IP Laptop B (Proxy)
SERVER_HOST = "192.168.1.10"  # IP Laptop A (Web Server)
```
