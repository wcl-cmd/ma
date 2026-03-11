#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket
import threading
import argparse
from ipaddress import ip_address, ip_network
import sys
from typing import List, Dict
import random
# 需安装pysocks库：pip install pysocks
import socks

# 全局锁，保证多线程输出不混乱
print_lock = threading.Lock()
# 存储开放的端口结果
open_ports = []
# 代理池（全局）
proxy_pool = []
# 代理池锁（保证多线程轮询代理时不冲突）
proxy_lock = threading.Lock()

def load_proxy_pool(proxy_input: str) -> List[Dict[str, str]]:
    """
    解析代理池输入，生成代理列表
    支持格式：
        1. 直接输入单个代理：socks5://127.0.0.1:1080
        2. 直接输入多个代理：socks5://127.0.0.1:1080,http://127.0.0.1:8080
        3. 读取代理文件：file:/path/to/proxy.txt（文件每行一个代理）
    
    代理格式要求：[协议]://[IP]:[端口] （如 socks5://127.0.0.1:1080、http://192.168.1.1:8080）
    """
    proxies = []
    
    # 处理代理文件
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
    # 处理直接输入的代理（单个/多个）
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
    """
    解析单个代理字符串，返回标准化代理字典
    输入示例：socks5://127.0.0.1:1080 → {"type": "socks5", "host": "127.0.0.1", "port": 1080}
    """
    try:
        proxy_type, addr = proxy_str.split("://")
        host, port = addr.split(":")
        port = int(port)
        
        # 验证代理类型
        if proxy_type.lower() not in ["http", "socks5"]:
            print(f"[警告] 不支持的代理类型 {proxy_type}，仅支持http/socks5，已忽略")
            return None
        
        # 验证端口范围
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
    """
    轮询获取代理池中的下一个代理（线程安全）
    """
    with proxy_lock:
        if not proxy_pool:
            return None
        # 弹出第一个代理，再添加到末尾，实现轮询
        proxy = proxy_pool.pop(0)
        proxy_pool.append(proxy)
        return proxy

def scan_port(ip: str, port: int, timeout: float = 1.0, use_proxy: bool = False) -> None:
    """
    扫描单个IP的指定端口是否开放（支持代理）
    
    参数:
        ip: 目标IP地址
        port: 目标端口号
        timeout: 连接超时时间（秒）
        use_proxy: 是否使用代理扫描
    """
    # 保存原始socket配置，用于还原
    original_socket = None
    try:
        if use_proxy:
            # 获取代理
            proxy = get_next_proxy()
            if not proxy:
                with print_lock:
                    print(f"[!] {ip}:{port} 无可用代理，跳过扫描")
                return
            
            # 配置socket通过代理连接
            proxy_type = socks.SOCKS5 if proxy["type"] == "socks5" else socks.HTTP
            original_socket = socks.socket.socket()  # 保存原始socket
            socks.set_default_proxy(proxy_type, proxy["host"], proxy["port"])
            socket.socket = socks.socksocket
        
        # 创建TCP套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        # 尝试连接目标IP和端口
        result = sock.connect_ex((ip, port))  # 0表示连接成功
        
        with print_lock:
            if result == 0:
                proxy_info = f"（代理：{proxy['type']}://{proxy['host']}:{proxy['port']}）" if use_proxy else ""
                print(f"[+] {ip}:{port} 开放 {proxy_info}")
                open_ports.append((ip, port))
    
    except socket.timeout:
        with print_lock:
            print(f"[!] {ip}:{port} 连接超时")
    except socket.error as e:
        with print_lock:
            print(f"[×] {ip}:{port} 扫描出错: {str(e)}")
    except Exception as e:
        with print_lock:
            print(f"[×] {ip}:{port} 未知错误: {str(e)}")
    finally:
        # 还原原始socket配置（避免影响其他线程）
        if use_proxy and original_socket:
            socket.socket = original_socket
        # 确保套接字关闭
        try:
            sock.close()
        except:
            pass

def parse_ip_range(ip_input: str) -> List[str]:
    """解析IP范围输入，生成待扫描的IP列表（原有功能，无修改）"""
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
    """解析端口范围输入，生成待扫描的端口列表（原有功能，无修改）"""
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
    """主函数：解析命令行参数，启动扫描任务（新增代理参数）"""
    parser = argparse.ArgumentParser(
        description="Python IP和端口扫描工具（支持代理池）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基础用法（无代理）
  python ip_port_scanner.py -i 192.168.1.1 -p 80
  
  # 使用单个代理扫描
  python ip_port_scanner.py -i 192.168.1.1 -p 80 -x socks5://127.0.0.1:1080
  
  # 使用多个代理（逗号分隔）
  python ip_port_scanner.py -i 192.168.1.1-10 -p 80,443 -x socks5://127.0.0.1:1080,http://192.168.1.1:8080
  
  # 使用代理池文件（文件每行一个代理）
  python ip_port_scanner.py -i 192.168.1.0/24 -p 1-100 -x file:/tmp/proxy.txt
  
  # 自定义超时和线程数+代理
  python ip_port_scanner.py -i 192.168.1.1 -p 1-1000 -t 2 -n 50 -x socks5://127.0.0.1:1080
        """
    )
    
    # 原有参数
    parser.add_argument("-i", "--ip", required=True, help="目标IP/IP段/子网（如192.168.1.1、192.168.1.1-10、192.168.1.0/24）")
    parser.add_argument("-p", "--port", required=True, help="目标端口/端口范围（如80、1-100、80,443,22）")
    parser.add_argument("-t", "--timeout", type=float, default=1.0, help="连接超时时间（秒），默认1秒")
    parser.add_argument("-n", "--threads", type=int, default=20, help="扫描线程数，默认20（建议不超过100）")
    # 新增代理参数
    parser.add_argument("-x", "--proxy", help="代理池（支持单个/多个代理、代理文件，格式：socks5://IP:端口 或 file:/路径）")
    
    args = parser.parse_args()
    
    # 加载代理池（如果指定了代理参数）
    use_proxy = False
    if args.proxy:
        global proxy_pool
        proxy_pool = load_proxy_pool(args.proxy)
        use_proxy = True
    
    # 解析IP和端口列表（原有逻辑）
    print(f"[*] 正在解析目标IP: {args.ip}")
    target_ips = parse_ip_range(args.ip)
    print(f"[*] 解析出 {len(target_ips)} 个目标IP")
    
    print(f"[*] 正在解析目标端口: {args.port}")
    target_ports = parse_port_range(args.port)
    print(f"[*] 解析出 {len(target_ports)} 个目标端口")
    
    # 限制线程数
    max_threads = min(args.threads, 100)
    proxy_note = f"，使用代理池（{len(proxy_pool)}个代理）" if use_proxy else ""
    print(f"[*] 开始扫描（线程数: {max_threads}，超时时间: {args.timeout}秒{proxy_note}）")
    print("-" * 80)
    
    # 启动扫描线程（原有逻辑，新增use_proxy参数）
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
    
    # 输出汇总信息
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
        # 检查pysocks库是否安装
        try:
            import socks
        except ImportError:
            print("[错误] 缺少pysocks库，请先安装：pip install pysocks")
            sys.exit(1)
        main()
    except KeyboardInterrupt:
        print("\n[!] 用户中断了扫描进程")
        sys.exit(0)
    except Exception as e:
        print(f"\n[×] 程序运行出错: {str(e)}")
        sys.exit(1)
