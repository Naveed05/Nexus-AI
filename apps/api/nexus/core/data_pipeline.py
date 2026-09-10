from typing import Any

import polars as pl


class DataPipeline:
    """Deterministic data-science pipeline primitives for NEXUS."""

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
            if series.dtype.is_numeric():
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
            if series.dtype.is_numeric():
                numeric[column] = {
                    "count": series.len() - series.null_count(),
                    "mean": series.mean(),
                    "median": series.median(),
                    "std": series.std(),
                    "min": series.min(),
                    "max": series.max(),
                }
            else:
                values = series.drop_nulls().value_counts().sort("count", descending=True).head(10).to_dicts()
                categorical[column] = {
                    "count": series.len() - series.null_count(),
                    "unique_count": series.n_unique(),
                    "top_values": values,
                }
        return {"numeric": numeric, "categorical": categorical}

    def analyze(self, frame: pl.DataFrame) -> dict[str, Any]:
        profile = self._profile(frame)
        cleaned, changes = self.clean(frame)
        return {
            "profile": profile,
            "cleaning_plan": self.cleaning_plan(frame),
            "cleaning_applied": changes,
            "cleaned_shape": {"rows": cleaned.height, "columns": cleaned.width},
            "eda": self.eda(cleaned),
        }

    @staticmethod
    def _profile(frame: pl.DataFrame) -> dict[str, Any]:
        if frame is None:
            raise ValueError("DataFrame cannot be None")
        rows = frame.height
        columns = []
        for name in frame.columns:
            series = frame.get_column(name)
            columns.append({
                "name": name,
                "dtype": str(series.dtype),
                "numeric": series.dtype.is_numeric(),
                "null_count": series.null_count(),
                "null_ratio": series.null_count() / rows if rows else 0.0,
                "unique_count": series.n_unique(),
            })
        return {"rows": rows, "columns": columns, "column_count": frame.width, "duplicate_rows": rows - frame.unique().height}
