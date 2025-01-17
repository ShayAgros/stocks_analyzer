import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QRadioButton, QLineEdit, QLabel, QPushButton, QButtonGroup
)
from ticker import Ticker
import sys
# from PySide6 import QtWidgets
# from PySide2 import QtWidgets
from PyQt5 import QtWidgets
from qt_material import apply_stylesheet  # import after the appropriate qtwidgets


# -----------------------------------------------------------------------------------------------------

class GrowthApp(QWidget):
    def __init__(self):
        super().__init__()
        self.ticker = Ticker.get_cache("QCOM", "NASDAQ")  # todo select
        self.initUI()

    def _init_radio(self, names : list, text_box : QLineEdit = None, horizontal : bool = False, prefix:str=None) -> QButtonGroup:
        """
        create a new boxlayout of the radios, optionally add the last radio a textbox and return the radio_group
        """
        radio_layout = QHBoxLayout() if horizontal else QVBoxLayout()
        radio_group  = QButtonGroup(self)

        if prefix is not None:
            radio_layout.addWidget(QLabel(prefix))

        for id, name in enumerate(names):
            radio_btn = QRadioButton(name, self)
            radio_group.addButton(radio_btn)
            if (text_box is not None) and (id == len(names)-1):
                # add the textbox to the radio
                custom_layout = QHBoxLayout()
                custom_layout.addWidget(radio_btn)
                custom_layout.addWidget(text_box)
                radio_layout.addLayout(custom_layout)
            else:
                radio_layout.addWidget(radio_btn)
        self.layout().addLayout(radio_layout)
        return radio_group

    def initUI(self):
        self.setWindowTitle("Growth Parameters")
        layout = QVBoxLayout()
        self.setLayout(layout)


        # Growth Trend Section
        self.trend_group = self._init_radio(prefix="Growth Trend:", names=["Linear", "Exponential"], horizontal=True)

        # Growth Time Section
        growth_time_layout = QHBoxLayout()
        growth_time_label = QLabel("Growth Time:")
        self.growth_time_input = QLineEdit()
        growth_time_layout.addWidget(growth_time_label)
        growth_time_layout.addWidget(self.growth_time_input)
        layout.addLayout(growth_time_layout)

        # Growth Benchmark Section
        self.custom_growth_input = QLineEdit()  # todo each benchmark should list its growth_rate
        self.growth_benchmark_group = self._init_radio(prefix="Growth Benchmark:", text_box=self.custom_growth_input,
                                                       names=[
                                                            "Earnings",
                                                            "Book Value",
                                                            "Revenue",
                                                            "FCF",
                                                            "Custom"
                                                       ])

        # Perpetuity Growth Section
        self.perpetuity_growth_input = QLineEdit()
        self.perpetuity_group = self._init_radio(prefix="Perpetuity Growth:", text_box=self.perpetuity_growth_input,
                                                 names=["Nothing", "Constant", "Slow Exponent"])
        # GO Button
        self.go_button = QPushButton("GO")
        layout.addWidget(self.go_button)
        self.go_button.clicked.connect(self.handle_go_press)

    def handle_go_press(self):
        args_iir = {  # todo what about discount_rate and price target
            "forward_to_present": True,
            "use_bv_growth": self.growth_benchmark_group.checkedButton().text() == "Book Value",  # todo handle all other benchmarks
            "add_bv": True,  # todo add to dialog
            "short_term_is_linear": self.trend_group.checkedButton().text() == "Linear",
            "long_growth_duration": 0 if self.perpetuity_group.checkedButton().text() == "Nothing" else -1,
            "forecasted_number_years_of_growth": int(self.growth_time_input.text()),
            "maximal_long_term_growth_rate": float(self.perpetuity_growth_input.text()) / 100 if self.perpetuity_group.checkedButton().text() == "Slow Exponent" else 0,
        }
        print(args_iir)
        price_target, iir = self.ticker._calc_dcf_intrinsic_values(discount_rate=0.01, **args_iir)
        print(iir)




if __name__ == '__main__':
    app = QApplication(sys.argv)

    # setup stylesheet
    apply_stylesheet(app, theme='dark_red.xml')

    ex = GrowthApp()
    ex.show()
    sys.exit(app.exec_())


