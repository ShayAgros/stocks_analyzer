#!/usr/bin/env python3

from reports import Reports
from yfinance_info import YahooInfo
import numpy as np
from numpy.polynomial.polynomial import Polynomial
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# TODO: the yahoo API doesn't allow to specify market easily,
# so currently we just ignore it. Maybe we should switch to some
# more robust service
class Ticker:

    def __calculate_stats(self):
        statistics = self.statistics
        approximate_bond_10 = 0.95 * 0.01  # updated @ 19.12.2020
        approximate_bond_30 = 1.7  * 0.01  # updated @ 19.12.2020
        all_yearly_income_statements = self.reports.get_reports_ascending("annual", "income_statement")
        all_yearly_balance_sheets = self.reports.get_reports_ascending("annual", "balance_sheet")
        all_yearly_cash_flows = self.reports.get_reports_ascending("annual", "cash_flow")
        last_yearly_balance_sheet = all_yearly_balance_sheets[-1]
        last_yearly_income_statement = all_yearly_income_statements[-1]
        last_yearly_cash_flow = all_yearly_cash_flows[-1]

        last_quarterly_balance_sheet = self.reports.get_last_report("quarterly", "balance_sheet")
        last_quarterly_income_statement = self.reports.get_last_report("quarterly", "income_statement")

        yahoo_info = self.yahoo_info

        # calculate eps
        earnings = last_yearly_income_statement["Net Income"]
        shares_outstanding = last_yearly_balance_sheet["Ordinary Shares Outstanding"]
        statistics["eps"] = earnings / shares_outstanding

        # operating cash-flow per share
        operating_cash_flow = last_yearly_cash_flow["Cash Flow from Operating Activities"]
        statistics["operating_cfps"] = operating_cash_flow / shares_outstanding

        # calculate non-operating(financing and investing) cash-flow per share
        total_cash_flow = last_yearly_cash_flow["Change in Cash"]
        non_operating_cash_flow = total_cash_flow - operating_cash_flow
        statistics["non_operating_cfps"] = operating_cash_flow / shares_outstanding

        # book value
        total_equity = last_quarterly_balance_sheet["Total Equity"]
        shares_outstanding = last_quarterly_balance_sheet["Ordinary Shares Outstanding"]
        statistics["book_value"] = total_equity / shares_outstanding

        # price to book
        balance_sheet_date = last_quarterly_balance_sheet["Period End Date"]
        stock_price = yahoo_info.get_stock_price_at_date(**balance_sheet_date)
        book_value  = statistics["book_value"]
        statistics["price_to_book"] = stock_price / book_value

        # pe ratio
        eps = statistics["eps"]
        statistics["pe_ratio"] = stock_price / eps

        # ep ratio
        pe_ratio = statistics["pe_ratio"]
        statistics["ep_ratio[%]"] = 100 / pe_ratio

        # pe * bv
        price_to_book_value = statistics["price_to_book"]
        statistics["pe*bv"] = pe_ratio * price_to_book_value

        # ROE
        return_on_equity = 100 * eps / book_value
        statistics["roe[%]"] = return_on_equity

        # price_to_operating_cf_ratio
        statistics["pocf_ratio"] = stock_price / statistics["operating_cfps"]

        # basic_discount_value - todo: check my formula
        #   current book_value plus the summary of the discounted eps till the end of time
        #   assumes fixed eps and a rather arbitrary bond yield rate
        approximate_bond = approximate_bond_30
        statistics["basic_discount_value"] = book_value + eps*((1+approximate_bond)/approximate_bond)

        # basic_discount_ratio
        discount_value = statistics["basic_discount_value"]
        statistics["basic_discount_ratio"] = discount_value / stock_price

        # current_ratio
        current_assets = last_quarterly_balance_sheet["Total Current Assets"]
        current_liabilities = last_quarterly_balance_sheet["Total Current Liabilities"]
        statistics["current_ratio"] = current_assets / current_liabilities

        # debt_to_equity
        total_debt = last_quarterly_balance_sheet["Current Debt"] + last_quarterly_balance_sheet["Long Term Debt"]
        statistics["debt_to_equity"] = total_debt / total_equity

        # market cap
        statistics["market_cap"] = stock_price * shares_outstanding

        # dividends. Negate the "Common Stock Dividends Paid" field since it indicates lost money for the company
        dividends = (-last_yearly_cash_flow["Common Stock Dividends Paid"]) / shares_outstanding
        statistics["dividends"] = dividends

        # naive time to profit
        statistics["naive_time_to_profit"] = (stock_price - book_value) / eps

        self._calculate_trends(all_yearly_income_statements,
                               all_yearly_balance_sheets,
                               all_yearly_cash_flows)
        self._calculate_quick_filter()
    
    def _calculate_trends(self, all_yearly_income_statements,
                          all_yearly_balance_sheets, all_yearly_cash_flows):
        """ Calculate 1st order trends from the financial reports statements.
        The trends are:
            - Net income trend
            - Equity trend
            - Operating cash flow (earned money by company's oprations)
            - Non operating cash flow (investing + financing activities)
        The function also calculates the min/max of some of these fields

        @all_yearly_income_statements   - the 'Income Statement' reports for all
                                          years
        @all_yearly_balance_sheets      - the 'Balance Sheet' reports for all years
        @all_yearly_cash_flows          - the 'Cash flow' statements for all years
        """

        statistics = self.statistics

        # earnings trend (total, not per-stock)
        yearly_earnings = [statement["Net Income"] for statement in all_yearly_income_statements]
        poly_fit = Polynomial.fit(range(len(yearly_earnings)), yearly_earnings, deg=1)
        earnings_fit = poly_fit.convert().coef
        statistics["earnings_yearly_trend"] = earnings_fit[1]  # keep the slope

        # equity_trend (total, not per-stock)
        yearly_equity = [sheet["Total Equity"] for sheet in all_yearly_balance_sheets]
        poly_fit = Polynomial.fit(range(len(yearly_equity)), yearly_equity, deg=1)
        equity_fit = poly_fit.convert().coef
        statistics["equity_yearly_trend"] = equity_fit[1]  # keep the slope

        # operating cash flow trend
        yearly_operating_cash_flow = np.array([flow["Cash Flow from Operating Activities"] for flow in all_yearly_cash_flows])
        poly_fit = Polynomial.fit(range(len(yearly_operating_cash_flow)), yearly_operating_cash_flow, deg=1)
        operating_cf_fit = poly_fit.convert().coef
        statistics["operating_cf_yearly_trend"] = operating_cf_fit[1]  # keep the slope

        # minimal operating cf
        statistics["minimal_operating_cf"] = np.min(yearly_operating_cash_flow)

        # non operating cash flow trend
        yearly_total_cash_flow = np.array([flow["Change in Cash"] for flow in all_yearly_cash_flows])
        yearly_non_operating_cash_flow = yearly_total_cash_flow - yearly_operating_cash_flow
        poly_fit = Polynomial.fit(range(len(yearly_non_operating_cash_flow)), yearly_non_operating_cash_flow, deg=1)
        non_operating_cf_fit = poly_fit.convert().coef
        statistics["non_operating_cf_yearly_trend"] = non_operating_cf_fit[1]  # keep the slope

        # maximal non operating cf
        statistics["maximal_non_operating_cf"] = np.max(yearly_non_operating_cash_flow)

    def _calculate_quick_filter(self):
        """ The function checks several conditions which determine if its a
        ticker we're might be interested in. The conditions are split into two
        categories:
            - former: general health parameters which are more restrictive and
              are enough to remove the ticker from buying considerations
            - latter: parameters which might be changed later but might be an
              indication for overvalued companies"""

        self.statistics["healthy"] = self.statistics["eps"] > 0 and \
                                self.statistics["book_value"] > 0 and \
                                self.statistics["debt_to_equity"] < 3.2 and \
                                self.statistics["earnings_yearly_trend"] > 0 and \
                                self.statistics["equity_yearly_trend"] > 0 and \
                                self.statistics["operating_cf_yearly_trend"] > 0 and \
                                self.statistics["non_operating_cf_yearly_trend"] < 0 and \
                                self.statistics["maximal_non_operating_cf"] < 0 and \
                                self.statistics["minimal_operating_cf"] > 0

        self.statistics["overvalued"] = self.statistics["pe*bv"] >= 100 or \
                                self.statistics["naive_time_to_profit"] >= 30

    def __init__(self, symbol, market):

        self.symbol = symbol.upper()
        self.market = market.upper()

        self.yahoo_info = YahooInfo(self.symbol)

        # This would throw an exception if it fails
        self.reports = Reports(self.symbol, self.market)

        self.statistics = {
            # calculated attributes (the order here is the order in the csv)
            "eps": None,
            "book_value": None,
            "price_to_book": None,
            "pe_ratio": None,
            "ep_ratio[%]": None,
            "pe*bv": None,
            "roe[%]": None,
            "operating_cfps": None,
            "non_operating_cfps": None,
            "pocf_ratio": None,
            "basic_discount_value": None,
            "basic_discount_ratio": None,
            "current_ratio": None,
            "debt_to_equity": None,
            "market_cap": None,
            "naive_time_to_profit": None,  # in years
            "minimal_operating_cf": None,
            "maximal_non_operating_cf": None,
            "earnings_yearly_trend": None,
            "equity_yearly_trend": None,
            "operating_cf_yearly_trend": None,
            "non_operating_cf_yearly_trend": None,
            "dividends": None,

            # fetched attributes
            "net_income": self.reports.get_last_report("annual", "income_statement")["Net Income"],
            "healthy": None,
            "overvalued": None,
            "sector": self.yahoo_info.info["sector"],
            "industry": self.yahoo_info.info["industry"],
            }

        self.__calculate_stats()

        last_quarterly_balance_sheet = self.reports.get_last_report("quarterly", "balance_sheet")
        balance_sheet_date = last_quarterly_balance_sheet["Period End Date"]
        stock_price = self.yahoo_info.get_stock_price_at_date(**balance_sheet_date)

    def get_price_graph(self, term):
        dates = self.reports.get_reports_dates(term)
        start_date = dates[0]
        end_date   = dates[-1]
        date_vector, price_vector = self.yahoo_info.get_stock_price_in_range(start_date, end_date)
        return date_vector, price_vector

    def plot_me(self):
        # todo: change to bv & eps as a better representation of the stock value
        plot_fields = (("income_statement", "Net Income"), ("balance_sheet", "Total Equity"))
        plot_terms = ("annual", "quarterly")

        fig = plt.figure()
        fig.set_tight_layout(True)
        plt.title(self.symbol)
        plt.box(on=None)
        axs = fig.subplots(len(plot_fields)+1, len(plot_terms))

        for col, term in enumerate(plot_terms):
            for row, field in enumerate([None, *plot_fields]):
                ax = axs[row, col]
                if row == 0:
                    # price graph:
                    # since this is the first graph, show the term in the title
                    ax.set_title(term)
                    times, values = self.get_price_graph(term)
                else:
                    # statistics graph:
                    ax.set_title(field[1])
                    plot_reports = self.reports.get_reports_ascending(term, field[0])
                    values = [report[field[1]] for report in plot_reports]
                    times = self.reports.get_reports_dates(term)

                locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
                formatter = mdates.ConciseDateFormatter(locator)
                ax.xaxis.set_major_locator(locator)
                ax.xaxis.set_major_formatter(formatter)
                ax.plot_date(times, values, '-')
        plt.show()
