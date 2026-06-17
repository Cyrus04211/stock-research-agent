"""
Barra 多因子风险模型数据层 — CNE5-like 风格因子计算

计算 10 类风格因子的原始暴露、标准化 z-score、因子协方差估计和风险分解。
单只股票分析场景下，用历史分位 + 行业可比 + 绝对阈值做标准化。
"""
from __future__ import annotations

import math
from data.utils import safe_float


# ═════════════════════════════════════════════
# 因子原始暴露计算
# ═════════════════════════════════════════════

def compute_barra_factors(data: dict) -> dict:
    """从全维度数据中提取并计算所有 Barra 风格因子暴露"""
    factors = {}

    _compute_size_factor(data, factors)
    _compute_value_factors(data, factors)
    _compute_momentum_factors(data, factors)
    _compute_volatility_factors(data, factors)
    _compute_quality_factors(data, factors)
    _compute_growth_factors(data, factors)
    _compute_leverage_factors(data, factors)
    _compute_liquidity_factors(data, factors)
    _compute_sentiment_factor(data, factors)

    _score_factors(factors)
    _build_factor_summary(factors)

    return factors


# --- Size ---

def _compute_size_factor(data: dict, out: dict):
    mkt_cap = _extract_market_cap(data)
    if mkt_cap:
        out["size"] = {
            "raw": round(math.log(mkt_cap), 4),
            "market_cap": mkt_cap,
            "market_cap_yi": _to_yi(mkt_cap),
            "label": "规模 (ln MCap)",
            "source": "东方财富估值 / Yahoo Finance",
        }


# --- Value ---

def _compute_value_factors(data: dict, out: dict):
    metrics = data.get("key_metrics", {})
    mkt_cap = _extract_market_cap(data)
    price = safe_float(metrics.get("current_price"))
    pe = safe_float(metrics.get("pe_trailing"))
    pb = safe_float(metrics.get("pb"))

    # Earnings Yield = 1/PE
    if pe and pe > 0:
        out["earnings_yield"] = {
            "raw": round(1.0 / pe, 4),
            "pe_trailing": pe,
            "label": "盈利收益率 (1/PE)",
            "source": metrics.get("pe_source", ""),
        }

    # Book-to-Price = 1/PB
    if pb and pb > 0:
        out["book_to_price"] = {
            "raw": round(1.0 / pb, 4),
            "pb": pb,
            "label": "账面市值比 (1/PB)",
            "source": metrics.get("pb_source", ""),
        }

    # Cash Earnings Yield (if cash flow available)
    fin_bundle = data.get("财务报表", {})
    a_fin = (fin_bundle.get("a_share") if isinstance(fin_bundle.get("a_share"), dict) else {}) or {}
    cf = a_fin.get("cashflow_recent", {})
    ocf_items = cf.get("经营活动现金流量净额", [])
    if ocf_items and mkt_cap:
        latest_ocf = safe_float(ocf_items[0].get("value"))
        if latest_ocf and latest_ocf > 0:
            out["cash_earnings_yield"] = {
                "raw": round(latest_ocf / mkt_cap, 4),
                "label": "现金盈利收益率 (OCF/MCap)",
                "source": "东方财富现金流量表",
            }

    # PE 历史分位 (A 股)
    price_bundle = data.get("行情估值", {})
    a_val = (price_bundle.get("a_valuation") if isinstance(price_bundle.get("a_valuation"), dict) else {}) or {}
    pe_pct = safe_float(a_val.get("pe_percentile"))
    pb_pct = safe_float(a_val.get("pb_percentile"))
    if pe_pct is not None and "earnings_yield" in out:
        out["earnings_yield"]["pe_percentile_5y"] = pe_pct
    if pb_pct is not None and "book_to_price" in out:
        out["book_to_price"]["pb_percentile_5y"] = pb_pct


# --- Momentum ---

