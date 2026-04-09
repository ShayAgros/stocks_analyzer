#!/usr/bin/env python3

import colorsys
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt

from ticker import Ticker, TickerGroup


class Portfolio(TickerGroup):
    """
    Used to predict future growth and volatility.
    Can show the efficient frontier and this portfolio plotted on it.
    """
    def __init__(self, symbols: list, markets: list, quantities: list, *,
                 risk_free_rate=None, existing_tickers: dict = dict(), use_past_growth=False):
        super().__init__(symbols, markets, risk_free_rate=risk_free_rate,
                         existing_tickers=existing_tickers, use_past_growth=use_past_growth)
        self.current_prices = self.get_stock_prices_now()
        self.quantities = np.array(quantities)
        self.weights = self.quantities * np.array(self.current_prices)
        self.weights = self.weights / np.sum(self.weights)
        self.weights_dict = dict(zip(zip(self.symbols, self.markets), self.weights))
        self.portfolio_annual_growth_forecast = np.nan
        self.portfolio_std = np.nan

    def get_weight(self, symbol: str, market: str):
        return round((self.weights_dict[(symbol, market)] * 100), 2)

    def calculate_correlation(self):
        super().calculate_correlation()
        self.portfolio_annual_growth_forecast = np.dot(self.weights, self.annual_growth_forecasts)
        valid_mask = np.array([f in self.valid_full_symbols for f in self.full_symbols])
        # 1st calculate the portfolio weights discarding all the non valid covariance tickers (Todo its dangerous to say its real)
        weights = self.weights[valid_mask]
        weights = weights / np.sum(weights)
        self.portfolio_std = np.sqrt(weights.T @ self.cov @ weights)

    def plot_pie(self, ax=None):
        if not ax:
            _, ax = plt.subplots()
        ax.pie(self.weights, labels=self.symbols)

    def get_weighted_stats(self):
        """PE = weighted_sum(price) / weighted_sum(eps), ROE = weighted_sum(eps) / weighted_sum(bv)"""
        total_price, total_eps, total_bv = 0.0, 0.0, 0.0
        for (sym, mkt), w in self.weights_dict.items():
            t = self.tickers_dictionary[(sym, mkt)]
            total_eps += w * t.statistics["eps"]
            total_bv += w * t.statistics["book_value"]
            total_price += w * t.statistics["price on update"]
        pe = total_price / total_eps
        roe = (total_eps / total_bv * 100)
        return pe, roe

    def plot_concentric_pie(self, ax=None):
        """Two pies: left=tickers sorted by sector, right=sector+industry concentric."""
        if ax is None:
            _, (ax_tickers, ax_sectors) = plt.subplots(1, 2)
        else:
            ax_tickers, ax_sectors = ax

        data = []
        for sym, mkt, w in zip(self.symbols, self.markets, self.weights):
            t = self.tickers_dictionary.get((sym, mkt))
            sector = (t.statistics.get("sector") or "Unknown") if t else "Unknown"
            industry = (t.statistics.get("industry") or "Unknown") if t else "Unknown"
            data.append((sector, industry, sym, w))

        data.sort(key=lambda x: (x[0], x[1]))
        sectors_sorted    = [d[0] for d in data]
        industries_sorted = [d[1] for d in data]
        symbols_sorted    = [d[2] for d in data]
        weights_sorted    = [d[3] for d in data]

        industry_slices, sector_slices = [], []
        for ind, sec, w in zip(industries_sorted, sectors_sorted, weights_sorted):
            if industry_slices and industry_slices[-1][0] == ind:
                industry_slices[-1] = (ind, industry_slices[-1][1] + w)
            else:
                industry_slices.append((ind, w))
            if sector_slices and sector_slices[-1][0] == sec:
                sector_slices[-1] = (sec, sector_slices[-1][1] + w)
            else:
                sector_slices.append((sec, w))

        cmap = plt.get_cmap("tab10")
        n_sec = len(sector_slices)
        sec_color = {s[0]: cmap(i / max(n_sec, 1)) for i, s in enumerate(sector_slices)}

        ax_tickers.pie(weights_sorted, labels=symbols_sorted,
                       wedgeprops=dict(edgecolor='w'), labeldistance=0.6)
        ax_tickers.set_title("Tickers")

        sec_industry_count = {}
        sec_industry_idx = {}
        for s in industry_slices:
            ind = s[0]
            sec = sectors_sorted[[i for i, x in enumerate(industries_sorted) if x == ind][0]]
            sec_industry_count[sec] = sec_industry_count.get(sec, 0) + 1
        for sec in sec_industry_count:
            sec_industry_idx[sec] = 0

        mid_colors = []
        for s in industry_slices:
            ind = s[0]
            sec = sectors_sorted[[i for i, x in enumerate(industries_sorted) if x == ind][0]]
            base = sec_color[sec][:3]
            total = sec_industry_count[sec]
            idx = sec_industry_idx[sec]
            factor = 0.35 + 0.5 * (idx / max(total - 1, 1))
            h, l, sat = colorsys.rgb_to_hls(*base)
            mid_colors.append(colorsys.hls_to_rgb(h, factor, sat))
            sec_industry_idx[sec] += 1

        ax_sectors.pie([s[1] for s in industry_slices],
                       labels=[s[0] for s in industry_slices],
                       radius=1.0, colors=mid_colors,
                       wedgeprops=dict(width=0.4, edgecolor='w'), labeldistance=0.8)
        ax_sectors.pie([s[1] for s in sector_slices],
                       labels=[s[0] for s in sector_slices],
                       radius=0.6, colors=[sec_color[s[0]] for s in sector_slices],
                       wedgeprops=dict(width=0.6, edgecolor='w'), labeldistance=0.8)
        ax_sectors.set_title("Sector / Industry")

        fig = ax_tickers.get_figure()
        annot = fig.text(0, 0, "", va="bottom", ha="left",
                         bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.8), visible=False)
        all_wedges = [w for ax in (ax_tickers, ax_sectors)
                      for w in ax.patches if hasattr(w, 'get_label')]

        def on_hover(event):
            visible = False
            for wedge in all_wedges:
                if wedge.contains(event)[0]:
                    pct_val = (wedge.theta2 - wedge.theta1) / 360 * 100
                    annot.set_text(f"{wedge.get_label()}: {pct_val:.1f}%")
                    annot.set_position((event.x / fig.get_size_inches()[0] / fig.dpi,
                                        event.y / fig.get_size_inches()[1] / fig.dpi))
                    visible = True
                    break
            annot.set_visible(visible)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect('motion_notify_event', on_hover)
        self._ticker_wedges = list(zip(ax_tickers.patches, symbols_sorted))

    def plot_portfolio(self, ax=None):
        ax = self.plot_frontier(ax=ax)
        ax.plot(self.portfolio_std, self.portfolio_annual_growth_forecast, 'ro')

    def to_df(self) -> pd.DataFrame:
        tickers = []
        for sym, mkt, full_sym in zip(self.symbols, self.markets, self.full_symbols):
            if (sym, mkt) not in self.tickers_dictionary:
                self.tickers_dictionary[(sym, mkt)] = Ticker.get_cache(
                    sym, mkt, yf_ticker=self.yf_ticker.tickers[full_sym])
            tickers.append(self.tickers_dictionary[(sym, mkt)])
        d = {f"{t.symbol}:{t.market}": t.statistics.values() for t in tickers}
        return pd.DataFrame.from_dict(d, orient='index', columns=tickers[0].statistics.keys())


