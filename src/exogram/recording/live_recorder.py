from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from exogram.models import RawStep, RawStepsDocument
from exogram.utils import normalize_text, safe_preview_value


# 默认 storage state 路径
DEFAULT_STORAGE_STATE_DIR = Path.home() / ".exogram" / "auth"


@dataclass(frozen=True)
class _Event:
    kind: str
    url: str | None
    target_text: str | None
    target_role: str | None
    target_label: str | None
    value: str | None
    meta: dict[str, Any]
    ts: float


# 可交互元素的 role 和 tag
_INTERACTIVE_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "menuitem", "option", "tab",
    "treeitem", "switch", "slider", "spinbutton", "combobox", "listbox",
    "textbox", "searchbox", "input", "select", "textarea", "menuitemcheckbox",
    "menuitemradio", "gridcell", "row", "columnheader", "rowheader",
})

_INTERACTIVE_TAGS = frozenset({
    "a", "button", "input", "select", "textarea", "summary", "details",
})

# 明确非交互的容器元素
_NON_INTERACTIVE_CONTAINERS = frozenset({
    "dialog", "tooltip", "tablist", "tree", "menu", "grid", "table",
    "tabpanel", "listbox", "group", "region", "main", "navigation",
    "complementary", "contentinfo", "banner", "form", "article", "section",
})


