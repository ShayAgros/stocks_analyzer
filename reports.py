#!/usr/bin/env python3

import requests
import os.path as path
from htmldom import htmldom
import json
import pandas as pd
from os import makedirs
import time
import re

site_format = "https://www.msn.com/en-us/money/stockdetailsvnext/financials/{report_name}/{term}/fi-126.1.{symbol}.{market}"
report_dir = "./msn_reports"
file_format="{symbol}-{market}-{report_name}-{term}.html"

market_to_msn_market = {
        "NASDAQ"    : "NAS",
        "NYSE"      : "NYS"
    }

num_of_fields = {
	"annual":4,
	"quarterly":4
} 
fields ={
	"balance_sheet": [
                "Period End Date",
                "Total Current Assets",
                "Total Assets",
                "Total Current Liabilities" ,
                "Total Liabilities",
                "Current Debt",
                "Long Term Debt",
                "Total Equity",
                "Ordinary Shares Outstanding"
            ],
    "income_statement" : [
                "Period End Date",
                "Net Income",
                "Total Revenue"
        ]
    }

def store_process_value(term_dict, key, str_value):
    """Receive a value parsed from the html of a form, and store
        its value in the dictionary in the correct type"""

    if key == "Period End Date":
        m = re.match(r"(?P<month>\d+)/(?P<day>\d+)/(?P<year>\d+)", str_value)
        term_dict[key] = { key: int(value) for key, value in m.groupdict().items()}
    elif str_value == "-":
        term_dict[key] = 'NaN'
    else:
        value = float(str_value.replace(',', ''))
        value = value * 10**6
        term_dict[key] = value


# TODO: catch specific exceptions and not just assume what they are
class Reports:

    def __parse_fields(self, term, report_name):
        """ parse all fields defined in self.fields and insert them into a
        a dictionary """
        site_file_name = file_format.format(symbol = self.symbol, market = self.market, report_name = report_name, term = term)
        site_path = path.join(report_dir, site_file_name) 
        with open(site_path) as f:
            document = htmldom.HtmlDom()
            document.createDom(f.read())

        report_dict = getattr(self, report_name)
        report_dict[term] = dict()
        term_dict = report_dict[term]
        report_fields = fields[report_name]

        for i in range(num_of_fields[term]):
            quarter_name = document.find("div.column-heading")[i+1].find("p").attr("title")
            # initialize the quarter column
            term_dict[quarter_name] = dict()
            for key in report_fields:
                words = key.split()
                selector = "".join("[title~={}]".format(word) for word in words)
                for ul in document.find("ul").has(selector):
                    p = ul.find(selector)
                    if p.attr("title") == key:
                        str_value = ul.find("li")[i+1].find('p').attr("title")
                        store_process_value(term_dict[quarter_name], key, str_value)

    def __fetch_url(self, site_url, site_file):
        response = requests.request("GET", site_url)
        time.sleep(0.5)

        with open(site_file, "w") as f:
            f.write(response.text)

    def __parse_and_save_report(self, term, report_name):
        site_file_name = file_format.format(symbol = self.symbol, market = self.market, report_name = report_name, term = term)
        site_path = path.join(report_dir, site_file_name) 

        site_url = site_format.format(report_name = report_name, term=term, symbol=self.symbol, market=self.msn_market)

        # Didn't parse it yet. Fetch from the web
        if not path.isfile(site_path):
            try:
                makedirs(report_dir, exist_ok = True)
                self.__fetch_url(site_url, site_path)
            except:
                raise Exception("Failed to fetch site symbol: {} market: {} msn market: {}".format(self.symbol, self.market, self.msn_market))

        self.__parse_fields(term, report_name)

    def get_last_report(self, term, report_name):
        report_dict = getattr(self, report_name)
        term_dict = report_dict[term]

        ordered_terms = sorted(term_dict.keys())
        return term_dict[ordered_terms[-1]]

    def __init__(self, symbol, market):
        self.symbol     = symbol
        self.market     = market

        try:
            self.msn_market = market_to_msn_market[market]
        except:
            raise Exception("market {} is not support for symbol {}".format(market, symbol))

        self.quarter = [None] * 4

        self.table = {
            "quarterly": None,
            "annual": None
        }

        self.balance_sheet = dict()
        self.income_statement = dict()

        self.__parse_and_save_report("quarterly", "balance_sheet")
        self.__parse_and_save_report("quarterly", "income_statement")

        self.__parse_and_save_report("annual", "balance_sheet")
        self.__parse_and_save_report("annual", "income_statement")
