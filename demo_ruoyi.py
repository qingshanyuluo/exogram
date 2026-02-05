#!/usr/bin/env python3
"""
Exogram Demo 脚本 - 若依管理系统操作日志查询演示
================================================

此脚本自动执行 Exogram 的四步流程：
1. setup-auth: 登录态初始化
2. record-live: 录制用户操作  
3. distill: 蒸馏认知
4. run: 执行任务

用于录制演示视频。

使用方法:
    python demo_ruoyi.py
    
    # 或者跳过某些步骤（如已完成登录态）
    python demo_ruoyi.py --skip-auth
    python demo_ruoyi.py --skip-auth --skip-record
"""

import subprocess
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# ANSI 颜色码
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_banner():
    """打印 Demo 横幅"""
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║     ███████╗██╗  ██╗ ██████╗  ██████╗ ██████╗  █████╗ ███╗   ███╗║
║     ██╔════╝╚██╗██╔╝██╔═══██╗██╔════╝ ██╔══██╗██╔══██╗████╗ ████║║
║     █████╗   ╚███╔╝ ██║   ██║██║  ███╗██████╔╝███████║██╔████╔██║║
║     ██╔══╝   ██╔██╗ ██║   ██║██║   ██║██╔══██╗██╔══██║██║╚██╔╝██║║
║     ███████╗██╔╝ ██╗╚██████╔╝╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║║
║     ╚══════╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝║
║                                                                  ║
║                    🎬 Demo 演示脚本 🎬                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
"""
    print(banner)

def print_step(step_num: int, title: str, description: str):
    """打印步骤标题"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.YELLOW}  步骤 {step_num}/4: {title}{Colors.ENDC}")
    print(f"{Colors.CYAN}  {description}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'='*70}{Colors.ENDC}\n")

def wait_for_user(message: str = "按 Enter 继续..."):
    """等待用户确认"""
    print(f"\n{Colors.YELLOW}{Colors.BOLD}👉 {message}{Colors.ENDC}")
    input()

