#!/usr/bin/env python3

from ticker import Ticker
from yfinance_info import YfinanceException
from reports import MsnReportsException
import pandas as pd
import warnings

import multiprocessing as mp

# to have colored output
from colorama import Fore, Back, Style

csv_path = "output.csv"

class tickerWorkerStatus():
    STATUS_SUCCESS = 0
    STATUS_WARNINGS = 1
    STATUS_FAILED = 2

    LONGEST_SYM_MAR_STR_LEN = 30

    def __init__(self, symbol, market):
        self.symbol = symbol
        self.market = market
        self.status = self.STATUS_SUCCESS

    def setWarning(self, msg):
        self.status = self.STATUS_WARNINGS
        self.msg = msg

    def setFailure(self, msg):
        self.status = self.STATUS_FAILED
        self.msg = msg

    def setTicker(self, ticker):
        self.ticker = ticker

    def getTicker(self):
        return self.ticker

    def isFailed(self):
        return self.status == self.STATUS_FAILED

    def __str__(self):
        if self.status == self.STATUS_SUCCESS:
            status_msg = Fore.GREEN + "SUCCESS" + Fore.RESET
        elif self.status == self.STATUS_WARNINGS:
            status_msg = Fore.LIGHTMAGENTA_EX + "WARNING" + Fore.RESET + " ({})".format(self.msg)
        else:
            status_msg = Fore.RED + "FAILURE" + Fore.RESET + " ({})".format(self.msg)

        symbol_market_str = "{}:{}".format(self.symbol, self.market)
        padded_symbol_market_str = symbol_market_str.ljust(self.LONGEST_SYM_MAR_STR_LEN)
        return Fore.BLUE + padded_symbol_market_str + Fore.RESET + "-\t\t" + status_msg

# TODO: replace all silly prints with proper log functions that indicate an
#   error
def create_ticker_worker(ticker_queue_tuple):

    symbol, market = ticker_queue_tuple["ticker_tuple"]
    status_queue = ticker_queue_tuple["queue"]

    status = tickerWorkerStatus(symbol, market)
    try:
        # print("Fetching data for {symbol}:{market}\n".format(symbol = symbol,
            # market = market))
        ticker = Ticker(symbol, market)

        if ticker.warnings:
            status.setWarning("Ticker {}:{} has warnings: {}".format(symbol, market, ticker.warnings[0]))

        status.setTicker(ticker)
    except YfinanceException as err:
        status.setFailure("Failed in yfinance. error: {}".format(err))
    except MsnReportsException as err:
        status.setFailure("Failed in reports. error: {}".format(err))
    except Exception as err:
        status.setFailure("Failed with unknown reason. error")
        print(err)

    try:
        status_queue.put(status)
    except Exception as err:
        print(f"Inserting the ticker {symbol}:{market} object into the queue failed.")
        print("This probably means that some of its objects cannot be serialized")
        print("This probably means that some of its objects cannot be serialized")

def create_tickers_from_symbol_names(symbol_list):
    """ Get a list of tuples that contain symbol ticker name and its
        stock exchange. Return a list of class Ticker that represent each of the
        stocks"""
    manager = mp.Manager()
    queue   = manager.Queue(len(symbol_list))
    ticker_queue_tuple = [ { "ticker_tuple" : ticker, "queue" : queue }
            for ticker in symbol_list ]

    tickers_list = list()
    with mp.Pool(processes=None) as pool:
        result = pool.map_async(create_ticker_worker, ticker_queue_tuple)
        while not result.ready():
            while not queue.empty():
                status_item = queue.get()
                if not status_item.isFailed():
                    tickers_list.append(status_item.getTicker())

                print(status_item)

    return tickers_list

def sort_stocks_by_fields(tickers_list, fields):
    """Sort stocks in @tickers_list by the @fields. The stocks
       are sorted by the first item in @fields_name, then by the second and so
       forth. @fields is a list containing field name and True/False value. True
       would sort the value in ascending order which False would do the opposite"""

    def get_ticker_fields(ticker):
        return tuple(ticker.statistics[field[0]] * (field[1] - 0.5) for field in fields)

    return sorted(tickers_list, key = get_ticker_fields)

