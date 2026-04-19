# MonoRelay 视觉设计文档

## 设计语言

MonoRelay 采用**现代简约**的设计语言，强调功能性、清晰度和用户体验。

### 核心原则

1. **功能性优先**：设计服务于功能，不追求过度装饰
2. **清晰度**：信息层次分明，用户能快速找到所需内容
3. **一致性**：整个应用保持统一的视觉风格和交互模式
4. **响应式**：适配各种屏幕尺寸，提供一致的用户体验
5. **可访问性**：支持浅色/深色主题，满足不同用户需求

---

## 色彩系统

### 主色调

| 颜色 | 用途 | Hex (深色) | Hex (浅色) |
|------|------|------------|------------|
| **主色** | 强调元素、按钮、链接 | `#6366f1` (Indigo) | `#6366f1` (Indigo) |
| **成功色** | 成功状态、正面反馈 | `#10b981` (Emerald) | `#10b981` (Emerald) |
| **错误色** | 错误状态、负面反馈 | `#ef4444` (Red) | `#ef4444` (Red) |
| **信息色** | 信息提示、中性状态 | `#3b82f6` (Blue) | `#3b82f6` (Blue) |

### 背景色

| 颜色 | 用途 | Hex (深色) | Hex (浅色) |
|------|------|------------|------------|
| **主背景** | 页面背景 | `#0a0a0f` | `#ffffff` |
| **卡片背景** | 卡片、面板 | `#12121a` | `#f8f9fa` |
| **输入框背景** | 表单输入 | `#1a1a24` | `#ffffff` |
| **悬停背景** | 悬停状态 | `rgba(255,255,255,0.03)` | `rgba(0,0,0,0.03)` |

### 文本色

| 颜色 | 用途 | Hex (深色) | Hex (浅色) |
|------|------|------------|------------|
| **主文本** | 主要文字 | `#e5e7eb` | `#1f2937` |
| **次要文本** | 次要文字、说明 | `#9ca3af` | `#6b7280` |
| **禁用文本** | 禁用状态 | `#4b5563` | `#9ca3af` |

### 边框色

| 颜色 | 用途 | Hex (深色) | Hex (浅色) |
|------|------|------------|------------|
| **主边框** | 默认边框 | `#272735` | `#e5e7eb` |
| **强调边框** | 悬停、激活状态 | `#6366f1` | `#6366f1` |

---

## 字体系统

### 字体族

```css
--font-sans: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
--font-mono: 'Space Mono', 'JetBrains Mono', monospace;
```

### 字体使用

| 用途 | 字体族 | 字重 | 大小 |
|------|--------|------|------|
| **标题** | `--font-sans` | 700 | 16-28px |
| **正文** | `--font-sans` | 400-500 | 13-14px |
| **按钮** | `--font-sans` | 600 | 12px |
| **代码** | `--font-mono` | 400 | 12px |
| **数据** | `--font-mono` | 400 | 12px |

### 字体层级

```css
/* H1 - 页面标题 */
font-size: 28px;
font-weight: 700;

/* H2 - 区块标题 */
font-size: 16px;
font-weight: 600;

/* H3 - 子标题 */
font-size: 14px;
font-weight: 600;

/* Body - 正文 */
font-size: 13px;
font-weight: 400;

/* Small - 小字 */
font-size: 11px;
font-weight: 400;
```

---

## 间距系统

### 基础间距单位

```css
--spacing-xs: 4px;
--spacing-sm: 8px;
--spacing-md: 12px;
--spacing-lg: 16px;
--spacing-xl: 20px;
--spacing-2xl: 24px;
--spacing-3xl: 32px;
```

### 间距使用

| 用途 | 间距 |
|------|------|
| **卡片内边距** | `--spacing-xl` (20px) |
| **表单间距** | `--spacing-md` (12px) |
| **按钮间距** | `--spacing-sm` (8px) |
| **区块间距** | `--spacing-lg` (16px) |
| **页面边距** | `--spacing-2xl` (24px) |

---

## 圆角系统

```css
--radius-sm: 4px;
--radius-md: 6px;
--radius-lg: 8px;
--radius-xl: 10px;
--radius-2xl: 12px;
```

### 圆角使用

| 用途 | 圆角 |
|------|------|
| **按钮** | `--radius-md` (6px) |
| **输入框** | `--radius-md` (6px) |
| **卡片** | `--radius-xl` (10px) |
| **标签** | `--radius-sm` (4px) |
| **模态框** | `--radius-lg` (8px) |

---

## 阴影系统

### 深色主题

```css
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
--shadow-md: 0 4px 6px rgba(0, 0, 0, 0.4);
--shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.5);
--shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.6);
```

### 浅色主题

```css
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
--shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
--shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.15);
--shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.2);
```

---

## 组件设计

### 按钮

#### 主要按钮
- 背景：主色
- 文字：白色
- 圆角：6px
- 悬停：加深 10%
- 激活：加深 20%

#### 次要按钮
- 背景：透明
- 边框：主边框色
- 文字：主文本色
- 悬停：边框变为主色

#### 幽灵按钮
- 背景：透明
- 边框：主边框色
- 文字：次要文本色
- 悬停：边框变为主色，文字变为主文本色

### 卡片

- 背景：卡片背景色
- 边框：主边框色
- 圆角：10px
- 内边距：20px
- 悬停：边框变为主色，轻微上移

### 表单

