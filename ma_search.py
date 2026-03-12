#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IP和端口扫描工具（修复socket not callable错误）
解决：多线程+代理下'socket' object is not callable问题
"""

import socket
import threading
import argparse
from ipaddress import ip_address, ip_network
import sys
from typing import List, Dict
import random
import socks  # pip install pysocks

# 全局锁
print_lock = threading.Lock()
proxy_lock = threading.Lock()
# 存储结果
open_ports = []
# 代理池
proxy_pool = []

def load_proxy_pool(proxy_input: str) -> List[Dict[str, str]]:
    """解析代理池（逻辑不变）"""
    proxies = []
    if proxy_input.startswith("file:"):
        file_path = proxy_input.replace("file:", "", 1)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            for line in lines:
                proxy = parse_proxy(line)
                if proxy:
                    proxies.append(proxy)
        except FileNotFoundError:
            print(f"[错误] 代理文件不存在：{file_path}")
            sys.exit(1)
        except Exception as e:
            print(f"[错误] 读取代理文件失败：{str(e)}")
            sys.exit(1)
    else:
        proxy_list = proxy_input.split(",")
        for proxy_str in proxy_list:
            proxy = parse_proxy(proxy_str.strip())
            if proxy:
                proxies.append(proxy)
    
    if not proxies:
        print("[错误] 未解析到有效代理，请检查代理格式")
        sys.exit(1)
    
    print(f"[*] 成功加载 {len(proxies)} 个有效代理")
    return proxies

def parse_proxy(proxy_str: str) -> Dict[str, str]:
    """解析单个代理（逻辑不变）"""
    try:
        proxy_type, addr = proxy_str.split("://")
        host, port = addr.split(":")
        port = int(port)
        
        if proxy_type.lower() not in ["http", "socks5"]:
            print(f"[警告] 不支持的代理类型 {proxy_type}，仅支持http/socks5，已忽略")
            return None
        
        if not (1 <= port <= 65535):
            print(f"[警告] 代理端口 {port} 超出范围，已忽略")
            return None
        
        return {
            "type": proxy_type.lower(),
            "host": host,
            "port": port
        }
    except ValueError:
        print(f"[警告] 代理格式错误 {proxy_str}，正确示例：socks5://127.0.0.1:1080，已忽略")
        return None

def get_next_proxy() -> Dict[str, str]:
    """轮询获取代理（逻辑不变）"""
    with proxy_lock:
        if not proxy_pool:
            return None
        proxy = proxy_pool.pop(0)
        proxy_pool.append(proxy)
        return proxy

def scan_port(ip: str, port: int, timeout: float = 3.0, use_proxy: bool = False) -> None:
    """
    扫描单个端口（核心修复：不再全局替换socket，改用局部socksocket实例）
    """
    sock = None
    try:
        if use_proxy:
            # 获取代理
            proxy = get_next_proxy()
            if not proxy:
                with print_lock:
                    print(f"[!] {ip}:{port} 无可用代理，跳过扫描")
                return
            
            # 直接创建socksocket实例（核心修复：不修改全局socket）
            proxy_type = socks.SOCKS5 if proxy["type"] == "socks5" else socks.HTTP
            sock = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
            # 为当前socksocket配置代理（仅作用于这个实例，不影响全局）
            sock.set_proxy(proxy_type, proxy["host"], proxy["port"])
        else:
            # 无代理：创建原生socket实例
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # 设置超时
        sock.settimeout(timeout)
        # 尝试连接
        result = sock.connect_ex((ip, port))
        
        with print_lock:
            if result == 0:
                proxy_info = f"（代理：{proxy['type']}://{proxy['host']}:{proxy['port']}）" if use_proxy else ""
                print(f"[+] {ip}:{port} 开放 {proxy_info}")
                open_ports.append((ip, port))
    
    except socket.timeout:
        with print_lock:
            pass
    except socket.error as e:
        with print_lock:
            print(f"[×] {ip}:{port} 扫描出错: {str(e)}")
    except Exception as e:
        with print_lock:
            print(f"[×] {ip}:{port} 未知错误: {str(e)}")
    finally:
        # 确保套接字关闭（无论是否出错）
        if sock:
            try:
                sock.close()
            except:
                pass

def parse_ip_range(ip_input: str) -> List[str]:
    """解析IP范围（逻辑不变）"""
    ip_list = []
    if "/" in ip_input:
        try:
            network = ip_network(ip_input, strict=False)
            for ip in network.hosts():
                ip_list.append(str(ip))
            return ip_list
        except ValueError:
            print(f"[错误] 子网格式错误: {ip_input}")
            sys.exit(1)
    if "-" in ip_input:
        try:
            ip_prefix, ip_suffix = ip_input.split("-")
            prefix_parts = ip_prefix.rsplit(".", 1)
            base_ip = prefix_parts[0]
            start_num = int(prefix_parts[1])
            end_num = int(ip_suffix)
            if start_num > end_num or end_num > 255:
                print("[错误] IP段数字范围无效（需满足0≤开始≤结束≤255）")
                sys.exit(1)
            for num in range(start_num, end_num + 1):
                ip_list.append(f"{base_ip}.{num}")
            return ip_list
        except ValueError:
            print(f"[错误] IP段格式错误: {ip_input}，正确示例: 192.168.1.1-10")
            sys.exit(1)
    try:
        ip_address(ip_input)
        ip_list.append(ip_input)
        return ip_list
    except ValueError:
        print(f"[错误] IP地址格式错误: {ip_input}")
        sys.exit(1)

def parse_port_range(port_input: str) -> List[int]:
    """解析端口范围（逻辑不变）"""
    port_list = []
    if "," in port_input:
        ports = port_input.split(",")
        for port in ports:
            try:
                port_num = int(port.strip())
                if 1 <= port_num <= 65535:
                    port_list.append(port_num)
                else:
                    print(f"[警告] 端口号 {port_num} 超出范围，已忽略")
            except ValueError:
                print(f"[警告] 无效端口号 {port}，已忽略")
        return port_list
    if "-" in port_input:
        try:
            start_port, end_port = port_input.split("-")
            start = int(start_port.strip())
            end = int(end_port.strip())
            if start > end or start < 1 or end > 65535:
                print("[错误] 端口范围无效（需满足1≤开始≤结束≤65535）")
                sys.exit(1)
            port_list = list(range(start, end + 1))
            return port_list
        except ValueError:
            print(f"[错误] 端口范围格式错误: {port_input}，正确示例: 1-100")
            sys.exit(1)
    try:
        port_num = int(port_input)
        if 1 <= port_num <= 65535:
            port_list.append(port_num)
            return port_list
        else:
            print(f"[错误] 端口号 {port_num} 超出范围（1-65535）")
            sys.exit(1)
    except ValueError:
        print(f"[错误] 端口号格式错误: {port_input}")
        sys.exit(1)

def main():
    """主函数（逻辑不变，仅调整默认超时为3秒）"""
    parser = argparse.ArgumentParser(
        description="Python IP和端口扫描工具（支持代理池，修复socket错误）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 带SOCKS5代理扫描（修复后）
  python ip_port_scanner.py -i 101.37.203.198 -p 8988-8997 -x socks5://127.0.0.1:7891 -t 3
        """
    )
    
    parser.add_argument("-i", "--ip", required=True, help="目标IP/IP段/子网")
    parser.add_argument("-p", "--port", required=True, help="目标端口/端口范围")
    parser.add_argument("-t", "--timeout", type=float, default=3.0, help="连接超时时间（秒），默认3秒（代理推荐≥3）")
    parser.add_argument("-n", "--threads", type=int, default=20, help="扫描线程数，默认20（建议不超过50）")
    parser.add_argument("-x", "--proxy", help="代理池（格式：socks5://IP:端口 或 file:/路径）")
    
    args = parser.parse_args()
    
    # 加载代理池
    use_proxy = False
    global proxy_pool
    if args.proxy:
        proxy_pool = load_proxy_pool(args.proxy)
        use_proxy = True
    
    # 解析IP和端口
    print(f"[*] 正在解析目标IP: {args.ip}")
    target_ips = parse_ip_range(args.ip)
    print(f"[*] 解析出 {len(target_ips)} 个目标IP")
    
    print(f"[*] 正在解析目标端口: {args.port}")
    target_ports = parse_port_range(args.port)
    print(f"[*] 解析出 {len(target_ports)} 个目标端口")
    
    # 限制线程数（代理扫描建议≤50）
    max_threads = min(args.threads, 50)
    proxy_note = f"，使用代理池（{len(proxy_pool)}个代理）" if use_proxy else ""
    print(f"[*] 开始扫描（线程数: {max_threads}，超时时间: {args.timeout}秒{proxy_note}）")
    print("-" * 80)
    
    # 启动扫描线程
    threads = []
    semaphore = threading.Semaphore(max_threads)
    
    for ip in target_ips:
        for port in target_ports:
            semaphore.acquire()
            thread = threading.Thread(
                target=lambda ip, port: (scan_port(ip, port, args.timeout, use_proxy), semaphore.release()),
                args=(ip, port)
            )
            threads.append(thread)
            thread.start()
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    # 输出结果
    print("-" * 80)
    print("[*] 扫描完成！")
    if open_ports:
        print(f"[+] 共发现 {len(open_ports)} 个开放端口:")
        for ip, port in open_ports:
            print(f"    {ip}:{port}")
    else:
        print("[-] 未发现开放的端口")

if __name__ == "__main__":
    try:
        import socks
    except ImportError:
        print("[错误] 缺少pysocks库，请先安装：pip install pysocks")
        sys.exit(1)
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] 用户中断了扫描进程")
        sys.exit(0)
    except Exception as e:
        print(f"\n[×] 程序运行出错: {str(e)}")
        sys.exit(1)
