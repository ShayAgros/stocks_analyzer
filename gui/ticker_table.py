from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QEvent, QItemSelection, QItemSelectionModel
from PyQt5.QtWidgets import (QTableView)

from ticker import Ticker

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
                return QtGui.QColor(color)

class TickersTableView(QTableView):

    def __init__(self, parent = None):
        super().__init__(parent)

        self.parent = parent

    def keyPressEvent(self, e):

        key = e.key()

        if key == Qt.Key_Escape or e.text() == 'q':
            self.parent.keyPressEvent(e)
        elif key == Qt.Key.Key_Return:
            print("enter has been pressed")
            selectionModel = self.selectionModel()
            current = selectionModel.currentIndex()

            model = self.model()

            data = model.data(current, Qt.DisplayRole)
            header = model.headerData(current.row(), Qt.Vertical, Qt.DisplayRole)
            print(f"cell data is {data}, header is {header}")

            # symbol and market array
            symbol, market = header.split(":")
            print(symbol, market)
            ticker = Ticker.get_cache(symbol, market)
            ticker.plot_me()
        else:
            super().keyPressEvent(e)
