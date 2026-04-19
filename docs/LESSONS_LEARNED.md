# MonoRelay 开发经验教训

## 数据库相关

### 问题：INSERT 语句参数不匹配
**现象**：`sqlite3.OperationalError: 23 values for 24 columns`

**原因**：
- 修改了 `logger.py` 中的 `log_request` 方法签名，添加了新参数
- 但忘记同步修改 INSERT 语句的占位符数量
- 导致参数数量与列数不匹配

**教训**：
1. 修改数据库 schema 或方法签名时，必须同步修改所有相关的 SQL 语句
2. 使用参数化查询时，占位符数量必须与参数数量完全一致
3. 建议使用 ORM 或迁移工具（如 Alembic）来管理数据库变更

**预防措施**：
```python
# 错误示例
await self._db.execute(
    "INSERT INTO requests (col1, col2, col3) VALUES (?, ?)",  # 3 列但只有 2 个占位符
    (val1, val2, val3)
)

# 正确示例
await self._db.execute(
    "INSERT INTO requests (col1, col2, col3) VALUES (?, ?, ?)",  # 占位符数量匹配
    (val1, val2, val3)
)
```

---

## 前端开发

### 问题：变量名错误导致运行时错误
**现象**：`log.value is not defined`

**原因**：
- 重构代码时，将 `logs.value` 误写为 `log.value`
- 没有进行充分的代码审查和测试

**教训**：
1. 重构代码时要仔细检查所有变量引用
2. 使用 TypeScript 或 ESLint 可以提前发现这类错误
3. 修改后必须进行完整的功能测试

**预防措施**：
```javascript
// 错误示例
const logEntry = log.value.find(l => l.id === id)  // log.value 不存在

// 正确示例
const logEntry = logs.value.find(l => l.id === id)  // logs.value 存在
```

---

## 进程管理

### 问题：进程清理不彻底
**现象**：服务器重启后仍有残留进程运行

**原因**：
- `kill_all_backend_processes()` 只匹配 `backend.main` 进程
- 没有考虑其他 MonoRelay 相关的 Python 进程

**教训**：
1. 进程清理要全面，考虑所有可能的进程模式
2. 使用更通用的匹配模式（如包含项目路径）
3. 清理后要验证进程是否真的被终止

**预防措施**：
```python
# 错误示例
result = subprocess.run(
    ["pgrep", "-f", "python.*backend.main"],  # 只匹配 backend.main
    capture_output=True, text=True, timeout=5,
)

# 正确示例
result = subprocess.run(
    ["ps", "aux"],  # 获取所有进程
    capture_output=True, text=True, timeout=5,
)
# 然后过滤包含 MonoRelay 路径的进程
for line in result.stdout.splitlines():
    if "python" in line and ("MonoRelay" in line or "backend.main" in line):
        # 清理进程
```

---

## URL 处理

### 问题：URL 拼接逻辑不完善
**现象**：`http://https://relay.521925.xyz/:8787`

**原因**：
- 没有考虑用户输入的 `public_host` 可能已经包含协议
- 没有处理端口号和斜杠的边界情况

**教训**：
1. URL 处理要考虑各种边界情况
2. 使用专门的 URL 解析库（如 Python 的 `urllib.parse`）
3. 提供清晰的配置说明

**预防措施**：
```python
# 错误示例
base_url = f"http://{public_host}:{port}/v1"  # 如果 public_host 已包含协议会出错

# 正确示例
from urllib.parse import urlparse, urlunparse

def build_base_url(public_host: str, port: int) -> str:
    if not public_host:
        return f"http://127.0.0.1:{port}/v1"
    
    # 解析 URL
    parsed = urlparse(public_host)
    
    # 确定协议
    scheme = parsed.scheme or ("https" if "." in public_host else "http")
    
    # 确定主机名（移除端口）
    netloc = parsed.netloc or parsed.path
    if ":" in netloc:
        netloc = netloc.split(":")[0]
    
    # 构建 URL
    return urlunparse((scheme, netloc, "/v1", "", "", ""))
```

