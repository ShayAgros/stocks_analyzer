#!/usr/bin/env python3
import warnings
from copy import deepcopy

from pypfopt import EfficientFrontier, plotting

from reports import Reports
from yahoo_reports import YReports
from yfinance_info import YahooInfo, YahooGroup, yahoo_symbol_is_index
import numpy as np
import pandas as pd
from numpy.polynomial.polynomial import Polynomial
import pickle
from pprint import pformat
import datetime
import os.path
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.widgets
import sys

# Define:
tickers_dir = "./tickers_cache"
cache_file_name = "{symbol}-{market}.pkl"

forcast_growth_field = "irr[%]"  # todo, make it dynamic


class MarketDataCache:
    """Caches risk-free rate (^TNX) and S&P500 1yr return with a 1-hour TTL."""
    _TTL = 3600

    def __init__(self):
        self._cache = {"rfr": (None, 0), "mkt": (None, 0)}

    def _get(self, key, fetch_fn):
        import time
        value, ts = self._cache[key]
        if value is None or time.time() - ts > self._TTL:
            value = fetch_fn()
            self._cache[key] = (value, time.time())
        return value

    def get_risk_free_rate(self) -> float:
        return self._get("rfr", lambda: YahooInfo("%5ETNX", "NASDAQ").get_stock_price_now() / 100)

    def get_market_return(self) -> float:
        import datetime
        def fetch():
            spx = YahooInfo("%5EGSPC", "NASDAQ")
            d = datetime.date.today() - datetime.timedelta(days=365)
            old = spx.get_stock_price_at_date(d.day, d.month, d.year)
            return (spx.get_stock_price_now() - old) / old
        return self._get("mkt", fetch)


market_data = MarketDataCache()


class StatisticsException(Exception):
    """Exceptions that are thrown during the Ticker statistics calculation.
        This will happen mostly due to a bug"""
    pass


def get_exception_line():
    """use inside except"""
    frame = sys.exc_info()[2]
    while frame.tb_next:
        frame = frame.tb_next
    return frame.tb_lineno


def search_growth(npv_function, price, min_growth, max_growth=1, delta_growth=0.1/100):
    """
    find the iir/growth from the discounted value
    :param npv_function: function which receive the guessed growth and return  the npv (assume monothonic one)
    :param price:
    :param min_groth:
    :param min_growth:
    :param max_growth:
    :param delta_growth:
    :return:
    """
    # calculate the intrinsic rate of return (by dcf model):
    # iteration parameters
    best_result = None
    best_growth = np.nan
    #plt.figure()
    skipped = 0
    for growth in range(0, int(1 + (max_growth-min_growth) / delta_growth)):  # todo: move to binary search
        growth = delta_growth * growth + min_growth
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.filterwarnings("error")
                npv = npv_function(growth)
        except Exception:
            npv = np.nan
        if npv is None or np.isnan(npv):
            skipped += 1
            continue
        error = np.abs(npv - price)
        #plt.scatter([growth], [npv - price])
        if (best_result is None) or error < best_result:
            best_result = error
            best_growth = growth

    irr = best_growth * 100
    if skipped > 0:
        print("error in npv calculation (%s)" % skipped)
    #plt.show()
    return irr