#### 输入框
- 背景：输入框背景色
- 边框：主边框色
- 圆角：6px
- 内边距：12px 16px
- 聚焦：边框变为主色

#### 下拉菜单
- 背景：卡片背景色
- 边框：主边框色
- 圆角：6px
- 选项：悬停背景色

### 表格

- 边框：主边框色
- 表头：次要文本色，大写
- 行：悬停背景色
- 单元格：内边距 10px 12px

---

## 布局系统

### 响应式断点

```css
--breakpoint-sm: 640px;
--breakpoint-md: 768px;
--breakpoint-lg: 1024px;
--breakpoint-xl: 1280px;
```

### 网格系统

```css
/* 移动端 */
grid-template-columns: 1fr;

/* 平板 */
@media (min-width: 768px) {
  grid-template-columns: repeat(2, 1fr);
}

/* 桌面 */
@media (min-width: 1024px) {
  grid-template-columns: repeat(3, 1fr);
}
```

---

## 动画系统

### 过渡时间

```css
--transition-fast: 0.1s;
--transition-base: 0.15s;
--transition-slow: 0.2s;
```

### 缓动函数

```css
--ease-in: cubic-bezier(0.4, 0, 1, 1);
--ease-out: cubic-bezier(0, 0, 0.2, 1);
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
```

### 常用动画

#### 悬停效果
```css
transition: all var(--transition-base) var(--ease-out);
```

#### 模态框
```css
transition: opacity var(--transition-slow) var(--ease-out),
            transform var(--transition-slow) var(--ease-out);
```

#### 加载动画
```css
@keyframes spin {
  to { transform: rotate(360deg); }
}
```

---

## 主题系统

### 深色主题（默认）

```css
:root {
  --color-bg: #0a0a0f;
  --color-bg-card: #12121a;
  --color-bg-input: #1a1a24;
  --color-text: #e5e7eb;
  --color-text-dim: #9ca3af;
  --color-border: #272735;
  --color-accent: #6366f1;
  --color-green: #10b981;
  --color-red: #ef4444;
  --color-info: #3b82f6;
}
```

### 浅色主题

```css
.light {
  --color-bg: #ffffff;
  --color-bg-card: #f8f9fa;
  --color-bg-input: #ffffff;
  --color-text: #1f2937;
  --color-text-dim: #6b7280;
  --color-border: #e5e7eb;
  --color-accent: #6366f1;
  --color-green: #10b981;
  --color-red: #ef4444;
  --color-info: #3b82f6;
}
```

---

## 图标系统

### 图标库

使用 [Lucide Icons](https://lucide.dev/) 作为主要图标库。

### 图标大小

| 用途 | 大小 |
|------|------|
| **小图标** | 14px |
| **标准图标** | 16px |
| **大图标** | 20px |
| **超大图标** | 24px |

### 图标颜色

- 默认：继承文本颜色
- 强调：主色
- 成功：成功色
- 错误：错误色
- 信息：信息色

---

## 可访问性

### 对比度

- 文本与背景对比度 ≥ 4.5:1
- 大文本与背景对比度 ≥ 3:1
- 交互元素与背景对比度 ≥ 3:1

### 焦点状态

- 焦点元素有明显的视觉指示
- 焦点边框颜色：主色
- 焦点偏移：2px

### 键盘导航

- 所有交互元素可通过键盘访问
- Tab 键顺序符合逻辑
- Enter/Space 键激活按钮

---

## 移动端适配

### 响应式策略

- 移动优先设计
- 渐进增强
- 触摸友好的交互元素（最小 44px）

### 移动端特有

- 汉堡菜单（从左侧滑出）
- 简化的导航
- 优化的触摸目标
- 适配的字体大小

---

## 设计资源

### 字体

- **Inter**: https://rsms.me/inter/
- **Noto Sans SC**: https://fonts.google.com/noto/specimen/Noto+Sans+SC
- **Space Mono**: https://fonts.google.com/specimen/Space+Mono
- **JetBrains Mono**: https://www.jetbrains.com/lp/mono/

### 图标

- **Lucide Icons**: https://lucide.dev/

### 配色工具

- **Coolors**: https://coolors.co/
- **Adobe Color**: https://color.adobe.com/

---

## 设计规范检查清单

### 视觉一致性

- [ ] 使用统一的色彩系统
- [ ] 使用统一的字体系统
- [ ] 使用统一的间距系统
- [ ] 使用统一的圆角系统
- [ ] 使用统一的阴影系统

### 交互一致性

- [ ] 按钮样式一致
- [ ] 表单样式一致
- [ ] 卡片样式一致
- [ ] 动画效果一致
- [ ] 悬停效果一致

### 响应式

- [ ] 移动端适配
- [ ] 平板适配
- [ ] 桌面适配
- [ ] 横屏适配
- [ ] 竖屏适配

### 可访问性

- [ ] 对比度符合标准
- [ ] 焦点状态明显
- [ ] 键盘导航可用
- [ ] 屏幕阅读器友好
- [ ] 色盲友好

---

## 版本历史

### v0.4.3 (2026-04-19)

- 优化 header title 字体，使用无衬线字体
- 完善视觉设计文档
- 总结设计语言和风格

---

## 参考资料

- [Material Design](https://material.io/design)
- [Apple Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/)
- [Web Content Accessibility Guidelines (WCAG)](https://www.w3.org/WAI/WCAG21/quickref/)