def filter_stocks_by_fields(ticker, fields):
    """Check stock @ticker by the elements in @fields which have the
    format [ field, value, less_than ]. If field element is a string, then
    the field == value is checked. Otherwise, field <= value or field >= value
    is checked depending on less_than value.
    All checks are AND'd"""

    passes=True
    for check in fields:
        fname, fvalue = check[0:2]
        field = ticker.statistics[fname]

        if type(field) == type("string"):
            passes &= field == fvalue
        else:
            less_than = check[2] if len(check) == 3 else True
            if less_than:
                passes &= field <= fvalue
            else:
                passes &= field >= fvalue
    return passes


def extract_statistics(ticker):
    return ticker.statistics


# This would output a csv file containing the statistics for each of the tickers
def stocks_list_to_csv(tickers_list, out_path, show_fields=None, max_count=None, ignore_fields=None):
    if max_count and max_count < len(tickers_list):
        tickers_list = tickers_list[:max_count]
    if len(tickers_list) == 0:
        print("No Tickers To Save. ignored.")
        return

    # as dictionary:
    d = {(ticker.symbol): extract_statistics(ticker).values() for ticker in tickers_list}
    # ---- As Dataframe: ----
    df = pd.DataFrame.from_dict(d, orient='index', columns=tickers_list[0].statistics.keys())

    if show_fields is not None:
        df = df[show_fields]
    if ignore_fields is not None:
        df = df.drop(ignore_fields)

    # print summary to the terminal
    pd.set_option('max_colwidth', 20)
    titles = ["name", "pe_ratio", "healthy", "overvalued", "industry"]
    if show_fields is not None:
        titles = [field for field in titles if field in show_fields]
    if ignore_fields is not None:
        titles = [field for field in titles if field not in ignore_fields]
    print(df[titles])
    pd.reset_option('max_colwidth')

    # save to file
    df.to_csv(out_path)

def create_tickers_from_file(file_path):
    """The function receives a path to a file containing entries of the form
    'TICKER MARKET' (e.g. 'AAPL NASDAQ') and returns a Ticker list"""

    symbol_list = []
    with open(file_path, "r") as f:
        print("Querying file " + file_path)
        for line in f:
            line_attr = line.split()
            # print("Ticker: {ticker}   Market: {market}".format(
                # ticker = line_attr[0],
                # market = line_attr[1]))
            symbol_list.append(line_attr)

    return create_tickers_from_symbol_names(symbol_list)

def main():

    # make warning throw exceptions
    # this is important when using Threads to avoid having writing to
    # stderr in parallel. The warnings would need to be caught explicitly so
    # that they wouldn't be missed
    warnings.simplefilter('error')

    # 1) Create 'Ticker' variable for every symbol
    # 2) store result in some list
    # 3) Do something with the Ticker's list

    tickers = create_tickers_from_symbol_names( [ ["MSFT", "NASDAQ"], ["AAPL", "NASDAQ"], ["NVDA", "NASDAQ"] ] )

    filtering_function = lambda stock: filter_stocks_by_fields(stock, [["eps", 3, False], ["sector", "Technology"]])
    filtered_stocks = filter(filtering_function, tickers)
    sorted_stocks = sort_stocks_by_fields(filtered_stocks, [["book_value", True], ["eps", True]])

    stocks_list_to_csv(sorted_stocks, csv_path)
    # for stock in filtered_stocks:
    #     s_name  = stock.symbol
    #     s_eps   = stock.statistics["eps"]
    #     s_bv    = stock.statistics["book_value"]
    #     print("{name}:  eps: {eps}  book_value: {book_value}".format(
    #             name = s_name,
    #             eps = s_eps,
    #             book_value = s_bv))


if __name__ == '__main__':
    main()
