#!/bin/bash
# QuantLab 一键部署脚本 (Linux/Mac)
set -e

echo "========================================"
echo "  QuantLab 双引擎量化平台 - 初始化部署"
echo "========================================"

cd "$(dirname "$0")/.."

# 安装依赖
echo "[1/4] 安装依赖..."
pip install pandas numpy matplotlib seaborn scipy scikit-learn \
    loguru click pyyaml python-dotenv tqdm pyarrow -q

# 创建目录
echo "[2/4] 创建目录..."
mkdir -p outputs/plots outputs/reports logs data/raw data/staging

# 验证数据
echo "[3/4] 验证环境..."
python -c "import pandas, numpy, matplotlib; print('[OK] 基础包OK')"

echo "[4/4] 完成"
echo ""
echo "运行回测: python scripts/run_kc50_backtest.py"