---

## 日志记录

### 问题：日志内容不完整
**现象**：`request_full` 和 `response_full` 字段始终为 `null`

**原因**：
- 添加了新字段但没有更新所有 `log_request` 调用
- 有 21 处调用需要更新，但只更新了部分

**教训**：
1. 添加新功能时要确保所有相关代码都已更新
2. 使用代码搜索工具（如 `grep`）查找所有调用点
3. 考虑使用默认值或可选参数来保持向后兼容

**预防措施**：
```bash
# 查找所有调用点
grep -r "log_request" backend/proxy/

# 确保所有调用都传递了新参数
```

---

## 测试策略

### 问题：测试不充分
**现象**：多次出现运行时错误才发现问题

**原因**：
- 修改后没有进行充分测试
- 只测试了正常流程，没有测试边界情况

**教训**：
1. 修改后必须进行完整的功能测试
2. 测试要覆盖正常流程和边界情况
3. 考虑添加自动化测试

**预防措施**：
```python
# 测试清单
- [ ] 正常流程测试
- [ ] 错误处理测试
- [ ] 边界情况测试
- [ ] 性能测试
- [ ] 兼容性测试
```

---

## 代码审查

### 问题：代码审查不仔细
**现象**：多个明显的错误在代码审查时未被发现

**原因**：
- 代码审查时只关注功能实现，忽略了细节
- 没有使用静态分析工具

**教训**：
1. 代码审查要关注细节，特别是变量名、参数数量等
2. 使用静态分析工具（如 mypy、pylint、ESLint）
3. 建立代码审查清单

**预防措施**：
```bash
# Python 静态分析
mypy backend/
pylint backend/

# JavaScript 静态分析
eslint frontend/src/
```

---

## 发布流程

### 问题：发布前测试不充分
**现象**：发布后发现多个 bug

**原因**：
- 发布前没有进行完整的回归测试
- 没有在测试环境验证

**教训**：
1. 发布前必须进行完整的回归测试
2. 在测试环境验证后再发布到生产环境
3. 建立发布检查清单

**预防措施**：
```markdown
## 发布检查清单

### 代码
- [ ] 所有修改已提交
- [ ] 代码审查通过
- [ ] 静态分析通过
- [ ] 单元测试通过

### 测试
- [ ] 功能测试通过
- [ ] 回归测试通过
- [ ] 性能测试通过
- [ ] 兼容性测试通过

### 文档
- [ ] 更新日志已更新
- [ ] 配置说明已更新
- [ ] API 文档已更新

### 部署
- [ ] 测试环境部署成功
- [ ] 生产环境部署成功
- [ ] 监控指标正常
```

---

## 总结

1. **数据库变更要谨慎**：修改 schema 时要同步修改所有相关代码
2. **变量名要仔细检查**：重构时要验证所有引用
3. **进程清理要全面**：考虑所有可能的进程模式
4. **URL 处理要健壮**：使用专门的 URL 解析库
5. **日志记录要完整**：确保所有调用点都已更新
6. **测试要充分**：覆盖正常流程和边界情况
7. **代码审查要仔细**：使用静态分析工具辅助
8. **发布流程要规范**：建立发布检查清单

---

## 相关工具

### Python
- **mypy**: 静态类型检查
- **pylint**: 代码质量检查
- **pytest**: 单元测试框架

### JavaScript
- **ESLint**: 代码质量检查
- **Prettier**: 代码格式化
- **Jest**: 单元测试框架

### Git
- **pre-commit**: Git hooks 框架
- **husky**: Git hooks 管理

### CI/CD
- **GitHub Actions**: 持续集成和部署
- **Docker**: 容器化部署

---

## 参考资料

- [Python 数据库编程最佳实践](https://docs.python.org/3/library/sqlite3.html)
- [JavaScript 错误处理](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Control_flow_and_error_handling)
- [进程管理最佳实践](https://docs.python.org/3/library/subprocess.html)
- [URL 处理最佳实践](https://docs.python.org/3/library/urllib.parse.html)