def run_command(args: list, description: str) -> bool:
    """运行命令并显示输出"""
    print(f"{Colors.BLUE}▶ 执行: {' '.join(args)}{Colors.ENDC}\n")
    
    try:
        result = subprocess.run(
            args,
            cwd=Path(__file__).parent,
            env={**os.environ},
        )
        
        if result.returncode == 0:
            print(f"\n{Colors.GREEN}✅ {description} 完成!{Colors.ENDC}")
            return True
        else:
            print(f"\n{Colors.RED}❌ {description} 失败 (退出码: {result.returncode}){Colors.ENDC}")
            return False
            
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  用户中断{Colors.ENDC}")
        return True  # 用户手动中断视为正常
    except Exception as e:
        print(f"\n{Colors.RED}❌ 错误: {e}{Colors.ENDC}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Exogram Demo 演示脚本")
    parser.add_argument("--skip-auth", action="store_true", help="跳过登录态初始化")
    parser.add_argument("--skip-record", action="store_true", help="跳过录制步骤")
    parser.add_argument("--skip-distill", action="store_true", help="跳过蒸馏步骤")
    args = parser.parse_args()
    
    # 配置
    TOPIC = "RuoYiDemo"
    START_URL = "http://vue.ruoyi.vip/"
    AUTH_DOMAIN = "vue.ruoyi.vip"
    TASK = "帮我查一下'admin'账号在 2025年11月1日 到 12月1日 期间的操作日志"
    RECORDING_FILE = f"data/recordings/{TOPIC}.raw_steps.json"
    
    # Python 解释器
    python = sys.executable
    
    print_banner()
    
    print(f"{Colors.BOLD}📋 演示任务:{Colors.ENDC}")
    print(f"   {Colors.CYAN}{TASK}{Colors.ENDC}")
    print(f"\n{Colors.BOLD}🌐 目标网站:{Colors.ENDC} {START_URL}")
    print(f"{Colors.BOLD}📁 Topic:{Colors.ENDC} {TOPIC}")
    print(f"{Colors.BOLD}⏰ 开始时间:{Colors.ENDC} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    wait_for_user("准备好开始演示了吗？按 Enter 开始...")
    
    # ========== 步骤 1: 登录态初始化 ==========
    if not args.skip_auth:
        print_step(1, "setup-auth (登录态初始化)", 
                   "打开浏览器，手动登录若依管理系统 (admin/admin123)")
        
        print(f"{Colors.YELLOW}💡 提示:{Colors.ENDC}")
        print(f"   1. 浏览器将自动打开若依管理系统登录页")
        print(f"   2. 请使用账号 {Colors.BOLD}admin{Colors.ENDC} / 密码 {Colors.BOLD}admin123{Colors.ENDC} 登录")
        print(f"   3. 登录成功后，按 {Colors.BOLD}Ctrl+C{Colors.ENDC} 结束此步骤")
        
        wait_for_user()
        
        run_command([
            python, "-m", "exogram.cli",
            "setup-auth",
            "--start-url", START_URL
        ], "登录态初始化")
        
        wait_for_user("登录完成后，按 Enter 继续下一步...")
    else:
        print(f"\n{Colors.YELLOW}⏭️  跳过步骤 1: setup-auth{Colors.ENDC}")
    
    # ========== 步骤 2: 录制操作 ==========
    if not args.skip_record:
        print_step(2, "record-live (录制操作)", 
                   "录制一次查询操作日志的完整流程")
        
        print(f"{Colors.YELLOW}💡 录制指引:{Colors.ENDC}")
        print(f"   1. 点击左侧菜单 {Colors.BOLD}「系统监控」{Colors.ENDC}")
        print(f"   2. 展开后点击 {Colors.BOLD}「操作日志」{Colors.ENDC}")
        print(f"   3. 在操作人员输入框输入 {Colors.BOLD}admin{Colors.ENDC}")
        print(f"   4. 选择操作时间范围 {Colors.BOLD}2025-11-01 ~ 2025-12-01{Colors.ENDC}")
        print(f"   5. 点击 {Colors.BOLD}「搜索」{Colors.ENDC} 按钮")
        print(f"   6. 录制完成后，按 {Colors.BOLD}Ctrl+C{Colors.ENDC} 结束录制")
        
        wait_for_user()
        
        run_command([
            python, "-m", "exogram.cli",
            "record-live",
            "--topic", TOPIC,
            "--start-url", START_URL,
            "--auth-domain", AUTH_DOMAIN
        ], "录制操作")
        
        wait_for_user("录制完成后，按 Enter 继续下一步...")
    else:
        print(f"\n{Colors.YELLOW}⏭️  跳过步骤 2: record-live{Colors.ENDC}")
    
    # ========== 步骤 3: 蒸馏认知 ==========
    if not args.skip_distill:
        print_step(3, "distill (蒸馏认知)", 
                   "AI 分析录制的操作，提取可复用的认知")
        
        print(f"{Colors.YELLOW}💡 说明:{Colors.ENDC}")
        print(f"   此步骤将自动进行，AI 会分析你刚才的操作")
        print(f"   并提取出「如何查询操作日志」的通用知识")
        
        wait_for_user()
        
        success = run_command([
            python, "-m", "exogram.cli",
            "distill",
            "--recording", RECORDING_FILE,
            "-v"
        ], "蒸馏认知")
        
        if not success:
            print(f"\n{Colors.RED}⚠️  蒸馏失败，请检查录制文件是否存在{Colors.ENDC}")
            return
        
        wait_for_user("蒸馏完成，按 Enter 继续最后一步...")
    else:
        print(f"\n{Colors.YELLOW}⏭️  跳过步骤 3: distill{Colors.ENDC}")
    
    # ========== 步骤 4: 执行任务 ==========
    print_step(4, "run (执行任务)", 
               "基于学到的认知，自动执行查询任务")
    
    print(f"{Colors.YELLOW}💡 说明:{Colors.ENDC}")
    print(f"   现在 AI 将自动执行任务:")
    print(f"   {Colors.CYAN}\"{TASK}\"{Colors.ENDC}")
    print(f"   ")
    print(f"   观察 AI 如何自主完成操作!")
    
    wait_for_user()
    
    run_command([
        python, "-m", "exogram.cli",
        "run",
        "--topic", TOPIC,
        "--task", TASK
    ], "执行任务")
    
    # ========== 完成 ==========
    print(f"""
{Colors.GREEN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║                      🎉 演示完成！🎉                              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
{Colors.CYAN}演示摘要:{Colors.ENDC}
  • Topic: {TOPIC}
  • 任务: {TASK}
  • 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{Colors.YELLOW}生成的文件:{Colors.ENDC}
  • 录制文件: data/recordings/{TOPIC}.raw_steps.json
  • 认知文件: data/memory/{TOPIC}.jsonl
  • 执行日志: data/runs/

感谢使用 Exogram! 🚀
""")

if __name__ == "__main__":
    main()
