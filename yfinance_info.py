#/usr/bin/python3

import yfinance as yf
import json
from os import makedirs, path
import datetime

yahoo_dir = "./yahoo_files"
file_format="{symbol}-yahoo.json"


def get_seconds_from_now(filename):
    sec_from_epoch = path.getmtime(filename)
    return datetime.datetime.now().timestamp() - sec_from_epoch

class YahooInfo:

    def __init__(self, symbol):

        self.symbol = symbol

        file_name = file_format.format(symbol = self.symbol)
        file_path = path.join(yahoo_dir, file_name)

        if not path.isfile(file_path) or get_seconds_from_now(file_path) > 3600 * 24:
            try:
                self.yf_symbol = yf.Ticker(self.symbol)
                info = self.yf_symbol.info
                stock_price = self.yf_symbol.history("5d")["Close"].iloc[-1]
            except:
                raise Exception("Failed to create yf symbol {} or fetch its info".format(self.symbol))

            makedirs(yahoo_dir, exist_ok=True)
            data = {"info": info, "stock_price": stock_price}
            with open(file_path, "w") as f:
                json.dump(data, f)

        with open(file_path, "r") as f:
            data = json.load(f)
            self.info = data["info"]
            self.stock_price = data["stock_price"]