def _compute_momentum_factors(data: dict, out: dict):
    price_bundle = data.get("行情估值", {})
    yf_price = (price_bundle.get("yf") if isinstance(price_bundle.get("yf"), dict) else {}) or {}
    a_price = (price_bundle.get("a_price") if isinstance(price_bundle.get("a_price"), dict) else {}) or {}

    ytd = safe_float(yf_price.get("ytd_change_pct") or a_price.get("ytd_change_pct"))

    # 均线偏离（替代短期动量信号）
    vs_ma60 = safe_float(yf_price.get("price_vs_ma60_pct") or a_price.get("price_vs_ma60_pct"))
    vs_ma200 = safe_float(yf_price.get("price_vs_ma200_pct") or a_price.get("price_vs_ma200_pct"))

    momentum_signals = {}
    if ytd is not None:
        momentum_signals["ytd_return_pct"] = ytd
    if vs_ma60 is not None:
        momentum_signals["vs_ma60_pct"] = vs_ma60
        momentum_signals["short_term_reversal"] = round(-1.0 * vs_ma60, 2)
    if vs_ma200 is not None:
        momentum_signals["vs_ma200_pct"] = vs_ma200

    if momentum_signals:
        momentum_signals["label"] = "动量因子"
        momentum_signals["source"] = yf_price.get("source", a_price.get("source", ""))
        out["momentum"] = momentum_signals


# --- Volatility ---

def _compute_volatility_factors(data: dict, out: dict):
    price_bundle = data.get("行情估值", {})
    yf_price = (price_bundle.get("yf") if isinstance(price_bundle.get("yf"), dict) else {}) or {}
    a_price = (price_bundle.get("a_price") if isinstance(price_bundle.get("a_price"), dict) else {}) or {}

    beta = safe_float(yf_price.get("beta"))
    vol_1y = safe_float(a_price.get("volatility_1y"))
    high_52w = safe_float(yf_price.get("high_52w") or a_price.get("high_252d"))
    low_52w = safe_float(yf_price.get("low_52w") or a_price.get("low_252d"))
    price = safe_float(yf_price.get("current_price") or a_price.get("current_price"))

    vol_signals = {}
    if beta is not None:
        vol_signals["beta"] = beta
    if vol_1y is not None:
        vol_signals["historical_sigma_pct"] = vol_1y
    if high_52w and low_52w and price and price > 0:
        vol_signals["cumulative_range_pct"] = round((high_52w - low_52w) / price * 100, 1)
    if yf_price.get("price_5y_position_pct") is not None:
        vol_signals["price_position_5y_pct"] = yf_price["price_5y_position_pct"]

    if vol_signals:
        vol_signals["label"] = "波动率因子"
        vol_signals["source"] = "Yahoo Finance / AKShare"
        out["volatility"] = vol_signals


# --- Quality ---

def _compute_quality_factors(data: dict, out: dict):
    metrics = data.get("key_metrics", {})
    fin_bundle = data.get("财务报表", {})
    yf_fin = (fin_bundle.get("yf") if isinstance(fin_bundle.get("yf"), dict) else {}) or {}
    a_fin = (fin_bundle.get("a_share") if isinstance(fin_bundle.get("a_share"), dict) else {}) or {}

    quality = {}

    # ROE
    roe = safe_float(metrics.get("roe"))
    if roe is not None:
        quality["roe_pct"] = roe

    # 利润率
    yf_ratios = yf_fin.get("ratios", {})
    a_ratios = a_fin.get("ratios", {})
    gross_margin = safe_float(yf_ratios.get("gross_margins") or a_ratios.get("gross_margin"))
    net_margin = safe_float(yf_fin.get("profit_margins") or a_ratios.get("net_margin"))
    if gross_margin is not None:
        quality["gross_margin_pct"] = gross_margin
    if net_margin is not None:
        quality["net_margin_pct"] = net_margin

    # 资产周转率（从利润表+资产负债表估算）
    inc = a_fin.get("income_recent", {})
    bal = a_fin.get("balance_recent", {})
    rev_items = inc.get("营业总收入", [])
    asset_items = bal.get("资产总计", [])
    if rev_items and asset_items:
        rev = safe_float(rev_items[0].get("value"))
        assets = safe_float(asset_items[0].get("value"))
        if rev and assets and assets > 0:
            quality["asset_turnover"] = round(rev / assets, 4)

    # 应计利润质量 (Accruals ≈ NI - OCF / TA)
    profit_items = inc.get("归母净利润", inc.get("净利润", []))
    cf = a_fin.get("cashflow_recent", {})
    ocf_items = cf.get("经营活动现金流量净额", [])
    if profit_items and ocf_items and asset_items:
        ni = safe_float(profit_items[0].get("value"))
        ocf = safe_float(ocf_items[0].get("value"))
        ta = safe_float(asset_items[0].get("value"))
        if ni and ocf and ta and ta > 0:
            quality["accruals_pct"] = round((ni - ocf) / ta * 100, 2)

    # yf quality ratios
    roa = safe_float(yf_ratios.get("roa"))
    roic = safe_float(yf_ratios.get("roic"))
    if roa is not None:
        quality["roa_pct"] = roa
    if roic is not None:
        quality["roic_pct"] = roic

    # 分红
    price_bundle = data.get("行情估值", {})
    yf_p = (price_bundle.get("yf") if isinstance(price_bundle.get("yf"), dict) else {}) or {}
    div_yield = safe_float(yf_p.get("dividend_yield"))
    if div_yield is not None:
        quality["dividend_yield_pct"] = div_yield

    if quality:
        quality["label"] = "质量因子"
        quality["source"] = "AKShare财务指标 / Yahoo Finance"
        out["quality"] = quality