_INIT_SCRIPT = r"""
(() => {
  const EXO_ID = "__exogram_stop_btn__";
  const EXO_BADGE_ID = "__exogram_badge__";

  function safeText(s) {
    return (s || "").replace(/\s+/g, " ").trim();
  }

  function roleOf(el) {
    try {
      const r = el.getAttribute && el.getAttribute("role");
      if (r) return safeText(r);
    } catch (_) {}
    const tag = (el.tagName || "").toLowerCase();
    if (tag === "a") return "link";
    if (tag === "button") return "button";
    if (tag === "input") {
      const t = ((el.getAttribute && el.getAttribute("type")) || "text").toLowerCase();
      if (["submit", "button", "reset", "image"].includes(t)) return "button";
      if (["checkbox", "radio"].includes(t)) return t;
      return "input";
    }
    if (tag === "select") return "select";
    if (tag === "textarea") return "textarea";
    return tag || null;
  }

  function labelOf(el) {
    try {
      const id = el.id;
      if (id && window.CSS && CSS.escape) {
        const lbl = document.querySelector(`label[for="${CSS.escape(id)}"]`);
        if (lbl) return safeText(lbl.innerText);
      }
    } catch (_) {}

    try {
      const aria = el.getAttribute && el.getAttribute("aria-label");
      if (aria) return safeText(aria);
    } catch (_) {}
    try {
      const ph = el.getAttribute && el.getAttribute("placeholder");
      if (ph) return safeText(ph);
    } catch (_) {}
    try {
      const nm = el.getAttribute && el.getAttribute("name");
      if (nm) return safeText(nm);
    } catch (_) {}
    return null;
  }

  function textOf(el) {
    let t = null;
    try {
      t = safeText(el.innerText);
    } catch (_) {}
    if (!t) {
      try {
        const aria = el.getAttribute && el.getAttribute("aria-label");
        if (aria) t = safeText(aria);
      } catch (_) {}
    }
    if (!t) {
      try {
        const title = el.getAttribute && el.getAttribute("title");
        if (title) t = safeText(title);
      } catch (_) {}
    }
    return t || null;
  }

  // ========== 增强：稳定定位信息采集 ==========

  // 获取 data-testid 或常见测试属性
  function getTestId(el) {
    const attrs = ["data-testid", "data-test-id", "data-cy", "data-test", "data-qa"];
    for (const attr of attrs) {
      try {
        const v = el.getAttribute && el.getAttribute(attr);
        if (v) return { attr, value: safeText(v) };
      } catch (_) {}
    }
    return null;
  }

  // 获取所有 data-* 属性（用于调试和增强定位）
  function getDataAttrs(el) {
    const result = {};
    try {
      if (!el.attributes) return result;
      for (const attr of el.attributes) {
        if (attr.name.startsWith("data-") && attr.value) {
          // 过滤掉过长或无意义的值
          const v = safeText(attr.value);
          if (v && v.length < 100) {
            result[attr.name] = v;
          }
        }
      }
    } catch (_) {}
    return result;
  }

  // 生成稳定的 CSS selector（优先使用唯一标识）
  function buildSelector(el) {
    try {
      // 1. 优先 data-testid
      const testId = getTestId(el);
      if (testId) {
        return `[${testId.attr}="${CSS.escape(testId.value)}"]`;
      }

      // 2. 有意义的 id（排除动态生成的 id）
      const id = el.id;
      if (id && !/^(ember|react|vue|ng-|__)/i.test(id) && !/^\d+$/.test(id) && id.length < 50) {
        return `#${CSS.escape(id)}`;
      }

      // 3. 有 name 属性的表单元素
      const name = el.getAttribute && el.getAttribute("name");
      if (name) {
        const tag = (el.tagName || "").toLowerCase();
        return `${tag}[name="${CSS.escape(name)}"]`;
      }

      // 4. 有 aria-label 的元素
      const ariaLabel = el.getAttribute && el.getAttribute("aria-label");
      if (ariaLabel && ariaLabel.length < 50) {
        const tag = (el.tagName || "").toLowerCase();
        return `${tag}[aria-label="${CSS.escape(ariaLabel)}"]`;
      }

      // 5. 按钮/链接用文本定位
      const tag = (el.tagName || "").toLowerCase();
      if (["button", "a"].includes(tag)) {
        const txt = safeText(el.innerText);
        if (txt && txt.length < 30) {
          return `${tag}:has-text("${txt.replace(/"/g, '\\"')}")`;
        }
      }

      // 6. 生成基于结构的 selector（nth-child）
      return buildStructuralSelector(el);
    } catch (_) {
      return null;
    }
  }

  // 基于 DOM 结构生成 selector（作为兜底）
  function buildStructuralSelector(el, maxDepth = 4) {
    const parts = [];
    let current = el;
    let depth = 0;

    while (current && current !== document.body && depth < maxDepth) {
      const tag = (current.tagName || "").toLowerCase();
      if (!tag) break;

      let part = tag;

      // 添加有意义的 class（过滤动态 class）
      const classes = Array.from(current.classList || [])
        .filter(c => c && !/^(active|selected|hover|focus|open|show|hide|ng-|ember|react)/i.test(c))
        .filter(c => c.length < 30)
        .slice(0, 2);
      if (classes.length > 0) {
        part += "." + classes.map(c => CSS.escape(c)).join(".");
      }

      parts.unshift(part);
      current = current.parentElement;
      depth++;
    }

    return parts.join(" > ") || null;
  }

  // ========== 增强：识别 UI 组件库的组件类型 ==========
  
  // 识别 Ant Design / Element UI / Arco 等组件
  function detectComponentType(el) {
    try {
      const classList = Array.from(el.classList || []).join(" ");
      const parentClasses = el.parentElement ? Array.from(el.parentElement.classList || []).join(" ") : "";
      const allClasses = classList + " " + parentClasses;

      // Ant Design 组件
      if (/ant-tree/.test(allClasses)) return "antd:tree";
      if (/ant-select/.test(allClasses)) return "antd:select";
      if (/ant-dropdown/.test(allClasses)) return "antd:dropdown";
      if (/ant-modal/.test(allClasses)) return "antd:modal";
      if (/ant-drawer/.test(allClasses)) return "antd:drawer";
      if (/ant-table/.test(allClasses)) return "antd:table";
      if (/ant-tabs/.test(allClasses)) return "antd:tabs";
      if (/ant-menu/.test(allClasses)) return "antd:menu";
      if (/ant-picker/.test(allClasses)) return "antd:datepicker";
      if (/ant-input/.test(allClasses)) return "antd:input";
      if (/ant-btn/.test(allClasses)) return "antd:button";
      if (/ant-checkbox/.test(allClasses)) return "antd:checkbox";
      if (/ant-radio/.test(allClasses)) return "antd:radio";
      if (/ant-switch/.test(allClasses)) return "antd:switch";
      if (/ant-collapse/.test(allClasses)) return "antd:collapse";
      if (/ant-tooltip/.test(allClasses)) return "antd:tooltip";
      if (/ant-popover/.test(allClasses)) return "antd:popover";
      if (/ant-form/.test(allClasses)) return "antd:form";

      // Element UI / Element Plus 组件
      if (/el-tree/.test(allClasses)) return "element:tree";
      if (/el-select/.test(allClasses)) return "element:select";
      if (/el-dropdown/.test(allClasses)) return "element:dropdown";
      if (/el-dialog/.test(allClasses)) return "element:dialog";
      if (/el-table/.test(allClasses)) return "element:table";
      if (/el-tabs/.test(allClasses)) return "element:tabs";
      if (/el-menu/.test(allClasses)) return "element:menu";
      if (/el-date/.test(allClasses)) return "element:datepicker";
      if (/el-input/.test(allClasses)) return "element:input";
      if (/el-button/.test(allClasses)) return "element:button";

      // Arco Design 组件
      if (/arco-tree/.test(allClasses)) return "arco:tree";
      if (/arco-select/.test(allClasses)) return "arco:select";

      return null;
    } catch (_) {
      return null;
    }
  }

  // 获取树节点的路径（用于 tree 组件）
  function getTreeNodePath(el) {
    try {
      // 先尝试找到 treenode 容器
      let treeNode = el.closest(".ant-tree-treenode, .el-tree-node, [role='treeitem']");
      
      // 如果点击的是展开图标（ant-tree-switcher），向上找 treenode
      if (!treeNode) {
        const switcher = el.closest(".ant-tree-switcher, .el-tree-node__expand-icon");
        if (switcher) {
          treeNode = switcher.closest(".ant-tree-treenode, .el-tree-node");
        }
      }
      
      if (!treeNode) return null;

      // 尝试获取节点文本
      const titleEl = treeNode.querySelector(".ant-tree-title, .ant-tree-node-content-wrapper, .el-tree-node__label, [class*='title']");
      const title = titleEl ? safeText(titleEl.innerText) : null;

      // 尝试获取节点层级
      const indent = treeNode.querySelectorAll(".ant-tree-indent-unit, .el-tree-node__indent").length;
      
      // 尝试获取完整路径（向上遍历父节点）
      const path = [];
      let current = treeNode;
      let maxDepth = 5;
      while (current && maxDepth-- > 0) {
        const nodeTitle = current.querySelector(".ant-tree-title, .ant-tree-node-content-wrapper");
        if (nodeTitle) {
          const text = safeText(nodeTitle.innerText);
          if (text && text.length < 50) {
            path.unshift(text);
          }
        }
        // 找父级 treenode
        const parent = current.parentElement;
        if (!parent) break;
        current = parent.closest(".ant-tree-treenode, .el-tree-node");
      }

      return { 
        title, 
        level: indent,
        path: path.length > 0 ? path : null
      };
    } catch (_) {
      return null;
    }
  }

  // 获取表格单元格信息
  function getTableCellInfo(el) {
    try {
      const cell = el.closest("td, th, .ant-table-cell, .el-table__cell");
      if (!cell) return null;

      const row = cell.closest("tr, .ant-table-row, .el-table__row");
      const rowIndex = row ? Array.from(row.parentElement?.children || []).indexOf(row) : -1;
      const cellIndex = Array.from(cell.parentElement?.children || []).indexOf(cell);

      // 尝试获取列标题
      const table = cell.closest("table, .ant-table, .el-table");
      let columnHeader = null;
      if (table && cellIndex >= 0) {
        const headers = table.querySelectorAll("th, .ant-table-thead th");
        if (headers[cellIndex]) {
          columnHeader = safeText(headers[cellIndex].innerText);
        }
      }

      return { rowIndex, cellIndex, columnHeader };
    } catch (_) {
      return null;
    }
  }

  // 获取父级组件上下文
  function getParentContext(el, maxLevels = 3) {
    const context = [];
    let current = el.parentElement;
    let level = 0;

    while (current && current !== document.body && level < maxLevels) {
      const compType = detectComponentType(current);
      if (compType) {
        const label = labelOf(current) || safeText(current.innerText || "").slice(0, 30);
        context.push({ component: compType, label: label || null });
      }
      current = current.parentElement;
      level++;
    }

    return context.length > 0 ? context : null;
  }

  // 获取直接子文本（不包含子元素的文本）
  function getDirectText(el) {
    try {
      let text = "";
      for (const node of el.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) {
          text += node.textContent;
        }
      }
      return safeText(text) || null;
    } catch (_) {
      return null;
    }
  }

  // 识别 Popover/Select/Dropdown 中点击的选项
  function detectSelectedOption(el) {
    try {
      // Ant Design Select 选项
      const selectItem = el.closest(".ant-select-item, .ant-select-item-option");
      if (selectItem) {
        const label = selectItem.querySelector(".ant-select-item-option-content");
        return {
          type: "antd:select-option",
          value: safeText(label ? label.innerText : selectItem.innerText),
          selected: selectItem.classList.contains("ant-select-item-option-selected"),
        };
      }

      // Ant Design Dropdown 菜单项
      const dropdownItem = el.closest(".ant-dropdown-menu-item");
      if (dropdownItem) {
        return {
          type: "antd:dropdown-item",
          value: safeText(dropdownItem.innerText),
          disabled: dropdownItem.classList.contains("ant-dropdown-menu-item-disabled"),
        };
      }

      // Ant Design Popover 内的列表项（常见于团队选择等）
      const listItem = el.closest(".ant-list-item, [class*='list-item'], [class*='option']");
      if (listItem) {
        // 尝试获取更精确的文本
        const titleEl = listItem.querySelector("[class*='title'], [class*='name'], [class*='label']");
        const text = titleEl ? safeText(titleEl.innerText) : safeText(listItem.innerText);
        if (text && text.length < 100) {
          return {
            type: "list-item",
            value: text,
          };
        }
      }

      // Ant Design Checkbox/Radio 选项
      const checkboxWrapper = el.closest(".ant-checkbox-wrapper, .ant-radio-wrapper");
      if (checkboxWrapper) {
        const input = checkboxWrapper.querySelector("input");
        const labelText = checkboxWrapper.querySelector(".ant-checkbox + span, .ant-radio + span");
        return {
          type: input?.type === "radio" ? "antd:radio" : "antd:checkbox",
          value: safeText(labelText ? labelText.innerText : checkboxWrapper.innerText),
          checked: input?.checked || false,
        };
      }

      // Element UI Select 选项
      const elSelectItem = el.closest(".el-select-dropdown__item");
      if (elSelectItem) {
        return {
          type: "element:select-option",
          value: safeText(elSelectItem.innerText),
          selected: elSelectItem.classList.contains("selected"),
        };
      }

      // 通用：如果点击的是一个看起来像选项的元素（li, [role=option]）
      const option = el.closest("li[role='option'], [role='option'], [role='menuitem']");
      if (option) {
        return {
          type: "option",
          value: safeText(option.innerText).slice(0, 100),
        };
      }

      // 检查是否在 Popover/Dropdown 容器内
      const popover = el.closest(".ant-popover-inner, .ant-dropdown, .el-popover, .el-dropdown-menu");
      if (popover) {
        // 尝试获取点击的具体文本
        const clickedText = getDirectText(el) || safeText(el.innerText);
        if (clickedText && clickedText.length < 100 && clickedText.length > 0) {
          return {
            type: "popover-click",
            value: clickedText,
          };
        }
      }

      return null;
    } catch (_) {
      return null;
    }
  }

  // ========== 增强：判断元素是否可交互 ==========
  
  const INTERACTIVE_ROLES = new Set([
    "button", "link", "checkbox", "radio", "menuitem", "option", "tab",
    "treeitem", "switch", "slider", "spinbutton", "combobox", "listbox",
    "textbox", "searchbox", "menuitemcheckbox", "menuitemradio", "gridcell",
    "row", "columnheader", "rowheader"
  ]);

  const INTERACTIVE_TAGS = new Set([
    "a", "button", "input", "select", "textarea", "summary", "details"
  ]);
  
  // 容器类 role - 这些通常不应该直接点击，而是点击其中的子元素
  const CONTAINER_ROLES = new Set([
    "tablist", "tabpanel", "menu", "menubar", "tree", "grid", "table",
    "dialog", "alertdialog", "toolbar", "group", "region", "list",
    "navigation", "main", "complementary", "contentinfo", "banner",
    "form", "article", "section", "presentation", "none"
  ]);

  // 判断元素是否是可交互的
  function isInteractiveElement(el) {
    try {
      const tag = (el.tagName || "").toLowerCase();
      
      // 1. 检查 tag
      if (INTERACTIVE_TAGS.has(tag)) return true;
      
      // 2. 检查 role
      const role = el.getAttribute && el.getAttribute("role");
      if (role && INTERACTIVE_ROLES.has(role.toLowerCase())) return true;
      
      // 3. 检查 tabindex
      const tabindex = el.getAttribute && el.getAttribute("tabindex");
      if (tabindex && parseInt(tabindex, 10) >= 0) return true;
      
      // 4. 检查 onclick 等事件属性
      if (el.onclick || el.getAttribute && el.getAttribute("onclick")) return true;
      
      // 5. 检查是否是 UI 组件的可交互部分
      // Tree 节点的展开/收起图标
      if (el.closest(".ant-tree-switcher, .el-tree-node__expand-icon")) return true;
      // 树节点标题
      if (el.closest(".ant-tree-title, .el-tree-node__label")) return true;
      // 表格行的展开按钮
      if (el.closest(".ant-table-row-expand-icon-cell")) return true;
      // Tab 标签
      if (el.closest(".ant-tabs-tab, .el-tabs__item")) return true;
      // 菜单项
      if (el.closest(".ant-menu-item, .ant-dropdown-menu-item, .el-menu-item")) return true;
      // Select 选项
      if (el.closest(".ant-select-item, .el-select-dropdown__item")) return true;
      // 有 cursor: pointer 样式的元素
      try {
        const cursor = getComputedStyle(el).cursor;
        if (cursor === "pointer") return true;
      } catch (_) {}
      
      return false;
    } catch (_) {
      return false;
    }
  }

  // 判断点击是否应该被过滤（无意义点击）
  function shouldFilterClick(el) {
    try {
      // 检查 role - 容器类 role 的点击通常无意义
      const role = el.getAttribute && el.getAttribute("role");
      if (role && CONTAINER_ROLES.has(role.toLowerCase())) {
        // 容器 role 的点击应该被过滤，用户应该点击具体的子元素
        return true;
      }
      
      // 如果元素本身或其近似祖先是可交互的，不过滤
      if (isInteractiveElement(el)) return false;
      
      // 检查点击的文本长度 - 如果太长可能是点击了整个容器
      const text = safeText(el.innerText || "");
      if (text.length > 200) {
        // 但如果是在特定组件内，可能是有效点击
        const compType = detectComponentType(el);
        if (!compType) return true;  // 不在已知组件内的长文本点击，过滤
      }
      
      // 检查 tag - 某些容器 tag 的点击通常无意义
      const tag = (el.tagName || "").toLowerCase();
      if (["div", "span", "section", "article", "main", "aside", "nav", "header", "footer"].includes(tag)) {
        // 但如果有特定的 class 或 role，可能是有效点击
        if (role && INTERACTIVE_ROLES.has(role.toLowerCase())) return false;
        
        // 检查是否在已识别的 UI 组件内
        const compType = detectComponentType(el);
        if (compType) return false;
        
        // 检查是否有点击相关的 class
        const classList = Array.from(el.classList || []).join(" ").toLowerCase();
        if (/click|btn|button|link|item|option|select/.test(classList)) return false;
        
        return true;  // 普通容器 div/span 点击，过滤
      }
      
      return false;
    } catch (_) {
      return false;
    }
  }

  // ========== 增强：获取页面可交互元素快照 ==========
  
  function getPageSnapshot() {
    try {
      const elements = [];
      const seen = new Set();
      
      // 获取所有可交互元素
      const interactiveSelectors = [
        "a", "button", "input", "select", "textarea",
        "[role='button']", "[role='link']", "[role='checkbox']", "[role='radio']",
        "[role='menuitem']", "[role='option']", "[role='tab']", "[role='treeitem']",
        "[tabindex]",
        ".ant-btn", ".ant-menu-item", ".ant-tabs-tab", ".ant-tree-title",
        ".ant-select-selector", ".ant-dropdown-trigger",
        ".el-button", ".el-menu-item", ".el-tabs__item", ".el-tree-node__label"
      ];
      
      const allElements = document.querySelectorAll(interactiveSelectors.join(","));
      
      for (const el of allElements) {
        // 跳过不可见元素
        if (el.offsetParent === null && el.tagName !== "INPUT") continue;
        
        const text = safeText(el.innerText || el.value || "");
        const label = labelOf(el);
        const role = roleOf(el);
        const selector = buildSelector(el);
        
        // 去重
        const key = selector + "|" + text.slice(0, 30);
        if (seen.has(key)) continue;
        seen.add(key);
        
        elements.push({
          tag: (el.tagName || "").toLowerCase(),
          role: role,
          text: text.slice(0, 80) || null,
          label: label,
          selector: selector,
        });
        
        // 限制数量，避免数据过大
        if (elements.length >= 100) break;
      }
      
      return {
        url: location.href,
        title: document.title,
        interactiveElements: elements,
        timestamp: Date.now(),
      };
    } catch (_) {
      return null;
    }
  }

  // 暴露给 Python 侧调用
  window.__exogram_get_page_snapshot__ = getPageSnapshot;

  function send(ev) {
    try {
      if (window.exogram_record_event) window.exogram_record_event(ev);
    } catch (_) {}
  }

  function ensureStopUI() {
    if (document.getElementById(EXO_ID)) return true;
    const root = document.body || document.documentElement;
    if (!root) return false;

    const wrap = document.createElement("div");
    wrap.id = EXO_BADGE_ID;
    Object.assign(wrap.style, {
      position: "fixed",
      top: "12px",
      right: "12px",
      zIndex: "2147483647",
      display: "flex",
      gap: "8px",
      alignItems: "center",
      fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
      pointerEvents: "auto",
    });

    const dot = document.createElement("div");
    Object.assign(dot.style, {
      width: "10px",
      height: "10px",
      borderRadius: "999px",
      background: "#ef4444",
      boxShadow: "0 0 0 4px rgba(239, 68, 68, 0.18)",
    });

    const btn = document.createElement("button");
    btn.id = EXO_ID;
    btn.type = "button";
    btn.textContent = "结束录制";
    Object.assign(btn.style, {
      padding: "10px 14px",
      background: "#ef4444",
      color: "#fff",
      border: "none",
      borderRadius: "999px",
      fontSize: "14px",
      fontWeight: "600",
      boxShadow: "0 10px 24px rgba(0,0,0,.25)",
      cursor: "pointer",
    });

    btn.addEventListener(
      "click",
      (e) => {
        try {
          e.preventDefault();
          e.stopPropagation();
          e.stopImmediatePropagation();
        } catch (_) {}
        try {
          if (window.exogram_stop_recording) window.exogram_stop_recording();
        } catch (_) {}
      },
      { capture: true }
    );

    wrap.appendChild(dot);
    wrap.appendChild(btn);
    root.appendChild(wrap);
    return true;
  }

  // 有些页面/时刻 init script 执行时 DOM 还没就绪（documentElement/body 为空），需要重试挂载
  function mountLoop(attempt) {
    const ok = ensureStopUI();
    if (ok) return;
    if ((attempt || 0) > 120) return; // ~6s
    setTimeout(() => mountLoop((attempt || 0) + 1), 50);
  }
  mountLoop(0);

  // 页面 SPA 更新/替换时，尽量保持按钮存在
  const obs = new MutationObserver(() => ensureStopUI());
  function observeLoop(attempt) {
    const root = document.documentElement || document.body;
    if (!root) {
      if ((attempt || 0) > 120) return;
      setTimeout(() => observeLoop((attempt || 0) + 1), 50);
      return;
    }
    try {
      obs.observe(root, { childList: true, subtree: true });
    } catch (_) {}
  }
  observeLoop(0);

  // 给 Python 侧一个可调用的兜底挂载入口（页面加载后可再次执行）
  try {
    window.__exogram_mount_stop_ui__ = () => {
      try { return ensureStopUI(); } catch (_) { return false; }
    };
  } catch (_) {}

  document.addEventListener(
    "click",
    (e) => {
      const target = e.target;
      if (!(target instanceof Element)) return;
      if (target.closest && (target.closest("#" + EXO_ID) || target.closest("#" + EXO_BADGE_ID))) return;

      const el = target.closest("a,button,input,textarea,select,[role]") || target;
      
      // 增强：过滤无意义点击
      if (shouldFilterClick(el)) {
        return;  // 跳过无意义的点击
      }
      
      // 增强：采集更多定位信息
      const testId = getTestId(el);
      const selector = buildSelector(el);
      const componentType = detectComponentType(el);
      const dataAttrs = getDataAttrs(el);
      const parentContext = getParentContext(el);
      const directText = getDirectText(el);
      
      // 特殊组件信息
      let treeNode = null;
      let tableCell = null;
      let selectedOption = null;
      
      if (componentType && componentType.includes("tree")) {
        treeNode = getTreeNodePath(el);
      }
      if (componentType && componentType.includes("table")) {
        tableCell = getTableCellInfo(el);
      }
      
      // 识别 Popover/Select/Dropdown 中的选中项
      selectedOption = detectSelectedOption(el);
      
      // 标记是否是可交互元素
      const isInteractive = isInteractiveElement(el);

      send({
        kind: "click",
        url: location.href,
        targetText: textOf(el),
        targetRole: roleOf(el),
        targetLabel: labelOf(el),
        tagName: (el.tagName || "").toLowerCase(),
        isInteractive: isInteractive,
        // 增强字段
        selector: selector,
        testId: testId,
        componentType: componentType,
        dataAttrs: Object.keys(dataAttrs).length > 0 ? dataAttrs : null,
        parentContext: parentContext,
        directText: directText,
        treeNode: treeNode,
        tableCell: tableCell,
        selectedOption: selectedOption,
      });
    },
    true
  );

  function onInputLike(e) {
    const target = e.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) return;
    if (target.closest && (target.closest("#" + EXO_ID) || target.closest("#" + EXO_BADGE_ID))) return;

    let val = null;
    let inputType = null;
    if (target instanceof HTMLSelectElement) {
      val = safeText(target.value);
    } else if (target instanceof HTMLInputElement) {
      inputType = (target.type || "text").toLowerCase();
      if (inputType === "password") val = "__PASSWORD__";
      else val = target.value || "";
    } else if (target instanceof HTMLTextAreaElement) {
      val = target.value || "";
    }

    // 增强：采集更多定位信息
    const testId = getTestId(target);
    const selector = buildSelector(target);
    const componentType = detectComponentType(target);
    const dataAttrs = getDataAttrs(target);
    const parentContext = getParentContext(target);

    send({
      kind: "input",
      url: location.href,
      targetText: null,
      targetRole: roleOf(target),
      targetLabel: labelOf(target),
      inputType: inputType,
      value: val,
      tagName: (target.tagName || "").toLowerCase(),
      // 增强字段
      selector: selector,
      testId: testId,
      componentType: componentType,
      dataAttrs: Object.keys(dataAttrs).length > 0 ? dataAttrs : null,
      parentContext: parentContext,
    });
  }

  document.addEventListener("input", onInputLike, true);
  document.addEventListener("change", onInputLike, true);

  // 兜底：Cmd/Ctrl + Esc 结束录制
  document.addEventListener(
    "keydown",
    (e) => {
      if (e.key === "Escape" && (e.metaKey || e.ctrlKey)) {
        try {
          if (window.exogram_stop_recording) window.exogram_stop_recording();
        } catch (_) {}
      }
    },
    true
  );
})();
"""

