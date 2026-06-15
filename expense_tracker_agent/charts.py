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
    df["week"] = pd.to_datetime(df["date"]).dt.strftime("%G-W%V")
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
    from datetime import date as _date
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)

    # Use daily bars for ranges ≤ 45 days, monthly line otherwise
    if start_date and end_date:
        days_range = (_date.fromisoformat(end_date) - _date.fromisoformat(start_date)).days
    else:
        days_range = 999

    df = pd.DataFrame(rows)
    if days_range <= 45:
        # Sort by ISO date (YYYY-MM-DD), display as DD/MM/YYYY
        grouped = (df.groupby("date")["amount"].sum()
                   .reset_index()
                   .rename(columns={"amount": "total"})
                   .sort_values("date"))
        grouped["period"] = pd.to_datetime(grouped["date"]).dt.strftime("%d/%m/%Y")
        title, xlabel = "Daily Spending", "Date"
        fig = px.bar(grouped, x="period", y="total",
                     labels={"period": xlabel, "total": "€ Spent"}, title=title,
                     color_discrete_sequence=["#0d9488"])
    else:
        # Sort by ISO month (YYYY-MM), display as MM/YYYY
        df["sort_key"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        grouped = (df.groupby("sort_key")["amount"].sum()
                   .reset_index()
                   .rename(columns={"amount": "total"})
                   .sort_values("sort_key"))
        grouped["period"] = pd.to_datetime(grouped["sort_key"]).dt.strftime("%m/%Y")
        title, xlabel = "Monthly Spending Trend", "Month"
        fig = px.line(grouped, x="period", y="total", markers=True,
                      labels={"period": xlabel, "total": "€ Spent"}, title=title,
                      color_discrete_sequence=["#0d9488"])
    fig.update_xaxes(type="category")
    return fig


def fig_category_donut(start_date: str, end_date: str) -> Figure:
    df = category_breakdown_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.pie(df, names="category", values="total", hole=0.45,
                  title="Spending by Category",
                  color_discrete_sequence=["#0d9488", "#3b82f6", "#f59e0b", "#8b5cf6", "#ef4444", "#84cc16", "#f97316"])


def fig_weekly_bar(start_date: str, end_date: str) -> Figure:
    df = weekly_bar_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    fig = px.bar(df, x="week", y="total",
                 labels={"week": "Week", "total": "€ Spent"},
                 title="Weekly Spending",
                 color_discrete_sequence=["#0d9488"])
    fig.update_xaxes(type="category")
    return fig


def fig_top_merchants(start_date: str, end_date: str) -> Figure:
    df = top_merchants_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.bar(df.sort_values("total"), x="total", y="merchant",
                  orientation="h",
                  labels={"total": "€ Spent", "merchant": ""},
                  title="Top Merchants",
                  color_discrete_sequence=["#0d9488"])


def fig_sub_expense_breakdown(start_date: str, end_date: str) -> Figure:
    df = sub_expense_breakdown_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No receipt data yet", showarrow=False)
    return px.bar(df, x="merchant", y="amount", color="category",
                  title="Sub-expense Breakdown by Store",
                  labels={"amount": "€", "merchant": "Store"},
                  color_discrete_sequence=["#0d9488", "#3b82f6", "#f59e0b", "#8b5cf6", "#ef4444", "#84cc16", "#f97316"])


def fig_heatmap(start_date: str, end_date: str) -> Figure:
    df = heatmap_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    df["date_obj"] = pd.to_datetime(df["date"])
    df["weekday"] = df["date_obj"].dt.day_name()
    df["week"] = df["date_obj"].dt.strftime("%G-W%V")
    pivot = df.pivot_table(index="weekday", columns="week", values="total", aggfunc="sum")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex([d for d in day_order if d in pivot.index])
    return px.imshow(pivot, color_continuous_scale="Teal",
                     title="Daily Spending Heatmap",
                     labels={"color": "€ Spent"})
