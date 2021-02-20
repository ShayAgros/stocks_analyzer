#!/usr/bin/env python3

from reports import Reports
from yfinance_info import YahooInfo
import numpy as np
from numpy.polynomial.polynomial import Polynomial
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


class Ticker:

    def __calculate_stats(self):
        statistics = self.statistics
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
        shares_outstanding = last_yearly_income_statement["Diluted Weighted Average Shares"]  # Diluted eps
        statistics["eps"] = earnings / shares_outstanding  # assuming no preferred dividends

        # operating cash-flow per share
        operating_cash_flow = last_yearly_cash_flow["Cash Flow from Operating Activities"]
        statistics["operating_cfps"] = operating_cash_flow / shares_outstanding

        # calculate non-operating(financing and investing) cash-flow per share
        total_cash_flow = last_yearly_cash_flow["Change in Cash"]
        non_operating_cash_flow = total_cash_flow - operating_cash_flow
        statistics["non_operating_cfps"] = operating_cash_flow / shares_outstanding

        # owners earnings
        owners_earnings = operating_cash_flow - last_yearly_cash_flow["Purchase/Sale of Prop,Plant,Equip: Net"]
        statistics["owners_earnings"] = owners_earnings / shares_outstanding

        # book value
        total_equity = last_quarterly_balance_sheet["Total Equity"]
        shares_outstanding = last_quarterly_income_statement["Diluted Weighted Average Shares"]  # Diluted
        statistics["book_value"] = total_equity / shares_outstanding

        # dividends. Negate the "Common Stock Dividends Paid" field since it indicates lost money for the company
        # take the non-diluted number of shares since only real stocks receives dividends
        dividends = (-last_yearly_cash_flow["Common Stock Dividends Paid"]) / last_yearly_balance_sheet["Ordinary Shares Outstanding"]
        statistics["dividends"] = dividends

        # delta_book_value
        yearly_total_equity = all_yearly_balance_sheets[-2]["Total Equity"]
        yearly_shares_outstanding = all_yearly_income_statements[-2]["Diluted Weighted Average Shares"]
        old_bv = yearly_total_equity / yearly_shares_outstanding
        yearly_total_equity = all_yearly_balance_sheets[-1]["Total Equity"]
        yearly_shares_outstanding = all_yearly_income_statements[-1]["Diluted Weighted Average Shares"]
        new_bv = yearly_total_equity / yearly_shares_outstanding
        delta_book_value = new_bv - old_bv

        # actual owners earnings
        statistics["actual_earnings"] = delta_book_value + dividends

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

        # current_ratio
        current_assets = last_quarterly_balance_sheet["Total Current Assets"]
        current_liabilities = last_quarterly_balance_sheet["Total Current Liabilities"]
        statistics["current_ratio"] = current_assets / current_liabilities

        # debt_to_equity
        total_debt = last_quarterly_balance_sheet["Current Debt"] + last_quarterly_balance_sheet["Long Term Debt"]
        statistics["debt_to_equity"] = total_debt / total_equity

        # market cap
        statistics["market_cap"] = stock_price * shares_outstanding  # take the most updated number (quarterly)

        # naive time to profit
        statistics["naive_time_to_profit"] = (stock_price - book_value) / eps

        self._calculate_trends(all_yearly_income_statements,
                               all_yearly_balance_sheets,
                               all_yearly_cash_flows)
        self._calculate_intrinsic_values(all_yearly_income_statements,
                               all_yearly_balance_sheets,
                               all_yearly_cash_flows,
                               shares_outstanding,
                               stock_price)
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

        # earnings growth (exponential)
        earnings_ln = np.log(yearly_earnings)
        poly_fit = Polynomial.fit(range(len(earnings_ln)), earnings_ln, deg=1)
        earnings_ln_fit = poly_fit.convert().coef
        growth_rate = (np.exp(earnings_ln_fit[1]) - 1) * 100
        statistics["growth_rate"] = growth_rate

        # peg ratio
        statistics["peg_ratio"] = statistics["pe_ratio"] / growth_rate

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

    @staticmethod
    def __calculate_free_cash_flow(cashflow_statement):
        # from online search, there are a few different ways of calculating free cash flow
        #   until farther research, I provide the course definition as owners earnings
        return cashflow_statement["Cash Flow from Operating Activities"] - \
               cashflow_statement["Purchase/Sale of Prop,Plant,Equip: Net"]

    def _calculate_intrinsic_values(self, all_yearly_income_statements,
                          all_yearly_balance_sheets, all_yearly_cash_flows, diluted_shares, stock_price):
        statistics = self.statistics
        approximate_bond_10 = 0.95 * 0.01  # updated @ 19.12.2020
        approximate_bond_30 = 1.7 * 0.01  # updated @ 19.12.2020

        discount_rate = 10 * 0.01  # the wished return rate of an investment

        # basic_discount_value - todo: check my formula
        #   current book_value plus the summary of the discounted eps till the end of time
        #   assumes fixed eps and a rather arbitrary bond yield rate
        approximate_bond = approximate_bond_30
        book_value = statistics["book_value"]
        eps = statistics["eps"]
        statistics["basic_discount_value"] = book_value + eps * ((1 + approximate_bond) / approximate_bond)

        # The Discounted Free Cash Flow Model (according to the youtube course):
        #   10 years of data are preffered, we use only 4
        avarage__annual_free_cash_flow = np.mean([Ticker.__calculate_free_cash_flow(report) for report in all_yearly_cash_flows])
        forcasted_short_term_growth_rate = statistics["growth_rate"] / 100  # in the video he used a simple root calculation
        forecasted_number_years_of_growth = 10  # he recommends 10 years or less
        forcasted_long_term_growth_rate = np.min([3 / 100, forcasted_short_term_growth_rate])  # recommends 3% or lower

        # we calculate the q of the geometric series
        short_term_q = forcasted_short_term_growth_rate / (1 + discount_rate)
        long_term_q  = forcasted_long_term_growth_rate  / (1 + discount_rate)

        # sum over the short term
        sum_discounted_fcf_short_term = avarage__annual_free_cash_flow * \
                                               (short_term_q - short_term_q ** (forecasted_number_years_of_growth+1)) /\
                                               (1 - short_term_q)
        # and from its ending to eternity
        sum_discounted_fcf_long_term = (avarage__annual_free_cash_flow * long_term_q
                                        * short_term_q ** forecasted_number_years_of_growth) / \
                                       (1 - long_term_q)

        intrinsic_value_dcf = (sum_discounted_fcf_short_term + sum_discounted_fcf_long_term) / diluted_shares  # + book_value ?
        statistics["intrinsic_value_dcf"] = intrinsic_value_dcf

        # basic_discount_ratio
        discount_value = statistics["basic_discount_value"]
        statistics["basic_discount_ratio"] = discount_value / stock_price


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
                                self.statistics["minimal_operating_cf"] > 0 and \
                                self.statistics["roe[%]"] >= 10

        self.statistics["overvalued"] = self.statistics["pe*bv"] >= 100 or \
                                self.statistics["naive_time_to_profit"] >= 30

    def __init__(self, symbol, market):

        self.symbol = symbol.upper()
        self.market = market.upper()

        self.yahoo_info = YahooInfo(self.symbol, market)

        # This would throw an exception if it fails
        self.reports = Reports(self.symbol, self.market)

        self.statistics = {
            # the order here is the order in the csv
            "name": self.yahoo_info.info["shortName"],

            "eps": None,
            "book_value": None,
            "price_to_book": None,
            "pe_ratio": None,
            "ep_ratio[%]": None,
            "pe*bv": None,
            "roe[%]": None,
            "peg_ratio": None,
            "operating_cfps": None,
            "non_operating_cfps": None,
            "pocf_ratio": None,
            "basic_discount_value": None,
            "basic_discount_ratio": None,
            "intrinsic_value_dcf": None,
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
            "growth_rate": None,
            "dividends": None,
            "owners_earnings": None,
            "actual_earnings": None,

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

    def get_current_pe(self):
        """
        Since the pe ratio in the statistics was calculated for the time of the last yearly report
        this function calculate the pe ratio according to the current price as a quick replacement for the websites
        and not as a screening parameter

        right now we generate multiple versions of this ratio, for experimenting with them
        e.g.:   Ticker('MSFT', 'NASDAQ').get_current_pe()
        """

        # calculate the diluted eps per quarter:
        last_quarterly_income_statement = self.reports.get_last_report("quarterly", "income_statement")
        last_quarterly_balance_sheet = self.reports.get_last_report("quarterly", "balance_sheet")
        shares_outstanding = last_quarterly_income_statement["Diluted Weighted Average Shares"]
        earnings = 4 * last_quarterly_income_statement["Net Income"]
        quarterly_eps = earnings / shares_outstanding

        yearly_eps = self.statistics["eps"]

        # find the prices, now, at the quarter & at the year:

        # Quarter:
        balance_sheet_date = last_quarterly_balance_sheet["Period End Date"]
        quarterly_price = self.yahoo_info.get_stock_price_at_date(**balance_sheet_date)

        # Year:
        last_yearly_balance_sheet = self.reports.get_last_report("annual", "balance_sheet")
        balance_sheet_date = last_yearly_balance_sheet["Period End Date"]
        yearly_price = self.yahoo_info.get_stock_price_at_date(**balance_sheet_date)

        # Now:
        real_price = self.yahoo_info.get_stock_price_now()

        # and finally, the pe ratios:
        yearly_pe_ratio        = real_price / yearly_eps
        quarterly_pe_ratio     = real_price / quarterly_eps
        old_yearly_pe_ratio    = yearly_price / yearly_eps
        old_quarterly_pe_ratio = quarterly_price / quarterly_eps

        print("yearly_pe_ratio:        " + str(yearly_pe_ratio))
        print("quarterly_pe_ratio:     " + str(quarterly_pe_ratio))
        print("")
        print("old_yearly_pe_ratio:    " + str(old_yearly_pe_ratio))
        print("old_quarterly_pe_ratio: " + str(old_quarterly_pe_ratio))
