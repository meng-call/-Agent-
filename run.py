"""
合约风控审查 Agent 系统 — 开发服务器启动脚本.

自动清理端口占用，然后启动 uvicorn。
用法: python run.py
"""

import os
import subprocess
import sys
import time


def kill_port(port: int) -> bool:
    """终止占用指定端口的全部进程（Windows）."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return False

    killed = set()
    for line in result.stdout.splitlines():
        if f":{port}" not in line or "LISTENING" not in line:
            continue
        parts = line.split()
        pid = parts[-1]
        if pid in killed:
            continue
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", pid],
                capture_output=True, timeout=10,
            )
            killed.add(pid)
            print(f"  已终止进程 PID={pid}")
        except Exception:
            pass

    return len(killed) > 0


def main():
    port = int(os.environ.get("PORT", 8001))

    print("=" * 55)
    print("  合约风控审查 Agent 系统 — 开发服务器")
    print("=" * 55)

    # 1. 清理端口
    print(f"\n[1/2] 检查端口 {port}…")
    if kill_port(port):
        time.sleep(1)
        print(f"  端口 {port} 已释放")
    else:
        print(f"  端口 {port} 未被占用")

    # 2. 启动 uvicorn
    print(f"\n[2/2] 启动服务 http://localhost:{port} …\n")
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )


if __name__ == "__main__":
    main()