# --- Growth ---

def _compute_growth_factors(data: dict, out: dict):
    price_bundle = data.get("行情估值", {})
    yf_price = (price_bundle.get("yf") if isinstance(price_bundle.get("yf"), dict) else {}) or {}
    research = data.get("研报评级", {}) if isinstance(data.get("研报评级"), dict) else {}

    growth = {}

    rev_g = safe_float(yf_price.get("revenue_growth_yoy"))
    earn_g = safe_float(yf_price.get("earnings_growth_yoy"))
    if rev_g is not None:
        growth["revenue_growth_yoy_pct"] = rev_g
    if earn_g is not None:
        growth["earnings_growth_yoy_pct"] = earn_g

    # 一致预期增长 (从研报)
    forecast = research.get("earnings_forecast", {})
    eps_keys = sorted(
        k for k in forecast if k.startswith("EPS_") and not k.endswith(("_min", "_max", "_analysts"))
    )
    if len(eps_keys) >= 2:
        e1, e2 = safe_float(forecast[eps_keys[0]]), safe_float(forecast[eps_keys[1]])
        y1, y2 = eps_keys[0].replace("EPS_", ""), eps_keys[1].replace("EPS_", "")
        if e1 and e2 and e1 > 0:
            years = max(int(y2) - int(y1), 1)
            cagr = round(((e2 / e1) ** (1.0 / years) - 1) * 100, 1)
            growth["consensus_eps_cagr_pct"] = cagr
            growth["consensus_source"] = "东方财富研报中心"

    # 隐含增长
    exp_data = data.get("预期差数据", {})
    if isinstance(exp_data, dict):
        implied = exp_data.get("implied_growth", {})
        if isinstance(implied, dict):
            implied_g = safe_float(implied.get("implied_fcf_growth_5y_pct"))
            consensus_g = safe_float(implied.get("consensus_eps_forecast_cagr_pct"))
            gap = safe_float(implied.get("growth_expectation_gap_pct"))
            if implied_g is not None:
                growth["implied_growth_5y_pct"] = implied_g
            if consensus_g is not None:
                growth["consensus_eps_cagr_pct"] = consensus_g
            if gap is not None:
                growth["growth_expectation_gap_pct"] = gap

    if growth:
        growth["label"] = "成长因子"
        growth["source"] = growth.get("consensus_source", "Yahoo Finance / 东方财富")
        out["growth"] = growth


# --- Leverage ---