class Ticker:

    def __calculate_stats(self):
        statistics = self.statistics
        use_ttm = self.reports.has_full_ttm()
        if not use_ttm:
            self.warnings.append("incomplete TTM")
        all_yearly_income_statements = self.reports.get_reports_ascending("annual", "income_statement", use_ttm)
        all_yearly_balance_sheets = self.reports.get_reports_ascending("annual", "balance_sheet", use_ttm)
        all_yearly_cash_flows = self.reports.get_reports_ascending("annual", "cash_flow", use_ttm)
        last_yearly_balance_sheet = all_yearly_balance_sheets[-1]
        last_yearly_income_statement = all_yearly_income_statements[-1]
        last_yearly_cash_flow = all_yearly_cash_flows[-1]
        statistics["TTM"] = use_ttm

        # for the tickers with an incomplete ttm, we will still take the most updated values from the quarterly reports
        last_quarterly_balance_sheet = self.reports.get_last_report("quarterly", "balance_sheet")
        last_quarterly_income_statement = self.reports.get_last_report("quarterly", "income_statement")

        annual_dates = self.reports.get_reports_dates("annual", use_ttm)
        statistics["updated at"] = annual_dates[-1]

        yahoo_info = self.yahoo_info

        statistics["price on update"] = self.yahoo_info.get_stock_price_at_date(annual_dates[-1].day,
                                                                                annual_dates[-1].month,
                                                                                annual_dates[-1].year)

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

        # owners earnings  - aka free cash flow
        owners_earnings = operating_cash_flow - last_yearly_cash_flow["Purchase/Sale of Prop,Plant,Equip: Net"]
        statistics["owners_earnings"] = owners_earnings / shares_outstanding

        # book value
        total_equity = last_quarterly_balance_sheet["Total Equity"]
        shares_outstanding = last_quarterly_income_statement["Diluted Weighted Average Shares"]  # Diluted
        statistics["book_value"] = total_equity / shares_outstanding
        statistics["shares (diluted)"] = shares_outstanding

        # dividends. Negate the "Common Stock Dividends Paid" field since it indicates lost money for the company
        # take the non-diluted number of shares since only real stocks receives dividends
        dividends = (-last_yearly_cash_flow["Common Stock Dividends Paid"]) / last_yearly_balance_sheet[
            "Ordinary Shares Outstanding"]
        statistics["dividends"] = dividends
        if np.isnan(dividends): dividends = 0

        # delta_book_value
        indicies = (-3, -2) if use_ttm else (-2, -1)  # we ignore the ttm
        yearly_total_equity = all_yearly_balance_sheets[indicies[0]]["Total Equity"]
        yearly_shares_outstanding = all_yearly_income_statements[indicies[0]]["Diluted Weighted Average Shares"]
        old_bv = yearly_total_equity / yearly_shares_outstanding
        yearly_total_equity = all_yearly_balance_sheets[indicies[1]]["Total Equity"]
        yearly_shares_outstanding = all_yearly_income_statements[indicies[1]]["Diluted Weighted Average Shares"]
        new_bv = yearly_total_equity / yearly_shares_outstanding
        delta_book_value = (new_bv - old_bv) / ((annual_dates[indicies[1]] - annual_dates[indicies[0]]).days / 365.25)

        # actual owners earnings
        statistics["actual_earnings"] = delta_book_value + dividends

        # price to book
        balance_sheet_date = last_quarterly_balance_sheet["Period End Date"]
        stock_price = yahoo_info.get_stock_price_at_date(**balance_sheet_date)
        book_value = statistics["book_value"]
        statistics["price_to_book"] = stock_price / book_value

        # pe ratio
        # NOTE: uses the last quarter price, but if without ttm, earnings of last year, true for all of our ratios
        eps = statistics["eps"]
        statistics["pe_ratio"] = stock_price / eps

        # ep ratio
        pe_ratio = statistics["pe_ratio"]
        statistics["ep_ratio[%]"] = 100 / pe_ratio

        # pe * bv
        price_to_book_value = statistics["price_to_book"]
        statistics["pe*bv"] = max(pe_ratio, 0) * price_to_book_value

        # ROE
        return_on_equity = 100 * eps / book_value
        statistics["roe[%]"] = return_on_equity

        # ROA
        return_on_assets = 100 * earnings / last_quarterly_balance_sheet["Total Assets"]
        statistics["roa[%]"] = return_on_assets

        # price_to_operating_cf_ratio
        statistics["pocf_ratio"] = stock_price / statistics["operating_cfps"]

        # current_ratio
        current_assets = last_quarterly_balance_sheet["Total Current Assets"]
        current_liabilities = last_quarterly_balance_sheet["Total Current Liabilities"]
        statistics["current_ratio"] = current_assets / current_liabilities  # todo check if need to use current debt or current liabilties

        # debt_to_equity
        total_debt = last_quarterly_balance_sheet["Current Debt"] + last_quarterly_balance_sheet["Long Term Debt"]
        statistics["debt_to_equity"] = total_debt / total_equity

        # market cap
        statistics["market_cap"] = stock_price * shares_outstanding  # take the most updated number (quarterly)

        # naive time to profit
        statistics["naive_time_to_profit"] = (stock_price - book_value) / eps if eps > 0 else np.nan

        self._calculate_trends(all_yearly_income_statements,
                               all_yearly_balance_sheets,
                               all_yearly_cash_flows,
                               annual_dates)
        self._calculate_intrinsic_values(shares_outstanding,
                                         stock_price,
                                         annual_dates[-1])
        self._calculate_quick_filter()
        self._round()

    def _calculate_trends(self, all_yearly_income_statements,
                          all_yearly_balance_sheets, all_yearly_cash_flows, annual_dates):
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
        years = Ticker.__calculate_year_diff(annual_dates)

        # earnings trend (slope) (total, not per-stock)
        yearly_earnings = [statement["Net Income"] for statement in all_yearly_income_statements]
        poly_fit = Polynomial.fit(years, yearly_earnings, deg=1)
        earnings_fit = poly_fit.coef  # TODO: --- check what changed when I removed the .convert() ---
        statistics["earnings_yearly_trend"] = earnings_fit[1]  # keep the slope

        # earnings growth (exponential)
        try:
            earnings_ln = np.log(yearly_earnings)
            poly_fit = Polynomial.fit(years, earnings_ln, deg=1)
            earnings_ln_fit = poly_fit.coef
            growth_rate = (np.exp(earnings_ln_fit[1]) - 1) * 100
            statistics["growth_rate"] = growth_rate
            # peg ratio
            statistics["peg_ratio"] = statistics["pe_ratio"] / growth_rate
        except RuntimeWarning as warn:
            if yearly_earnings[0] > 0 and yearly_earnings[-1] > 0:
                self.warnings.append("Failed to calculate log growth_rate. Growth rate fallback calculation")
                growth_rate = (yearly_earnings[-1] / yearly_earnings[0]) ** (1 / years[-1])
                growth_rate = (growth_rate - 1) * 100
                statistics["growth_rate"] = growth_rate
                statistics["peg_ratio"] = statistics["pe_ratio"] / growth_rate
            else:
                self.warnings.append("Failed to calculate log growth_rate. Warning: {}".format(warn))
                statistics["growth_rate"] = float('NaN')
                statistics["peg_ratio"] = float('NaN')

        # revenues trend (total, not per-stock)
        yearly_revenues = [statement["Total Revenue"] for statement in all_yearly_income_statements]
        poly_fit = Polynomial.fit(years, yearly_revenues, deg=1)
        revenues_fit = poly_fit.coef
        statistics["revenues_yearly_trend"] = revenues_fit[1]  # keep the slope

        # revenue growth
        try:
            revenues_ln = np.log(yearly_revenues)
            poly_fit = Polynomial.fit(years, revenues_ln, deg=1)
            revenues_ln_fit = poly_fit.convert().coef
            revenue_growth_rate = (np.exp(revenues_ln_fit[1]) - 1) * 100
            statistics["revenue_growth_rate"] = revenue_growth_rate
            # peg ratio
            statistics["peg_ratio"] = statistics["pe_ratio"] / revenue_growth_rate
        except RuntimeWarning as warn:
            if yearly_revenues[0] > 0 and yearly_revenues[-1] > 0:
                self.warnings.append("Failed to calculate log revenue_growth_rate. Growth rate fallback calculation")
                revenue_growth_rate = (yearly_revenues[-1] / yearly_revenues[0]) ** (1 / years[-1])
                revenue_growth_rate = (revenue_growth_rate - 1) * 100
                statistics["revenue_growth_rate"] = revenue_growth_rate
            else:
                self.warnings.append("Failed to calculate log revenue_growth_rate. Warning: {}".format(warn))
                statistics["revenue_growth_rate"] = float('NaN')

        # equity_trend (total, not per-stock)
        yearly_equity = [sheet["Total Equity"] for sheet in all_yearly_balance_sheets]
        poly_fit = Polynomial.fit(years, yearly_equity, deg=1)
        equity_fit = poly_fit.convert().coef
        statistics["equity_yearly_trend"] = equity_fit[1]  # keep the slope

        # bv growth rate
        shares = [statement["Diluted Weighted Average Shares"] for statement in all_yearly_income_statements]
        yearly_bv = np.divide(yearly_equity, shares)
        try:
            equity_ln = np.log(yearly_bv)  # might throw
            poly_fit = Polynomial.fit(years, equity_ln, deg=1)
            equity_ln_fit = poly_fit.convert().coef
            bv_growth_rate = (np.exp(equity_ln_fit[1]) - 1) * 100
            statistics["bv_growth_rate"] = bv_growth_rate
        except RuntimeWarning as warn:
            if yearly_bv[0] > 0 and yearly_bv[-1] > 0:
                self.warnings.append("Failed to calculate log bv_growth_rate. Growth rate fallback calculation")
                bv_growth_rate = (yearly_bv[-1] / yearly_bv[0]) ** (1 / years[-1])
                bv_growth_rate = (bv_growth_rate - 1) * 100
                statistics["bv_growth_rate"] = bv_growth_rate
            else:
                self.warnings.append("Failed to calculate log bv_growth_rate. Warning: {}".format(warn))
                statistics["bv_growth_rate"] = float('NaN')

        # operating cash flow trend
        yearly_operating_cash_flow = np.array(
            [flow["Cash Flow from Operating Activities"] for flow in all_yearly_cash_flows])
        poly_fit = Polynomial.fit(years, yearly_operating_cash_flow, deg=1)
        operating_cf_fit = poly_fit.convert().coef
        statistics["operating_cf_yearly_trend"] = operating_cf_fit[1]  # keep the slope

        # minimal operating cf
        statistics["minimal_operating_cf"] = np.min(yearly_operating_cash_flow)

        # non operating cash flow trend
        yearly_total_cash_flow = np.array([flow["Change in Cash"] for flow in all_yearly_cash_flows])
        yearly_non_operating_cash_flow = yearly_total_cash_flow - yearly_operating_cash_flow
        poly_fit = Polynomial.fit(years, yearly_non_operating_cash_flow, deg=1)
        non_operating_cf_fit = poly_fit.convert().coef
        statistics["non_operating_cf_yearly_trend"] = non_operating_cf_fit[1]  # keep the slope

        # maximal non operating cf
        statistics["maximal_non_operating_cf"] = np.max(yearly_non_operating_cash_flow)

    @staticmethod
    def __calculate_free_cash_flow(cashflow_statement):
        # from online search, there are a few different ways of calculating free cash flow
        #   until farther research, I provide the course definition as owners earnings
        return cashflow_statement["Cash Flow from Operating Activities"] + \
               cashflow_statement["Purchase/Sale of Prop,Plant,Equip: Net"]

    @staticmethod
    def __calculate_time_forward(last_annual_date):
        now = datetime.datetime.now()
        return (now - last_annual_date).days / 365.25

    @staticmethod
    def __calculate_year_diff(annual_dates):
        first_date = annual_dates[0]
        return [(date - first_date).days / 365.25 for date in annual_dates]

    def get_irr(self):
        """ a wrapper of _calc_dcf_intrinsic_values for the gui part (with current price) """
        _, irr = self._calc_dcf_intrinsic_values(forward_to_present=True)
        _, linear_irr = self._calc_dcf_intrinsic_values(
            growth_rate=self.statistics["growth_rate"],
            forward_to_present=True,
            short_term_is_linear=True,
            long_growth_duration=0,
            forecasted_number_years_of_growth=10
        )
        return irr, linear_irr

    def _calculate_intrinsic_values(self, diluted_shares, stock_price, last_annual_date):
        statistics = self.statistics

        # for reference:
        # approximate_bond_10 = 0.95 * 0.01  # updated @ 19.12.2020
        # approximate_bond_30 = 1.7 * 0.01  # updated @ 19.12.2020
        discount_rate = 10 * 0.01  # the wished return rate of an investment (used only for the basic calculations)

        # --- basic_discount_value - todo: check my formula
        #
        #   current book_value plus the summary of the discounted eps till the end of time
        #   assumes fixed eps and a pre-selected discount ratio
        book_value = statistics["book_value"]
        eps = statistics["eps"]
        statistics["basic_discount_value"] = book_value + eps * ((1 + discount_rate) / discount_rate)

        # basic_discount_ratio todo: polish details so can be used in the graphical part
        discount_value = statistics["basic_discount_value"]
        statistics["basic_discount_ratio"] = 100 * (discount_value - stock_price) / stock_price

        # --- dcf model ---
        statistics["intrinsic_value_dcf"], statistics["irr[%]"] = self._calc_dcf_intrinsic_values()
        statistics["dcf_discount_ratio"] = 100 * (statistics["intrinsic_value_dcf"] - stock_price) / stock_price

        # --- capm ---
        beta = statistics.get("beta")
        if beta is not None and not np.isnan(beta):
            rfr = market_data.get_risk_free_rate()
            mkt = market_data.get_market_return()
            capm_rate = rfr + beta * (mkt - rfr)
            statistics["capm_interest"] = capm_rate * 100
            statistics["capm_npv"] = self._get_calc_npv()(capm_rate)
            statistics["capm_discount_ratio"] = 100 * (statistics["capm_npv"] - stock_price) / stock_price

    def _get_calc_npv(self,
                   growth_rate=None,
                   add_bv=True,
                   forward_to_present=False,
                   short_term_is_linear=False,
                   long_growth_duration=-1,
                   forecasted_number_years_of_growth=8,
                   maximal_long_term_growth_rate=3/100,
                   ):
        #
        # --- The Discounted Free Cash Flow Model (according to the youtube course): ---
        #
        #   10 years of data are preffered, we use only 4

        use_ttm = self.reports.has_full_ttm()
        all_yearly_cash_flows = self.reports.get_reports_ascending("annual", "cash_flow", use_ttm)
        statistics = self.statistics
        book_value = statistics["book_value"]
        last_annual_date = statistics["updated at"]
        diluted_shares = statistics["shares (diluted)"]

        if growth_rate is not None:
            forcasted_short_term_growth_rate = growth_rate / 100
        else:
            forcasted_short_term_growth_rate = statistics["growth_rate"] / 100
        forcasted_long_term_growth_rate = np.min([maximal_long_term_growth_rate, forcasted_short_term_growth_rate])
        # estimation for the first next cashflow (multiply in the growth rate once)
        average_annual_free_cash_flow = np.mean(
            [Ticker.__calculate_free_cash_flow(report) for report in all_yearly_cash_flows])
        if short_term_is_linear:
            # only use earnings, for equity growth, we need to think on a different model (quadratic) todo
            # no ttm in the average
            average_earnings = np.average(self.reports.get_field_as_list("income_statement", "annual", "Net Income"))
            linear_growth = statistics["earnings_yearly_trend"] * average_annual_free_cash_flow / average_earnings
            forcasted_long_term_growth_rate = maximal_long_term_growth_rate  # keep it independent of the log-regression

        def calc_npv(discount_rate):
            assert discount_rate > -100E-2, "discontinuity at -1"
            # we calculate the q of the geometric series
            short_term_q = (1 + forcasted_short_term_growth_rate) / (1 + discount_rate)
            long_term_q = (1 + forcasted_long_term_growth_rate) / (1 + discount_rate)

            # sum over the short term
            if not short_term_is_linear:
                first_short_term = average_annual_free_cash_flow * short_term_q
                last_short_term = average_annual_free_cash_flow * (short_term_q ** forecasted_number_years_of_growth)
                if short_term_q == 1:  # discontinuity point
                    sum_discounted_fcf_short_term = first_short_term * forecasted_number_years_of_growth
                else:
                    sum_discounted_fcf_short_term = (first_short_term - last_short_term * short_term_q) / (1 - short_term_q)
            else:
                # there is no easy formula for *discounted* constant addition, we will calculate explicitly
                terms = np.arange(1, forecasted_number_years_of_growth + 1)
                fcf = average_annual_free_cash_flow + linear_growth * terms
                dfcf = fcf / (1 + discount_rate) ** terms
                sum_discounted_fcf_short_term = np.sum(dfcf)
                last_short_term = dfcf[-1]

            # and from its ending to eternity
            first_long_term = last_short_term * long_term_q
            if long_growth_duration < 0:
                if long_term_q >= 1:  # edge cases
                    sum_discounted_fcf_long_term = np.sign(first_long_term)*np.inf
                elif long_term_q <= -1:
                    sum_discounted_fcf_long_term = np.nan
                else:
                    sum_discounted_fcf_long_term = first_long_term / (discount_rate - forcasted_long_term_growth_rate)
            else:  # (a1-an*q)/(1-q)
                last_long_term_times_q = last_short_term * long_term_q ** (long_growth_duration + 1)
                if long_term_q == 1:  # discontinuity point
                    sum_discounted_fcf_long_term = first_long_term * long_growth_duration
                else:
                    sum_discounted_fcf_long_term = (first_long_term - last_long_term_times_q) / (1 - long_term_q)

            intrinsic_value_dcf = (sum_discounted_fcf_short_term + sum_discounted_fcf_long_term) / diluted_shares
            if add_bv:
                intrinsic_value_dcf += book_value
            if forward_to_present:
                years = Ticker.__calculate_time_forward(last_annual_date)
                intrinsic_value_dcf *= (discount_rate + 1) ** years
            return intrinsic_value_dcf

        return calc_npv

    def _calc_dcf_intrinsic_values(self,
                                   discount_rate=10/100,
                                   forward_to_present=False,
                                   **kwargs
                                   ):

        old_stock_price = self.statistics["price on update"]
        if forward_to_present:
            stock_price = self.yahoo_info.get_stock_price_now()
        else:
            stock_price = old_stock_price
        calc_npv = self._get_calc_npv(**kwargs)  # a lambda to calculate the npv given a wanted growth
        intrinsic_value = calc_npv(discount_rate)
        # calculate the intrinsic rate of return (by dcf model):
        if intrinsic_value > 0 and self.statistics["eps"] > 0:   # negative values will prefer high discount (unintuitivly)
            delta = 0.1/100
            #start_at = max(forcasted_long_term_growth_rate + delta, 0) if long_growth_duration < 0 else 0  # todo: add negative if not infinite
            start_at = -0.9
            if np.isnan(start_at):
                start_at=0
            irr = search_growth(calc_npv, stock_price, start_at, 1, delta)
        else:
            irr = np.nan

        return intrinsic_value, irr

    def _calculate_quick_filter(self):
        """ The function checks several conditions which determine if its a
        ticker we're might be interested in. The conditions are split into two
        categories:
            - former: general health parameters which are more restrictive and
              are enough to remove the ticker from buying considerations
            - latter: parameters which might be changed later but might be an
              indication for overvalued companies"""

        self.statistics["healthy"] = (self.statistics["eps"] > 0 and
                                      self.statistics["book_value"] > 0 and
                                      self.statistics["earnings_yearly_trend"] > 0 and
                                      self.statistics["equity_yearly_trend"] > 0 and
                                      self.statistics["operating_cf_yearly_trend"] > 0 and
                                      self.statistics["revenues_yearly_trend"] > 0 and
                                      self.statistics["minimal_operating_cf"] > 0 and
                                      self.statistics["roe[%]"] >= 10 and
                                      self.statistics["roa[%]"] >= 3 and
                                      self.statistics["growth_rate"] >= 2.5 and
                                      self.statistics["bv_growth_rate"] >= 2.5 and
                                      self.statistics["revenue_growth_rate"] >= 1.7
                                      )

        self.statistics["leveraged"] = (self.statistics["debt_to_equity"] > 3.2 or
                                        self.statistics["non_operating_cf_yearly_trend"] > 0 or
                                        self.statistics["maximal_non_operating_cf"] > 0  # too restrictive
                                        )

        self.statistics["overvalued"] = (self.statistics["pe*bv"] >= 100 or
                                         self.statistics["naive_time_to_profit"] >= 20 or
                                         self.statistics["irr[%]"] < 10 or
                                         self.statistics["basic_discount_ratio"] < -1
                                         )
        # TODO: add a current ratio metric for credit obligations?


    @staticmethod
    def get_cache(symbol, market, yf_ticker=None):
        symbol = symbol.upper()
        market = market.upper()
        symbol_file_name = cache_file_name.format(symbol=symbol, market=market)
        cache_file = os.path.join(tickers_dir, symbol_file_name)

        def get_seconds_from_now(filename):
            sec_from_epoch = os.path.getmtime(filename)
            return datetime.datetime.now().timestamp() - sec_from_epoch

        # if old, ignore cache
        if not os.path.isfile(cache_file) or get_seconds_from_now(cache_file) > 3600 * 24 * 30:  # 30 days
            return Ticker(symbol, market, yf_info=yf_ticker)
        try:
            with open(cache_file, 'rb') as file:
                return pickle.load(file).post_pickle(yf_ticker=yf_ticker)
        except FileNotFoundError:
            return Ticker(symbol, market, yf_info=yf_ticker)


    def pre_pickle(self):
        self.reports.pre_pickle()
        self.yahoo_info.pre_pickle()

    def post_pickle(self, yf_ticker=None):
        self.yahoo_info.post_pickle(yf_ticker)
        self.reports.post_pickle(self.yahoo_info.yf_ticker)
        return self

    def save_cache(self):
        try:
            symbol_file_name = cache_file_name.format(symbol=self.symbol, market=self.market)
            cache_file = os.path.join(tickers_dir, symbol_file_name)
            os.makedirs(tickers_dir, exist_ok=True)
            with open(cache_file, 'wb') as file:
                yf_ticker = self.yahoo_info.yf_ticker
                self.pre_pickle()
                pickle.dump(self, file)
                self.post_pickle(yf_ticker)
                
            
        except TypeError:
            print("Ticker.py: warnning: failed to save cache, probably yf_ticker object")

    def __str__(self):
        result = "Ticker of %s:%s\n{\n" % (self.symbol, self.market)
        result += "Statistics:\n%s,\n" % pformat(self.statistics)


    def __init__(self, symbol, market, *, yf_info = None):

        self.symbol = symbol.upper()
        self.market = market.upper()

        self.yahoo_info = YahooInfo(self.symbol, self.market, yf_info = yf_info)

        # This would throw an exception if it fails
        self.reports = YReports(symbol, market, self.yahoo_info.yf_ticker)
        #self.reports = Reports(self.symbol, self.market)

        self.statistics = {
            # the order here is the order in the csv
            "name": self.yahoo_info.info.get("shortName"),

            "price_to_book": None,
            "pe_ratio": None,
            "ep_ratio[%]": None,
            "pe*bv": None,
            "roe[%]": None,
            "roa[%]": None,
            "peg_ratio": None,
            "operating_cfps": None,
            "non_operating_cfps": None,
            "pocf_ratio": None,
            "basic_discount_value": None,
            "basic_discount_ratio": None,
            "intrinsic_value_dcf": None,
            "dcf_discount_ratio": None,
            "irr[%]": None,
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
            "revenues_yearly_trend": None,
            "growth_rate": None,
            "bv_growth_rate": None,
            "revenue_growth_rate": None,
            "dividends": None,
            "owners_earnings": None,
            "actual_earnings": None,
            "shares (diluted)": None,

            "net_income": self.reports.get_last_report("annual", "income_statement")["Net Income"],
            "healthy": None,
            "overvalued": None,
            "leveraged": None,
            "sector": self.yahoo_info.info.get("sector"),
            "industry": self.yahoo_info.info.get("industry"),
            "beta": self.yahoo_info.info.get("beta"),
            "capm_interest": None,
            "capm_npv": None,
            "capm_discount_ratio": None,
            "price on update": None,
            "eps": None,
            "book_value": None,
            "updated at": None,
            "TTM": None
        }

        # allow __calculate_stats to log warning in this file
        self.warnings = list()
        try:
            self.__calculate_stats()
        except Exception as err:
            line = get_exception_line()
            raise StatisticsException(str(err) + " in line: " + str(line))

        self.save_cache()

    def get_forecasted_annual_growth(self):
        return self.statistics[forcast_growth_field]/100  # assume field is annual and in percents

    # Plotting:

    def get_price_graph(self, term, add_ttm=False):
        dates = self.reports.get_reports_dates(term, add_ttm)
        start_date = dates[0]
        end_date = dates[-1]
        date_vector, price_vector = self.yahoo_info.get_stock_price_in_range(start_date, end_date, interval="1d")
        return date_vector, price_vector

    def get_price_graph_after_report(self, term, add_ttm=False):
        dates = self.reports.get_reports_dates(term, add_ttm)
        start_date = dates[-1]
        end_date = datetime.datetime.now()
        date_vector, price_vector = self.yahoo_info.get_stock_price_in_range(start_date, end_date, interval="1d")
        return date_vector, price_vector

    def get_price_at_report_dates(self, term, add_ttm=False):
        reports_ordered = self.reports.get_reports_ascending(term, 'balance_sheet', add_ttm)
        dates = [report["Period End Date"] for report in reports_ordered]
        prices = [self.yahoo_info.get_stock_price_at_date(date["day"], date["month"], date["year"]) for date in dates]
        return prices

    def plot_me(self, show=True):
        fig = plt.figure()
        gs = fig.add_gridspec(4, 2)

        # 00 - Book Value
        ax = fig.add_subplot(gs[0, 0])
        label = "book value"
        equity = np.array(self.reports.get_field_as_list("balance_sheet", "annual", "Total Equity", add_ttm=True))
        quantity = np.array(
            self.reports.get_field_as_list("income_statement", "annual", "Diluted Weighted Average Shares",
                                           add_ttm=True))
        values = equity / quantity
        times = self.reports.get_reports_dates("annual", add_ttm=True)
        format_axis(ax)
        ax.plot(times, values, '-', label=label)
        ax.legend(framealpha=0.4)

        # 01 - EPS
        ax = fig.add_subplot(gs[0, 1])
        label = "eps"
        earnings = np.array(self.reports.get_field_as_list("income_statement", "annual", "Net Income", add_ttm=True))
        eps = earnings / quantity
        format_axis(ax)
        ax.plot(times, eps, '-', label=label)
        ax.legend(framealpha=0.4)

        # 10 - {Free, Operating} Cash Flow
        ax = fig.add_subplot(gs[1, 0])
        format_axis(ax)
        # label = ("operating", "free")
        operating = np.array(
            self.reports.get_field_as_list("cash_flow", "annual", "Cash Flow from Operating Activities", add_ttm=True))
        capex = np.array(self.reports.get_field_as_list("cash_flow", "annual", "Purchase/Sale of Prop,Plant,Equip: Net",
                                                        add_ttm=True))
        free_cf = operating + capex
        label_n_values = [["operating", operating], ["free", free_cf]]
        for label, values in label_n_values:
            ax.plot(times, values, '-', label=label)
        ax.legend(framealpha=0.4)

        # 11 - price & intrinsic value
        # IDK how to calculate the intrinsic value, so just price
        ax = fig.add_subplot(gs[1, 1])
        format_axis(ax)
        label = "price"
        prices = np.array(self.get_price_at_report_dates('annual', add_ttm=True))
        ax.plot(times, prices, '-', label=label)
        ax.legend(framealpha=0.4)

        # 21 - PE Ratio & Annual Earnings Growth Rate
        ax = fig.add_subplot(gs[2, 1])
        format_axis(ax)
        label = "PE"
        pe_ratios = prices / eps 
        ax.plot(times, pe_ratios, '-', label=label)
        ax.legend(framealpha=0.4)

        ax2 = ax.twinx()
        label = "EPS Growth"
        times = np.array(times)
        time_for_deltas = times[1:]
        dt = np.array(times[1:] - times[:-1], dtype='timedelta64[D]')
        dt = dt / np.timedelta64(1, 'D') / 365.25
        de = eps[1:] / eps[:-1]
        growths = de ** (1 / dt)
        growths = (growths - 1) * 100
        ax2.plot(time_for_deltas, growths, label=label, color="C1")
        ax2.legend(framealpha=0.4)

        # wide price graph
        ax = fig.add_subplot(gs[-1, :])
        format_axis(ax)
        # label = "price"
        # ax.plot(times, prices, '-', label=label)  # for offline testing
        price_times, price_values = self.get_price_graph('annual', add_ttm=self.reports.has_full_ttm())
        ax.plot(price_times, price_values, '-')
        new_price_times, new_price_values = self.get_price_graph_after_report('annual', add_ttm=self.reports.has_full_ttm())
        ax.plot(new_price_times, new_price_values)
        # ax.legend(framealpha=0.4)

        # widget
        self._price_series = pd.concat([price_values, new_price_values])
        rectprops = dict(facecolor='cyan', alpha=0.15)
        self.widget = matplotlib.widgets.SpanSelector(ax,
                                                      lambda from_date, to_date: self.show_delta(
                                                          mdates.num2date(from_date).replace(tzinfo=None),
                                                          mdates.num2date(to_date).replace(tzinfo=None)),
                                                      'horizontal', props=rectprops, useblit=True)

        ax.set_xlim((self._price_series.index[0], self._price_series.index[-1]))

        fig.set_layout_engine('tight')
        fig.suptitle(self.symbol + "({:,.2f}): IRR {:.1f}% L {:.1f}%, PE {:.1f}".format(
            self.yahoo_info.get_stock_price_now(), *(self.get_irr()), self.get_projected_pe()))

        if show:
            plt.show()
        else:
            return fig

    def show_delta(self, from_date, to_date):
        """ called by the mpl widget to inspect price growth """
        #  some sort of rounding of the date, think about how to reflect this to the user
        index = self._price_series.index.unique()
        # set timezone to allow comparing with the index
        timezone = index.tzinfo
        from_date = timezone.localize(from_date)
        to_date = timezone.localize(to_date)
        start_price = self._price_series.loc[index[index.get_indexer([from_date], method="nearest")]].iloc[0]
        end_price = self._price_series.loc[index[index.get_indexer([to_date], method="nearest")]].iloc[0]
        change = (end_price - start_price) / start_price
        # not the real time delta if the market was closed
        days = (to_date - from_date).days
        if days == 0:
            print("price at %s: %.2f" % (from_date.date(), start_price))
            return
        years = days / 365.25  # in years
        yoy_change = (change + 1) ** (1 / years) - 1
        print("")
        print("during %s days (%.1f years):" % (days, years))
        print("price growth: " + "%.2f%%" % (change * 100))
        print("yearly growth: " + "%.2f%%" % (yoy_change * 100))

    def get_projected_pe(self):
        """ pe ratio with current price and forcasted growth of the income since the report till now """
        # estimate income (linear fit) - crude hard copy of the trend calculation:
        statements = self.reports.get_reports_ascending("annual", "income_statement", self.reports.has_full_ttm())
        # - subtract some date just to convert to timedelta type
        annual_dates = [(date - self.statistics["updated at"]).days for date in


                        self.reports.get_reports_dates("annual", self.reports.has_full_ttm())]
        yearly_earnings = [statement["Net Income"] for statement in statements]
        poly_fit = Polynomial.fit(annual_dates, yearly_earnings, deg=1)
        earnings_fit = poly_fit.convert().coef
        forecasted_income = earnings_fit[0] + (datetime.datetime.now() - self.statistics["updated at"]).days * \
                            earnings_fit[1]
        diluted_shares = self.reports.get_last_report("quarterly", "income_statement")[
            "Diluted Weighted Average Shares"]
        return (diluted_shares * self.yahoo_info.get_stock_price_now()) / forecasted_income

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
        yearly_pe_ratio = real_price / yearly_eps
        quarterly_pe_ratio = real_price / quarterly_eps
        old_yearly_pe_ratio = yearly_price / yearly_eps
        old_quarterly_pe_ratio = quarterly_price / quarterly_eps

        print("yearly_pe_ratio:        " + str(yearly_pe_ratio))
        print("quarterly_pe_ratio:     " + str(quarterly_pe_ratio))
        print("")
        print("old_yearly_pe_ratio:    " + str(old_yearly_pe_ratio))
        print("old_quarterly_pe_ratio: " + str(old_quarterly_pe_ratio))

    def _round(self, digits=2):
        for key, value in self.statistics.items():
            if np.issubdtype(type(value), np.floating):
                self.statistics[key] = np.round(value, digits)


