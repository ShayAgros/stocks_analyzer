#!/usr/bin/env python3

from ticker import Ticker

# TODO: replace all silly prints with proper log functions that indicate an
# error

# def sort_stocks_by_field()

# def create_tickers_list_from_file(file_name) -> return list of class Ticker

def create_tickers_from_symbol_names(symbol_list):
    """ Get a list of dictionaries that contain symbol ticker name and its
        stock exchange. Return a list of class Ticker that represent each of the
        stocks"""
    tickers_list = list()
    for symbol, market in symbol_list:
        try:
            ticker = Ticker(symbol, market)
        except:
            print("Failed to create a ticker for {symbol}:{market}".format(
                symbol = symbol,
                market = market))
        tickers_list.append(ticker)

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

# TODO: This would output a csv file containing the statistics for each of the tickers
# def stocks_list_to_csv(tickers_list, show_fields=None, max_count=None):

        

def main():

    # 1) Create 'Ticker' variable for every symbol
    # 2) store result in some list
    # 3) Do something with the Ticker's list

    tickers = create_tickers_from_symbol_names( [ ["MSFT", "NASDAQ"], ["AAPL", "NASDAQ"], ["NVDA", "NASDAQ"] ] )

    sorting_function = lambda stock: filter_stocks_by_fields(stock, [["eps", 4, False], ["sector", "Technology"]])
    filtered_stocks = filter(sorting_function, tickers)

    # sorted_stocks = sort_stocks_by_fields(tickers, [["book_value", True], ["eps", True]])

    for stock in filtered_stocks:
        s_name  = stock.symbol
        s_eps   = stock.statistics["eps"]
        s_bv    = stock.statistics["book_value"]
        print("{name}:  eps: {eps}  book_value: {book_value}".format(
                name = s_name,
                eps = s_eps,
                book_value = s_bv))


if __name__ == '__main__':
    main()