def _compute_leverage_factors(data: dict, out: dict):
    fin_bundle = data.get("财务报表", {})
    yf_fin = (fin_bundle.get("yf") if isinstance(fin_bundle.get("yf"), dict) else {}) or {}
    a_fin = (fin_bundle.get("a_share") if isinstance(fin_bundle.get("a_share"), dict) else {}) or {}

    leverage = {}

    yf_balance = yf_fin.get("balance", {})
    de = safe_float(yf_balance.get("debt_to_equity"))
    cr = safe_float(yf_balance.get("current_ratio"))

    a_ratios = a_fin.get("ratios", {})
    debt_ratio = safe_float(a_ratios.get("debt_ratio"))
    quick_ratio = safe_float(a_ratios.get("quick_ratio"))

    if de is not None:
        leverage["debt_to_equity"] = de
    if debt_ratio is not None:
        leverage["debt_to_assets_pct"] = debt_ratio
    if cr is not None:
        leverage["current_ratio"] = cr
    if quick_ratio is not None:
        leverage["quick_ratio"] = quick_ratio

    # 从资产负债表计算
    bal = a_fin.get("balance_recent", {})
    total_assets = _first_period_val(bal, "资产总计")
    total_liab = _first_period_val(bal, "负债合计")
    equity = _first_period_val(bal, "归母股东权益")
    cash = _first_period_val(bal, "货币资金")
    if total_assets and total_liab:
        leverage["debt_to_assets"] = round(total_liab / total_assets, 4)
    if total_liab and cash and total_liab > 0:
        leverage["net_debt_to_equity"] = round((total_liab - cash) / equity, 4) if equity else None

    if leverage:
        leverage["label"] = "杠杆因子"
        leverage["source"] = "AKShare资产负债表 / Yahoo Finance"
        out["leverage"] = leverage


# --- Liquidity ---

def _compute_liquidity_factors(data: dict, out: dict):
    price_bundle = data.get("行情估值", {})
    yf_price = (price_bundle.get("yf") if isinstance(price_bundle.get("yf"), dict) else {}) or {}

    liquidity = {}
    avg_vol = safe_float(yf_price.get("avg_volume_3m"))
    mkt_cap = safe_float(yf_price.get("market_cap"))
    if avg_vol and avg_vol > 0:
        liquidity["avg_volume_3m"] = avg_vol
        # 月换手率估算
        if mkt_cap and mkt_cap > 0:
            price_now = safe_float(yf_price.get("current_price"))
            if price_now:
                shares = mkt_cap / price_now
                if shares > 0:
                    liquidity["monthly_turnover_pct"] = round(avg_vol * 21 / shares * 100, 2)

    if liquidity:
        liquidity["label"] = "流动性因子"
        liquidity["source"] = "Yahoo Finance"
        out["liquidity"] = liquidity


# --- Sentiment ---

def _compute_sentiment_factor(data: dict, out: dict):
    sentiment_data = data.get("情绪极端信号", {})
    if not isinstance(sentiment_data, dict):
        return

    sentiment = {}
    short = sentiment_data.get("short_interest", {})
    if isinstance(short, dict):
        sp = safe_float(short.get("short_pct_of_float"))
        if sp is not None:
            sentiment["short_pct_of_float"] = sp

    inst = sentiment_data.get("institutional_flow", {})
    if isinstance(inst, dict):
        ip = safe_float(inst.get("institutional_ownership_pct"))
        if ip is not None:
            sentiment["institutional_ownership_pct"] = ip

    insider = sentiment_data.get("insider_cluster", {})
    if isinstance(insider, dict):
        buys = insider.get("buy_count", 0)
        sells = insider.get("sell_count", 0)
        if buys or sells:
            sentiment["insider_cluster_signal"] = insider.get("cluster_signal", "")
            sentiment["insider_buy_count"] = buys
            sentiment["insider_sell_count"] = sells

    # 分析师一致预期偏见
    research = data.get("研报评级", {})
    if isinstance(research, dict):
        rating = research.get("rating_summary", {})
        total = sum(v for v in rating.values() if isinstance(v, (int, float)))
        if total > 0:
            buy_pct = round(
                sum(v for k, v in rating.items() if "买入" in str(k) or "增持" in str(k)) / total * 100, 1
            )
            sentiment["analyst_buy_ratio_pct"] = buy_pct
            sentiment["analyst_consensus_source"] = "东方财富研报中心"

    if sentiment:
        sentiment["label"] = "情绪因子"
        sentiment["source"] = "综合（YF / AKShare / 东方财富）"
        out["sentiment"] = sentiment


