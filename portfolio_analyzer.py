from matplotlib import pyplot as plt

from yfinance_info import YahooInfo
from ticker import search_growth, Portfolio
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sys import stdout

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


def get_performance(table):
    # todo check if can be assumed to be monotonic, I think not
    profitable, portfolio_value, money_invested, get_npv = get_get_npv(table)
    print("Amount of money invested: %.2f" % money_invested)
    print("Current portfolio value:  %.2f" % portfolio_value)
    print("Calculating avarage performance...")
    return search_growth(
        npv_function=get_npv,
        price=0,
        min_growth=0 if profitable else -1,
        max_growth=4 if profitable else 0,
        delta_growth=0.1 / 100
    )


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



if __name__ == '__main__':
    file = "inputs/Portfolio1.tsv"
    table = read_tsv(file)
    print("Portfolio performed annually at: %.2f%%" % get_performance(table))
    stdout.flush()

    index_name, index_table = get_index(table)
    print("\nSimulated investment in %s gives:" % index_name)
    print("Index performed annually at: %.2f%%" % get_performance(index_table))

    #portfolio = create_portfolio(table)
    #portfolio.plot_portfolio()  # todo crushing
    #plt.show()



