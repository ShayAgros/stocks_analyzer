#/usr/bin/python3

import yfinance as yf
import json
from os import makedirs, path
import datetime

class YfinanceException(Exception):
    """Exceptions that are thrown from the yfinance class. The class is
    responsible for fetching the financial data from Yahoo. This includes mostly
    stock data such as price."""
    pass

yahoo_dir = "./yahoo_files"
file_format = "{symbol}-yahoo.json"

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
    }


def get_seconds_from_now(filename):
    sec_from_epoch = path.getmtime(filename)
    return datetime.datetime.now().timestamp() - sec_from_epoch


class YahooInfo:

    def translate_price(self, value):
        """ In Israel, convert from agura to shekel, as in the reports """
        if self.market_endian == "TA":
            return value / 100
        return value

    def get_stock_price_now(self):
        """Get the current stock price, or, if the market is closed, the closing price,
        without caching, as the price continue to change"""
        todays_data = self.yf_symbol.history(period='1d')
        return self.translate_price(todays_data['Close'][0])

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
        stocks_data = self.yf_symbol.history(start = date, end = next_date,
                debug = False)

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

        # save this data for future uses
        data = {"info": self.info, "stock_prices": self.stock_prices}
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=4)

        # return the first value in the table which is the closest stock price
        # to the requested date
        return self.translate_price(stocks_data.iloc[0]["Close"])

    def get_stock_price_in_range(self, from_date, to_date, interval="1d"):
        # in case any date isn't cached, fetch the entire date range and cache
        # @return date & price vectors
        # todo: this is only a dummy implementation without caching and without filling weekends
        #   this is for testing the rest of the code
        stocks_data = self.yf_symbol.history(start=from_date + datetime.timedelta(days=1),
                                             end=to_date + datetime.timedelta(days=1),
                                             interval=interval)
        times = stocks_data.index
        prices = stocks_data['Close']
        return times, self.translate_price(prices)

    def __init__(self, symbol, market):
        symbol = symbol.replace('.', '-').replace(' ', '-')  # for tickers like "brk.b"

        if market not in market_to_yf_market.keys():
            raise YfinanceException("unrecognised market")

        self.market_endian = market_to_yf_market[market]
        if self.market_endian is not None:
            self.symbol = symbol + "." + self.market_endian
        else:
            self.symbol = symbol

        file_name = file_format.format(symbol = self.symbol)
        file_path = path.join(yahoo_dir, file_name)

        self.file_path = file_path

        self.yf_symbol = yf.Ticker(self.symbol)

        if not path.isfile(file_path) or get_seconds_from_now(file_path) > 3600 * 24 * 30: # 30 days
            force_old_data = False
            try:
                info = self.yf_symbol.info
            except:
                raise YfinanceException("Failed to create yf symbol {} or fetch its info".format(self.symbol))

            makedirs(yahoo_dir, exist_ok=True)

            # initialize stock prices to be an empty dictionary
            if not force_old_data:
                data = {"info": info, "stock_prices": dict()}
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=4)

        with open(file_path, "r") as f:
            data = json.load(f)
            self.info = data["info"]
            self.stock_prices = data["stock_prices"]