# ═════════════════════════════════════════════
# 因子评分与标准化
# ═════════════════════════════════════════════

def _score_factors(factors: dict):
    """为每个因子生成方向性评分和强度 (1-10)"""
    _score_size(factors)
    _score_value(factors)
    _score_momentum(factors)
    _score_volatility(factors)
    _score_quality(factors)
    _score_growth(factors)
    _score_leverage(factors)
    _score_liquidity(factors)
    _score_sentiment(factors)


def _score_size(factors: dict):
    f = factors.get("size", {})
    mkt_cap = safe_float(f.get("market_cap"))
    if mkt_cap is None:
        return
    # 中国市场：大盘 > 1000亿，中盘 > 200亿，小盘 < 200亿
    yi = f.get("market_cap_yi", 0)
    if yi >= 1000:
        f["tilt"] = "大盘"
        f["strength"] = min(10, round(4 + yi / 500, 1))
    elif yi >= 200:
        f["tilt"] = "中盘"
        f["strength"] = round(3 + yi / 200, 1)
    else:
        f["tilt"] = "小盘"
        f["strength"] = max(1, round(yi / 50, 1))
    f["tilt_direction"] = "large" if yi >= 200 else "small"


def _score_value(factors: dict):
    for key in ("earnings_yield", "book_to_price", "cash_earnings_yield"):
        f = factors.get(key, {})
        raw = safe_float(f.get("raw"))
        if raw is None:
            continue
        # EP 参考阈值: > 8.3% (PE<12) = 深度价值, > 5% (PE<20) = 价值, < 2.5% (PE>40) = 成长溢价
        if "earnings" in key:
            if raw > 0.083:
                f["tilt"] = "深度价值"
                f["strength"] = min(10, round(raw * 100, 1))
            elif raw > 0.05:
                f["tilt"] = "价值"
                f["strength"] = round(raw * 120, 1)
            elif raw > 0.025:
                f["tilt"] = "中性偏价值"
                f["strength"] = round(raw * 160, 1)
            else:
                f["tilt"] = "成长溢价（低价值暴露）"
                f["strength"] = max(1, round(raw * 200, 1))
        elif "book" in key:
            if raw > 0.5:
                f["tilt"] = "深度价值"
                f["strength"] = min(10, round(raw * 8, 1))
            elif raw > 0.3:
                f["tilt"] = "价值"
                f["strength"] = round(raw * 15, 1)
            else:
                f["tilt"] = "成长溢价"
                f["strength"] = max(1, round(raw * 20, 1))
        f["tilt_direction"] = "value" if safe_float(f.get("raw", 0)) > 0.03 else "growth_premium"


def _score_momentum(factors: dict):
    f = factors.get("momentum", {})
    ytd = safe_float(f.get("ytd_return_pct"))
    vs_ma60 = safe_float(f.get("vs_ma60_pct"))
    if ytd is not None:
        if ytd > 30:
            f["tilt"] = "极强动量"; f["strength"] = min(10, round(3 + ytd / 10, 1))
        elif ytd > 10:
            f["tilt"] = "偏强动量"; f["strength"] = round(3 + ytd / 8, 1)
        elif ytd > -10:
            f["tilt"] = "中性动量"; f["strength"] = 5
        elif ytd > -30:
            f["tilt"] = "偏弱动量"; f["strength"] = round(3 + abs(ytd) / 15, 1)
        else:
            f["tilt"] = "极弱动量"; f["strength"] = min(10, round(3 + abs(ytd) / 20, 1))
        f["tilt_direction"] = "momentum" if ytd > 0 else "contrarian"
    elif vs_ma60 is not None:
        if vs_ma60 > 10:
            f["tilt"] = "短期偏强"; f["strength"] = round(3 + vs_ma60 / 5, 1)
        elif vs_ma60 < -10:
            f["tilt"] = "短期偏弱"; f["strength"] = round(3 + abs(vs_ma60) / 5, 1)
        else:
            f["tilt"] = "短期中性"; f["strength"] = 5


