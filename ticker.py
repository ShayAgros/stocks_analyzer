#!/usr/bin/env python3

from reports import Reports
from yfinance_info import YahooInfo
import numpy as np
from numpy.polynomial.polynomial import Polynomial
import json

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
        last_yearly_balance_sheet = all_yearly_balance_sheets[-1]
        last_yearly_income_statement = all_yearly_income_statements[-1]

        last_quarterly_balance_sheet = self.reports.get_last_report("quarterly", "balance_sheet")
        last_quarterly_income_statement = self.reports.get_last_report("quarterly", "income_statement")

        yahoo_info = self.yahoo_info

        # calculate eps
        earnings = last_yearly_income_statement["Net Income"]
        shares_outstanding = last_yearly_balance_sheet["Ordinary Shares Outstanding"]
        statistics["eps"] = earnings / shares_outstanding

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

        # naive time to profit
        statistics["naive_time_to_profit"] = (stock_price - book_value) / eps

        # earnings_trend
        #   - fetching only 4 years, so I use all of them
        #   - not the same as eps in the case of a change in the shares number
        yearly_earnings = [statement["Net Income"] for statement in all_yearly_income_statements]
        poly_fit = Polynomial.fit(range(len(yearly_earnings)), yearly_earnings, deg=1)
        earnings_fit = poly_fit.convert().coef
        statistics["earnings_yearly_trend"] = earnings_fit[1]  # keep the slope

        # equity_trend
        yearly_equity = [sheet["Total Equity"] for sheet in all_yearly_balance_sheets]
        poly_fit = Polynomial.fit(range(len(yearly_equity)), yearly_equity, deg=1)
        equity_fit = poly_fit.convert().coef
        statistics["equity_yearly_trend"] = equity_fit[1]  # keep the slope

    def __init__(self, symbol, market):

        self.symbol = symbol.upper()
        self.market = market.upper()

        self.yahoo_info = YahooInfo(self.symbol)

        # This would throw an exception if it fails
        self.reports = Reports(self.symbol, self.market)

        self.statistics = {
            # calculated attributes
            "eps": None,
            "book_value": None,
            "price_to_book": None,
            "pe_ratio": None,
            "ep_ratio[%]": None,
            "pe*bv": None,
            "basic_discount_value": None,
            "basic_discount_ratio": None,
            "current_ratio": None,
            "debt_to_equity": None,
            "market_cap": None,
            "naive_time_to_profit": None,  # in years
            "earnings_yearly_trend": None,
            "equity_yearly_trend": None,

            # fetched attributes
            "net_income": self.reports.get_last_report("annual", "income_statement")["Net Income"],
            "sector": self.yahoo_info.info["sector"],
            "industry": self.yahoo_info.info["industry"],
            }

        self.__calculate_stats()

        print(json.dumps({"symbol":self.symbol, **self.statistics}, indent=4))

        last_quarterly_balance_sheet = self.reports.get_last_report("quarterly", "balance_sheet")
        balance_sheet_date = last_quarterly_balance_sheet["Period End Date"]
        stock_price = self.yahoo_info.get_stock_price_at_date(**balance_sheet_date)
        print("stock price at last report: " + str(stock_price))

# msft = Ticker("nvda", "nasdaq")
