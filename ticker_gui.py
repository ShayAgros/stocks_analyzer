#!/usr/bin/env python3

from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import (QApplication, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem)
import pandas as pd
import sys

import stocks_analyzer

MAX_DISPLAY_ENTRIES = 14

class TickersTableModel(QtCore.QAbstractTableModel):

    def __init__(self, data):
        super(TickersTableModel, self).__init__()

        self._data = data
        # This would allow us to access the "healthy" column number easier
        # (needed when presenting the data)
        self._healthy_col_ix = data.columns.get_loc("healthy")

    def data(self, index, role):
        if role == Qt.DisplayRole:
            # See below for the nested-list data structure.
            # .row() indexes into the outer list,
            # .column() indexes into the sub-list
            value = self._data.iloc[index.row(), index.column()]

            if isinstance(value, float):
                return "%.3f" % value

            return str(value)

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return min(self._data.shape[1], MAX_DISPLAY_ENTRIES)

    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                header = str(self._data.columns[section])
                header = header.replace("_", " ").title()
                return header

            if orientation == Qt.Vertical:
                return str(self._data.index[section])

        if role == Qt.ForegroundRole:
            if orientation == Qt.Vertical:
                healthy = self._data.iloc[section, self._healthy_col_ix]
                color = "green" if healthy else "red"
                # healthy_col_ix = 
                # print(healthy_col_ix)
                # print(self._data.iloc[section, healthy_col_ix])
                # print(healthy)
                return QtGui.QColor(color)

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

        self.tickers_table = QtWidgets.QTableView()
        self.model = TickersTableModel(tickers_stats)

        header = self.tickers_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        self.tickers_table.setModel(self.model)
        
        vlayout.addWidget(self.tickers_table)

        self.setLayout(vlayout)

    def keyPressEvent(self, e):

        key = e.key()

        if key == Qt.Key_Escape or e.text() == 'q':
            self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)

    tickers = stocks_analyzer.create_tickers_from_file('./russel_formated_first_50.txt')


    d = {(ticker.symbol): ticker.statistics.values() for ticker in tickers}
    # ---- As Dataframe: ----
    df = pd.DataFrame.from_dict(d, orient='index', columns=tickers[0].statistics.keys())

    # print(data)

    window = tickers_gui(df)

    sys.exit(app.exec_())

