#!/usr/bin/env python3

from reports import Reports
from yfinance_info import YahooInfo
import json


# TODO: the yahoo API doesn't allow to specify market easily,
# so currently we just ignore it. Maybe we should switch to some
# more robust service
class Ticker:

    def __calculate_stats(self):
        statistics = self.statistics
        last_yearly_balance_sheet = self.reports.get_last_report("annual", "balance_sheet")
        last_yearly_income_statement = self.reports.get_last_report("annual", "income_statement")

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
            "current_ratio": None,
            "debt_to_equity": None,
            "market_cap": None,
            "naive_time_to_profit": None,  # in years

            # fetched attributes
            "net_income": self.reports.get_last_report("annual", "income_statement")["Net Income"],
            "sector": self.yahoo_info.info["sector"],
            "industry": self.yahoo_info.info["industry"],
            }

        self.__calculate_stats()

        print(json.dumps(self.statistics, indent=4))

msft = Ticker("nvda", "nasdaq")
