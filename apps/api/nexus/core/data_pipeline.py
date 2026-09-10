from typing import Any

import polars as pl


class DataPipeline:
    """Deterministic data-science intelligence primitives for NEXUS."""

    def cleaning_plan(self, frame: pl.DataFrame) -> list[dict[str, Any]]:
        profile = self._profile(frame)
        actions: list[dict[str, Any]] = []
        if profile["duplicate_rows"]:
            actions.append({"action": "remove_duplicates", "rows": profile["duplicate_rows"]})
        for column in profile["columns"]:
            if column["null_count"]:
                strategy = "median" if column["numeric"] else "mode"
                actions.append({"action": "impute_missing", "column": column["name"], "strategy": strategy, "null_count": column["null_count"]})
            if column["unique_count"] <= 1 and profile["rows"] > 0:
                actions.append({"action": "review_constant_column", "column": column["name"]})
        return actions

    def clean(self, frame: pl.DataFrame) -> tuple[pl.DataFrame, list[dict[str, Any]]]:
        """Apply conservative deterministic cleaning; never drops columns automatically."""
        if frame is None:
            raise ValueError("DataFrame cannot be None")
        result = frame.unique(maintain_order=True)
        changes: list[dict[str, Any]] = []
        removed = frame.height - result.height
        if removed:
            changes.append({"action": "remove_duplicates", "rows_removed": removed})
        for column in result.columns:
            series = result.get_column(column)
            if series.null_count() == 0:
                continue
            if self._is_numeric(series):
                fill_value = series.median()
                if fill_value is None:
                    continue
                result = result.with_columns(pl.col(column).fill_null(fill_value))
                strategy = "median"
            else:
                modes = series.drop_nulls().mode()
                if modes.len() == 0:
                    continue
                result = result.with_columns(pl.col(column).fill_null(modes[0]))
                strategy = "mode"
            changes.append({"action": "impute_missing", "column": column, "strategy": strategy})
        return result, changes

    def eda(self, frame: pl.DataFrame) -> dict[str, Any]:
        if frame is None:
            raise ValueError("DataFrame cannot be None")
        numeric: dict[str, dict[str, Any]] = {}
        categorical: dict[str, dict[str, Any]] = {}
        for column in frame.columns:
            series = frame.get_column(column)
            if self._is_numeric(series):
                numeric[column] = {
                    "count": series.len() - series.null_count(),
                    "mean": series.mean(),
                    "median": series.median(),
                    "std": series.std(),
                    "min": series.min(),
                    "max": series.max(),
                    "outlier_count_iqr": self._iqr_outliers(series),
                }
            else:
                values = series.drop_nulls().value_counts().sort("count", descending=True).head(10).to_dicts()
                categorical[column] = {
                    "count": series.len() - series.null_count(),
                    "unique_count": series.n_unique(),
                    "top_values": values,
                }
        return {"numeric": numeric, "categorical": categorical}

    def correlations(self, frame: pl.DataFrame) -> list[dict[str, Any]]:
        numeric_columns = [c for c in frame.columns if self._is_numeric(frame.get_column(c))]
        pairs: list[dict[str, Any]] = []
        for index, left in enumerate(numeric_columns):
            for right in numeric_columns[index + 1:]:
                value = frame.select(pl.corr(left, right)).item()
                if value is not None:
                    pairs.append({"feature_a": left, "feature_b": right, "correlation": float(value)})
        return sorted(pairs, key=lambda item: abs(item["correlation"]), reverse=True)

    def infer_problem(self, frame: pl.DataFrame, target: str | None = None) -> dict[str, Any]:
        if target is not None and target not in frame.columns:
            raise ValueError(f"Target column not found: {target}")
        if target is None:
            return {"type": "descriptive", "target": None, "confidence": 1.0, "reason": "No target was supplied."}
        series = frame.get_column(target)
        if self._is_numeric(series) and series.n_unique() > max(2, min(20, int(frame.height * 0.05))):
            return {"type": "regression", "target": target, "confidence": 0.8, "reason": "Continuous numeric target."}
        return {"type": "classification", "target": target, "confidence": 0.8, "reason": "Categorical or low-cardinality target."}

    def recommendations(self, frame: pl.DataFrame, target: str | None = None) -> list[str]:
        recommendations: list[str] = []
        profile = self._profile(frame)
        if profile["duplicate_rows"]:
            recommendations.append("Remove duplicate rows before modeling.")
        if any(column["null_count"] for column in profile["columns"]):
            recommendations.append("Review missing-value patterns and imputation choices.")
        if any(column["unique_count"] <= 1 for column in profile["columns"]):
            recommendations.append("Review constant columns because they carry no predictive variation.")
        if len([c for c in frame.columns if self._is_numeric(frame.get_column(c))]) >= 2:
            recommendations.append("Inspect numeric correlations and potential multicollinearity.")
        if target is not None:
            recommendations.append(f"Establish a baseline model for target '{target}' and evaluate on a held-out test set.")
        else:
            recommendations.append("Choose a target explicitly before supervised ML training.")
        return recommendations

    def analyze(self, frame: pl.DataFrame, target: str | None = None) -> dict[str, Any]:
        profile = self._profile(frame)
        cleaned, changes = self.clean(frame)
        return {
            "profile": profile,
            "cleaning_plan": self.cleaning_plan(frame),
            "cleaning_applied": changes,
            "cleaned_shape": {"rows": cleaned.height, "columns": cleaned.width},
            "eda": self.eda(cleaned),
            "correlations": self.correlations(cleaned),
            "problem": self.infer_problem(cleaned, target),
            "recommendations": self.recommendations(cleaned, target),
        }

    @staticmethod
    def _is_numeric(series: pl.Series) -> bool:
        return series.dtype in pl.NUMERIC_DTYPES

    @staticmethod
    def _iqr_outliers(series: pl.Series) -> int:
        clean = series.drop_nulls()
        if clean.len() < 4:
            return 0
        q1 = clean.quantile(0.25)
        q3 = clean.quantile(0.75)
        if q1 is None or q3 is None:
            return 0
        iqr = q3 - q1
        if iqr == 0:
            return 0
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        return int(((clean < lower) | (clean > upper)).sum())

    @classmethod
    def _profile(cls, frame: pl.DataFrame) -> dict[str, Any]:
        if frame is None:
            raise ValueError("DataFrame cannot be None")
        rows = frame.height
        columns = []
        for name in frame.columns:
            series = frame.get_column(name)
            columns.append({
                "name": name,
                "dtype": str(series.dtype),
                "numeric": cls._is_numeric(series),
                "null_count": series.null_count(),
                "null_ratio": series.null_count() / rows if rows else 0.0,
                "unique_count": series.n_unique(),
            })
        return {"rows": rows, "columns": columns, "column_count": frame.width, "duplicate_rows": rows - frame.unique().height}
