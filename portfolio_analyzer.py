#!/usr/bin/env python3

from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy, QPushButton)
from PyQt5.QtCore import Qt

from yfinance_info import YahooInfo
from ticker import TickerGroup, search_growth, Portfolio, Ticker
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sys import stdout
import sys

"""
Calculate your average portfolio's growth, and compare it to an index
*   supports indices inside the table (with yahoo's unintuitive names)
*   does not include currency conversion/taxes/etc...
*   file can have blank lines & commented-out ones

Table Format (tab separated):
Ticker	Market	Date	Amount	BuyNotSell	Cost
"""

sep  = "\t"
comment = "#"
frmt = "%Y-%m-%d"  # T%H:%M:%S"
read_tsv = lambda file: pd.read_csv(file, sep=sep, comment=comment, skip_blank_lines=True)


def get_buy_amount(df):
    buy_sign = df["BuyNotSell"] * 2 - 1
    buy_amount = buy_sign * df["Amount"]
    return buy_amount


def create_portfolio(table):
    # remove repetitions:
    symbols = []
    markets = []
    ids = []
    amounts  = []
    for _, row in table.iterrows():
        symbol = row["Ticker"]
        market = row["Market"]
        buy_amount = get_buy_amount(row)
        if (symbol, market) in ids:
            old_index = ids.index((symbol, market))
            amounts[old_index] += buy_amount
        else:
            symbols.append(symbol)
            markets.append(market)
            ids.append((symbol, market))
            amounts.append(buy_amount)
    return Portfolio(symbols, markets, amounts, use_past_growth=True)


def get_get_npv(table):  # will return the lambda function
    # time which had passed for each transaction
    duration = (pd.Timestamp.now().normalize() - pd.to_datetime(table["Date"], format=frmt)) / np.timedelta64(365, "D")
    # current price
    market_value = np.array([YahooInfo(row[1]["Ticker"], row[1]["Market"]).get_stock_price_now() for row in table.iterrows()])
    # buy\sell sign
    buy_amount = get_buy_amount(table)
    # calculate once, use in every get_npv
    portfolio_value = (market_value * buy_amount).sum()
    money_invested = buy_amount * table["Cost"]
    # net_present_value of each transaction including opportunity cost
    get_npv = lambda rate: portfolio_value - (money_invested * ((1 + rate) ** duration)).sum()
    # more stats
    profitable = (portfolio_value - money_invested.sum()) >= 0  # will be used to limit the search range
    return profitable, portfolio_value, money_invested.sum(), get_npv


def get_get_future_npv(table):
    pass  # todo will call all ticker.get_calc_npv()


def get_performance(table, verbose=True):
    # todo check if can be assumed to be monotonic, I think not
    profitable, portfolio_value, money_invested, get_npv = get_get_npv(table)
    if verbose: print("Money invested: %.2f -> %.2f" % (money_invested, portfolio_value))
    return search_growth(
        npv_function=get_npv,
        price=0,
        min_growth=0 if profitable else -1,
        max_growth=4 if profitable else 0,
        delta_growth=0.1 / 100
    )
    

def performance_per_ticker(table, portfolio:Portfolio) -> pd.DataFrame:
    # each ticker need: portfolio_weight, growth
    Histories = {name[0]:group for name, group in table.groupby(["Ticker"])}
    Performance = dict()
    for name, history in Histories.items():
        market = history.iloc[0]["Market"]
#        ticker = portfolio.tickers_dictionary[(name, market)]
        Performance[name] = dict()
        Performance[name]["Annualized Price Growth"] = get_performance(history, verbose=False)
        Performance[name]["Weight[%]"] = portfolio.get_weight(name, market)
#        # more data at a glance:
#        Performance[name]["pe_ratio"]    = ticker.statistics["pe_ratio"]
#        Performance[name]["healthy"]     = ticker.statistics["healthy"]
#        Performance[name]["overvalued"]  = ticker.statistics["overvalued"]
    return pd.DataFrame.from_dict(Performance, orient="index")


def get_index(table):
    """ a similiar table for investing the money in an index instead """
    index_name = "NASDAQ-100"  # informative name
    index_market = "NASDAQ"
    index_yahoo_name = "^IXIC".replace("^", "%5E")

    idx = YahooInfo(index_yahoo_name, index_market)
    table = table.copy()
    dates = pd.to_datetime(table["Date"], format=frmt)
    idx_prices = [idx.get_stock_price_at_date(date.day, date.month, date.year) for date in dates]
    adjusted_amount = table["Amount"] * table["Cost"] / idx_prices
    table["Cost"] = idx_prices
    table["Amount"] = adjusted_amount
    table["Ticker"] = index_yahoo_name
    table["Market"] = index_market
    return index_name, table

