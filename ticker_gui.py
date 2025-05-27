#!/usr/bin/env python3

from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QEvent, QItemSelection, QItemSelectionModel
from PyQt5.QtWidgets import (QApplication, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem)

from gui.ticker_table import TickersTableView, TickersTableModel

import pandas as pd
import sys

import stocks_analyzer

class tickers_gui(QWidget):

    def __init__(self, tickers_stats):
        super().__init__()

        self.setWindowTitle("Stocks analyzer")
        self.setGeometry(50, 200, 1500, 1000)

        self.column_headers = dict()

        self.place_tickers(tickers_stats)
        self.show()


    def place_tickers(self, tickers_stats):

        vlayout = QVBoxLayout()

        self.tickers_table = TickersTableView(self)
        self.model = TickersTableModel(tickers_stats)

        header = self.tickers_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        self.tickers_table.setModel(self.model)

        # selection_model = self.tickers_table.selectionModel()
        # top_left, bottom_right = self.model.index(0, 0), self.model.index(10, 10)
        # selection = QItemSelection(top_left, bottom_right)
        # selection_model.select(selection, QItemSelectionModel.SelectionFlag.Select)
        
        vlayout.addWidget(self.tickers_table)

        self.setLayout(vlayout)

    def keyPressEvent(self, e):

        key = e.key()

        if key == Qt.Key_Escape or e.text() == 'q':
            self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)

    input_file = stocks_analyzer.select_stocks_file() 
    tickers = stocks_analyzer.create_tickers_from_file(input_file)
    df = stocks_analyzer.ticker_list_to_df(tickers)
    df = df[stocks_analyzer.tldr_statistics]

    window = tickers_gui(df)

    sys.exit(app.exec_())

