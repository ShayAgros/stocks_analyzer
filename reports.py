#!/usr/bin/env python3

import requests
import os.path as path
from htmldom import htmldom
import json
import pandas as pd
from os import makedirs
import time
import re
import datetime

site_format_init = "https://www.msn.com/en-us/money/stockdetailsvnext/financials"
site_format_dict = {
    "NAS": site_format_init + "/{report_name}/{term}/fi-126.1.{symbol}.{market}",
    "NYS": site_format_init + "/{report_name}/{term}/fi-126.1.{symbol}.{market}",
    "TAI": site_format_init + "/{report_name}/{term}/fi-144.1.{symbol}.{market}",
    "TKS": site_format_init + "/{report_name}/{term}/fi-133.1.{symbol}.{market}",
    "LON": site_format_init + "/{report_name}/{term}/fi-151.1.{symbol}.{market}",
    "TAE": site_format_init + "/{report_name}/{term}/fi-292.1.IS-{symbol}.{market}.{symbol}",
}
site_for_ticker_with_dot = site_format_init + "/{report_name}/{term}/fi-126.1.{tempered_symbol}.{market}.{symbol}"
report_dir = "./msn_reports"
file_format = "{symbol}-{market}-{report_name}-{term}.html"

market_to_msn_market = {
        "NASDAQ"    : "NAS",
        "NYSE"      : "NYS",
        "TPE"       : "TAI",  # Taiwan
        "TYO"       : "TKS",  # Japan
        "LON"       : "LON",  # UK
        "TLV"       : "TAE"   # Israel
    }

num_of_fields = {
    "annual": 4,
    "quarterly": 4
} 
fields = {
    "balance_sheet": [
        "Period End Date",
        "Total Current Assets",
        "Total Assets",
        "Total Current Liabilities",
        "Total Liabilities",
        "Current Debt",
        "Long Term Debt",
        "Total Equity",
        "Goodwill and Other Intangible Assets",
        "Ordinary Shares Outstanding",
        "Currency Code"
    ],
    "income_statement": [
        "Period End Date",
        "Net Income",
        "Total Revenue",
        "Diluted Weighted Average Shares"
    ],
    "cash_flow": [
        "Period End Date",
        "Cash Flow from Operating Activities",
        # "Cash Flow from Investing Activities",  # Warnning! in msft this field is '-', but the graph is still viewable
        # "Cash Flow from Financing Activities",
        "Change in Cash",                       # Im using this field minus the operating as a more stable replacement
                                                # to the sum of investing + financing
        "Common Stock Dividends Paid",
        "Purchase/Sale of Prop,Plant,Equip: Net"  # Capital Expenditures
    ]
}


def store_process_value(term_dict, key, str_value):
    """Receive a value parsed from the html of a form, and store
        its value in the dictionary in the correct type"""

    if key == "Period End Date":
        m = re.match(r"(?P<month>\d+)/(?P<day>\d+)/(?P<year>\d+)", str_value)
        term_dict[key] = { key: int(value) for key, value in m.groupdict().items()}
    elif key in ("Currency Code",):
        term_dict[key] = str_value
    elif str_value == "-":
        term_dict[key] = float('NaN')
    else:
        value = float(str_value.replace(',', ''))
        value = value * 10**6
        term_dict[key] = value

def get_number_of_fields(document, searched_field):
    """ Get an htmlDom object and count how many instances of a tag exist in it
    @document: the document to search in
    @searched_field: the field to search
    """

    num = 0
    while document.find(searched_field)[num + 1]:
        num += 1

    return num

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

        # year or quarter columns
        periods_number = get_number_of_fields(document, "div.column-heading")

        for i in range(periods_number):
            columns = document.find("div.column-heading")[i + 1]
            quarter_name = columns.find("p").attr("title")

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

        if len(response.text) < 70:
            print("sute url: " + site_url)
            raise Exception("MSN Server Error")
        with open(site_file, "w") as f:
            f.write(response.text)

    def __parse_and_save_report(self, term, report_name):
        site_file_name = file_format.format(symbol = self.symbol, market = self.market, report_name = report_name, term = term)
        site_path = path.join(report_dir, site_file_name) 

        if "." in self.symbol:
            site_symbol = self.symbol.replace(".", "%7CSLA%7C")
            site_url = site_for_ticker_with_dot.format(report_name = report_name, term=term, symbol=self.symbol, market=self.msn_market, tempered_symbol=site_symbol)
        else:
            site_url = site_format_dict[self.msn_market].format(report_name = report_name, term=term, symbol=self.symbol, market=self.msn_market)

        # Didn't parse it yet. Fetch from the web
        if not path.isfile(site_path):
            try:
                makedirs(report_dir, exist_ok = True)
                self.__fetch_url(site_url, site_path)
            except:
                raise Exception("Failed to fetch site symbol: {} market: {} msn market: {}".format(self.symbol, self.market, self.msn_market))

        self.__parse_fields(term, report_name)

    def get_reports_ascending(self, term, report_name):
        report_dict = getattr(self, report_name)
        term_dict = report_dict[term]

        ordered_terms = sorted(term_dict.keys())
        return [term_dict[t] for t in ordered_terms]

    def get_last_report(self, term, report_name):
        ordered_reports = self.get_reports_ascending(term, report_name)
        return ordered_reports[-1]

    def get_reports_dates(self, term):
        # it doesnt really matter if we take the dates from a balance_sheet or income_statement:
        reports_ordered = self.get_reports_ascending(term, 'balance_sheet')
        dates = [report["Period End Date"] for report in reports_ordered]
        dates = [datetime.datetime(date["year"], date["month"], date["day"]) for date in dates]
        return dates

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
        self.cash_flow = dict()

        self.__parse_and_save_report("quarterly", "balance_sheet")
        self.__parse_and_save_report("quarterly", "income_statement")
        self.__parse_and_save_report("quarterly", "cash_flow")

        self.__parse_and_save_report("annual", "balance_sheet")
        self.__parse_and_save_report("annual", "income_statement")
        self.__parse_and_save_report("annual", "cash_flow")
