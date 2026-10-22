"""Checks of the assumptions that matter for an honest forecasting experiment."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import FEATURES, error_scores, evaluate_store, load_data, make_features


def sample_data(n=200):
    dates = pd.date_range("2023-01-01", periods=n)
    sales = -0.9 + 0.5 * np.sin(np.arange(n) * 2 * np.pi / 7) + np.arange(n) * 0.002
    return pd.DataFrame({
        "date": dates, "store": "store_test", "sales": sales,
        "unsold": np.nan, "ordered": np.nan,
        "is_state_holiday": "normal_day", "is_school_holiday": "normal_day",
        "is_special_day": "normal_day", "temperature_mean": 12.0,
    })


def test_lags_follow_calendar_days_and_do_not_fill_missing_sales():
    data = sample_data(40)
    missing_date = data.loc[12, "date"]
    previous_day_sales = data.loc[11, "sales"]
    features = make_features(data.drop(index=12))
    assert pd.isna(features.loc[missing_date, "actual"])
    assert pd.isna(features.loc[missing_date + pd.Timedelta(days=7), "lag_7"])
    assert features.loc[missing_date + pd.Timedelta(days=6), "lag_7"] == previous_day_sales
    assert not any("unsold" in column or "ordered" in column or "temperature" in column for column in FEATURES)


def test_week_forecasts_ignore_sales_and_observed_weather_inside_that_week():
    data = sample_data()
    original = evaluate_store(data, "store_test", holdout_days=14)
    changed = data.copy()
    first_day = original["predictions"].iloc[0]["date"]
    week_mask = changed["date"].between(first_day, first_day + pd.Timedelta(days=6))
    changed.loc[week_mask, "sales"] = 50000.0
    changed.loc[week_mask, "temperature_mean"] = -999.0
    altered = evaluate_store(changed, "store_test", holdout_days=14)
    first_origin = original["predictions"].iloc[0]["origin"]
    a = original["predictions"].query("origin == @first_origin")
    b = altered["predictions"].query("origin == @first_origin")
    np.testing.assert_allclose(a["ml"], b["ml"], rtol=0, atol=0)
    np.testing.assert_allclose(a["baseline"], b["baseline"], rtol=0, atol=0)
    assert a["horizon"].tolist() == list(range(1, 8))
    assert (a["date"] > a["origin"]).all()
    assert a["actual"].lt(0).any()  # Negative scaled sales remain meaningful.


def test_short_history_has_an_honest_empty_result():
    result = evaluate_store(sample_data(61), "store_test")
    assert result["evaluation"]["eligible"] is False
    assert result["evaluation"]["ml_mae"] is None
    assert result["predictions"].empty


def test_store_with_no_observed_sales_has_a_clear_error():
    data = sample_data()
    data["sales"] = np.nan
    with pytest.raises(ValueError, match="no observed sales"):
        evaluate_store(data, "store_test")


def test_scores_handle_negative_and_zero_targets_without_percentage_errors():
    assert error_scores([-1, 0, 1], [0, 0, 0])["mae"] == pytest.approx(2 / 3)
    with pytest.raises(ValueError):
        error_scores([], [])


def test_input_validation_rejects_duplicate_store_dates_and_keeps_negative_values(tmp_path):
    path = tmp_path / "sample.csv"
    data = sample_data(10)
    data.to_csv(path, index=False)
    assert load_data(path)["sales"].min() < 0
    pd.concat([data, data.iloc[:1]], ignore_index=True).to_csv(path, index=False)
    with pytest.raises(ValueError, match="at most one"):
        load_data(path)


def test_real_sample_and_common_evaluation_dates():
    data = load_data()
    assert len(data) == 5142
    assert data["store"].nunique() == 9
    assert data["date"].max() == pd.Timestamp("2023-11-30")
    result = evaluate_store(data, "store_1", holdout_days=7)
    predictions = result["predictions"]
    assert result["evaluation"]["eligible"]
    assert predictions[["actual", "baseline", "ml"]].notna().all().all()
    assert result["evaluation"]["n_predictions"] == len(predictions)
    assert predictions["date"].min() > predictions["origin"].max()
