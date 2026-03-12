#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Windows专属优化版：实时写入文件，中途停止也有内容
import requests
import socket
import socks
import threading
import os
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 核心配置（可自行修改）=====================
# 目标有效代理数量，达标立即停止
MAX_VALID_PROXIES = 100
# 校验超时时间（秒），Windows下建议≥3秒，1秒太严格很难抓到
CHECK_TIMEOUT = 3
# 校验并发线程数（Windows建议≤30，避免卡顿）
CHECK_THREADS = 20
# 代理文件输出路径（Windows用原生路径，r""避免转义问题）
OUTPUT_FILE = r"C:\Users\32544\Desktop\pythonkaifa\proxy_pool_100.txt"
# 代理抓取源（优先稳定源）
PROXY_SOURCE_URLS = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://www.proxy-list.download/api/v1/get?type=socks5",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt"
]
# ==================================================================

# 全局线程安全控制
valid_count = 0
count_lock = threading.Lock()
file_lock = threading.Lock()  # 防止多线程同时写文件冲突
stop_flag = threading.Event()  # 达标/手动停止时触发

def init_output_file():
    """初始化输出文件：自动创建目录+清空旧内容"""
    # 自动创建不存在的文件夹（Windows关键！）
    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"[✓] 自动创建目录：{output_dir}")
    # 清空旧文件内容
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("")
    print(f"[✓] 初始化输出文件：{OUTPUT_FILE}")

def write_proxy_to_file(proxy_str: str):
    """线程安全：把单个有效代理写入文件（实时追加）"""
    with file_lock:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(proxy_str + "\n")

def check_proxy_alive(proxy_str: str) -> bool:
    """校验单个代理是否可用"""
    if stop_flag.is_set():
        return False
    try:
        _, addr = proxy_str.split("://")
        host, port = addr.split(":")
        port = int(port)
        sock = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
        sock.set_proxy(socks.SOCKS5, host, port)
        sock.settimeout(CHECK_TIMEOUT)
        sock.connect(("8.8.8.8", 53))
        sock.close()
        return True
    except Exception:
        return False

def add_valid_proxy(proxy_str: str):
    """线程安全：添加有效代理+更新计数+实时写入文件"""
    global valid_count
    with count_lock:
        if valid_count >= MAX_VALID_PROXIES:
            return
        valid_count += 1
        print(f"[✓] 已获取 {valid_count}/{MAX_VALID_PROXIES} | {proxy_str}")
        # 实时写入文件！这是解决空文件的关键
        write_proxy_to_file(proxy_str)
        if valid_count >= MAX_VALID_PROXIES:
            stop_flag.set()
            print("[!] 已达到目标数量，停止抓取")

def signal_handler(signum, frame):
    """捕获Ctrl+C，手动停止时提示"""
    print("\n[!] 手动停止抓取，已获取的代理已保存到文件")
    stop_flag.set()

def fetch_proxies_from_url(url: str) -> list:
    """从单个源抓取代理"""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        lines = [line.strip() for line in resp.text.split("\n") if line.strip() and ":" in line]
        return [f"socks5://{line}" for line in lines if not line.startswith("#")]
    except Exception:
        return []

def main():
    # 注册Ctrl+C信号
    signal.signal(signal.SIGINT, signal_handler)
    # 初始化输出文件
    init_output_file()
    print(f"[*] 开始抓取SOCKS5代理，目标：{MAX_VALID_PROXIES} 个，实时写入到：{OUTPUT_FILE}")
    print("-" * 80)

    all_raw_proxies = set()
    for idx, url in enumerate(PROXY_SOURCE_URLS, 1):
        if stop_flag.is_set():
            break
        print(f"[*] 正在抓取第 {idx}/{len(PROXY_SOURCE_URLS)} 个源...")
        proxies = fetch_proxies_from_url(url)
        if not proxies:
            print(f"[!] 第 {idx} 个源抓取失败，跳过")
            continue
        new_proxies = set(proxies) - all_raw_proxies
        all_raw_proxies.update(new_proxies)
        print(f"[*] 本轮新增 {len(new_proxies)} 个待校验代理，累计待校验：{len(all_raw_proxies)} 个")

        # 并发校验
        with ThreadPoolExecutor(max_workers=CHECK_THREADS) as executor:
            future_to_proxy = {executor.submit(check_proxy_alive, proxy): proxy for proxy in new_proxies}
            for future in as_completed(future_to_proxy):
                if stop_flag.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                proxy = future_to_proxy[future]
                try:
                    is_alive = future.result()
                    if is_alive:
                        add_valid_proxy(proxy)
                except Exception:
                    continue

    print("-" * 80)
    print(f"[✓] 抓取结束！共获取 {valid_count} 个有效代理，已保存到：{OUTPUT_FILE}")

if __name__ == "__main__":
    # 检查依赖
    try:
        import requests
        import socks
    except ImportError:
        print("[错误] 缺少依赖，请先执行：")
        print("pip install requests pysocks -i https://pypi.tuna.tsinghua.edu.cn/simple")
        exit(1)
    main()
