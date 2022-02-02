from yfinance_info import YahooInfo
from ticker import search_growth
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


sep  = "\t"
comment = "#"
frmt = "%Y-%m-%d"  # T%H:%M:%S"
read_tsv = lambda file: pd.read_csv(file, sep=sep, comment=comment, skip_blank_lines=True)


def get_get_npv(table):  # will return the lambda function
    # time which had passed for each transaction
    duration = (pd.Timestamp.now().normalize() - pd.to_datetime(table["Date"], format=frmt)) / np.timedelta64(1, "Y")
    # current price
    market_value = np.array([YahooInfo(row[1]["Ticker"], row[1]["Market"]).get_stock_price_now() for row in table.iterrows()])
    # buy\sell sign
    buy_sign = table["BuyNotSell"] * 2 - 1
    buy_amount = buy_sign * table["Amount"]
    # calculate once, use in every get_npv
    portfolio_value = (market_value * buy_amount).sum()
    money_invested = buy_amount * table["Cost"]
    # net_present_value of each transaction including opportunity cost
    get_npv = lambda rate: portfolio_value - (money_invested * ((1 + rate) ** duration)).sum()
    # more stats
    profitable = (portfolio_value - money_invested.sum()) >= 0  # will be used to limit the search range
    return profitable, portfolio_value, money_invested.sum(), get_npv


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


if __name__ == '__main__':
    file = "Portfolio1.tsv"
    table = read_tsv(file)
    #print(table["Date"].array)
    #print(get_npv(table, 0.1))
    print("Portfolio performed annually at: %.2f%%" % get_performance(table))



