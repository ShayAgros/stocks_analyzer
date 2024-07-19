import numpy as np
from ticker import search_growth


def calc_yield_to_maturity(face_value, coupon, time_to_maturity, time_to_first_coupon, coupons_per_year, price):
    coupon = coupon * face_value
    def calc_npv(rate):
        times = np.arange(time_to_first_coupon, time_to_maturity, 1/coupons_per_year)  # without the last one
        discounted_coupons = np.sum(coupon * (1/(1+rate)) ** times)
        discounted_facevalue = (face_value+coupon) * (1/(1+rate)) ** time_to_maturity
        return discounted_facevalue + discounted_coupons
    return search_growth(
        npv_function=calc_npv,
        price=price,
        min_growth=0,
        max_growth=5,
        delta_growth=0.01 / 100
    )