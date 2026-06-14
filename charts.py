# charts.py
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objects import Figure

from expense_tracker_agent.db import fetch_expense_items, fetch_expenses


def kpi_stats(start_date: str, end_date: str) -> dict:
    rows = fetch_expenses(start_date, end_date)
    total = sum(r["amount"] for r in rows)
    count = len(rows)
    if rows:
        dates = sorted({r["date"] for r in rows})
        days = max(len(dates), 1)
        avg = total / days
    else:
        avg = 0.0
    return {"total": total, "count": count, "avg_per_day": avg}


def monthly_trend_data(start_date: str = None, end_date: str = None) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["month", "total"])
    df = pd.DataFrame(rows)
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    return df.groupby("month")["amount"].sum().reset_index().rename(columns={"amount": "total"})


def category_breakdown_data(start_date: str, end_date: str) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["category", "total"])
    df = pd.DataFrame(rows)
    return df.groupby("category")["amount"].sum().reset_index().rename(columns={"amount": "total"})


def weekly_bar_data(start_date: str, end_date: str) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["week", "total"])
    df = pd.DataFrame(rows)
    df["week"] = pd.to_datetime(df["date"]).dt.to_period("W").astype(str)
    return df.groupby("week")["amount"].sum().reset_index().rename(columns={"amount": "total"})


def top_merchants_data(start_date: str, end_date: str, n: int = 10) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["merchant", "total"])
    df = pd.DataFrame(rows)
    df = df[df["merchant"].notna() & (df["merchant"] != "")]
    if df.empty:
        return pd.DataFrame(columns=["merchant", "total"])
    return (
        df.groupby("merchant")["amount"].sum()
        .reset_index()
        .rename(columns={"amount": "total"})
        .sort_values("total", ascending=False)
        .head(n)
    )


def sub_expense_breakdown_data(start_date: str, end_date: str) -> pd.DataFrame:
    expenses = fetch_expenses(start_date, end_date)
    rows = []
    for exp in expenses:
        if not exp["merchant"]:
            continue
        items = fetch_expense_items(exp["id"])
        for item in items:
            rows.append({
                "merchant": exp["merchant"],
                "category": item["category"],
                "amount": item["amount"],
            })
    if not rows:
        return pd.DataFrame(columns=["merchant", "category", "amount"])
    return pd.DataFrame(rows)


def heatmap_data(start_date: str, end_date: str) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["date", "total"])
    df = pd.DataFrame(rows)
    return df.groupby("date")["amount"].sum().reset_index().rename(columns={"amount": "total"})


# --- Figure builders ---

def fig_monthly_trend(start_date: str = None, end_date: str = None) -> Figure:
    df = monthly_trend_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.line(df, x="month", y="total", markers=True,
                   labels={"month": "Month", "total": "€ Spent"},
                   title="Monthly Spending Trend")


def fig_category_donut(start_date: str, end_date: str) -> Figure:
    df = category_breakdown_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.pie(df, names="category", values="total", hole=0.45,
                  title="Spending by Category")


def fig_weekly_bar(start_date: str, end_date: str) -> Figure:
    df = weekly_bar_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.bar(df, x="week", y="total",
                  labels={"week": "Week", "total": "€ Spent"},
                  title="Weekly Spending")


def fig_top_merchants(start_date: str, end_date: str) -> Figure:
    df = top_merchants_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.bar(df.sort_values("total"), x="total", y="merchant",
                  orientation="h",
                  labels={"total": "€ Spent", "merchant": ""},
                  title="Top Merchants")


def fig_sub_expense_breakdown(start_date: str, end_date: str) -> Figure:
    df = sub_expense_breakdown_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No receipt data yet", showarrow=False)
    return px.bar(df, x="merchant", y="amount", color="category",
                  title="Sub-expense Breakdown by Store",
                  labels={"amount": "€", "merchant": "Store"})


def fig_heatmap(start_date: str, end_date: str) -> Figure:
    df = heatmap_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    df["date_obj"] = pd.to_datetime(df["date"])
    df["weekday"] = df["date_obj"].dt.day_name()
    df["week"] = df["date_obj"].dt.isocalendar().week.astype(str)
    pivot = df.pivot_table(index="weekday", columns="week", values="total", aggfunc="sum")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex([d for d in day_order if d in pivot.index])
    return px.imshow(pivot, color_continuous_scale="Blues",
                     title="Daily Spending Heatmap",
                     labels={"color": "€ Spent"})