# Future estimate:



class PortfolioGui(QWidget):
    def __init__(self, portfolio, perf_df, portfolio_irr, money_invested, portfolio_value,
                 index_name, index_irr, index_value, show_frontier=False):
        super().__init__()
        self.setWindowTitle("Portfolio Analyzer")
        self.setGeometry(100, 100, 1400, 700)

        root = QHBoxLayout(self)

        # --- left: frontier ---
        if show_frontier:
            fig_frontier, ax = plt.subplots()
            portfolio.plot_portfolio(ax=ax)
            growth_mode = "Past Growth" if portfolio.use_past_growth else "DCF Forecast"
            ax.set_ylabel("Expected Return (%s)" % growth_mode)
            ax.grid(True)
            root.addWidget(FigureCanvas(fig_frontier), stretch=3)

        # --- right: stats + pie ---
        stats_layout = QVBoxLayout()
        stats_layout.setAlignment(Qt.AlignTop)
        root.addLayout(stats_layout, stretch=1)

        summary = (
            "Portfolio:  {:.2f} -> {:.2f}\n"
            "            {:.2f}% / yr\n\n"
            "{}:  {:.2f} -> {:.2f}\n"
            "            {:.2f}% / yr"
        ).format(money_invested, portfolio_value, portfolio_irr,
                 index_name, money_invested, index_value, index_irr)
        lbl = QLabel(summary)
        lbl.setStyleSheet("font-size: 14px; padding: 8px;")
        stats_layout.addWidget(lbl)

        table_text = perf_df.to_string(float_format=lambda x: "%.1f" % x)
        tbl = QLabel(table_text)
        tbl.setStyleSheet("font-family: monospace; font-size: 12px; padding: 8px;")
        tbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        stats_layout.addWidget(tbl)

        # --- screener button ---
        self._portfolio = portfolio
        self._screener_window = None
        btn = QPushButton("Open Screener")
        btn.clicked.connect(self._open_screener)
        stats_layout.addWidget(btn)

        fig_pie, (ax_t, ax_s) = plt.subplots(1, 2)
        portfolio.plot_concentric_pie(ax=(ax_t, ax_s))
        canvas_pie = FigureCanvas(fig_pie)
        stats_layout.addWidget(canvas_pie)

        # double-click on ticker wedge opens GrowthApp
        self._growth_windows = []
        def on_pie_dblclick(event):
            if event.dblclick and event.inaxes is ax_t:
                for wedge, symbol in portfolio._ticker_wedges:
                    if wedge.contains(event)[0]:
                        market = dict(zip(portfolio.symbols, portfolio.markets)).get(symbol)
                        if market:
                            from npv_calculator import GrowthApp
                            ticker = portfolio.tickers_dictionary.get((symbol, market)) or \
                                     Ticker.get_cache(symbol, market)
                            win = GrowthApp(ticker=ticker)
                            self._growth_windows.append(win)
                            win.show()
                        break
        fig_pie.canvas.mpl_connect('button_press_event', on_pie_dblclick)


    def _open_screener(self):
        from stocks_analyzer import tldr_statistics
        from ticker_gui import tickers_gui
        df = self._portfolio.to_df()
        df = df[[c for c in tldr_statistics if c in df.columns]]
        self._screener_window = tickers_gui(df)
        self._screener_window.show()


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    from qt_material import apply_stylesheet
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme='dark_red.xml')

    file = "test_inputs/Portfolio1.tsv"
    run_portfolio_optimization = True

    table = read_tsv(file)
    portfolio_irr = get_performance(table)
    _, portfolio_value, money_invested, _ = get_get_npv(table)
    index_name, index_table = get_index(table)
    index_irr = get_performance(index_table)
    _, index_value, _, _ = get_get_npv(index_table)
    portfolio = create_portfolio(table)
    perf_df = performance_per_ticker(table, portfolio)

    if run_portfolio_optimization:
        portfolio.calculate_correlation()

    gui = PortfolioGui(portfolio, perf_df, portfolio_irr, money_invested, portfolio_value,
                       index_name, index_irr, index_value, run_portfolio_optimization)
    gui.show()
    sys.exit(app.exec_())