def format_axis(ax):
    years = mdates.YearLocator()  # every year
    months = mdates.MonthLocator()  # every month
    years_fmt = mdates.DateFormatter('%Y')

    # format the ticks
    ax.xaxis.set_major_locator(years)
    ax.xaxis.set_major_formatter(years_fmt)
    ax.xaxis.set_minor_locator(months)

    # # round to nearest years.
    # datemin = np.datetime64(data['date'][0], 'Y')
    # datemax = np.datetime64(data['date'][-1], 'Y') + np.timedelta64(1, 'Y')
    # ax.set_xlim(datemin, datemax)
    #
    # # rotates and right aligns the x labels, and moves the bottom of the
    # # axes up to make room for them
    # fig.autofmt_xdate()


""" --- Portfolios: --- """
class TickerGroup(YahooGroup):
    def __init__(self, symbols:list, markets:list, *,
                 risk_free_rate=None, existing_tickers:dict = dict(), use_past_growth=False):
        symbols = [s.upper() for s in symbols]
        markets = [m.upper() for m in markets]
        super().__init__(symbols, markets)
        self.risk_free_rate = risk_free_rate
        self.symbols = symbols
        self.markets = markets
        self.portfolio_std = np.nan
        self.tickers_dictionary = existing_tickers  # dict[(symbol,market)] will hold the ticker, will be used for get_forcasted_monthly_growth(), otherwise use past growth
        self.use_past_growth = use_past_growth
        self.annual_growth_forecasts = list()

    def calculate_correlation(self):
        super().calculate_correlation()
        self.calculate_growth_forecast()
        self.create_frontier()

    def calculate_growth_forecast(self):
        print("recreating tickers and calculating growth")  # todo optimize runtime
        for symbol, market, full_symbol in zip(self.symbols, self.markets, self.full_symbols):
            if not self.use_past_growth or not yahoo_symbol_is_index(symbol):
                if (symbol,market) not in self.tickers_dictionary:
                    self.tickers_dictionary[(symbol,market)] = Ticker.get_cache(symbol, market, yf_ticker=self.yf_ticker.tickers[full_symbol])
                self.annual_growth_forecasts.append(self.tickers_dictionary[(symbol,market)].get_forecasted_annual_growth())
            else:
                self.annual_growth_forecasts.append(self.get_past_annual_performance(symbol,market))