_FORCE_MOUNT_UI = r"""
(() => {
  try {
    if (window.__exogram_mount_stop_ui__) return window.__exogram_mount_stop_ui__();
  } catch (_) {}
  return false;
})()
"""


def _mask_value(value: str | None, *, input_type: str | None) -> str | None:
    if value is None:
        return None
    if value == "__PASSWORD__":
        return "***"
    if input_type and input_type.lower() in {"password"}:
        return "***"
    return value


class LiveRecorder:
    """
    交互式录制（Playwright）：
    - 打开浏览器让用户操作
    - 注入悬浮"结束录制"按钮
    - 采集 click/input/navigation 事件并输出 RawStepsDocument
    - 支持 storageState 复用 SSO 登录态
    - 在关键步骤捕获页面状态（可交互元素快照）
    """

    def __init__(self) -> None:
        self._events: list[_Event] = []
        self._last_nav_url: str | None = None
        self._page_snapshots: dict[str, dict] = {}  # url -> snapshot
        self._pending_snapshot_url: str | None = None  # 待捕获快照的 URL

    @staticmethod
    def _extract_domain(url: str) -> str:
        """从 URL 提取域名（用于命名 storage state 文件）"""
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            return parsed.netloc.replace(":", "_") or "default"
        except Exception:
            return "default"

    @staticmethod
    def _resolve_storage_state_path(
        storage_state_path: Path | str | None,
        start_url: str,
        auth_domain: str | None,
    ) -> Path:
        """解析 storage state 路径"""
        if storage_state_path:
            return Path(storage_state_path)
        # 自动生成路径
        domain = auth_domain or LiveRecorder._extract_domain(start_url)
        DEFAULT_STORAGE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_STORAGE_STATE_DIR / f"{domain}.json"

    def record(
        self,
        *,
        topic: str,
        start_url: str,
        out_path: Path,
        storage_state_path: Path | str | None = None,
        save_storage_state: bool = True,
        auth_domain: str | None = None,
    ) -> Path:
        """
        录制用户操作。

        Args:
            topic: 录制主题名称
            start_url: 起始 URL
            out_path: 输出文件路径
            storage_state_path: 登录态文件路径（可选）。
                - 如果文件存在，会自动加载复用登录态
                - 如果不存在或为 None，会使用默认路径 ~/.exogram/auth/{domain}.json
            save_storage_state: 录制结束后是否保存登录态（默认 True）
            auth_domain: 用于命名 storage state 的域名（可选，默认从 start_url 提取）

        Returns:
            输出文件路径
        """
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "缺少依赖 playwright。请先安装：pip install -e '.[recorder]' 或 pip install playwright，并运行：playwright install chromium"
            ) from e

        # 解析 storage state 路径
        resolved_storage_path = self._resolve_storage_state_path(
            storage_state_path=storage_state_path,
            start_url=start_url,
            auth_domain=auth_domain,
        )

        stop = {"value": False}

        def on_event(obj: Any) -> None:
            if not isinstance(obj, dict):
                return
            kind = str(obj.get("kind") or "").strip()
            url = obj.get("url")
            url = normalize_text(url) if isinstance(url, str) and url.strip() else None

            target_text = obj.get("targetText")
            target_text = normalize_text(target_text) if isinstance(target_text, str) and target_text.strip() else None

            target_role = obj.get("targetRole")
            target_role = normalize_text(target_role) if isinstance(target_role, str) and target_role.strip() else None

            target_label = obj.get("targetLabel")
            target_label = normalize_text(target_label) if isinstance(target_label, str) and target_label.strip() else None

            value = obj.get("value")
            value = str(value) if isinstance(value, (str, int, float)) else None

            meta: dict[str, Any] = {}
            # 基础字段
            for k in ("tagName", "inputType"):
                if k in obj and isinstance(obj.get(k), str) and str(obj.get(k)).strip():
                    meta[k] = normalize_text(str(obj.get(k)))

            # 增强字段：稳定定位信息
            for k in ("selector", "testId", "componentType", "dataAttrs", "parentContext", "directText", "treeNode", "tableCell", "selectedOption"):
                v = obj.get(k)
                if v is not None:
                    meta[k] = v

            self._events.append(
                _Event(
                    kind=kind,
                    url=url,
                    target_text=target_text,
                    target_role=target_role,
                    target_label=target_label,
                    value=value,
                    meta=meta,
                    ts=time.time(),
                )
            )

        def request_stop() -> None:
            stop["value"] = True

        def on_nav(url: str) -> None:
            u = normalize_text(url) if url else ""
            if not u or u == "about:blank":
                return
            if u == self._last_nav_url:
                return
            self._last_nav_url = u
            self._pending_snapshot_url = u  # 标记需要捕获快照
            self._events.append(
                _Event(
                    kind="navigate",
                    url=u,
                    target_text=None,
                    target_role=None,
                    target_label=None,
                    value=None,
                    meta={},
                    ts=time.time(),
                )
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)

            # 加载或创建 context（支持 storageState）
            storage_loaded = False
            if resolved_storage_path.exists():
                try:
                    context = browser.new_context(storage_state=str(resolved_storage_path))
                    storage_loaded = True
                    print(f"[exogram] 已加载登录态: {resolved_storage_path}")
                except Exception as e:
                    print(f"[exogram] 加载登录态失败，使用空白上下文: {e}")
                    context = browser.new_context()
            else:
                context = browser.new_context()
                print(f"[exogram] 登录态文件不存在，首次录制后会保存到: {resolved_storage_path}")

            context.add_init_script(_INIT_SCRIPT)
            page = context.new_page()

            # JS -> Python
            page.expose_binding("exogram_record_event", lambda _src, obj: on_event(obj))
            page.expose_binding("exogram_stop_recording", lambda _src: request_stop())

            page.on("close", lambda: request_stop())
            page.on("framenavigated", lambda frame: on_nav(frame.url) if frame == page.main_frame else None)

            # 初始打开
            if start_url and start_url != "about:blank":
                try:
                    page.goto(start_url, wait_until="domcontentloaded")
                except Exception:
                    # 有些站点会阻止自动 goto；不致命，用户仍可手动输入
                    pass

            # 兜底：强制再挂一次按钮（某些页面 early script 时机不稳定）
            try:
                page.wait_for_timeout(200)
                page.evaluate(_FORCE_MOUNT_UI)
            except Exception:
                pass

            # 兜底：记录一次当前地址（如果不是 about:blank）
            try:
                on_nav(page.url)
            except Exception:
                pass

            # 用于追踪待捕获快照的时间
            snapshot_wait_start: float | None = None
            
            while not stop["value"]:
                # 给浏览器事件循环让步
                page.wait_for_timeout(120)

                # 兜底：某些 SPA 会清掉 document，这里周期性确保按钮仍在
                try:
                    page.evaluate(_FORCE_MOUNT_UI)
                except Exception:
                    pass
                
                # 捕获页面快照：在 navigate 后等待页面稳定，然后捕获
                if self._pending_snapshot_url:
                    if snapshot_wait_start is None:
                        snapshot_wait_start = time.time()
                    elif time.time() - snapshot_wait_start >= 1.0:  # 等待 1 秒让页面稳定
                        try:
                            snapshot = page.evaluate("window.__exogram_get_page_snapshot__()")
                            if snapshot:
                                self._page_snapshots[self._pending_snapshot_url] = snapshot
                        except Exception:
                            pass  # 页面可能正在加载，忽略错误
                        self._pending_snapshot_url = None
                        snapshot_wait_start = None

            # 保存登录态
            if save_storage_state:
                try:
                    resolved_storage_path.parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(resolved_storage_path))
                    print(f"[exogram] 已保存登录态: {resolved_storage_path}")
                except Exception as e:
                    print(f"[exogram] 保存登录态失败: {e}")

            try:
                context.close()
            finally:
                browser.close()

        doc = RawStepsDocument(topic=topic, source="live-recorder:playwright", steps=self._build_steps())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(doc.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return out_path

    @staticmethod
    def setup_auth(
        *,
        start_url: str,
        storage_state_path: Path | str | None = None,
        auth_domain: str | None = None,
    ) -> Path:
        """
        专门用于登录并保存登录态的工具方法。
        打开浏览器，等待用户手动完成登录（如扫码），然后保存 storageState。

        Args:
            start_url: 登录页 URL
            storage_state_path: 登录态保存路径（可选）
            auth_domain: 用于命名的域名（可选）

        Returns:
            保存的 storage state 文件路径
        """
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "缺少依赖 playwright。请先安装：pip install -e '.[recorder]' 或 pip install playwright，并运行：playwright install chromium"
            ) from e

        resolved_path = LiveRecorder._resolve_storage_state_path(
            storage_state_path=storage_state_path,
            start_url=start_url,
            auth_domain=auth_domain,
        )

        print(f"[exogram] 正在打开浏览器...")
        print(f"[exogram] 请手动完成登录（如扫码），登录成功后关闭浏览器窗口")
        print(f"[exogram] 登录态将保存到: {resolved_path}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            try:
                page.goto(start_url, wait_until="domcontentloaded")
            except Exception:
                pass

            # 等待用户关闭窗口
            try:
                page.wait_for_event("close", timeout=0)  # 无限等待
            except Exception:
                pass

            # 保存登录态
            try:
                resolved_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(resolved_path))
                print(f"[exogram] 登录态已保存: {resolved_path}")
            except Exception as e:
                print(f"[exogram] 保存登录态失败: {e}")
                raise

            try:
                context.close()
            finally:
                browser.close()

        return resolved_path

    def _build_steps(self) -> list[RawStep]:
        steps: list[RawStep] = []
        # 轻量聚合：连续的 input 事件（同 url+selector）合并成一次 type
        # 改进：用 selector 作为更精确的标识，增大时间窗口
        last_type_sig: tuple[str | None, str | None] | None = None
        last_type_ts: float | None = None

        for ev in self._events:
            kind = (ev.kind or "").lower()
            if kind == "navigate":
                # 添加页面快照到 meta（如果有）
                nav_meta: dict[str, Any] = {"ts": ev.ts}
                if ev.url and ev.url in self._page_snapshots:
                    snapshot = self._page_snapshots[ev.url]
                    nav_meta["page_snapshot"] = snapshot
                
                steps.append(
                    RawStep(
                        idx=len(steps),
                        action="navigate",
                        url=ev.url,
                        meta=nav_meta,
                    )
                )
                last_type_sig = None
                last_type_ts = None
                continue

            if kind == "click":
                steps.append(
                    RawStep(
                        idx=len(steps),
                        action="click",
                        url=ev.url,
                        target_text=ev.target_text,
                        target_role=ev.target_role,
                        target_label=ev.target_label,
                        value=None,
                        meta={**ev.meta, "ts": ev.ts},
                    )
                )
                last_type_sig = None
                last_type_ts = None
                continue

            if kind == "input":
                input_type = str(ev.meta.get("inputType") or "") or None
                masked = _mask_value(ev.value, input_type=input_type)
                masked = safe_preview_value(masked, limit=80)

                # 改进：使用 selector 作为更精确的标识（selector 比 label 更能唯一标识一个输入框）
                selector = ev.meta.get("selector")
                sig = (ev.url, selector or ev.target_label or ev.target_role)
                
                # 改进：增大时间窗口到 5 秒（用户连续打字的合理间隔）
                # 同一个输入框的连续输入应该合并为一条记录
                should_merge = (
                    steps
                    and steps[-1].action == "type"
                    and last_type_sig == sig
                    and last_type_ts is not None
                    and (ev.ts - last_type_ts) <= 5.0  # 从 0.8 秒增加到 5 秒
                )

                if should_merge:
                    # 仅更新 value 和结束时间戳（保留最早的 label/role 和开始时间）
                    steps[-1].value = masked
                    # 保留原始 ts（开始时间），添加 ts_end（结束时间）
                    orig_meta = steps[-1].meta or {}
                    steps[-1].meta = {**orig_meta, **ev.meta, "ts_end": ev.ts}
                    last_type_ts = ev.ts
                    continue

                steps.append(
                    RawStep(
                        idx=len(steps),
                        action="type",
                        url=ev.url,
                        target_text=None,
                        target_role=ev.target_role,
                        target_label=ev.target_label,
                        value=masked,
                        meta={**ev.meta, "ts": ev.ts},
                    )
                )
                last_type_sig = sig
                last_type_ts = ev.ts
                continue

            # 其他未知事件：忽略（MVP）

        # 重新编号兜底（防止未来中途删除导致 idx 不连续）
        for i, s in enumerate(steps):
            s.idx = i
        return steps