class HistoricPortfolio(Portfolio):
    """A portfolio with buy & sell events for tracking past performance."""
    pass


class PortfolioGui(QWidget):
    """Base portfolio GUI: shows frontier, pie charts, screener button.
    Summary text area is left blank — subclasses fill it via set_summary()."""

    def __init__(self, portfolio: Portfolio, show_frontier=False):
        super().__init__()
        self.setWindowTitle("Portfolio Analyzer")
        self.setGeometry(100, 100, 1400, 700)
        self._portfolio = portfolio
        self._growth_windows = []
        self._screener_window = None

        root = QHBoxLayout(self)

        if show_frontier:
            fig_frontier, ax = plt.subplots()
            portfolio.plot_portfolio(ax=ax)
            growth_mode = "Past Growth" if portfolio.use_past_growth else "DCF Forecast"
            ax.set_ylabel("Expected Return (%s)" % growth_mode)
            ax.grid(True)
            canvas = FigureCanvas(fig_frontier)
            frontier_layout = QVBoxLayout()
            frontier_layout.addWidget(canvas)
            frontier_layout.addWidget(NavigationToolbar(canvas, self))
            root.addLayout(frontier_layout, stretch=3)

        self._stats_layout = QVBoxLayout()
        self._stats_layout.setAlignment(Qt.AlignTop)
        root.addLayout(self._stats_layout, stretch=1)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet("font-size: 14px; padding: 8px;")
        self._stats_layout.addWidget(self._summary_lbl)

        # portfolio stats
        try:
            pe, roe = portfolio.get_weighted_stats()
            stats_text = "PE: {:.1f}  |  ROE: {:.1f}%".format(pe, roe)
        except Exception as e:
            stats_text = "PE/ROE: unavailable ({})".format(e)
        self._stats_lbl = QLabel(stats_text)
        self._stats_lbl.setStyleSheet("font-size: 12px; padding: 4px; color: gray;")
        self._stats_layout.addWidget(self._stats_lbl)

        btn = QPushButton("Open Screener")
        btn.clicked.connect(self._open_screener)
        self._stats_layout.addWidget(btn)

        fig_pie, (ax_t, ax_s) = plt.subplots(1, 2)
        try:
            portfolio.plot_concentric_pie(ax=(ax_t, ax_s))
        except Exception as e:
            ax_t.text(0.5, 0.5, f"Pie unavailable:\n{e}", ha='center', va='center', transform=ax_t.transAxes)
        self._stats_layout.addWidget(FigureCanvas(fig_pie))

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

    def set_summary(self, summary_text, perf_df):
        self._summary_lbl.setText(summary_text)
        tbl = QLabel(perf_df.to_string(float_format=lambda x: "%.1f" % x))
        tbl.setStyleSheet("font-family: monospace; font-size: 12px; padding: 8px;")
        tbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._stats_layout.insertWidget(1, tbl)

    def _open_screener(self):
        from stocks_analyzer import tldr_statistics
        from ticker_gui import tickers_gui
        df = self._portfolio.to_df()
        df = df[[c for c in tldr_statistics if c in df.columns]]
        self._screener_window = tickers_gui(df)
        self._screener_window.show()

class HistoricPortfolio(Portfolio):
    """
    A portfolio who also includs buy & sell events. Allows tracking past performance
    todo: use in portfolio_analyzer.py (instead of direct calculation)
    """
    pass


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    from qt_material import apply_stylesheet
    import sys

    app = QApplication(sys.argv)
    apply_stylesheet(app, theme='dark_red.xml')

    portfolio = Portfolio(["msft", "aapl", "nvda", "googl", "brk.b"], 
                          ["nasdaq", "nasdaq", "nasdaq", "nasdaq", "nyse"], [10, 5, 3, 4, 2])
    portfolio.calculate_correlation()
    gui = PortfolioGui(portfolio, show_frontier=True)
    gui.show()
    sys.exit(app.exec_())
