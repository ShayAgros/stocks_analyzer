from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QEvent, QItemSelection, QItemSelectionModel
from PyQt5.QtWidgets import QTableView, QHeaderView

from ticker import Ticker

MAX_DISPLAY_ENTRIES = 14


class ColoredHeaderView(QHeaderView):
    """Vertical header that colors each section based on the model's ForegroundRole."""

    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.setSectionsClickable(True)

    def paintSection(self, painter, rect, logical_index):
        painter.save()
        # draw default section (background, borders) but without text
        opt = QtWidgets.QStyleOptionHeader()
        self.initStyleOption(opt)
        opt.rect = rect
        opt.section = logical_index
        opt.text = ""  # suppress default text
        self.style().drawControl(QtWidgets.QStyle.CE_Header, opt, painter, self)
        # draw text in the model's foreground color
        color = self.model().headerData(logical_index, Qt.Vertical, Qt.ForegroundRole)
        text = self.model().headerData(logical_index, Qt.Vertical, Qt.DisplayRole)
        if text:
            painter.setClipRect(rect)
            if color:
                painter.setPen(color)
            painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()

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
                return QtGui.QColor("#00e676") if healthy else QtGui.QColor("#ff1744")

class TickersTableView(QTableView):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setVerticalHeader(ColoredHeaderView(self))
        self.doubleClicked.connect(self._on_double_click)

    def _on_double_click(self, index):
        from npv_calculator import GrowthApp
        # map proxy index to source if a proxy model is in use
        source_index = index
        model = self.model()
        if hasattr(model, 'mapToSource'):
            source_index = model.mapToSource(index)
            model = model.sourceModel()
        header = model.headerData(source_index.row(), Qt.Vertical, Qt.DisplayRole)
        symbol, market = header.split(":")
        ticker = Ticker.get_cache(symbol, market)
        self._growth_windows = getattr(self, '_growth_windows', [])
        win = GrowthApp(ticker=ticker)
        self._growth_windows.append(win)
        win.show()

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
