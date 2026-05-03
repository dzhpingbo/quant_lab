@echo off
REM QuantLab 一键部署脚本 (Windows)
echo ========================================
echo   QuantLab 双引擎量化平台 - 初始化部署
echo ========================================

cd /d %~dp0..

REM 检查Python
python --version
if errorlevel 1 (
    echo [ERROR] Python未安装，请先安装Python 3.9+
    pause
    exit /b 1
)

REM 安装依赖
echo.
echo [1/4] 安装基础依赖...
pip install pandas numpy matplotlib seaborn scipy scikit-learn -q
pip install loguru click pyyaml python-dotenv tqdm pyarrow -q

echo.
echo [2/4] 创建必要目录...
mkdir outputs\plots 2>nul
mkdir outputs\reports 2>nul
mkdir logs 2>nul
mkdir data\raw 2>nul
mkdir data\staging 2>nul

echo.
echo [3/4] 验证数据目录...
if exist "E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\20100101_20260407" (
    echo [OK] 数据目录存在
) else (
    echo [WARNING] 未找到数据目录 E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\...
    echo           请确认数据路径，或修改 scripts/run_kc50_backtest.py 中的 data_dir
)

echo.
echo [4/4] 运行测试...
python -c "import pandas, numpy, matplotlib; print('[OK] 基础包测试通过')"

echo.
echo ========================================
echo   部署完成！
echo.
echo   运行回测: python scripts/run_kc50_backtest.py
echo   CLI命令:  python -m src.cli --help
echo ========================================
pause
