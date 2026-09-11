"""Portfolio-ready advertising sales analysis for Python, Power BI, and GitHub."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, train_test_split


OUTPUT_DIR = Path(__file__).with_name("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
RANDOM_STATE = 42


def metrics(actual, predicted):
    return {
        "Test_MAE": mean_absolute_error(actual, predicted),
        "Test_RMSE": mean_squared_error(actual, predicted) ** 0.5,
        "Test_R2": r2_score(actual, predicted),
    }


def cross_validated_mae(data, formula):
    splitter = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    scores = []
    for fold, (train_index, valid_index) in enumerate(splitter.split(data), start=1):
        fold_train = data.iloc[train_index]
        fold_valid = data.iloc[valid_index]
        fold_model = smf.ols(formula=formula, data=fold_train).fit()
        prediction = fold_model.predict(fold_valid)
        scores.append({"Fold": fold, "MAE": mean_absolute_error(fold_valid.sales, prediction)})
    return pd.DataFrame(scores)


url = "https://raw.githubusercontent.com/selva86/datasets/master/Advertising.csv"
data = pd.read_csv(url).drop(columns=["Unnamed: 0"])
columns = ["TV", "radio", "newspaper", "sales"]

quality_summary = pd.DataFrame(
    {
        "Metric": ["資料筆數", "缺失值總數", "重複紀錄數"],
        "Value": [len(data), int(data[columns].isna().sum().sum()), int(data.duplicated(columns).sum())],
    }
)

train, test = train_test_split(data[columns], test_size=0.2, random_state=RANDOM_STATE)
formulas = {
    "原回歸模型": "sales ~ TV + radio + newspaper",
    "交互作用模型": "sales ~ TV * radio + newspaper",
}

baseline_prediction = np.repeat(train.sales.median(), len(test))
baseline = metrics(test.sales, baseline_prediction)
metric_rows = [{"Model": "中位數基準", **baseline, "CV_MAE_Mean": np.nan}]
fold_rows = []
models = {}

for model_name, formula in formulas.items():
    fitted = smf.ols(formula=formula, data=train).fit()
    models[model_name] = fitted
    prediction = fitted.predict(test)
    fold_scores = cross_validated_mae(train, formula)
    fold_scores.insert(0, "Model", model_name)
    fold_rows.append(fold_scores)
    metric_rows.append(
        {
            "Model": model_name,
            **metrics(test.sales, prediction),
            "CV_MAE_Mean": fold_scores.MAE.mean(),
        }
    )

model_metrics = pd.DataFrame(metric_rows)
model_metrics["MAE_Improvement_vs_Baseline_Pct"] = (
    (baseline["Test_MAE"] - model_metrics.Test_MAE) / baseline["Test_MAE"] * 100
)
model_metrics["Is_Final_Model"] = model_metrics.Model.eq("交互作用模型")

final_model = models["交互作用模型"]
test_results = test.copy()
test_results.insert(0, "Sample_ID", test_results.index + 1)
test_results["Predicted_Sales"] = final_model.predict(test)
test_results["Residual"] = test_results.sales - test_results.Predicted_Sales
test_results["Absolute_Error"] = test_results.Residual.abs()
test_results["Residual_Zero_Line"] = 0.0
test_results["Error_Level"] = pd.cut(
    test_results.Absolute_Error,
    bins=[-np.inf, 0.5, 1.0, np.inf],
    labels=["低", "中", "高"],
)

full_additive_model = smf.ols(formula=formulas["原回歸模型"], data=data).fit()
coefficient_summary = full_additive_model.conf_int().rename(columns={0: "CI_Lower", 1: "CI_Upper"})
coefficient_summary.insert(0, "Coefficient", full_additive_model.params)
coefficient_summary.index.name = "Variable"
coefficient_summary = coefficient_summary.reset_index()
coefficient_summary["Statistically_Clear_at_95Pct"] = ~(
    (coefficient_summary.CI_Lower <= 0) & (coefficient_summary.CI_Upper >= 0)
)

model_metrics.to_csv(OUTPUT_DIR / "advertising_model_metrics.csv", index=False, encoding="utf-8-sig")
test_results.to_csv(OUTPUT_DIR / "advertising_test_predictions.csv", index=False, encoding="utf-8-sig")
pd.concat(fold_rows, ignore_index=True).to_csv(
    OUTPUT_DIR / "advertising_cross_validation.csv", index=False, encoding="utf-8-sig"
)
coefficient_summary.to_csv(
    OUTPUT_DIR / "advertising_coefficients.csv", index=False, encoding="utf-8-sig"
)
quality_summary.to_csv(OUTPUT_DIR / "advertising_data_quality.csv", index=False, encoding="utf-8-sig")

# Portfolio images
plt.style.use("seaborn-v0_8-whitegrid")

fig, ax = plt.subplots(figsize=(7.2, 5.2))
ax.scatter(test_results.sales, test_results.Predicted_Sales, alpha=0.78, color="#24526B")
low = min(test_results.sales.min(), test_results.Predicted_Sales.min())
high = max(test_results.sales.max(), test_results.Predicted_Sales.max())
ax.plot([low, high], [low, high], "--", color="#C44E52", label="Perfect prediction")
ax.set(xlabel="Actual sales", ylabel="Predicted sales", title="Actual vs predicted sales")
ax.legend()
fig.tight_layout(); fig.savefig(OUTPUT_DIR / "actual_vs_predicted.png", dpi=180); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.2, 5.2))
ax.scatter(test_results.Predicted_Sales, test_results.Residual, alpha=0.78, color="#24526B")
ax.axhline(0, linestyle="--", color="#C44E52")
ax.set(xlabel="Predicted sales", ylabel="Residual", title="Residuals vs predicted sales")
fig.tight_layout(); fig.savefig(OUTPUT_DIR / "residuals_vs_predicted.png", dpi=180); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.2, 4.8))
ordered = model_metrics.sort_values("Test_MAE", ascending=True)
plot_labels = ordered.Model.map(
    {"中位數基準": "Median baseline", "原回歸模型": "Additive regression", "交互作用模型": "Interaction model"}
)
ax.barh(plot_labels, ordered.Test_MAE, color=["#287271", "#5B8E7D", "#D9A441"])
for index, value in enumerate(ordered.Test_MAE):
    ax.text(value + 0.06, index, f"{value:.3f}", va="center")
ax.set(xlabel="Test MAE (lower is better)", title="Model comparison")
fig.tight_layout(); fig.savefig(OUTPUT_DIR / "model_comparison.png", dpi=180); plt.close(fig)

print("\n=== Power BI model metrics ===")
print(model_metrics.round(3).to_string(index=False))
print(f"\nOutputs saved to: {OUTPUT_DIR}")