def _score_volatility(factors: dict):
    f = factors.get("volatility", {})
    beta = safe_float(f.get("beta"))
    sigma = safe_float(f.get("historical_sigma_pct"))
    if beta is not None:
        if beta > 1.3:
            f["tilt"] = "高贝塔"; f["strength"] = min(10, round(beta * 5, 1))
        elif beta > 0.8:
            f["tilt"] = "中性贝塔"; f["strength"] = 5
        else:
            f["tilt"] = "低贝塔/防御型"; f["strength"] = max(1, round((1 - beta) * 10, 1))
        f["tilt_direction"] = "defensive" if beta and beta < 0.8 else ("aggressive" if beta and beta > 1.3 else "neutral")
    elif sigma is not None:
        if sigma > 40:
            f["tilt"] = "高波动"; f["strength"] = min(10, round(sigma / 10, 1))
        elif sigma > 25:
            f["tilt"] = "中高波动"; f["strength"] = round(sigma / 7, 1)
        else:
            f["tilt"] = "低波动"; f["strength"] = max(1, round(sigma / 5, 1))


def _score_quality(factors: dict):
    f = factors.get("quality", {})
    roe = safe_float(f.get("roe_pct"))
    if roe is not None:
        if roe > 20:
            f["tilt"] = "高质量"; f["strength"] = min(10, round(roe / 3, 1))
        elif roe > 10:
            f["tilt"] = "中等质量"; f["strength"] = round(roe / 3, 1)
        elif roe > 0:
            f["tilt"] = "低质量"; f["strength"] = max(1, round(roe / 2, 1))
        else:
            f["tilt"] = "质量恶化"; f["strength"] = 8
        f["tilt_direction"] = "quality" if roe and roe > 10 else "low_quality"


def _score_growth(factors: dict):
    f = factors.get("growth", {})
    rev_g = safe_float(f.get("revenue_growth_yoy_pct"))
    earn_g = safe_float(f.get("earnings_growth_yoy_pct"))
    consensus_g = safe_float(f.get("consensus_eps_cagr_pct"))

    # 优先使用一致预期，其次历史盈利增速，最后营收增速
    g = consensus_g or earn_g or rev_g
    if g is not None:
        if g > 30:
            f["tilt"] = "高成长"; f["strength"] = min(10, round(g / 6, 1))
        elif g > 15:
            f["tilt"] = "成长"; f["strength"] = round(g / 4, 1)
        elif g > 5:
            f["tilt"] = "稳健增长"; f["strength"] = round(g / 2.5, 1)
        elif g > -5:
            f["tilt"] = "低增长"; f["strength"] = max(2, round(3 + g, 1))
        else:
            f["tilt"] = "负增长"; f["strength"] = min(10, round(4 + abs(g) / 5, 1))
        f["tilt_direction"] = "high_growth" if g and g > 15 else ("low_growth" if g and g <= 5 else "moderate_growth")


def _score_leverage(factors: dict):
    f = factors.get("leverage", {})
    de = safe_float(f.get("debt_to_equity"))
    da = safe_float(f.get("debt_to_assets_pct"))
    dr = safe_float(f.get("debt_to_assets"))
    if dr is not None:
        if dr > 0.6:
            f["tilt"] = "高杠杆"; f["strength"] = min(10, round(dr * 12, 1))
        elif dr > 0.3:
            f["tilt"] = "中等杠杆"; f["strength"] = round(dr * 14, 1)
        else:
            f["tilt"] = "低杠杆"; f["strength"] = max(1, round((1 - dr) * 6, 1))
        f["tilt_direction"] = "low_leverage" if dr and dr < 0.3 else "high_leverage"
    elif de is not None:
        if de > 2:
            f["tilt"] = "高杠杆"; f["strength"] = min(10, round(de * 3, 1))
        elif de > 1:
            f["tilt"] = "中等杠杆"; f["strength"] = round(de * 4, 1)
        else:
            f["tilt"] = "低杠杆"; f["strength"] = max(1, round((1 - de) * 5, 1))


