"""
认证状态管理模块

负责加载和管理 Playwright 的 storageState（cookies, localStorage 等）。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse


# 默认的认证状态存储目录
DEFAULT_AUTH_DIR = Path.home() / ".exogram" / "auth"

# CDP 不支持的 cookie 字段（需要清理）
CDP_INCOMPATIBLE_COOKIE_FIELDS = {"partitionKey", "_crHasCrossSiteAncestor"}


def get_auth_file_path(url: str, auth_dir: Path | None = None) -> Path | None:
    """
    根据 URL 获取对应的认证状态文件路径。
    
    认证文件命名规则：{domain}.json
    例如：https://metis2.hellobike.cn/campaign -> metis2.hellobike.cn.json
    
    查找优先级：
    1. 完整域名匹配 (metis2.hellobike.cn.json)
    2. 基础域名匹配 (hellobike.cn.json)
    3. 同组织的其他域名 (sso2.hellobike.cn.json)
    
    Args:
        url: 目标网站 URL
        auth_dir: 认证文件存储目录，默认为 ~/.exogram/auth/
        
    Returns:
        认证文件路径，如果不存在则返回 None
    """
    if not url:
        return None
    
    auth_dir = auth_dir or DEFAULT_AUTH_DIR
    if not auth_dir.exists():
        return None
    
    # 提取域名
    parsed = urlparse(url)
    domain = parsed.netloc
    if not domain:
        return None
    
    # 尝试多种可能的文件名（按优先级排序）
    candidates = []
    
    # 1. 完整域名（最高优先级）
    exact_match = auth_dir / f"{domain}.json"
    if exact_match.exists():
        candidates.append(exact_match)
    
    # 2. 基础域名
    parts = domain.split(".")
    if len(parts) > 2:
        base_domain = ".".join(parts[-2:])
        base_match = auth_dir / f"{base_domain}.json"
        if base_match.exists():
            candidates.append(base_match)
    
    # 3. 同组织的其他域名 (如 sso2.hellobike.cn)
    if auth_dir.exists() and len(parts) > 2:
        base = ".".join(parts[-2:])
        for f in auth_dir.glob("*.json"):
            fname = f.stem
            if base in fname and f not in candidates:
                candidates.append(f)
    
    # 返回第一个存在的文件
    return candidates[0] if candidates else None


def load_storage_state(url: str, auth_dir: Path | None = None) -> dict | None:
    """
    加载指定 URL 对应的 Playwright storageState。
    
    Args:
        url: 目标网站 URL
        auth_dir: 认证文件存储目录
        
    Returns:
        storageState 字典，如果没有找到则返回 None
    """
    auth_file = get_auth_file_path(url, auth_dir)
    if not auth_file:
        return None
    
    try:
        content = auth_file.read_text(encoding="utf-8")
        state = json.loads(content)
        return state
    except (json.JSONDecodeError, IOError) as e:
        print(f"[Auth] 加载认证状态失败: {e}")
        return None


def list_available_auth_domains(auth_dir: Path | None = None) -> list[str]:
    """
    列出所有可用的认证域名。
    
    Returns:
        域名列表
    """
    auth_dir = auth_dir or DEFAULT_AUTH_DIR
    if not auth_dir.exists():
        return []
    
    domains = []
    for f in auth_dir.glob("*.json"):
        domains.append(f.stem)
    return domains


def _clean_cookie_for_cdp(cookie: dict) -> dict:
    """清理 cookie 中 CDP 不支持的字段"""
    return {k: v for k, v in cookie.items() if k not in CDP_INCOMPATIBLE_COOKIE_FIELDS}


def get_cdp_compatible_auth_file(url: str, auth_dir: Path | None = None) -> str | None:
    """
    获取 CDP 兼容的认证状态文件路径。
    
    由于 Playwright 保存的 storageState 可能包含 CDP 不支持的字段（如 partitionKey），
    此函数会：
    1. 查找原始认证文件
    2. 清理不兼容的字段
    3. 保存到临时文件
    4. 返回临时文件路径
    
    Args:
        url: 目标网站 URL
        auth_dir: 认证文件存储目录
        
    Returns:
        CDP 兼容的临时文件路径，如果没有找到原始文件则返回 None
    """
    auth_file = get_auth_file_path(url, auth_dir)
    if not auth_file:
        return None
    
    try:
        content = auth_file.read_text(encoding="utf-8")
        state = json.loads(content)
        
        # 清理 cookies 中的不兼容字段
        if "cookies" in state:
            state["cookies"] = [_clean_cookie_for_cdp(c) for c in state["cookies"]]
        
        # 保存到临时文件
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="exogram-auth-",
            delete=False,  # 保留文件，browser-use 需要读取
        )
        json.dump(state, temp_file, indent=2)
        temp_file.close()
        
        return temp_file.name
        
    except (json.JSONDecodeError, IOError) as e:
        print(f"[Auth] 处理认证状态失败: {e}")
        return None
