#!/usr/bin/env bash
# preflight.sh — 公开仓库提交前自检。
# 检查：个人信息、敏感措辞、非 noreply 邮箱、手机号、本机绝对路径、常见密钥。
# 用法：bash scripts/preflight.sh [--staged]
#   默认扫描已跟踪文件；--staged 只扫描暂存区（提交前跑一次最省事）。
# 退出码：0 干净；1 命中；2 用法或环境错误。
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "不在 git 仓库里"; exit 2; }

STAGED=0
case "${1:-}" in
  --staged) STAGED=1 ;;
  "") ;;
  *) echo "用法: bash scripts/preflight.sh [--staged]"; exit 2 ;;
esac

# 每行一个正则。原则是「宁多勿漏」：误报就加进 EXCLUDES，不要放宽模式。
PATTERNS=(
  '简历|求职|春招|秋招|内推|大三|学号|面试|实习'
  '[A-Za-z0-9._%+-]+@(gmail|qq|163|outlook|hotmail|foxmail)\.[A-Za-z]{2,}'
  '(^|[^0-9.])1[3-9][0-9]{9}([^0-9.]|$)'
  '[A-Za-z]:[\\]{1,2}[A-Za-z0-9_.-]+[\\]{1,2}[A-Za-z0-9_.-]+'
  'sk-[A-Za-z0-9]{16,}'
  'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'
)

# 第三方产物与依赖目录，不参与扫描。
EXCLUDES=(
  ':!web/node_modules'
  ':!web/dist'
  ':!*.min.js'
  ':!*.map'
  ':!static/swagger-ui-bundle.js'
  ':!models'
  ':!.venv'
  ':!scripts/preflight.sh'
)

if [ "$STAGED" = 1 ]; then
  GREP=(git grep --cached -n -I -E)
else
  GREP=(git grep -n -I -E)
fi

hits=0
for pat in "${PATTERNS[@]}"; do
  out=$("${GREP[@]}" -e "$pat" -- . "${EXCLUDES[@]}" 2>/dev/null) || true
  [ -z "$out" ] && continue
  hits=$((hits + 1))
  total=$(printf '%s\n' "$out" | wc -l | tr -d ' ')
  echo "── 命中：$pat"
  printf '%s\n' "$out" | head -20
  [ "$total" -gt 20 ] && echo "   … 共 $total 行"
done

if [ "$hits" -gt 0 ]; then
  echo
  echo "✗ preflight 失败：上面这些内容不应该出现在公开仓库。"
  echo "  改写措辞 / 换成相对路径；确属误报就加进本脚本的 EXCLUDES。"
  exit 1
fi

echo "✓ preflight 通过：没有个人信息、敏感措辞、本机路径或密钥。"