#    def calculate_tickers(self):
#        """fetch in parrallel"""
#        uncached_tickers = [item for item in zip(self.symbols, self.markets) if (item not in self.tickers_dictionary) and not yahoo_symbol_is_index(item[0]) ] 
#        tickers_list = create_tickers_from_symbol_names(uncached_tickers)
#        for ticker in tickers_list:
#            self.tickers_dictionary[(ticker.symbol, ticker.market)] = ticker



    def create_frontier(self):
        print("EF")
        named_growth = pd.Series(data=self.annual_growth_forecasts, index=self.symbols)
        self.efficient_frontier = EfficientFrontier(named_growth, self.cov, solver="OSQP")  # , verbose=True # todo 

    def optimize(self, ax1=None, ax2=None):
        print("risk_free_rate: %s" % self.risk_free_rate)
        ax1 = self.plot_frontier(ax=ax1)
        self.find_tangency_portfolio()
        ax2 = self.plot_tangency(ax1, ax2)
        plt.show()



    def find_tangency_portfolio(self):
        self.tangency_portfolio = self.efficient_frontier.max_sharpe(risk_free_rate=self.risk_free_rate)

        self.return_tangent, self.std_tangent, self.sharpe_tangent = self.efficient_frontier.portfolio_performance(risk_free_rate=self.risk_free_rate)
        #ax.scatter(std_tangent, ret_tangent, marker="*", s=100, c="r", label="Max Sharpe")



    def plot_frontier(self, ax=None):
        if not ax:
            _, ax = plt.subplots()
        plotting.plot_efficient_frontier(self.efficient_frontier.deepcopy(), ax=ax, ef_param="return", show_assets=True, show_tickers=True)
        ax.set_title("Efficient Frontier")
        ax.legend()
        ax.get_figure().set_layout_engine('tight')
        return ax

    def plot_tangency(self, ax1, ax2=None):
        if not ax2:
            _, ax2 = plt.subplots()
        ax1.plot(   [0, self.std_tangent], [self.risk_free_rate, self.return_tangent], c="r", label="Tangent")
        ax1.scatter([0, self.std_tangent], [self.risk_free_rate, self.return_tangent], marker="*", s=100, c="r", label="Tangency Portfolio")
        plotting.plot_weights(self.tangency_portfolio, ax=ax2)
        return ax2


