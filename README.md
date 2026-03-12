proxy.py
# 目标有效代理数量，达标立即停止
MAX_VALID_PROXIES = 100
# 校验超时时间（秒），Windows下建议≥3秒，1秒太严格很难抓到
CHECK_TIMEOUT = 3
# 校验并发线程数（Windows建议≤30，避免卡顿）
CHECK_THREADS = 20
# 代理文件输出路径（Windows用原生路径，r""避免转义问题）
OUTPUT_FILE = r"C:\Users\32544\Desktop\pythonkaifa\proxy_pool_100.txt"
# 代理抓取源（优先稳定源）
python proxy.py (更改时在py文件找到上方修改)

ma_search.py
    parser.add_argument("-i", "--ip", required=True, help="目标IP/IP段/子网")
    parser.add_argument("-p", "--port", required=True, help="目标端口/端口范围")
    parser.add_argument("-t", "--timeout", type=float, default=3.0, help="连接超时时间（秒），默认3秒（代理推荐≥3）")
    parser.add_argument("-n", "--threads", type=int, default=20, help="扫描线程数，默认20（建议不超过50）")
    parser.add_argument("-x", "--proxy", help="代理池（格式：socks5://IP:端口 或 file:/路径）")
python ma_search.py -i ip -p port -t time -n thread -x proxy