def _score_liquidity(factors: dict):
    f = factors.get("liquidity", {})
    turnover = safe_float(f.get("monthly_turnover_pct"))
    if turnover is not None:
        if turnover > 100:
            f["tilt"] = "极高换手"; f["strength"] = min(10, round(turnover / 30, 1))
        elif turnover > 50:
            f["tilt"] = "高流动性"; f["strength"] = round(turnover / 15, 1)
        elif turnover > 20:
            f["tilt"] = "中等流动性"; f["strength"] = round(turnover / 7, 1)
        else:
            f["tilt"] = "低换手"; f["strength"] = max(1, round(turnover / 4, 1))


def _score_sentiment(factors: dict):
    f = factors.get("sentiment", {})
    short_pct = safe_float(f.get("short_pct_of_float"))
    analyst_buy = safe_float(f.get("analyst_buy_ratio_pct"))
    inst_pct = safe_float(f.get("institutional_ownership_pct"))

    bullish_count = 0
    if short_pct is not None and short_pct < 5:
        bullish_count += 1
    if analyst_buy is not None and analyst_buy > 70:
        bullish_count += 1
    if inst_pct is not None and inst_pct > 50:
        bullish_count += 1

    if bullish_count >= 2:
        f["tilt"] = "偏乐观"
        f["strength"] = 6 + bullish_count
    elif bullish_count == 1:
        f["tilt"] = "中性"
        f["strength"] = 5
    else:
        f["tilt"] = "偏悲观/分歧"
        f["strength"] = 6
    f["tilt_direction"] = "bullish" if bullish_count >= 2 else ("bearish" if bullish_count == 0 else "neutral")


# ═════════════════════════════════════════════
# 汇总与风险分解
# ═════════════════════════════════════════════

def _build_factor_summary(factors: dict):
    """生成因子暴露总览和文本摘要"""
    active_factors = []
    for name, f in factors.items():
        if isinstance(f, dict) and f.get("tilt"):
            active_factors.append({
                "factor": f.get("label", name),
                "raw_key": name,
                "tilt": f["tilt"],
                "strength": f.get("strength", 5),
                "direction": f.get("tilt_direction", ""),
            })

    active_factors.sort(key=lambda x: abs(x["strength"] - 5), reverse=True)
    factors["_summary"] = {
        "total_factors_computed": len(active_factors) + sum(
            1 for k in factors if isinstance(factors[k], dict) and "raw" in factors[k] and k != "_summary"
        ),
        "active_tilts": active_factors,
        "dominant_tilts": [f for f in active_factors if f["strength"] >= 7],
    }


def factor_risk_decomposition(factors: dict) -> dict:
    """估算因子风险分解: 系统风险 vs 特质风险"""
    vol = factors.get("volatility", {})
    beta = safe_float(vol.get("beta")) if isinstance(vol, dict) else None
    sigma = safe_float(vol.get("historical_sigma_pct")) if isinstance(vol, dict) else None

    result = {"method": "Barra CNE5-like 单只股票近似分解"}

    if beta is not None and sigma is not None:
        # 单只股票下无法直接分离市场波动，用典型市场波动率参考值估算
        # A 股沪深 300 长期年化波动约 20%，美股 SPX 约 16%
        # 同时通过 beta 反向校验：如果 beta=1 且 sigma=20%，则特质=0 合理
        REF_MARKET_VOL = 20.0  # 参考市场年化波动率 (%)
        market_var = REF_MARKET_VOL ** 2
        systematic_var = (beta * REF_MARKET_VOL) ** 2
        total_var = sigma ** 2
        idiosyncratic_var = max(0, total_var - systematic_var)
        sys_pct = round(systematic_var / total_var * 100, 1) if total_var > 0 else 0
        sys_pct = min(sys_pct, 100.0)
        result.update({
            "total_volatility_pct": sigma,
            "beta": beta,
            "reference_market_vol_pct": REF_MARKET_VOL,
            "reference_market_vol_note": "典型市场波动率参考值（沪深300 ~20%, SPX ~16%）",
            "systematic_risk_pct": round(math.sqrt(systematic_var), 1),
            "systematic_risk_share_pct": sys_pct,
            "idiosyncratic_risk_pct": round(math.sqrt(idiosyncratic_var), 1),
            "idiosyncratic_risk_share_pct": round(100 - sys_pct, 1),
            "interpretation": (
                f"假设市场年化波动率 {REF_MARKET_VOL}%，总波动 {sigma}% 中约 {sys_pct}% "
                f"来自市场系统性风险 (beta={beta})，{round(100-sys_pct, 1)}% 来自个股特质风险。"
                f"注：实际分解取决于真实市场波动率，此估算仅作参考。"
                if sigma else "数据不足"
            ),
        })
    else:
        result["note"] = "缺少 Beta 或历史波动率数据，无法完成风险分解"

    # 因子集中度风险
    summary = factors.get("_summary", {})
    dominant = summary.get("dominant_tilts", [])
    if dominant:
        result["factor_concentration"] = {
            "dominant_factors": [
                {"factor": d["factor"], "tilt": d["tilt"], "strength": d["strength"]}
                for d in dominant
            ],
            "risk_implication": (
                f"有 {len(dominant)} 个因子的暴露强度 >= 7，"
                "这些因子上的集中持仓可能在特定市场环境下承受较大回撤"
            ),
        }

    # 因子拥挤度估算
    crowded = []
    for d in (summary.get("active_tilts", [])):
        if d["raw_key"] == "sentiment" and d["strength"] >= 8:
            crowded.append("情绪因子过度乐观，警惕拥挤交易反转")
        if d["raw_key"] == "momentum" and d["strength"] >= 8:
            crowded.append("动量因子暴露极高，注意趋势断裂风险")
        if d["raw_key"] == "size" and d["tilt"] == "大盘":
            crowded.append("大盘因子暴露，市场共识持仓集中")
    if crowded:
        result["crowding_warnings"] = crowded

    return result