class Portfolio(TickerGroup):
    """
    Used to predict future growth and volatility

    Can show the efficient frontier and this portfolio plotted on it
    todo: to calculate a beta of a stock against this portfolio
    todo: calaculate avarage statistics like pe ratio
    """
    def __init__(self, symbols:list, markets:list, quantities:list, *,
                 risk_free_rate=None, existing_tickers:dict = dict(), use_past_growth=False):
        super().__init__(symbols, markets, risk_free_rate=risk_free_rate, existing_tickers=existing_tickers, use_past_growth=use_past_growth)
        self.current_prices = self.get_stock_prices_now()
        self.quantities = np.array(quantities)
        self.weights = self.quantities * np.array(self.current_prices)
        self.weights = self.weights / np.sum(self.weights)
        self.weights_dict = dict(zip(zip(self.symbols, self.markets), self.weights))

        self.portfolio_annual_growth_forecast = np.nan
        self.portfolio_std = np.nan


    def get_weight(self, symbol:str, market:str):
        """in percents and rounded"""
        return round((self.weights_dict[(symbol, market)] * 100), 2)

    def calculate_correlation(self):
        super().calculate_correlation()
        # calc avarage behavior:
        self.portfolio_annual_growth_forecast = np.dot(self.weights, self.annual_growth_forecasts)
        self.portfolio_std = np.sqrt(self.weights.T @ self.cov @ self.weights)
        # todo: if we want to have beta/covariance of the portfolio, we will need to avarage also the historical prices data

    def plot_pie(self, ax=None):
        if not ax:
            _, ax = plt.subplots()
        ax.pie(self.weights, labels=self.symbols)

    def plot_concentric_pie(self, ax=None):
        """Two pies: left=tickers sorted by sector, right=sector+industry concentric."""
        if ax is None:
            _, (ax_tickers, ax_sectors) = plt.subplots(1, 2)
        else:
            # ax is expected to be a tuple (ax_tickers, ax_sectors)
            ax_tickers, ax_sectors = ax

        # build per-ticker metadata
        data = []
        for sym, mkt, w in zip(self.symbols, self.markets, self.weights):
            t = self.tickers_dictionary.get((sym, mkt))
            sector = (t.statistics.get("sector") or "Unknown") if t else "Unknown"
            industry = (t.statistics.get("industry") or "Unknown") if t else "Unknown"
            data.append((sector, industry, sym, w))

        data.sort(key=lambda x: (x[0], x[1]))
        sectors_sorted   = [d[0] for d in data]
        industries_sorted = [d[1] for d in data]
        symbols_sorted   = [d[2] for d in data]
        weights_sorted   = [d[3] for d in data]

        # collapse consecutive runs for industry/sector rings
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

        import colorsys
        cmap = plt.get_cmap("tab10")
        n_sec = len(sector_slices)
        sec_color = {s[0]: cmap(i / max(n_sec, 1)) for i, s in enumerate(sector_slices)}

        # --- left pie: tickers get matplotlib default colors ---
        ax_tickers.pie(weights_sorted, labels=symbols_sorted,
                       wedgeprops=dict(edgecolor='w'),
                       labeldistance=0.6)
        ax_tickers.set_title("Tickers")

        # --- right pie: industry (outer) = shades of sector color, sector (inner) = base color ---
        # count industries per sector to vary lightness
        sec_industry_idx = {}
        sec_industry_count = {}
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
                       wedgeprops=dict(width=0.4, edgecolor='w'),
                       labeldistance=0.8)
        ax_sectors.pie([s[1] for s in sector_slices],
                       labels=[s[0] for s in sector_slices],
                       radius=0.6, colors=[sec_color[s[0]] for s in sector_slices],
                       wedgeprops=dict(width=0.6, edgecolor='w'),
                       labeldistance=0.8)
        ax_sectors.set_title("Sector / Industry")

        # --- hover tooltip showing percentage ---
        fig = ax_tickers.get_figure()
        annot = fig.text(0, 0, "", va="bottom", ha="left",
                         bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.8),
                         visible=False)

        all_wedges = [w for ax in (ax_tickers, ax_sectors)
                      for w in ax.patches if hasattr(w, 'get_label')]

        def on_hover(event):
            visible = False
            for wedge in all_wedges:
                if wedge.contains(event)[0]:
                    pct = wedge.theta2 - wedge.theta1
                    pct_val = pct / 360 * 100
                    label = wedge.get_label()
                    annot.set_text(f"{label}: {pct_val:.1f}%")
                    annot.set_position((event.x / fig.get_size_inches()[0] / fig.dpi,
                                        event.y / fig.get_size_inches()[1] / fig.dpi))
                    visible = True
                    break
            annot.set_visible(visible)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect('motion_notify_event', on_hover)

        # store ticker wedges for double-click handling
        self._ticker_wedges = list(zip(ax_tickers.patches, symbols_sorted))

    def plot_portfolio(self, ax=None):
        ax = self.plot_frontier(ax=ax)
        ax.plot(self.portfolio_std, self.portfolio_annual_growth_forecast, 'ro')

    def to_df(self) -> pd.DataFrame:
        """Return a statistics DataFrame in the same format as stocks_analyzer.ticker_list_to_df()."""
        tickers = []
        for sym, mkt, full_sym in zip(self.symbols, self.markets, self.full_symbols):
            if (sym, mkt) not in self.tickers_dictionary:
                self.tickers_dictionary[(sym, mkt)] = Ticker.get_cache(
                    sym, mkt, yf_ticker=self.yf_ticker.tickers[full_sym])
            tickers.append(self.tickers_dictionary[(sym, mkt)])
        d = {f"{t.symbol}:{t.market}": t.statistics.values() for t in tickers}
        return pd.DataFrame.from_dict(d, orient='index', columns=tickers[0].statistics.keys())


class HistoricPortfolio(Portfolio):
    """
    A portfolio who also includs buy & sell events. Allows tracking past performance
    todo: use in portfolio_analyzer.py (instead of direct calculation)
    """
    pass



if __name__ == '__main__':
    # ticker_name = input("Ticker Name: ")
    # stock_exchange = input("Stock Exchange: ")

    # Ticker.get_cache(ticker_name, stock_exchange).plot_me()
    Portfolio(["msft", "brk.b"], ["nasdaq", "nyse"], [10, 2])
