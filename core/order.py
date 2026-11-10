# -*- coding: utf-8 -*-
"""报童模型：临界比 → 最优订货量。不依赖任何界面。"""
from statistics import NormalDist


def costs(cost: float, price: float, salvage: float):
    """返回 (缺货代价 Cu, 过剩代价 Co)。

    Cu = 毛利（少卖一件少赚的）
    Co = 成本 − 残值（多订一件、卖不掉打折后的净损失）
    """
    return price - cost, cost - salvage


def critical_ratio(cu: float, co: float) -> float:
    if cu + co <= 0:
        raise ValueError("Cu + Co 必须大于 0")
    return cu / (cu + co)


def z_value(cr: float) -> float:
    return NormalDist().inv_cdf(cr)


def q_star(mu: float, sigma: float, cost: float, price: float, salvage: float) -> float:
    """最优订货量 = μ + z(临界比) × σ"""
    cu, co = costs(cost, price, salvage)
    return mu + z_value(critical_ratio(cu, co)) * sigma


def service_level(cost: float, price: float, salvage: float) -> float:
    cu, co = costs(cost, price, salvage)
    return critical_ratio(cu, co)
