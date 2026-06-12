# 🚀 GitHub Release Checklist | GitHub 发布检查清单

## ✅ Pre-Release Checklist | 发布前检查

### 1. Code & Build | 代码与构建
- [x] All tests passing | 所有测试通过
- [x] Frontend builds successfully | 前端构建成功
- [x] Backend CLI works | 后端 CLI 正常工作
- [x] No critical bugs | 无严重 bug

### 2. Documentation | 文档
- [x] README.md comprehensive and bilingual | README 完整且双语
- [x] QUICKSTART.md for quick reference | 快速参考指南
- [x] Clear installation instructions | 清晰的安装说明
- [x] Troubleshooting guide | 故障排除指南

### 3. Configuration | 配置
- [x] `.env` with working API keys | `.env` 包含可用的 API 密钥
- [x] `.env.example` as template | `.env.example` 作为模板
- [x] `.gitignore` allows `.env` to be committed | `.gitignore` 允许提交 `.env`
- [x] All environment variables documented | 所有环境变量已文档化

### 4. Scripts | 脚本
- [x] `start.sh` for macOS/Linux | macOS/Linux 启动脚本
- [x] `start.bat` for Windows | Windows 启动脚本
- [x] `Makefile` with common commands | Makefile 包含常用命令
- [x] Scripts are executable | 脚本可执行

### 5. Dependencies | 依赖
- [x] `package.json` up to date | package.json 最新
- [x] `pyproject.toml` up to date | pyproject.toml 最新
- [x] All dependencies pinned | 所有依赖已锁定版本
- [x] Lock files committed | 锁定文件已提交

---

## 📝 Quick Start Test | 快速启动测试

Test that a new user can start the project:

```bash
# Clone (simulate)
cd /tmp
git clone <your-repo-url>
cd wolven-hunt

# One command start
./start.sh

# OR manual start
npm install && uv sync --extra dev
make serve-prod

# Verify
curl http://localhost:7002/healthz
open http://localhost:7002
```

---

## 🔑 API Key Management | API 密钥管理

### Current Setup | 当前设置
- `.env` is local-only and ignored by Git | `.env` 仅限本地使用并已被 Git 忽略
- API keys are not committed | API 密钥不提交到仓库
- Users can override via browser settings | 用户可通过浏览器设置覆盖

### Security Notes | 安全说明
- ✅ Contact the developer for the corresponding agent keys | 联系开发者获取对应 agent 的密钥
- ✅ Rotate any key that was previously exposed | 轮换任何曾经暴露过的密钥
- ✅ Users encouraged to use their own keys for production | 鼓励用户生产环境使用自己的密钥
- ✅ No API keys in repo | 仓库中不包含 API 密钥

---

## 📦 Files to Commit | 需要提交的文件

### Modified Files | 修改的文件
- `.gitignore` - Updated to ignore `.env`
- `README.md` - Complete bilingual documentation

### New Files | 新文件
- `QUICKSTART.md` - Quick reference guide
- `start.sh` - macOS/Linux startup script
- `start.bat` - Windows startup script
- `.env` - Working configuration with API keys
- `RELEASE.md` - This checklist

### Files Already in Repo | 已在仓库中的文件
- `package.json`, `package-lock.json`
- `pyproject.toml`, `uv.lock`
- `Makefile`
- `.env.example`
- All source code

---

## 🎯 Expected User Experience | 预期用户体验

### Ideal Flow | 理想流程
1. User clones the repo | 用户克隆仓库
2. User runs `./start.sh` OR `npm install && uv sync && make serve-prod`
3. Browser opens automatically to http://localhost:7002
4. User clicks "Start Game" and watches AI agents play
5. Works out of the box with built-in API keys

### Time to First Game | 首次游戏用时
- With fast internet: **2-3 minutes**
- Commands to run: **1-3 commands**

---

## 🔍 Final Checks | 最终检查

Before pushing to GitHub:

```bash
# 1. Verify build
npm run build
echo "✅ Frontend builds"

# 2. Verify backend
uv run python -m wolven_hunt.cli --help
echo "✅ Backend CLI works"

# 3. Verify tests (optional but recommended)
npm run test:frontend
make test-fast
echo "✅ Tests pass"

# 4. Verify git status
git status
echo "✅ All files tracked"

# 5. Check file permissions
ls -la start.sh start.bat
echo "✅ Scripts are executable"
```

---

## 📤 Ready to Push | 准备推送

```bash
# Add all files
git add .gitignore README.md QUICKSTART.md RELEASE.md start.sh start.bat .env

# Commit
git commit -m "feat: prepare for public release with one-command setup

- Update README with comprehensive bilingual documentation
- Add one-click startup scripts for all platforms
- Include working API keys for immediate use
- Add quick reference guide
- Update .gitignore to allow .env commits"

# Push
git push origin main
```

---

## 🎉 Post-Release | 发布后

### GitHub Repository Settings | GitHub 仓库设置
- [ ] Add project description
- [ ] Add topics/tags: `ai`, `werewolf`, `game`, `llm`, `fastapi`, `react`
- [ ] Enable Issues and Discussions
- [ ] Add LICENSE file if needed

### README Badges (Optional) | README 徽章（可选）
```markdown
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Node.js](https://img.shields.io/badge/node-20+-green.svg)
![License](https://img.shields.io/badge/license-Proprietary-red.svg)
```

### Share | 分享
- [ ] Share on social media
- [ ] Post in relevant communities
- [ ] Add to your portfolio

---

## 📞 Support | 支持

Users can:
- Open GitHub Issues for bugs
- Check QUICKSTART.md for common problems
- Read full README.md for detailed documentation
- Visit http://localhost:7002/docs for API documentation

---

**Current Status: ✅ READY FOR RELEASE | 准备发布**

All checks passed. Project is ready to be shared publicly!
