#!/usr/bin/python3

import yfinance as yf
import datetime


class YfinanceException(Exception):
    """Exceptions that are thrown from the yfinance class. The class is
    responsible for fetching the financial data from Yahoo. This includes mostly
    stock data such as price."""
    pass


market_to_yf_market = {
        "NASDAQ"    : None,  # None value will leave the symbol intact
        "NYSE"      : None,
        "AMEX"      : None,
        "TPE"       : "TW",  # Taiwan
        "TYO"       : "T",   # Japan
        "LON"       : "L",   # UK
        "SWX"       : "SW",  # Switzerland
        "AMS"       : "AS",  # Holland
        "STO"       : "ST",  # Sweden
        "TLV"       : "TA",  # Israel
        "KRX"       : "KS",  # Korea
        "SHE"       : "SZ",
    }

def get_ticker_from_standard_symbols(symbol:str, market:str):
    full_symbol = symbol.replace('.', '-').replace(' ', '-')  # for tickers like "brk.b"

    if market not in market_to_yf_market.keys():
        raise YfinanceException("unrecognised market")

    market_endian = market_to_yf_market[market]
    if market_endian is not None:
        full_symbol = full_symbol + "." + market_endian
    else:
        full_symbol = full_symbol
    return full_symbol, market_endian


class YahooInfo:

    def translate_price(self, value):
        """ In Israel, convert from agura to shekel, as in the reports """
        if self.market_endian == "TA":
            return value / 100
        return value

    def get_stock_price_now(self):
        """Get the current stock price, or, if the market is closed, the closing price,
        without caching, as the price continue to change"""
        todays_data = self.yf_ticker.history(period='1d')
        return self.translate_price(todays_data['Close'].iloc[0])

    def get_stock_price_at_date(self, day, month, year):
        """Get the stock price at the given date, or the closet after it if the
        market was close in that date. @date is a dictionary of keys day, month
        and year"""

        # Use zfill to make 6 appear as 06. This would make it compatible with
        # the format in the cache file
        date_str = "{year}-{month}-{day}".format(day=str(day).zfill(2), month=str(month).zfill(2), year=year)
        if date_str in self.stock_prices:
            return self.translate_price(self.stock_prices[date_str])

        # We never fetched the stock for this date, we fetch the stock price
        # from a day *after* the requested one because yahoo data (for some
        # reason) returns the stock one day earlier than requested
        date      = datetime.date(day=day, month=month, year=year) + datetime.timedelta(days=1)
        next_date = date + datetime.timedelta(days=10)
        
        # return value is a pandas table in the form
        #                  Open      High        Low      Close    Volume  Dividends  Stock Splits
        # Date                                                                                    
        # 2018-03-14  91.601436  91.88071  90.041359  90.378410  32132000          0             0
        stocks_data = self.yf_ticker.history(start = date, end = next_date) #,debug = False)

        # to stock data at date. Cache and return 'NaN'
        if not len(stocks_data):
            self.stock_prices[date_str] = float('NaN')
            return float('NaN')

        for entry in range(len(stocks_data)):
            stock = stocks_data.iloc[entry]
            stock_date  = stock.name.strftime("%Y-%m-%d")
            stock_price = stock["Close"]
            self.stock_prices[stock_date] = stock_price

        # In case the closest stock price to date is not the requested date in
        # this function, make sure the requested date is cached as well.
        # E.g. if the requested date is Saturday, no stock data would be
        # available for this date
        self.stock_prices[date_str] = stocks_data.iloc[0]["Close"]

        # return the first value in the table which is the closest stock price
        # to the requested date
        return self.translate_price(stocks_data.iloc[0]["Close"])

    def get_stock_price_in_range(self, from_date, to_date, interval="1d"):
        # in case any date isn't cached, fetch the entire date range and cache
        # @return date & price vectors
        # todo: this is only a dummy implementation without caching and without filling weekends
        #   this is for testing the rest of the code
        stocks_data = self.yf_ticker.history(start=from_date + datetime.timedelta(days=1),
                                             end=to_date + datetime.timedelta(days=1),
                                             interval=interval)
        times = stocks_data.index
        prices = stocks_data['Close']
        return times, self.translate_price(prices)

    def pre_pickle(self):
        self.yf_ticker = None

    def post_pickle(self):
        self.yf_ticker = yf.Ticker(self.full_symbol)

    def __init__(self, symbol, market):
        self.full_symbol, self.market_endian = get_ticker_from_standard_symbols(symbol, market)
        self.yf_ticker = yf.Ticker(self.full_symbol)
        try:
            self.info = self.yf_ticker.info
            self.stock_prices = dict()
        except:
            raise YfinanceException("Failed to create yf symbol {} or fetch its info".format(self.full_symbol))



class YahooGroup:
    """ Get prices synchronised. tested only with same currency """
    def __init__(self, symbols: list, markets: list):
        self.full_symbols = list()
        self.history = None
        for i in range(len(symbols)):
            self.full_symbols.append(get_ticker_from_standard_symbols(symbols[i], markets[i])[0])
        self.yf_ticker = yf.Tickers(" ".join(self.full_symbols))
        self.get_monthly_prices()  #

    def get_monthly_prices(self) -> None:
        """
        TODO: return vectors of dates, weight(price), growth(divided by price) - will be used by portfolio volatility analysis
        should cache the result?
        should take into account splits and dividends(will be added to the monthly growth)
        """
        if self.history is None:
            self.history = self.yf_ticker.history(period="10y")["Close"].iloc[::30]  # todo better implement period & interval (more years and real months?, maybe add overlaps)

    def get_monthly_growths(self):
        p1 = self.history[1:]
        p0 = self.history[:-1]
        p0.index = p1.index
        return (p1 - p0) / p0

    def get_past_annual_performance(self, symbol, market, is_yahoo=False):
        full_symbol = symbol if is_yahoo else get_ticker_from_standard_symbols(symbol,market)[0]
        return self.get_monthly_growths()[full_symbol].mean()

    def get_cov(self):
        return self.get_monthly_growths().cov().values





if __name__ == '__main__':  # test index
    import matplotlib.pyplot as plt
    y = YahooInfo('%5EGSPC', 'NYSE')  # S&P500
    fig = plt.figure()
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=(365.25*4))
    date_vector, price_vector = y.get_stock_price_in_range(start_date, end_date, interval="1d")
    plt.plot(date_vector, price_vector, '-')
    plt.show()

