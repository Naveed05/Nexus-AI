from __future__ import annotations

from typing import Any

import polars as pl
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


class MLEngine:
    """Conservative ML intelligence for NEXUS.

    The engine detects a likely problem type and can train a transparent baseline
    only when the caller supplies a target column. It deliberately avoids
    silently inventing a target for arbitrary datasets.
    """

    def detect_problem(self, frame: pl.DataFrame, target: str | None = None) -> dict[str, Any]:
        if frame is None or frame.height == 0:
            raise ValueError("A non-empty DataFrame is required")
        if target is not None and target not in frame.columns:
            raise ValueError(f"Target column not found: {target}")
        if target is None:
            return {
                "problem_type": "descriptive",
                "target": None,
                "confidence": 1.0,
                "reason": "No target column was supplied; NEXUS will not guess one for training.",
            }
        series = frame.get_column(target)
        unique = series.n_unique()
        if series.dtype.is_numeric():
            if unique <= max(2, min(20, int(frame.height * 0.05))):
                problem_type = "classification"
                reason = "Numeric target has a small number of distinct values."
            else:
                problem_type = "regression"
                reason = "Numeric target has many distinct values."
        else:
            problem_type = "classification"
            reason = "Non-numeric target is treated as a categorical class label."
        return {"problem_type": problem_type, "target": target, "confidence": 0.8, "reason": reason}

    def baseline(self, frame: pl.DataFrame, target: str, test_size: float = 0.2, random_state: int = 42) -> dict[str, Any]:
        if frame is None or frame.height < 5:
            raise ValueError("At least 5 rows are required for baseline training")
        if target not in frame.columns:
            raise ValueError(f"Target column not found: {target}")
        problem = self.detect_problem(frame, target)
        working = frame.drop_nulls(subset=[target])
        if working.height < 5:
            raise ValueError("Not enough non-null target rows for training")
        X = working.drop(target).to_pandas()
        y = working.get_column(target).to_pandas()
        numeric = [c for c in X.columns if X[c].dtype.kind in "biufc"]
        categorical = [c for c in X.columns if c not in numeric]
        transformers = []
        if numeric:
            transformers.append(("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric))
        if categorical:
            transformers.append(("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical))
        if not transformers:
            raise ValueError("No usable feature columns remain after selecting the target")
        preprocessor = ColumnTransformer(transformers=transformers)
        if problem["problem_type"] == "classification":
            model = LogisticRegression(max_iter=1000)
            stratify = y if y.value_counts().min() >= 2 else None
        else:
            model = Ridge()
            stratify = None
        pipeline = Pipeline([("preprocess", preprocessor), ("model", model)])
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=stratify)
        pipeline.fit(X_train, y_train)
        predictions = pipeline.predict(X_test)
        if problem["problem_type"] == "classification":
            metrics = {"accuracy": float(accuracy_score(y_test, predictions))}
        else:
            metrics = {
                "mae": float(mean_absolute_error(y_test, predictions)),
                "rmse": float(mean_squared_error(y_test, predictions) ** 0.5),
                "r2": float(r2_score(y_test, predictions)),
            }
        return {
            "problem": problem,
            "rows_used": int(working.height),
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "features": list(X.columns),
            "model": "logistic_regression" if problem["problem_type"] == "classification" else "ridge_regression",
            "metrics": metrics,
        }