def factor_exposure_text(factors: dict) -> str:
    """生成因子暴露的可读文本摘要，注入 LLM prompt"""
    summary = factors.get("_summary", {})
    active = summary.get("active_tilts", [])
    dominant = summary.get("dominant_tilts", [])

    lines = [
        "## Barra 风格因子暴露分析",
        f"- 有效因子数: {summary.get('total_factors_computed', 0)}",
        "",
        "### 因子暴露总览",
        "| 因子 | 暴露方向 | 强度 (1-10) |",
        "|------|---------|-------------|",
    ]
    for f in active:
        lines.append(f"| {f['factor']} | {f['tilt']} | {f['strength']} |")

    if dominant:
        lines.append(f"\n### 主导因子 (强度 >= 7, 共 {len(dominant)} 个)")
        for d in dominant:
            lines.append(f"- **{d['factor']}**: {d['tilt']} (强度 {d['strength']})")
        lines.append(f"\n这些主导因子意味着该股票的风格暴露高度集中，因子轮动时波动可能较大。")

    # 因子风格画像 (一句话)
    style_profile = _style_profile_sentence(active)
    if style_profile:
        lines.append(f"\n### 因子风格画像")
        lines.append(style_profile)

    return "\n".join(lines)


def _style_profile_sentence(active: list) -> str:
    """生成一句话因子风格概述"""
    parts = []
    for f in active:
        if f["strength"] >= 6:
            parts.append(f["tilt"])
    if not parts:
        return ""
    return f"该股票的因子特征可概括为: {' + '.join(parts[:5])}"


# ═════════════════════════════════════════════
# 工具函数
# ═════════════════════════════════════════════

def _extract_market_cap(data: dict) -> float | None:
    metrics = data.get("key_metrics", {})
    mkt_cap = safe_float(metrics.get("market_cap"))
    if mkt_cap:
        return mkt_cap
    price_bundle = data.get("行情估值", {})
    yf_price = (price_bundle.get("yf") if isinstance(price_bundle.get("yf"), dict) else {}) or {}
    a_val = (price_bundle.get("a_valuation") if isinstance(price_bundle.get("a_valuation"), dict) else {}) or {}
    return safe_float(a_val.get("market_cap") or yf_price.get("market_cap"))


def _to_yi(val: float) -> float:
    """转为亿单位"""
    return round(val / 1e8, 2) if val else 0


def _first_period_val(sheet: dict, label: str) -> float | None:
    items = sheet.get(label, [])
    if items and isinstance(items, list) and len(items) > 0:
        return safe_float(items[0].get("value"))
    return None
