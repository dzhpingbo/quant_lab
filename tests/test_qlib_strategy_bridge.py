import yaml

from src.qlib_ext import (
    QlibWorkflowSpec,
    build_qlib_workflow_config,
    get_dual_framework_strategy,
    list_dual_framework_strategies,
    qlib_topk_dropout_strategy_config,
)


def test_dual_framework_strategy_exposes_vectorbt_and_qlib_configs():
    spec = get_dual_framework_strategy("topk_dropout_50_5")

    vectorbt_config = spec.vectorbt_config(rebalance_freq="W")
    qlib_config = spec.qlib_strategy_config()

    assert vectorbt_config["portfolio_method"] == "topk_dropout"
    assert vectorbt_config["top_k"] == 50
    assert vectorbt_config["n_drop"] == 5
    assert vectorbt_config["rebalance_freq"] == "W"
    assert qlib_config["class"] == "TopkDropoutStrategy"
    assert qlib_config["module_path"] == "qlib.contrib.strategy"
    assert qlib_config["kwargs"]["signal"] == "<PRED>"
    assert qlib_config["kwargs"]["topk"] == 50
    assert qlib_config["kwargs"]["n_drop"] == 5


def test_qlib_workflow_config_contains_model_dataset_records_and_strategy():
    workflow = build_qlib_workflow_config(
        QlibWorkflowSpec(
            strategy_name="topk_dropout_100_10",
            market="csi500",
            benchmark="SH000905",
            train_segment=("2010-01-01", "2018-12-31"),
            valid_segment=("2019-01-01", "2020-12-31"),
            test_segment=("2021-01-01", "2024-12-31"),
            backtest_start_time="2021-01-01",
            backtest_end_time="2024-12-31",
        )
    )

    assert workflow["market"] == "csi500"
    assert workflow["benchmark"] == "SH000905"
    assert workflow["task"]["model"]["class"] == "LGBModel"
    assert workflow["task"]["dataset"]["kwargs"]["handler"]["class"] == "Alpha360"
    assert workflow["port_analysis_config"]["strategy"]["kwargs"]["topk"] == 100
    assert workflow["port_analysis_config"]["strategy"]["kwargs"]["n_drop"] == 10
    assert workflow["task"]["record"][-1]["class"] == "PortAnaRecord"
    assert workflow["task"]["record"][-1]["kwargs"]["config"]["strategy"]["kwargs"]["topk"] == 100


def test_qlib_topk_config_validates_parameters():
    cfg = qlib_topk_dropout_strategy_config(topk=10, n_drop=2, signal="score")
    assert cfg["kwargs"] == {"signal": "score", "topk": 10, "n_drop": 2}


def test_strategy_catalog_is_yaml_serializable():
    rows = [spec.as_dict() for spec in list_dual_framework_strategies()]
    text = yaml.safe_dump(rows, sort_keys=False)

    assert "topk_dropout_50_5" in text
    assert "ic_weighted_topk_dropout_50_5" in text
